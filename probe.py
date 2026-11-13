"""Answers by experiment what no scrape can. Forks one practice world at one minute, tries one varied action in each
copy, and bisects to the value where the outcome flips. A copy has the same future draws as its parent, so a change in
outcome comes from the action alone. README.md says how to run it.

    uv run --env-file .env probe.py quote --level 8 --seed scrape-1 --share 0.05 --days 0,1
    uv run --env-file .env probe.py fee --level 8 --seed scrape-1 --requests R00042,R00100
    uv run --env-file .env probe.py shape --level 8 --seed scrape-1 --days 0,1

`quote`: at a request's arrival, quotes one option at different prices in copies and advances to its respondBy. The
flip price is the highest price that wins this request with this world's draws: the competitor and the dealer's
value, as one number. `fee`: wins the request cheaply, then posts its cars at different flat fees in copies and
advances `--window` minutes (never past the order's lastPickupAt). The flip fee is the lowest flat fee that a driver
books within the window. `shape`: scouts the week's requests once, pairs them (a trade-in's two cars, a round trip
on reverse lanes, or a chain), wins both orders of a pair, and at that minute bisects the flip fee of each car alone
and of both cars as one gig, then posts both single gigs at once at their flips.

The parent plays no gigs and declines every request that it does not probe (10 times the list price, which costs
nothing). Rows go to out/probe/<mode>-L<level>-<seed>.jsonl, one per probed option, order or pair. A probe run again
skips the rows that it has, and picks the same requests or pairs. Every copy is deleted after its step; on any stop the probe deletes
every world that it made, and prints the ids of any that it could not.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import random
import signal
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from spread.client import Client, SpreadError, Unreachable, World

from spread_proxy import ProxyClient

HOUR, DAY = 60, 24 * 60
PRACTICE_SLOTS = 8
DECLINE = 10  # a quote at this multiple of the list price loses at no cost
LAST_REQUEST = 4 * DAY + 18 * HOUR + 15  # Friday 18:15: no request comes later
CHARGE_KM = 200  # an electric car under 30% needs a charging stop on a route over this


class TrialError(Exception):
    """A trial whose action the world refused, or that gave no outcome: neither a yes nor a no."""


def retrying(call: Callable[[], Any]) -> Any:
    """Calls again while the server restarts (502 to 504 come as Unreachable or a 5xx): it answers within a minute."""
    for attempt in range(12):
        try:
            return call()
        except Unreachable:
            pass
        except SpreadError as error:
            if error.status < 500:
                raise
        time.sleep(5 * (attempt + 1))
    return call()


class Probe:
    """One probe world: the parent, its copies, and the slots that they take."""

    def __init__(self, client: Client, keep_free: int):
        self.client, self.keep_free = client, keep_free
        self.copies = 0  # copies made, for the report
        self.parent: World | None = None
        self.live: list[World] = []  # worlds to delete when the probe stops

    def wait_slot(self) -> None:
        """Waits until a world can be made without taking the slots left for teammates."""
        said = False
        while sum(1 for w in retrying(self.client.worlds) if not w["ended"]) >= PRACTICE_SLOTS - self.keep_free:
            if not said:
                print(f"Waiting for a free practice slot ({self.keep_free} kept for teammates)...", flush=True)
                said = True
            time.sleep(5)

    def create(self, level: int, seed: str) -> World:
        self.wait_slot()
        self.parent = retrying(lambda: self.client.create(level=level, seed=seed))
        self.live.append(self.parent)
        return self.parent

    def fork(self, parent: World) -> World:
        while True:
            self.wait_slot()
            try:
                copy = retrying(parent.fork)
            except SpreadError as error:
                if error.status != 409:  # 409: a teammate took the slot first
                    raise
                time.sleep(5)
                continue
            self.copies += 1
            self.live.append(copy)
            return copy

    def drop(self, world: World) -> bool:
        """Deletes a world; False when it could not."""
        try:
            retrying(world.delete)
        except SpreadError as error:
            if error.status != 404:
                return False
        if world in self.live:
            self.live.remove(world)
        return True

    def close(self) -> None:
        """Deletes every world of the probe: the copies it knows, every open copy of the parent that the server lists
        (a fork that a stop cut short is made but not known), then the parent."""
        if self.parent is not None:
            try:
                for w in retrying(self.client.worlds):
                    if w["parent"] == self.parent.id and not w["ended"]:
                        self.live.append(self.client.world(w["worldId"]))
            except SpreadError:
                pass
        left = [w.id for w in sorted(self.live, key=lambda w: w is self.parent) if not self.drop(w)]
        if left:
            print(f"Could not delete these worlds; delete them to free their slots: {', '.join(left)}", flush=True)


def decline(request: dict) -> dict:
    first = request["options"][0]
    return {"type": "quote", "requestId": request["id"], "prices": {first["kind"]: DECLINE * first["listPriceCents"]}}


def outcome(events: list[dict], request_id: str) -> tuple[str | None, dict | None]:
    """won or lost for the request, with the order when won; None while the dealer has not decided."""
    for event in events:
        if event["kind"] == "order_won" and event["order"]["id"] == request_id:
            return "won", event["order"]
        if event["kind"] == "order_lost" and event["requestId"] == request_id:
            return "lost", None
    return None, None


def check(results: list[dict]) -> None:
    for result in results:
        if not result["ok"]:
            raise TrialError(result["reason"])


def bisect(test: Callable[[int], bool], low: int, high: int, resolution: int) -> dict:
    """The flip of a test that should be True at low values and False at high ones. Tries both ends first: a test
    that is the same at both says so, and one that is False at low and True at high is `inverted` and not bisected.
    Returns the bracket [last True, first False] and every trial."""
    trials: dict[int, bool] = {}

    def run(value: int) -> bool:
        trials[value] = test(value)
        return trials[value]

    at_low, at_high = run(low), run(high)
    if at_low == at_high:
        return {"flip": None, "bracket": None, "ends": "true" if at_low else "false", "trials": trials}
    if not at_low:
        return {"flip": None, "bracket": None, "ends": "inverted", "trials": trials}
    lo, hi = low, high
    while hi - lo > resolution:
        mid = (lo + hi) // 2
        if run(mid):
            lo = mid
        else:
            hi = mid
    return {"flip": (lo + hi) / 2, "bracket": [lo, hi], "ends": None, "trials": trials}


def check_near(found: dict, test: Callable[[int], bool], rng: random.Random, spread: int, checks: int) -> None:
    """Extra trials a little either side of the bracket, where a coin would show: a threshold answers them all alike."""
    if not found["bracket"]:
        return
    lo, hi = found["bracket"]
    for _ in range(checks):
        value = rng.randint(max(1, lo - spread), hi + spread)
        if value not in found["trials"]:
            found["trials"][value] = test(value)


def monotone(trials: dict[int, bool]) -> bool:
    """True when the outcomes, in order of value, change at most once, from True to False: a threshold, not a coin."""
    outcomes = [trials[v] for v in sorted(trials)]
    return sum(a != b for a, b in itertools.pairwise(outcomes)) <= 1 and (
        not outcomes or outcomes[0] or not any(outcomes)
    )


def when(minute: int) -> dict:
    return {"day": minute // DAY, "hour": minute % DAY // HOUR}


def probe_quote(probe: Probe, parent: World, request: dict, args: argparse.Namespace, others: list[dict]) -> list[dict]:
    """Bisects each option of the request on its own: in each copy, only that option is quoted, so the flip is
    against the competitor's price for that option."""
    rows = []
    for option in request["options"]:
        list_price = option["listPriceCents"]

        def wins(price: int, option=option) -> bool:
            copy = probe.fork(parent)
            try:
                actions = [decline(r) for r in others]
                actions.append({"type": "quote", "requestId": request["id"], "prices": {option["kind"]: price}})
                step = retrying(lambda: copy.advance(to=request["respondBy"] + 1, actions=actions))
                check(step["results"])
                result, _ = outcome(step["events"], request["id"])
                if result is None:
                    raise TrialError("no order_won or order_lost by respondBy")
                return result == "won"
            finally:
                probe.drop(copy)

        row = {
            "requestId": request["id"],
            "option": option["kind"],
            "options": [o["kind"] for o in request["options"]],
            "dealerId": request["dealerId"],
            "arrivedAt": request["arrivedAt"],
            **when(request["arrivedAt"]),
            "lane": [request["legs"][0]["pickup"]["placeId"], request["legs"][0]["delivery"]["placeId"]],
            "legs": len(request["legs"]),
            "listPriceCents": list_price,
            "referenceFeeCents": request["referenceFeeCents"],
        }
        try:
            found = bisect(
                wins,
                round(list_price * args.low),
                round(list_price * args.high),
                max(1, round(list_price * args.resolution)),
            )
            rng = random.Random(f"{request['id']}:{option['kind']}")
            check_near(found, wins, rng, max(1, round(list_price * 0.03)), args.checks)
        except TrialError as error:
            rows.append({**row, "error": str(error)})
            continue
        rows.append(
            {
                **row,
                "flipCents": found["flip"],
                "flipRatio": None if found["flip"] is None else found["flip"] / list_price,
                "bracketCents": found["bracket"],
                "ends": found[
                    "ends"
                ],  # "true": won at both ends, "false": lost at both, "inverted": lost low, won high
                "monotone": monotone(found["trials"]),
                "trials": sorted(found["trials"].items()),
            }
        )
    return rows


