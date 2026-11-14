"""What the TypeScript system knows about serving an order (`src/ops/`), as functions of plain data: world time and
opening hours (`calendar.ts`), road minutes (`map.ts`), stop windows from a note (`windows.ts`), the features the fee
model prices (`features.ts`), the shape of a gig and how to post a car again (`gig.ts`), and whether an option can
arrive on time (`serve.ts`). A port, line for line; `note.py` next to this file is `note.ts`."""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Any

from strategies.lean.js import INF, day_of
from strategies.lean.note import NO_FACTS, NoteFacts, earliest_pickup, read_note

HOUR = 60
DAY = 24 * HOUR
SATURDAY = 5

# ----------------------------------------------------------------------------------------------------- calendar


def weekday(day: int) -> int:
    return day % 7


def is_weekend(day: int) -> bool:
    return weekday(day) >= SATURDAY


def open_on(day: int, hours: dict, real: dict | None = None) -> tuple[int, int] | None:
    """The opening and closing minute of a site on a day, from midnight, or None when it is closed all day. A note
    changes the weekday hours only: Saturday keeps its stated hours."""
    if weekday(day) == SATURDAY:
        saturday = hours.get("saturday")
        return (saturday["opens"], saturday["closes"]) if saturday else None
    if weekday(day) not in hours["weekdays"]:
        return None
    real = real or {}
    opens = real.get("opens")
    closes = real.get("closes")
    return (hours["opens"] if opens is None else opens, hours["closes"] if closes is None else closes)


def next_open(at: float, hours: dict | None, real: dict | None = None) -> float:
    """The first minute from `at` on when the site is open: `at` itself at a private address (no hours), and
    infinity when it does not open within two weeks. A site is closed from its closing minute on."""
    if not hours or not math.isfinite(at):
        return at
    start = day_of(at)
    for day in range(start, start + 14):
        opened = open_on(day, hours, real)
        if not opened:
            continue
        begin = max(at, day * DAY + opened[0])
        if begin < day * DAY + opened[1]:
            return begin
    return INF


def shift_by_business_days(deadline: int, from_day: int, to_day: int) -> int:
    """The deadline moved by as many business days as there are from `from_day` to `to_day`."""
    shift = sum(1 for day in range(from_day + 1, to_day + 1) if not is_weekend(day))
    day = day_of(deadline)
    while shift > 0:
        day += 1
        if not is_weekend(day):
            shift -= 1
    return day * DAY + (deadline - day_of(deadline) * DAY)


# ---------------------------------------------------------------------------------------------------------- map


class Roads:
    """The roads of the world map, by their two ends."""

    def __init__(self, world_map: dict) -> None:
        self.map = world_map
        self.roads = {(r["from"], r["to"]): r for r in world_map.get("roads", [])}

    def road(self, a: str, b: str) -> dict | None:
        return self.roads.get((a, b))

    def minutes(self, a: str | None, b: str | None) -> float:
        """Road minutes between two places: 0 to the same place, infinity when the map has no road."""
        if a == b:
            return 0
        found = self.roads.get((a, b))  # type: ignore[arg-type]
        return INF if found is None else found["minutes"]

    def drive(self, legs: list[dict]) -> float:
        """Road minutes to move the cars one after the other, with the drive from one car's delivery to the next."""
        total: float = 0
        here = None
        for leg in legs:
            if here is not None:
                total += self.minutes(here, leg["pickup"]["placeId"])
            total += self.minutes(leg["pickup"]["placeId"], leg["delivery"]["placeId"])
            here = leg["delivery"]["placeId"]
        return total


@dataclass
class Context:
    """The world around an order: the map, the snow forecasts so far, the level, and how tight admission is (1 at
    the on-time target, down to 0.25 at the delivery minimum)."""

    roads: Roads
    forecasts: list[dict] = field(default_factory=list)
    level: int = 8
    tightening: float = 1


# ------------------------------------------------------------------------------------------------------ windows

MARGIN = HOUR  # a window inside real hours ends this long before closing


