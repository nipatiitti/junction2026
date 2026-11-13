"""Bundling: puts the cars of several orders in one gig when that saves a driver's trips.

A gig with several cars is a chain: pickup, delivery, then the next car's pickup, and so on. One driver drives
it, so the chain saves the trip home after one car and the trip out to the next. Bundling holds new orders for
a short time when more cars of the same batch are coming, then builds chains from the orders it holds. It needs
no network: it reads the map, the driver list (through `strategies.fees.Market`) and the units the desk gives it.
See README.md next to this file.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from itertools import pairwise

from spread.types import Audience, OpeningHours, PriceRequest, StopRef, TimeWindow

from strategies.fees import Gig, Market

HOUR, DAY = 60, 24 * 60
RULE_MINUTES = 12 * HOUR  # a gig with more than one car may plan at most this much driving (RULES.md)
PLATES_MINUTES, CHARGING_MINUTES = 30, 40


@dataclass(frozen=True)
class Params:
    """The thresholds. See README.md for how each one was chosen."""

    max_cars: int = 3  # cars in one gig
    max_drive: int = 8 * HOUR  # planned road minutes of a bundle: well under the 12-hour rule, as drivers cap their day
    transit: float = 0.5  # a minute on public transport costs a driver this share of a minute at the wheel
    min_saving: float = 30.0  # a car joins a chain only when it saves at least this many driver-minutes
    max_wait: int = 2 * HOUR  # longest wait in a chain for the next car's window to open
    lead: int = 2 * HOUR  # a driver needs this long to see the gig and reach the first pickup
    slow: float = 1.15  # real drives take longer than the road minutes: the timing check stretches them
    buffer: int = HOUR  # each delivery is planned to arrive at least this long before its window ends
    hold: int = 45  # a batch order waits at most this long after it is won, for more cars of the batch
    quiet: int = 20  # ... and posts once the batch has sent no request for this long, and none is open
    safe: int = 6 * HOUR  # an order never waits later than this before its last pickup
    fee_floor: float = 0.6  # the fee of a bundle is at least this share of the sum of its single fees
    fee_cap: float = 0.95  # ... and at most this share


@dataclass(frozen=True)
class Unit:
    """One order's cars that go together: one leg, or both legs of a trade-in, with the stops the desk
    would post for them alone. The lists run along the stops."""

    order_id: str
    legs: list[int]  # the order's legs, in stop order
    stops: list[StopRef]
    places: list[str]  # the place of each stop
    windows: list[TimeWindow]  # the window of each stop: its own, or the order's
    hours: list[OpeningHours | None]  # the stated opening hours of each stop; None at a private address
    audience: Audience
    typical: float  # the typical fee for these cars, in cents
    price: float  # the order's price for these cars, in cents
    last_pickup_at: int  # the order's `lastPickupAt`

    @property
    def cars(self) -> int:
        return sum(1 for stop in self.stops if stop["kind"] == "pickup")


Minutes = dict[tuple[str, str], int]


def chain_minutes(group: list[Unit], minutes: Minutes) -> int:
    """Road minutes from the first pickup to the last delivery, the drive between every two stops included:
    what the 12-hour rule counts. Plates and charging stops do not count."""
    places = [place for unit in group for place in unit.places]
    return sum(minutes.get((a, b), 0) for a, b in pairwise(places))


def next_open(at: int, hours: OpeningHours | None) -> int | None:
    """The first minute from `at` on when the site's stated hours show it open, or None within a week."""
    if hours is None:
        return at
    for day in range(at // DAY, at // DAY + 8):
        weekday = day % 7
        if weekday == 5:
            saturday = hours.get("saturday")
            opening = (saturday["opens"], saturday["closes"]) if saturday else None
        elif weekday in hours["weekdays"]:
            opening = (hours["opens"], hours["closes"])
        else:
            opening = None
        if opening is None:
            continue
        start = max(at, day * DAY + opening[0])
        if start < day * DAY + opening[1]:
            return start
    return None


def timeline(group: list[Unit], now: int, minutes: Minutes, params: Params) -> list[int] | None:
    """The minute a driver reaches each stop of the chain when they start as early as they can, at the earliest
    `params.lead` from now, with drives stretched by `params.slow`. None when a stop cannot be reached inside its
    window and its site's hours, a delivery comes less than `params.buffer` before its window ends, or a wait
    for the next car is longer than `params.max_wait`."""
    times: list[int] = []
    here, at = None, now + params.lead
    for unit in group:
        for stop, place, window, hours in zip(unit.stops, unit.places, unit.windows, unit.hours):
            arrive = at if here is None else at + round(minutes.get((here, place), 0) * params.slow)
            ready = next_open(max(arrive, window["from"]), hours)
            if ready is None:
                return None
            if here is not None and stop["kind"] == "pickup" and ready - arrive > params.max_wait:
                return None
            end = window["to"] - (params.buffer if stop["kind"] == "delivery" else 0)
            if ready > end:
                return None
            times.append(ready)
            at = ready
            if stop["kind"] == "pickup":
                at += PLATES_MINUTES if stop.get("withPlates") else 0
                at += CHARGING_MINUTES if stop.get("withCharging") else 0
            here = place
    return times


def feasible(group: list[Unit], now: int, minutes: Minutes, params: Params) -> bool:
    """Whether the chain keeps the rules for a gig with several cars and every stop's window."""
    if sum(unit.cars for unit in group) > params.max_cars:
        return False
    drive = chain_minutes(group, minutes)
    if drive > min(RULE_MINUTES, params.max_drive):
        return False
    return timeline(group, now, minutes, params) is not None


def audience(group: list[Unit]) -> Audience:
    """Who may take the gig: an experienced driver when any car is premium, a manual licence when any car needs one."""
    return {
        "experienced": any(unit.audience["experienced"] for unit in group),
        "manualLicence": any(unit.audience["manualLicence"] for unit in group),
    }


def single_cost(unit: Unit, market: Market, minutes: Minutes, params: Params) -> float:
    """What the unit's cars cost a driver alone, in minutes at the wheel: the trip out from where the nearest
    drivers live, the drives, and the trip home from the last delivery."""
    drive = sum(minutes.get((a, b), 0) for a, b in pairwise(unit.places))
    trips = market.travel_minutes(unit.places[0]) + market.travel_minutes(unit.places[-1])
    return drive + params.transit * trips


def bundle_cost(group: list[Unit], market: Market, minutes: Minutes, params: Params) -> float:
    """What the chain costs one driver, in minutes at the wheel: one trip out, the drives, the trips between one
    car's delivery and the next car's pickup, and one trip home."""
    places = [place for unit in group for place in unit.places]
    drive = sum(minutes.get((a, b), 0) for unit in group for a, b in pairwise(unit.places))
    gaps = chain_minutes(group, minutes) - drive
    trips = market.travel_minutes(places[0]) + market.travel_minutes(places[-1])
    return drive + params.transit * (gaps + trips)


def saving(group: list[Unit], market: Market, minutes: Minutes, params: Params) -> float:
    return sum(single_cost(unit, market, minutes, params) for unit in group) - bundle_cost(
        group, market, minutes, params
    )


def fee_share(group: list[Unit], market: Market, minutes: Minutes, params: Params) -> float:
    """The bundle's fee over the sum of its single fees: its cost over the sum of the single costs, kept between
    `params.fee_floor` and `params.fee_cap`, so a bundle always pays less than its cars posted alone."""
    singles = sum(single_cost(unit, market, minutes, params) for unit in group)
    if singles <= 0:
        return params.fee_cap
    share = bundle_cost(group, market, minutes, params) / singles
    return min(params.fee_cap, max(params.fee_floor, share))


def latest_start(group: list[Unit], minutes: Minutes) -> int:
    """The last minute to collect the chain's first car and still collect each later car by its order's
    `lastPickupAt`, by the road minutes."""
    latest, offset, here = None, 0, None
    for unit in group:
        if here is not None:
            offset += minutes.get((here, unit.places[0]), 0)
        latest = unit.last_pickup_at - offset if latest is None else min(latest, unit.last_pickup_at - offset)
        offset += sum(minutes.get((a, b), 0) for a, b in pairwise(unit.places))
        here = unit.places[-1]
    return latest if latest is not None else 0


def fee_gig(group: list[Unit], now: int, market: Market, minutes: Minutes, params: Params) -> Gig:
    """The facts that `strategies.fees` plans a bundle's fee schedule from: the summed typical fee, scaled down by
    `fee_share`, the summed price, and the first car's place and time."""
    first = group[0]
    return Gig(
        typical=sum(unit.typical for unit in group) * fee_share(group, market, minutes, params),
        price=sum(unit.price for unit in group),
        last_pickup_at=latest_start(group, minutes),
        starts_at=max(now, first.windows[0]["from"]),
        drive_minutes=chain_minutes(group, minutes),
        scarcity=market.scarcity(first.places[0]),
        travel_minutes=market.travel_minutes(first.places[0]),
    )


def chains(
    starts: list[Unit], extra: list[Unit], now: int, market: Market, minutes: Minutes, params: Params
) -> list[list[Unit]]:
    """Groups the units: each unit of `starts` heads a chain, in the order of its first window, or joins an
    earlier chain. A chain grows by the unit, from `starts` or `extra`, that saves the most driver-minutes
    while the chain stays feasible and has the same audience. A unit that no chain takes goes alone."""
    used: set[str] = set()
    groups: list[list[Unit]] = []
    pool = starts + extra
    for head in sorted(starts, key=lambda unit: unit.windows[0]["from"]):
        if head.order_id in used:
            continue
        group = [head]
        used.add(head.order_id)
        while True:
            best, best_saving = None, params.min_saving
            for unit in pool:
                if unit.order_id in used or unit.audience != head.audience:
                    continue
                candidate = group + [unit]
                gain = saving(candidate, market, minutes, params) - saving(group, market, minutes, params)
                if gain > best_saving and feasible(candidate, now, minutes, params):
                    best, best_saving = unit, gain
            if best is None:
                break
            group.append(best)
            used.add(best.order_id)
        groups.append(group)
    return groups


@dataclass
class Held:
    """An order that waits in the pool: when it was won, its batch, and the last minute it may wait to."""

    order_id: str
    batch: str | None
    won_at: int
    until: int


@dataclass
class Bundler:
    """Holds new orders for a short time and turns them into chains. Feed it every price request with
    `request`, every new order with `hold`, and call `due` at each step for the groups to post."""

    market: Market
    params: Params = field(default_factory=Params)

    def __post_init__(self) -> None:
        self.minutes: Minutes = self.market.road
        self.pool: dict[str, Held] = {}
        self.batches: dict[str, list[tuple[int, int]]] = {}  # batch id -> (arrivedAt, respondBy) of its requests
        self.counts: Counter[str] = Counter()  # orders, bundles, cars in bundles, and what the desk reports

    def request(self, request: PriceRequest) -> None:
        batch = request.get("batchId")
        if batch:
            self.batches.setdefault(batch, []).append((request["arrivedAt"], request["respondBy"]))

    def hold(self, order_id: str, batch: str | None, last_pickup_at: int, now: int) -> None:
        """Puts a new order in the pool. An order of a batch may wait up to `params.hold`, never later than
        `params.safe` before its last pickup; any other order goes at the next `due`, with the orders held then."""
        until = now
        if batch:
            until = max(now, min(now + self.params.hold, last_pickup_at - self.params.safe))
        self.pool[order_id] = Held(order_id, batch, now, until)

    def holds(self, order_id: str) -> bool:
        return order_id in self.pool

    def forget(self, order_id: str) -> None:
        self.pool.pop(order_id, None)

    def ready(self, held: Held, now: int) -> bool:
        """An order goes when its wait is over, or when its batch has gone quiet: no request open, none lately."""
        if now >= held.until:
            return True
        requests = self.batches.get(held.batch or "", [])
        if any(respond_by > now for _, respond_by in requests):
            return False
        last = max((arrived for arrived, _ in requests), default=held.won_at)
        return now >= last + self.params.quiet

    def next_due(self) -> int | None:
        """The minute the desk must look again at the latest, for an order whose wait ends."""
        return min((held.until for held in self.pool.values()), default=None)

    def due(self, now: int, unit_of: Callable[[str], Unit | None]) -> list[list[Unit]]:
        """The groups to post now. Each order that is ready heads or joins a chain; an order still waiting can
        join a chain too, and then goes with it. `unit_of` builds an order's unit at this minute, or None when
        the order is gone: it then leaves the pool."""
        ready = {held.order_id for held in self.pool.values() if self.ready(held, now)}
        if not ready:
            return []
        starts: list[Unit] = []
        extra: list[Unit] = []
        for order_id in list(self.pool):
            unit = unit_of(order_id)
            if unit is None or order_id in ready:
                self.pool.pop(order_id)
            if unit is not None:
                (starts if order_id in ready else extra).append(unit)
        groups = chains(starts, extra, now, self.market, self.minutes, self.params)
        for group in groups:
            for unit in group[1:]:
                self.pool.pop(unit.order_id, None)
            self.counts["orders"] += len(group)
            if len(group) > 1:
                self.counts["bundles"] += 1
                self.counts["bundled orders"] += len(group)
                self.counts["bundled cars"] += sum(unit.cars for unit in group)
        return groups

    def summary(self) -> str:
        """One line on the week: the orders that went through the pool, the bundles and what became of them."""
        return "Bundling " + ", ".join(f"{name} {n:,}" for name, n in self.counts.items())

    def gig(self, group: list[Unit], now: int) -> Gig:
        return fee_gig(group, now, self.market, self.minutes, self.params)