def stops(order: dict, km: dict[tuple[str, str], float]) -> list[dict]:
    """A pickup and a delivery for each car, without windows of their own: the world plans them in the order's.
    An electric car under 30% gets a charging stop on a route over 200 km (RULES, handling rule 3)."""
    out = []
    for i, leg in enumerate(order["legs"]):
        car, route = leg["car"], (leg["pickup"]["placeId"], leg["delivery"]["placeId"])
        low = car["electric"] and car["chargePercent"] is not None and car["chargePercent"] < 30
        charge = low and km.get(route, 0) > CHARGE_KM
        out.append({"orderId": order["id"], "leg": i, "kind": "pickup", "withPlates": False, "withCharging": charge})
        out.append({"orderId": order["id"], "leg": i, "kind": "delivery"})
    return out


def fee_flip(
    probe: Probe,
    parent: World,
    now: int,
    gig_stops: list[dict],
    audience: dict,
    reference: int,
    window: int,
    args: argparse.Namespace,
    name: str,
    homes: dict[str, str],
    km: dict,
    places: tuple[str, str],
) -> dict:
    """Bisects the flat fee at which a driver books one gig of these stops within the window, one copy per trial.
    `places` is the gig's first pickup and last delivery place, for the booking driver's distances from home. A refused
    trial raises TrialError."""
    post = {"type": "post", "stops": gig_stops, "audience": audience}
    seen: dict[int, dict] = {}  # fee -> booking, expiry and views of that trial

    def unbooked(fee: int) -> bool:
        copy = probe.fork(parent)
        try:
            action = {**post, "schedule": [{"at": now, "feeCents": fee}]}
            step = retrying(
                lambda: copy.advance(until=["gig_booked", "gig_expired"], max=now + window, actions=[action])
            )
            check(step["results"])
            gig = step["results"][-1]["id"]
            mine = [e for e in step["events"] if e.get("gigId") == gig]
            booking = next((e for e in mine if e["kind"] == "gig_booked"), None)
            seen[fee] = {
                "views": sum(e["kind"] == "gig_viewed" for e in mine),
                "expired": any(e["kind"] == "gig_expired" for e in mine),
                "driverId": booking["driverId"] if booking else None,
                "minutes": booking["at"] - now if booking else None,
            }
            return booking is None  # True while too low: the bisection wants True at the low end
        finally:
            probe.drop(copy)

    found = bisect(
        unbooked,
        round(reference * args.low),
        round(reference * args.high),
        max(1, round(reference * args.resolution)),
    )
    check_near(found, unbooked, random.Random(f"{name}:fee"), max(1, round(reference * 0.05)), args.checks)
    flip = found["flip"]
    at_flip = dict(seen[found["bracket"][1]]) if found["bracket"] else None
    if at_flip and at_flip["driverId"]:
        home = homes.get(at_flip["driverId"])
        at_flip["homePlaceId"] = home
        at_flip["toPickupKm"] = km.get((home, places[0]))
        at_flip["fromDeliveryKm"] = km.get((places[1], home))
    # "true": unbooked at both ends (no driver within the window even at the top fee), "false": booked at both ends
    ends = {"true": "never", "false": "always"}.get(found["ends"], found["ends"])
    return {
        "referenceFeeCents": reference,
        "flipCents": flip,
        "flipRatio": None if flip is None else flip / reference,
        "bracketCents": found["bracket"],
        "ends": ends,
        "atFlip": at_flip,  # the lowest booked trial: who booked, how soon, views, expiry, and the driver's home
        "expiredAtTop": seen.get(round(reference * args.high), {}).get("expired"),
        "monotone": monotone(found["trials"]),
        "trials": sorted((fee, not unbooked_) for fee, unbooked_ in found["trials"].items()),
    }