def snow_at(forecasts: list[dict], places: list[str]) -> list[dict]:
    return [snow for snow in forecasts if any(place in places for place in snow["placeIds"])]


def after_snow(start: float, snow: list[dict]) -> float:
    moved = True
    while moved:
        moved = False
        for fall in snow:
            if fall["from"] <= start < fall["to"]:
                start = fall["to"]
                moved = True
    return start


def pickup_window(
    stated: dict, hours: dict | None, facts: NoteFacts, now: int, not_before: float = 0, snow: list | None = None
) -> dict | None:
    """The pickup window that the note needs from `now` on, or None when the order's own window will do."""
    snow = snow or []
    earliest = max(earliest_pickup(facts) or 0, not_before)
    if facts.summer_tyres and snow:
        earliest = after_snow(max(earliest, now, stated["from"]), snow)
    real = facts.pickup_hours if hours else None
    if earliest <= now and not real:
        return None
    start = max(stated["from"], earliest, now)
    if hours and real:
        first = day_of(start)
        for day in range(first, first + 14):
            opened = open_on(day, hours, real)
            if not opened:
                continue
            begin = max(start, day * DAY + opened[0])
            end = day * DAY + opened[1] - MARGIN
            if end - begin >= MARGIN:
                return {"from": begin, "to": end}
        return None
    return None if start <= stated["from"] else {"from": start, "to": max(stated["to"], start + DAY)}


def delivery_window(base: dict, hours: dict | None, facts: NoteFacts) -> dict:
    """The delivery window by the note: it ends at a tighter deadline, and MARGIN before the real closing time."""
    end = min(base["to"], INF if facts.deadline is None else facts.deadline)
    opened = open_on(day_of(end), hours, facts.delivery_hours) if hours and facts.delivery_hours else None
    if opened:
        end = min(end, day_of(end) * DAY + opened[1] - MARGIN)
    return {"from": base["from"], "to": end} if end >= base["from"] else base


# ----------------------------------------------------------------------------------------------------- features


@dataclass(frozen=True)
class Features:
    private_pickup: bool = False
    private_delivery: bool = False
    trade_in: bool = False
    premium: bool = False
    weekend_delivery: bool = False
    lane_km: float = 0
    lane_minutes: float = 0


def features(work: dict, roads: Roads, option: dict | None = None) -> Features:
    """The features of an order, or of a request quoted for `option` (its first option by default)."""
    try:
        legs = work["legs"]
        first = legs[0] if legs else None
        if option is not None:
            deadline = option["deadline"]
        elif "deadline" in work:
            deadline = work["deadline"]
        else:
            deadline = work["options"][0]["deadline"] if work["options"] else None
        trip = roads.road(first["pickup"]["placeId"], first["delivery"]["placeId"]) if first else None
        return Features(
            private_pickup=any(leg["pickup"]["privateAddress"] for leg in legs),
            private_delivery=any(leg["delivery"]["privateAddress"] for leg in legs),
            trade_in=len(legs) > 1,
            premium=any(leg["car"]["premium"] for leg in legs),
            weekend_delivery=first is not None
            and deadline is not None
            and spans_weekend(first["pickup"]["window"]["from"], deadline),
            lane_km=trip["km"] if trip else 0,
            lane_minutes=trip["minutes"] if trip else 0,
        )
    except KeyError, TypeError, IndexError:
        return Features()


def spans_weekend(start: int, end: int) -> bool:
    last = min(day_of(end), day_of(start) + 6)
    return any(is_weekend(day) for day in range(day_of(start), last + 1))


# ---------------------------------------------------------------------------------------------------------- gig

MAX_SHARED_DRIVE = 12 * HOUR  # a gig with more than one car may plan at most this much driving
LOW_CHARGE = 30
RETRY_WAIT = 2 * HOUR


@dataclass(frozen=True)
class Retry:
    """What the setbacks of a car have taught: how to post it again."""

    pickup_from: float = 0  # no pickup before this minute
    manual_licence: bool = False
    plates: bool = False
    late: bool = False  # a window passed with no driver


