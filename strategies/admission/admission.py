"""Admission control: decides, before we quote, whether we can move a request's cars on time and at a profit.

The scoring needs no network: it reads the request, the driver list, the map and the orders we hold.
See README.md next to this file for the score, its thresholds and the bench results.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, NamedTuple

HOUR, DAY = 60, 24 * 60
SATURDAY = 5
BIG = 10**6  # road minutes between two places the map does not join


@dataclass(frozen=True)
class Params:
    """The thresholds. The defaults are tuned on seeds spread-1 to spread-5 at level 8 (README.md)."""

    reach_minutes: float = 45.0  # a driver's weight falls by e for each this many road minutes from home
    area_minutes: int = 60  # held orders picked up within this drive of the pickup share its drivers
    capacity_per_driver: float = 0.10  # unbooked same-day orders an area holds for each driver weight near it
    min_capacity: float = 1.0  # even a place with few drivers can take one car at a time
    min_slack: int = 5 * HOUR  # an option needs this much time beyond the drive, or we do not offer it
    comfortable_slack: int = 9 * HOUR  # the earliest option with this much slack is the one we quote
    target_on_time: float = 0.95  # our running on-time share above which admission is not tightened
    floor_on_time: float = 0.90  # the delivery minimum: admission is tightest here
    tightest: float = 0.25  # the share of capacity left when the running on-time share is at the floor
    cost_base: float = 1.15  # expected fee over the typical fee in a shortage (levels 7 and 8)
    cost_base_normal: float = 1.0  # the same up to level 6, where most gigs book at the typical fee
    price_factor: float = 1.0  # the price we quote over the list price; the pricing logic (#13) raises it
    min_margin: float = 0.0  # decline when the expected cost leaves less than this share of the price
    # A return leg: one of our transports ends within `chain_minutes` of the car, its driver gets there at
    # most `chain_wait` before the car is ready, and drives the car back to within `chain_back` of where
    # that transport started, `chain_spare` before the deadline of the option we quote. The car then costs
    # `chain_cost` of the usual estimate, and takes half a place in the area's capacity.
    chain_minutes: int = 30
    chain_wait: int = 2 * HOUR
    chain_back: int = 60
    chain_spare: int = HOUR
    chain_cost: float = 0.85


class Held(NamedTuple):
    """An order we hold, as the desk knows it: whether a driver holds all of its undelivered cars now."""

    order: dict
    booked: bool

    @property
    def waiting(self) -> bool:
        """No driver holds it yet, and a car of it is still to deliver."""
        return not self.booked and any(t is None for t in self.order["deliveredAt"])


class Verdict(NamedTuple):
    """The answer for one request. `options` are the option kinds to quote, empty when we decline."""

    accept: bool
    options: list[str]
    expected_cost: int  # cents: what we expect to pay drivers for the request's cars
    score: float  # how good the request is: above 0 we take it; the expected margin over the price
    reason: str


@dataclass
class _Tracked:
    deadline: int
    delivered: list[int | None]
    pickup: str
    dealer: str


@dataclass
class Admission:
    """Scores price requests. Feed it every event with `observe`, then ask `assess` before each quote."""

    roster: list[dict]
    world_map: dict
    level: int = 8
    params: Params = field(default_factory=Params)

    def __post_init__(self) -> None:
        self.minutes: dict[tuple[str, str], int] = {(r["from"], r["to"]): r["minutes"] for r in self.world_map["roads"]}
        self.places = [p["id"] for p in self.world_map["places"]]
        self.home = {d["id"]: d["homePlaceId"] for d in self.roster}
        self.homes: dict[str, dict[str, int]] = {a: defaultdict(int) for a in ("all", "experienced", "manual")}
        for d in self.roster:
            self.homes["all"][d["homePlaceId"]] += 1
            if d["rating"] >= 4.8 and d["completedGigs"] >= 50:
                self.homes["experienced"][d["homePlaceId"]] += 1
            if d["licence"] == "manual":
                self.homes["manual"][d["homePlaceId"]] += 1
        self.booked_by_town: dict[str, int] = defaultdict(int)
        self.dropped_by_town: dict[str, int] = defaultdict(int)
        # Our own week: on-time tracking, and what each area's drivers did with our gigs.
        self.orders: dict[str, _Tracked] = {}
        self.on_time = 0
        self.late = 0
        self.closes: dict[str, float] = defaultdict(float)  # pickup place -> deadline warnings
        self.won: dict[str, int] = defaultdict(int)  # pickup place -> orders won
        self.pending: dict[str, tuple[int, str, int, float]] = {}  # request id -> (respondBy, pickup, day, weight)
        # order id -> (request id, its respondBy): the request whose return leg rides on that order's transport
        self.claims: dict[str, tuple[str, int]] = {}

    # --- the driver supply ---------------------------------------------------------------------------------

    def supply(self, place: str, audience: str = "all") -> float:
        """Drivers living near `place`, each weighted by exp(-road minutes from home / reach) and by how
        reliable their town's drivers have been with our gigs this week. `audience` is `all`,
        `experienced` (rating >= 4.8 and >= 50 gigs, for premium cars) or `manual` (manual licence)."""
        return sum(
            count
            * math.exp(-self.minutes.get((town, place), 10**6) / self.params.reach_minutes)
            * self.reliability(town)
            for town, count in self.homes[audience].items()
        )

    def reliability(self, town: str) -> float:
        """1 for a town whose drivers have not dropped our gigs; lower as drops outnumber bookings."""
        booked, dropped = self.booked_by_town[town], self.dropped_by_town[town]
        return (booked + 2.0) / (booked + 2.0 * dropped + 2.0)

    def stress(self, place: str) -> float:
        """How much harder than the roster says an area's cars are to place, from our own week: deadline
        warnings per order won there. 1 is as expected; it grows as the area's cars wait for drivers."""
        return 1.0 + 2.0 * self.closes[place] / (self.won[place] + 3.0)

    # --- our running on-time share -------------------------------------------------------------------------

    def observe(self, event: dict) -> None:
        """Learns from one event of the week: wins, changes, deliveries, deadline warnings and drops."""
        kind, at = event["kind"], event["at"]
        if kind == "order_won":
            order = event["order"]
            self.pending.pop(order["id"], None)
            pickup = order["legs"][0]["pickup"]["placeId"]
            self.orders[order["id"]] = _Tracked(
                order["deadline"], list(order["deliveredAt"]), pickup, order["dealerId"]
            )
            self.won[pickup] += 1
        elif kind == "order_lost":
            self.pending.pop(event["requestId"], None)
        elif kind == "order_changed":
            tracked = self.orders.get(event["order"]["id"])
            if tracked:
                tracked.deadline = event["order"]["deadline"]
        elif kind == "order_cancelled":
            self.orders.pop(event["orderId"], None)
        elif kind == "delivered":
            tracked = self.orders.get(event["orderId"])
            if tracked:
                tracked.delivered[event["leg"]] = at
                if all(t is not None for t in tracked.delivered):
                    self._resolve(event["orderId"], all(t <= tracked.deadline for t in tracked.delivered))
        elif kind in ("gig_booked", "gig_dropped") and event["driverId"] in self.home:
            towns = self.booked_by_town if kind == "gig_booked" else self.dropped_by_town
            towns[self.home[event["driverId"]]] += 1
        elif kind == "deadline_close":
            tracked = self.orders.get(event["orderId"])
            if tracked:
                self.closes[tracked.pickup] += 1.0
        self._expire(at)

    def _resolve(self, order_id: str, on_time: bool) -> None:
        self.orders.pop(order_id, None)
        if on_time:
            self.on_time += 1
        else:
            self.late += 1

    def _expire(self, now: int) -> None:
        """An order still on the road after its deadline is late, whenever it arrives."""
        for order_id in [i for i, t in self.orders.items() if now > t.deadline]:
            self._resolve(order_id, False)
        for request_id in [i for i, p in self.pending.items() if p[0] < now]:
            del self.pending[request_id]

    def on_time_share(self, held: Iterable[Held] = (), now: int = 0) -> float:
        """Our running on-time share, counting an order without a driver past its deadline warning as half
        late. It starts at the target: an empty week has nothing to say yet."""
        at_risk = sum(1 for h in held if h.waiting and now > h.order["lastPickupAt"] - 3 * HOUR)
        prior = 10.0
        late = self.late + 0.5 * at_risk
        return (self.on_time + prior * self.params.target_on_time) / (self.on_time + late + prior)

    def tightening(self, share: float) -> float:
        """1 at or above the target share, `tightest` at the delivery minimum and below, linear between."""
        p = self.params
        if share >= p.target_on_time:
            return 1.0
        if share <= p.floor_on_time:
            return p.tightest
        return p.tightest + (1 - p.tightest) * (share - p.floor_on_time) / (p.target_on_time - p.floor_on_time)

    # --- the score of a request ----------------------------------------------------------------------------

    def drive_minutes(self, legs: list[dict]) -> int:
        """Road minutes to move the request's cars one after the other, as one driver would."""
        total, here = 0, None
        for leg in legs:
            a, b = leg["pickup"]["placeId"], leg["delivery"]["placeId"]
            if here is not None and here != a:
                total += self.minutes.get((here, a), 0)
            total += self.minutes.get((a, b), 0)
            here = b
        return total

    def load(self, place: str, day: int, held: Iterable[Held]) -> float:
        """Orders that still need a driver from the area around `place` on `day`: held orders that no
        driver holds yet, and requests we have just quoted to take."""
        near = self.params.area_minutes
        total = 0.0
        for h in held:
            if not h.waiting:
                continue
            first = h.order["legs"][0]["pickup"]
            if first["window"]["from"] // DAY == day and self.minutes.get((first["placeId"], place), near + 1) <= near:
                total += 1
        for _, pickup, pending_day, weight in self.pending.values():
            if pending_day == day and self.minutes.get((pickup, place), near + 1) <= near:
                total += weight
        return total

    def chain(self, request: dict, held: Iterable[Held], now: int, deadline: int | None = None) -> str | None:
        """A return leg: one of our transports ends near where the request's car waits, its driver gets there
        in time to collect the car and deliver it by `deadline` (by default the request's earliest), and the
        car goes back towards where that transport started. That driver can take the car back, so it costs
        less and needs no new driver. Returns the transport's order id, or None. A transport that a driver
        already holds comes first, each one carries one return leg, and only a premium transport, whose
        driver is experienced, carries a premium car."""
        p = self.params
        first = request["legs"][0]["pickup"]
        window = first["window"]
        end = request["legs"][-1]["delivery"]["placeId"]  # where the driver finishes with the request's cars
        due = (min(o["deadline"] for o in request["options"]) if deadline is None else deadline) - p.chain_spare
        drive = self.drive_minutes(request["legs"])
        premium = any(leg["car"]["premium"] for leg in request["legs"])
        for h in sorted(held, key=lambda h: not h.booked):
            order = h.order
            if order["deliveredAt"][-1] is not None or self.claimed(order["id"], now):
                continue
            if premium and not any(leg["car"]["premium"] for leg in order["legs"]):
                continue
            start = order["legs"][0]["pickup"]  # where the transport's driver set out, near their home
            stop = order["legs"][-1]["delivery"]["placeId"]  # where they will be free
            reach = self.minutes.get((stop, first["placeId"]), BIG)
            if reach > p.chain_minutes or self.minutes.get((end, start["placeId"]), BIG) > p.chain_back:
                continue
            there = max(now, start["window"]["from"]) + self.drive_minutes(order["legs"]) + reach
            collect = max(there, window["from"])
            if collect - there <= p.chain_wait and collect <= window["to"] and collect + drive <= due:
                return order["id"]
        return None

    def claimed(self, order_id: str, now: int) -> bool:
        """The order's transport already carries the return leg of a request we quoted and wait to hear on,
        or of an order we won and have not delivered."""
        claim = self.claims.get(order_id)
        return claim is not None and (claim[1] >= now or claim[0] in self.orders)

    def expected_cost(self, request: dict, held: Iterable[Held] = (), now: int | None = None) -> int:
        """What we expect to pay drivers: the typical fee, scaled by the supply at both ends, the hour,
        private addresses, the note and a return leg."""
        now = request["arrivedAt"] if now is None else now
        return self.cost(request, self.chain(request, held, now) is not None)

    def cost(self, request: dict, chained: bool) -> int:
        """The expected cost, with `chained` when the car is a return leg of one of our transports."""
        p = self.params
        leg = request["legs"][0]
        pickup, delivery = leg["pickup"]["placeId"], request["legs"][-1]["delivery"]["placeId"]
        cost = request["referenceFeeCents"] * (p.cost_base if self.level >= 7 else p.cost_base_normal)
        cost *= 1 + 1.2 * math.exp(-self.supply(pickup) / 15)  # few drivers near the car: a long trip to it
        cost *= 1 + 0.5 * math.exp(-self.supply(delivery) / 15)  # few drivers at the end: an expensive trip home
        ready = leg["pickup"]["window"]["from"]
        hour, weekday = ready % DAY // HOUR, ready // DAY % 7
        if hour >= 17:
            cost *= 1.15  # evening work
        if weekday >= SATURDAY:
            cost *= 1.15  # weekend work
        if any(leg["pickup"]["privateAddress"] or leg["delivery"]["privateAddress"] for leg in request["legs"]):
            cost *= 1.1  # private address work, and a slot to keep
        if risky_note(request.get("note")):
            cost *= 1.05
        if chained:
            cost *= p.chain_cost
        return int(cost + 0.5)

    def option_slack(self, request: dict, option: dict, now: int) -> int:
        """Minutes to spare for one option: from when a driver can collect the car to its deadline, less the drive."""
        start = max(max(leg["pickup"]["window"]["from"] for leg in request["legs"]), now + HOUR)
        return option["deadline"] - start - self.drive_minutes(request["legs"])

    def assess(self, request: dict, held: Iterable[Held] = (), now: int | None = None) -> Verdict:
        """Decline, or accept with the options to quote and the expected cost."""
        held = list(held)
        p = self.params
        now = request["arrivedAt"] if now is None else now
        self._expire(now)
        leg = request["legs"][0]
        pickup, day = leg["pickup"]["placeId"], leg["pickup"]["window"]["from"] // DAY
        premium = any(leg["car"]["premium"] for leg in request["legs"])
        supply = self.supply(pickup, "experienced" if premium else "all") / self.stress(pickup)
        squeeze = self.tightening(self.on_time_share(held, now))
        min_slack = p.min_slack / max(squeeze, 0.5)
        usable = [o for o in request["options"] if self.option_slack(request, o, now) >= min_slack]
        comfortable = [o for o in usable if self.option_slack(request, o, now) >= p.comfortable_slack / squeeze]
        option = comfortable[0] if comfortable else usable[-1] if usable else None
        chained = self.chain(request, held, now, option["deadline"] if option else None)

        capacity = max(p.min_capacity, p.capacity_per_driver * supply) * squeeze
        load = self.load(pickup, day, held)
        weight = 0.5 if chained is not None else 1.0
        if load + weight > capacity:
            return Verdict(False, [], 0, -1.0, f"area full: {load:.1f} waiting of {capacity:.1f}")

        cost = self.cost(request, chained is not None)
        if option is None:
            return Verdict(False, [], cost, -1.0, "no option leaves time for the drive")
        price = option["listPriceCents"] * p.price_factor
        margin = (price - cost) / price
        if margin < p.min_margin:
            return Verdict(False, [], cost, margin, f"cost {cost / 100:.0f} over price {price / 100:.0f}")
        self.pending[request["id"]] = (request["respondBy"], pickup, day, weight)
        if chained is not None:
            self.claims[chained] = (request["id"], request["respondBy"])
        return Verdict(True, [option["kind"]], cost, margin, "ok")


# A note that asks for something a driver can miss: a manual gearbox, plates, a deadline or a payment.
RISK = re.compile(
    r"manu|käsivai|plat|kilv|skylt|kesär|sommar|summer|maksu|betal|payment|ennen|before|senast|mennessä", re.IGNORECASE
)


def risky_note(note: Any) -> bool:
    return bool(note) and bool(RISK.search(note.get("text", "")))