def gig_places(gig_stops: list[dict], legs: dict[tuple[str, int], dict]) -> tuple[str, str]:
    """The first pickup place and the last delivery place of a gig's stops."""
    first, last = gig_stops[0], gig_stops[-1]
    pickup = legs[first["orderId"], first["leg"]]["pickup"]["placeId"]
    return pickup, legs[last["orderId"], last["leg"]]["delivery"]["placeId"]


def probe_fee(
    probe: Probe,
    parent: World,
    now: int,
    order: dict,
    request: dict,
    args: argparse.Namespace,
    km: dict,
    homes: dict[str, str],
) -> dict:
    """Bisects the flat fee at which a driver books the order's gig within the window."""
    reference = request["referenceFeeCents"]
    gig_stops = stops(order, km)
    audience = {"experienced": any(leg["car"]["premium"] for leg in order["legs"]), "manualLicence": False}
    window = max(1, min(args.window, order["lastPickupAt"] - now))
    row = {
        "orderId": order["id"],
        "option": order["option"],
        "dealerId": order["dealerId"],
        "wonAt": now,
        **when(now),
        "lastPickupAt": order["lastPickupAt"],
        "deadline": order["deadline"],
        "lane": [order["legs"][0]["pickup"]["placeId"], order["legs"][0]["delivery"]["placeId"]],
        "legs": len(order["legs"]),
        "premium": audience["experienced"],
        "referenceFeeCents": reference,
        "windowMinutes": window,
    }
    legs = {(order["id"], i): leg for i, leg in enumerate(order["legs"])}
    try:
        found = fee_flip(
            probe,
            parent,
            now,
            gig_stops,
            audience,
            reference,
            window,
            args,
            order["id"],
            homes,
            km,
            gig_places(gig_stops, legs),
        )
    except TrialError as error:
        return {**row, "error": str(error)}
    return {**row, **found}