FIRST_TRY = Retry()


def gig_shape(order: dict, legs: list[int], facts: NoteFacts, retry: Retry, now: int, context: Context) -> list[dict]:
    """The gigs that carry the order's cars `legs`, as {stops, audience}: one, or one for each car of a trade-in over
    the 12-hour limit. An order it cannot read gives none."""
    try:
        return shapes(order, legs, facts, retry, now, context)
    except KeyError, TypeError, IndexError, ValueError:
        return []


def shapes(order: dict, legs: list[int], facts: NoteFacts, retry: Retry, now: int, context: Context) -> list[dict]:
    cars = sorted(leg for leg in set(legs) if 0 <= leg < len(order["legs"]) and order["deliveredAt"][leg] is None)

    def shape(chosen: list[int]) -> dict:
        stops: list[dict] = []
        for leg in chosen:
            stops += stops_for(order, leg, facts if leg == 0 else NO_FACTS, retry, now, context)
        return {"stops": without_windows(stops, now), "audience": audience_for(order, chosen, facts, retry)}

    if not cars:
        return []
    together = context.roads.drive([order["legs"][leg] for leg in cars])
    return [shape([leg]) for leg in cars] if len(cars) > 1 and together > MAX_SHARED_DRIVE else [shape(cars)]


def stops_for(order: dict, leg: int, noted: NoteFacts, retry: Retry, now: int, context: Context) -> list[dict]:
    """A pickup and a delivery for one car. The note speaks of the first car only."""
    car, pickup, delivery = (order["legs"][leg][k] for k in ("car", "pickup", "delivery"))
    snow = snow_at(context.forecasts, [pickup["placeId"], delivery["placeId"]]) if noted.summer_tyres else []
    pickup_at = pickup_window(pickup["window"], pickup["hours"], noted, now, retry.pickup_from, snow)
    if pickup["privateAddress"] and pickup_at:
        pickup_at = (
            None
            if pickup_at["from"] > pickup["window"]["to"]
            else {**pickup_at, "to": min(pickup_at["to"], pickup["window"]["to"])}
        )
    base = {"from": delivery["window"]["from"], "to": max(delivery["window"]["from"], order["deadline"])}
    note_delivery = delivery_window(base, delivery["hours"], noted)
    start = pickup_at["from"] if pickup_at else pickup["window"]["from"]
    arrival = max(now, start) + context.roads.minutes(pickup["placeId"], delivery["placeId"])
    deliver_by = base if arrival > note_delivery["to"] else note_delivery
    first: dict[str, Any] = {
        "orderId": order["id"],
        "leg": leg,
        "kind": "pickup",
        "withPlates": retry.plates or noted.plates,
        "withCharging": low_battery(car),
    }
    if pickup_at:
        first["window"] = pickup_at
    second: dict[str, Any] = {"orderId": order["id"], "leg": leg, "kind": "delivery"}
    narrower = deliver_by["from"] > base["from"] or deliver_by["to"] < base["to"]
    return [first, {**second, "window": deliver_by} if narrower and not retry.late else second]


def audience_for(order: dict, legs: list[int], facts: NoteFacts, retry: Retry) -> dict:
    """A premium car needs an experienced driver, and a manual car a manual licence."""
    return {
        "experienced": any(order["legs"][leg]["car"]["premium"] is True for leg in legs if leg < len(order["legs"])),
        "manualLicence": retry.manual_licence or (0 in legs and facts.manual),
    }


def low_battery(car: dict) -> bool:
    return bool(car["electric"]) and car.get("chargePercent") is not None and car["chargePercent"] < LOW_CHARGE


def without_windows(stops: list[dict], before: float) -> list[dict]:
    """Leaves out the stop windows that end before `before`, so the world's window applies."""
    kept = []
    for stop in stops:
        window = stop.get("window")
        rest = {k: v for k, v in stop.items() if k != "window"}
        kept.append({**rest, "window": window} if window and window["to"] >= before else rest)
    return kept


def undelivered(order: dict) -> list[int]:
    return [leg for leg in range(len(order["legs"])) if order["deliveredAt"][leg] is None]


def retry_after(
    setback: str, order: dict, request: dict | None, leg: int, now: int, before: Retry = FIRST_TRY
) -> Retry:
    """How to post a car again after a setback, from what earlier setbacks taught."""
    if setback in ("not_ready", "closed"):
        return replace(before, pickup_from=max(before.pickup_from, retry_from(order, request, leg, now)))
    if setback == "licence":
        return replace(before, manual_licence=True)
    if setback == "no_plates":
        return replace(before, plates=True)
    if setback == "expired":
        return replace(before, late=True)
    return before


def retry_from(order: dict, request: dict | None, leg: int, now: int) -> float:
    try:
        options = request["options"] if request else []
        promised = next((o["deadline"] for o in options if o["kind"] == order["option"]), order["deadline"])
        delay = max(0, order["deadline"] - promised)
        later = order["legs"][leg]["pickup"]["window"]["from"] + delay if leg < len(order["legs"]) else now + delay
        return max(now + RETRY_WAIT, later)
    except KeyError, TypeError:
        return now + RETRY_WAIT


# -------------------------------------------------------------------------------------------------------- serve

LEAD = HOUR
MIN_SLACK = 5 * HOUR
PLATES_MINUTES = 30
CHARGING_MINUTES = 40


def can_serve(request: dict, option: dict, now: int, context: Context) -> bool:
    """Whether we can deliver `option` of `request` on time, with the slack that admission asks for. A request it
    cannot read is declined."""
    try:
        return judge(request, option, now, context, read_note(request.get("note"), request["arrivedAt"]))
    except KeyError, TypeError, IndexError, ValueError:
        return False


def tightening(context: Context) -> float:
    value = context.tightening
    return min(1, max(0.25, value)) if math.isfinite(value) else 1


def judge(request: dict, option: dict, now: int, context: Context, facts: NoteFacts) -> bool:
    first, every = earliest_finish(request, now, context, facts)
    legs = request["legs"]
    stated = legs[0]["pickup"]["window"]["from"] if legs else now
    deadline = shift_by_business_days(option["deadline"], day_of(stated), day_of(max(stated, facts.ready_at or 0)))
    if not every <= deadline:
        return False
    if facts.deadline is not None and not first <= facts.deadline:
        return False
    ready = max(now + LEAD, *(leg["pickup"]["window"]["from"] for leg in legs))
    slack = option["deadline"] - ready - context.roads.drive(legs)
    return slack >= MIN_SLACK / max(tightening(context), 0.5)


def earliest_finish(request: dict, now: int, context: Context, facts: NoteFacts) -> tuple[float, float]:
    """When a driver who leaves now can deliver the first car, and all of them, one after the other."""
    at: float = now + LEAD
    first = INF
    here = None
    for index, leg in enumerate(request["legs"]):
        car, pickup, delivery = leg["car"], leg["pickup"], leg["delivery"]
        noted = facts if index == 0 else NO_FACTS
        if here is not None:
            at += context.roads.minutes(here, pickup["placeId"])
        at = max(at, pickup["window"]["from"], noted.ready_at or 0, noted.released_at or 0)
        if index == 0 and pickup["privateAddress"] and at > pickup["window"]["to"]:
            at = INF
        at = next_open(at, pickup["hours"], noted.pickup_hours)
        at += context.roads.minutes(pickup["placeId"], delivery["placeId"])
        at += (PLATES_MINUTES if noted.plates else 0) + (CHARGING_MINUTES if low_battery(car) else 0)
        at = next_open(at, delivery["hours"], noted.delivery_hours)
        if delivery["privateAddress"]:
            at = max(at, delivery["window"]["from"])
        if index == 0:
            first = at
        here = delivery["placeId"]
    return first, at if request["legs"] else INF