# Shape mode: two cars as one gig against each car alone.

MIN_WINDOW = 60  # minutes a pair must stay bookable after the win
MAX_DRIVE = 12 * HOUR  # a gig over this breaks the 12-hour rule
CHAIN_KM = 100  # a chain ends at least this far from where it began
OUTCOMES = ("sumSingleFlipCents", "combinedFlipCents", "savingCents", "savingRatio", "combinedOverSum")


def is_open(hours: dict | None, t: int) -> bool:
    """A site's stated hours at minute t; a private address (no hours) is always open."""
    if hours is None:
        return True
    d, m = t // DAY % 7, t % DAY
    if d in hours["weekdays"]:
        return hours["opens"] <= m <= hours["closes"]
    if d == 5 and hours["saturday"]:
        return hours["saturday"]["opens"] <= m <= hours["saturday"]["closes"]
    return False


def last_start(plan: list[tuple[int, dict, dict | None]], now: int) -> int | None:
    """The latest first pickup t >= now at which every stop of the plan, at t + its offset, is inside its window
    and at an open site; None when there is none."""
    top = min(window["to"] - offset for offset, window, _ in plan)
    bottom = max(now, max(window["from"] - offset for offset, window, _ in plan))
    for t in range(top, bottom - 1, -1):
        if all(is_open(hours, t + offset) for offset, _, hours in plan):
            return t
    return None


def pair_plan(first: dict, second: dict, minutes: dict) -> list[tuple[int, dict, dict | None]]:
    """The four stops of two legs driven one after the other, as (offset from the first pickup, window, hours).
    The last offset is the plan's drive minutes."""
    m1 = minutes[first["pickup"]["placeId"], first["delivery"]["placeId"]]
    between = minutes[first["delivery"]["placeId"], second["pickup"]["placeId"]]
    m2 = minutes[second["pickup"]["placeId"], second["delivery"]["placeId"]]
    offsets = (0, m1, m1 + between, m1 + between + m2)
    places = (first["pickup"], first["delivery"], second["pickup"], second["delivery"])
    return [(offset, place["window"], place["hours"]) for offset, place in zip(offsets, places)]


def find_pairs(requests: list[dict], kinds: set[str], gap: int, km: dict, minutes: dict) -> list[dict]:
    """Every pair of the week, from the requests alone: trade-ins, then round trips, then chains (a request is in at
    most one round trip or chain). A pair holds its requests and its cars, (request id, leg), in stop order."""
    pairs = []
    if "trade_in" in kinds:
        for r in requests:
            if len(r["legs"]) == 2 and pair_plan(r["legs"][0], r["legs"][1], minutes)[-1][0] <= MAX_DRIVE:
                cars = [(r["id"], 0), (r["id"], 1)]
                pairs.append({"pairId": r["id"], "kind": "trade_in", "requests": [r], "cars": cars})
    singles = sorted((r for r in requests if len(r["legs"]) == 1), key=lambda r: (r["arrivedAt"], r["id"]))
    used: set[str] = set()

    def fits(x: dict, y: dict, later: dict, kind: str) -> bool:
        a, b = x["legs"][0], y["legs"][0]
        if a["delivery"]["placeId"] != b["pickup"]["placeId"]:
            return False
        back = b["delivery"]["placeId"], a["pickup"]["placeId"]
        if kind == "round_trip" and back[0] != back[1]:
            return False
        if kind == "chain" and (back[0] == back[1] or km[back] < CHAIN_KM):
            return False
        if any(leg["car"]["premium"] or leg["pickup"]["placeId"] == leg["delivery"]["placeId"] for leg in (a, b)):
            return False
        plan = pair_plan(a, b, minutes)
        if plan[-1][0] > MAX_DRIVE:
            return False
        start = last_start(plan, later["respondBy"])
        return start is not None and start >= later["respondBy"] + MIN_WINDOW

    for kind in ("round_trip", "chain"):
        if kind not in kinds:
            continue
        for i, a in enumerate(singles):
            if a["id"] in used:
                continue
            for b in singles[i + 1 :]:
                if b["arrivedAt"] - a["arrivedAt"] > gap:
                    break
                if b["id"] in used:
                    continue
                order = next(((x, y) for x, y in ((a, b), (b, a)) if fits(x, y, b, kind)), None)
                if order:
                    used.update((a["id"], b["id"]))
                    cars = [(order[0]["id"], 0), (order[1]["id"], 0)]
                    pairs.append(
                        {"pairId": f"{a['id']}+{b['id']}", "kind": kind, "requests": list(order), "cars": cars}
                    )
                    break
    return pairs


def scout(probe: Probe, args: argparse.Namespace) -> list[dict]:
    """The week's requests, from a cached file or from a world played to the last request with no actions. The
    request stream does not depend on our actions, so every week of this seed and level has these requests."""
    path = Path(args.out) / f"requests-L{args.level}-{args.seed}.json"
    if path.exists():
        return json.loads(path.read_text())
    print("Scouting the week's requests...", flush=True)
    world = probe.create(args.level, args.seed)
    stop_at = min(retrying(world.snapshot)["endsAt"], LAST_REQUEST + 30)
    requests, now = [], 0
    while now < stop_at:
        step = retrying(lambda: world.advance(until=["price_request"], max=stop_at))
        now = step["now"]
        requests += [e["request"] for e in step["events"] if e["kind"] == "price_request"]
    probe.drop(world)
    probe.parent = None
    path.write_text(json.dumps(requests))
    return requests


def probe_shape(
    probe: Probe,
    parent: World,
    now: int,
    pair: dict,
    args: argparse.Namespace,
    km: dict,
    minutes: dict,
    homes: dict[str, str],
) -> dict:
    """Bisects, at this minute, the flat fee that books each car alone and both cars as one gig, then posts both
    single gigs together, each at its own single flip."""
    head = {"pairId": pair["pairId"], "kind": pair["kind"], **when(now)}
    orders = {o["id"]: o for o in retrying(parent.snapshot)["orders"]}
    ids = [r["id"] for r in pair["requests"]]
    if any(i not in orders or orders[i]["status"] == "cancelled" for i in ids):
        return {**head, "error": "order cancelled before the probe"}
    mine = [orders[i] for i in ids]
    legs = {(o, i): orders[o]["legs"][i] for o, i in pair["cars"]}
    cars = [legs[car] for car in pair["cars"]]
    plan = pair_plan(cars[0], cars[1], minutes)
    trade_in = pair["kind"] == "trade_in"
    start = None
    if not trade_in:
        start = last_start(plan, now)
        if start is None:
            return {**head, "error": "no joint plan at the probe minute"}
    window = max(1, min(args.window, *(o["lastPickupAt"] - now for o in mine), *([] if trade_in else [start - now])))
    if window < MIN_WINDOW:
        return {**head, "error": "window too short"}

    if trade_in:
        combined = stops(mine[0], km)
        singles = [[s for s in combined if s["leg"] == i] for i in (0, 1)]
        reference = pair["requests"][0]["referenceFeeCents"]
        m0, m1 = (minutes[c["pickup"]["placeId"], c["delivery"]["placeId"]] for c in cars)
        first_ref = round(reference * m0 / (m0 + m1))
        refs = [first_ref, reference - first_ref]
    else:
        singles = [stops(o, km) for o in mine]
        combined = singles[0] + singles[1]
        refs = [r["referenceFeeCents"] for r in pair["requests"]]
    row = {
        **head,
        "orderIds": ids,
        "dealerIds": [o["dealerId"] for o in mine],
        "probedAt": now,
        "arrivedAt": [r["arrivedAt"] for r in pair["requests"]],
        "gapMinutes": abs(pair["requests"][-1]["arrivedAt"] - pair["requests"][0]["arrivedAt"]),
        "lanes": [[c["pickup"]["placeId"], c["delivery"]["placeId"]] for c in cars],
        "betweenKm": km[cars[0]["delivery"]["placeId"], cars[1]["pickup"]["placeId"]],
        "returnKm": km[cars[1]["delivery"]["placeId"], cars[0]["pickup"]["placeId"]],
        "driveMinutes": plan[-1][0],
        "premium": [c["car"]["premium"] for c in cars],
        "private": any(c[s]["privateAddress"] for c in cars for s in ("pickup", "delivery")),
        "lastPickupAt": [o["lastPickupAt"] for o in mine],
        "deadline": [o["deadline"] for o in mine],
        "lastStartAt": start,
        "referenceFeeCents": refs,
        "pairReferenceCents": refs[0] + refs[1],
        "windowMinutes": window,
    }

    def audience(gig_stops: list[dict]) -> dict:
        premium = any(legs[s["orderId"], s["leg"]]["car"]["premium"] for s in gig_stops)
        return {"experienced": premium, "manualLicence": False}

    treatments = {"single0": (singles[0], refs[0]), "single1": (singles[1], refs[1]), "combined": (combined, sum(refs))}
    results: dict[str, dict | None] = dict.fromkeys(treatments)
    error = None
    for name, (gig_stops, reference) in treatments.items():
        try:
            results[name] = fee_flip(
                probe,
                parent,
                now,
                gig_stops,
                audience(gig_stops),
                reference,
                window,
                args,
                f"{pair['pairId']}:{name}",
                homes,
                km,
                gig_places(gig_stops, legs),
            )
        except TrialError as e:
            results[name], error = {"error": str(e)}, str(e)
            break  # the finished treatments stay; the rest are not run
    found = [results["single0"], results["single1"]]
    row["single"], row["combined"] = found, results["combined"]
    flipped = error is None and all(f["bracketCents"] for f in found)
    row["together"] = probe_together(probe, parent, now, singles, found, audience, window) if flipped else None

    flips = [r and r.get("flipCents") for r in results.values()]
    if all(f is not None for f in flips):
        total = flips[0] + flips[1]
        saving = total - flips[2]
        row |= dict(zip(OUTCOMES, (total, flips[2], saving, saving / row["pairReferenceCents"], flips[2] / total)))
    else:
        row |= dict.fromkeys(OUTCOMES)
    row["ends"] = ",".join(f"{n}:{r['ends']}" for n, r in results.items() if r and r.get("ends")) or None
    row["monotone"] = all(r["monotone"] for r in results.values() if r and "monotone" in r)
    if error is not None:
        row["error"] = error
    return row


def probe_together(
    probe: Probe,
    parent: World,
    now: int,
    singles: list[list[dict]],
    found: list[dict],
    audience: Callable[[list[dict]], dict],
    window: int,
) -> dict:
    """Posts both single gigs at once, each at the lowest fee that booked it alone, and waits until both are booked
    or expired, or the window ends."""
    fees = [f["bracketCents"][1] for f in found]
    actions = [
        {"type": "post", "stops": s, "audience": audience(s), "schedule": [{"at": now, "feeCents": fee}]}
        for s, fee in zip(singles, fees)
    ]
    end, wake = now + window, ["gig_booked", "gig_expired"]
    copy = probe.fork(parent)
    try:
        step = retrying(lambda: copy.advance(until=wake, max=end, actions=actions))
        check(step["results"])
        gigs = [r["id"] for r in step["results"]]
        booked: dict[str, dict] = {}
        resolved: set[str] = set()
        while True:
            for event in step["events"]:
                if event.get("gigId") in gigs and event["kind"] in wake:
                    resolved.add(event["gigId"])
                    if event["kind"] == "gig_booked":
                        booked[event["gigId"]] = event
            if len(resolved) == len(gigs) or step["now"] >= end:
                break
            step = retrying(lambda: copy.advance(until=wake, max=end))
    except TrialError as error:
        return {"error": str(error)}
    finally:
        probe.drop(copy)
    drivers = [booked[g]["driverId"] if g in booked else None for g in gigs]
    return {
        "feesCents": fees,
        "driverIds": drivers,
        "minutes": [booked[g]["at"] - now if g in booked else None for g in gigs],
        "sameDriver": drivers[0] is not None and drivers[0] == drivers[1],
    }


def chosen(seed: str, level: int, mode: str, request_id: str, share: float) -> bool:
    """The same requests on every run of the same probe: a hash, not a random stream that a resume would shift."""
    digest = hashlib.sha256(f"{seed}:{level}:{mode}:{request_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64 < share


def run_shape(
    probe: Probe,
    args: argparse.Namespace,
    done: set[str],
    wanted: set[str] | None,
    write: Callable[[dict, str], None],
    km: dict,
    minutes: dict,
) -> int:
    """Shape mode: scouts the week's pairs, then wins each selected pair's orders in one parent and probes the pair
    at the minute that its last order is won. Returns the number of pairs probed."""
    pairs = find_pairs(scout(probe, args), set(args.kinds), args.gap, km, minutes)

    def selected(pair: dict) -> bool:
        if pair["kind"] not in args.kinds or pair["pairId"] in done:
            return False
        if max(r["arrivedAt"] for r in pair["requests"]) // DAY not in args.days:
            return False
        if wanted is not None:
            return any(r["id"] in wanted for r in pair["requests"])
        return chosen(args.seed, args.level, "shape", pair["pairId"], args.share)

    todo = sorted(filter(selected, pairs), key=lambda p: max(r["arrivedAt"] for r in p["requests"]))[: args.limit]
    print(f"{len(pairs)} pairs in the week, {len(todo)} to probe", flush=True)
    if not todo:
        return 0
    member = {r["id"]: pair for pair in todo for r in pair["requests"]}
    won: dict[str, dict[str, dict]] = {pair["pairId"]: {} for pair in todo}  # pair id -> order id -> order
    finished: set[str] = set()
    parent = probe.create(args.level, args.seed)
    homes = {d["id"]: d["homePlaceId"] for d in retrying(parent.roster)}
    stop_at = min(retrying(parent.snapshot)["endsAt"], LAST_REQUEST + 30)
    probed = now = 0
    while now < stop_at and len(finished) < len(todo):
        step = retrying(lambda: parent.advance(until=["price_request", "order_won", "order_lost"], max=stop_at))
        now = step["now"]
        actions = []
        for event in step["events"]:
            if event["kind"] == "price_request":
                request = event["request"]
                pair = member.get(request["id"])
                if pair is None or pair["pairId"] in finished:
                    actions.append(decline(request))
                    continue
                option = max(request["options"], key=lambda o: o["deadline"])  # the widest windows
                price = round(option["listPriceCents"] * args.win_ratio)
                actions.append({"type": "quote", "requestId": request["id"], "prices": {option["kind"]: price}})
            elif event["kind"] == "order_lost" and event["requestId"] in member:
                pair = member[event["requestId"]]
                if pair["pairId"] not in finished:
                    error = f"lost at the win price: {event['requestId']}"
                    write({"pairId": pair["pairId"], "kind": pair["kind"], **when(now), "error": error}, pair["pairId"])
                    finished.add(pair["pairId"])
            elif event["kind"] == "order_won" and event["order"]["id"] in member:
                pair = member[event["order"]["id"]]
                if pair["pairId"] in finished:
                    continue
                won[pair["pairId"]][event["order"]["id"]] = event["order"]
                if len(won[pair["pairId"]]) == len(pair["requests"]):
                    write(probe_shape(probe, parent, now, pair, args, km, minutes, homes), pair["pairId"])
                    finished.add(pair["pairId"])
                    probed += 1
        if actions:
            results = retrying(lambda actions=actions: parent.act(actions))
            for action, result in zip(actions, results):
                if not result["ok"]:
                    print(f"parent: {action['requestId']} refused: {result['reason']}", flush=True)
    return probed


def run(args: argparse.Namespace) -> None:
    out = Path(args.out) / f"{args.mode}-L{args.level}-{args.seed}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    key = {"quote": "requestId", "fee": "orderId", "shape": "pairId"}[args.mode]
    done = {json.loads(line)[key] for line in out.open()} if out.exists() else set()
    wanted = set(args.requests.split(",")) if args.requests else None
    client = ProxyClient()
    roads = client.map()["roads"]
    km = {(r["from"], r["to"]): r["km"] for r in roads}
    minutes = {(r["from"], r["to"]): r["minutes"] for r in roads}
    probe = Probe(client, args.keep_free)
    started, requests_before = time.monotonic(), client.requests

    def target(request: dict) -> bool:
        if request["id"] in done or request["arrivedAt"] // DAY not in args.days:
            return False
        if wanted is not None:
            return request["id"] in wanted
        return chosen(args.seed, args.level, args.mode, request["id"], args.share)

    def write(row: dict, label: str) -> None:
        with out.open("a") as f:
            f.write(json.dumps(row) + "\n")
        if args.mode == "shape":
            shown = f"savingRatio {row.get('error') or row.get('savingRatio') or row.get('ends')}"
        else:
            shown = f"flip {row.get('error') or row.get('flipRatio') or row.get('ends')}"
        print(f"{label} {shown}{'' if row.get('monotone', True) else '  NOT MONOTONE'}", flush=True)

    def play() -> int:
        """Quote and fee modes: one parent that probes the requests as they arrive. Returns the probed count."""
        probed = 0
        parent = probe.create(args.level, args.seed)
        homes = {d["id"]: d["homePlaceId"] for d in retrying(parent.roster)}
        stop_at = min(retrying(parent.snapshot)["endsAt"], LAST_REQUEST + 30)
        winning: dict[str, dict] = {}  # fee mode: request id -> request, quoted cheaply to win
        wake = ["price_request"] if args.mode == "quote" else ["price_request", "order_won", "order_lost"]
        now = 0
        while now < stop_at and (args.limit is None or probed < args.limit):
            if wanted is not None and wanted <= done and not winning:
                break  # every wanted request is probed
            step = retrying(lambda: parent.advance(until=wake, max=stop_at))
            now = step["now"]
            arrived = [e["request"] for e in step["events"] if e["kind"] == "price_request"]
            targets = [r for r in arrived if target(r)]
            actions = []
            if args.mode == "quote":
                for request in targets:
                    others = [r for r in arrived if r["id"] != request["id"]]
                    for row in probe_quote(probe, parent, request, args, others):
                        write(row, f"{row['requestId']} {row['option']:<13}")
                    done.add(request["id"])
                    probed += 1
                actions = [decline(r) for r in arrived]
            else:
                for request in arrived:
                    if request in targets:
                        winning[request["id"]] = request
                        first = request["options"][0]
                        price = round(first["listPriceCents"] * args.win_ratio)
                        actions.append({"type": "quote", "requestId": request["id"], "prices": {first["kind"]: price}})
                    else:
                        actions.append(decline(request))
                for event in step["events"]:
                    if event["kind"] == "order_lost" and event["requestId"] in winning:
                        request = winning.pop(event["requestId"])
                        write({"orderId": request["id"], **when(now), "error": "lost at the win price"}, request["id"])
                        done.add(request["id"])
                    elif event["kind"] == "order_won" and event["order"]["id"] in winning:
                        order = event["order"]
                        row = probe_fee(probe, parent, now, order, winning.pop(order["id"]), args, km, homes)
                        write(row, row["orderId"])
                        done.add(order["id"])
                        probed += 1
            if actions:
                results = retrying(lambda actions=actions: parent.act(actions))
                for action, result in zip(actions, results):
                    if not result["ok"]:
                        print(f"parent: {action['requestId']} refused: {result['reason']}", flush=True)
        return probed

    try:
        if args.mode == "shape":
            probed = run_shape(probe, args, done, wanted, write, km, minutes)
        else:
            probed = play()
    finally:
        probe.close()
    print(
        f"{probed} probed, {probe.copies} copies, {client.requests - requests_before} requests, "
        f"{time.monotonic() - started:.0f}s, into {out}",
        flush=True,
    )


def stop_on_signal(signum: int, frame: Any) -> None:
    raise KeyboardInterrupt


def ratio_pair(text: str) -> tuple[float, float]:
    low, high = (float(x) for x in text.split(","))
    if not 0 < low < high:
        raise argparse.ArgumentTypeError("give low,high with 0 < low < high")
    return low, high


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Bisects quotes, fees, or the fees of two cars as one gig against each alone, on copies of one "
        "practice world."
    )
    parser.add_argument("mode", choices=("quote", "fee", "shape"))
    parser.add_argument("--level", type=int, choices=range(4, 9), default=8, help="4 to 8: a level with a competitor")
    parser.add_argument("--seed", required=True)
    parser.add_argument(
        "--requests",
        help="comma-separated request ids to probe; shape: a pair with any of them (default: a hashed --share)",
    )
    parser.add_argument(
        "--share", type=float, help="share of the week's requests (quote, fee: default 0.05) or pairs (shape: 1)"
    )
    parser.add_argument(
        "--days",
        default="0,1,2,3,4",
        help="weekdays to probe, 0 = Monday; shape: the later request's day (default all; 0,1 avoids late drift)",
    )
    parser.add_argument("--limit", type=int, help="stop after this many probed requests, orders or pairs (shape)")
    parser.add_argument(
        "--range",
        type=ratio_pair,
        help="low,high: quote / list price (default 0.6,2.5) or fee / typical fee (fee, shape: 0.2,3)",
    )
    parser.add_argument("--resolution", type=float, default=0.01, help="bracket width / list price or typical fee")
    parser.add_argument("--checks", type=int, default=2, help="extra trials near the bracket, to test for a threshold")
    parser.add_argument("--window", type=int, default=180, help="fee, shape: minutes a copy waits for a booking")
    parser.add_argument("--win-ratio", type=float, default=0.5, help="fee, shape: the price / list price to win orders")
    parser.add_argument(
        "--kinds",
        default="trade_in,round_trip",
        help="shape: comma-separated pair kinds out of trade_in, round_trip, chain (default trade_in,round_trip)",
    )
    parser.add_argument(
        "--gap", type=int, default=180, help="shape: most minutes between the arrivals of a pair's two requests"
    )
    parser.add_argument("--keep-free", type=int, default=2, help="practice slots left for teammates (default 2)")
    parser.add_argument("--out", default="out/probe", help="output folder (default out/probe)")
    args = parser.parse_args(argv)
    args.low, args.high = args.range or ((0.6, 2.5) if args.mode == "quote" else (0.2, 3.0))
    if args.share is None:
        args.share = 1.0 if args.mode == "shape" else 0.05
    args.kinds = args.kinds.split(",")
    unknown = set(args.kinds) - {"trade_in", "round_trip", "chain"}
    if unknown:
        parser.error(f"--kinds: unknown {', '.join(sorted(unknown))}")
    args.days = {int(d) for d in args.days.split(",")}
    for name in ("SIGTERM", "SIGHUP"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), stop_on_signal)
    try:
        run(args)
    except SpreadError as error:
        sys.exit(f"spread: {error}")
    except KeyboardInterrupt:
        sys.exit("Stopped. The probe's worlds are deleted; the rows saved so far stay.")


if __name__ == "__main__":
    main()
