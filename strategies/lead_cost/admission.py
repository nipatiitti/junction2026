"""Lead-cost admission: the expected driver cost of a request by its lead times, measured on the saved weeks, and the
option that leaves the most margin.

A strategy (strategies/strategy.py) built on the ceiling system's admission (strategies/ceiling), unchanged there:
the capacity of an area, the tightening by our on-time share and the timed return leg are that admission's. This
class replaces its driver cost and its choice of option. README.md next to this file explains the table, and fit.py
measures it.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from spread.types import DriverProfile, WorldMap

from strategies.admission import Held, Verdict
from strategies.admission.admission import DAY, HOUR, risky_note
from strategies.ceiling.admission import ChainAdmission
from strategies.ceiling.admission import Params as ChainParams

SATURDAY = 5


@dataclass(frozen=True)
class Params(ChainParams):
    """The admission thresholds of the ceiling system, plus the driver cost by lead time (fit.py prints the table)."""

    # An area holds twice the unbooked orders of strategies/admission: under dawn fees a gig waits for its morning on
    # purpose, so an order without a driver yet is not a sign that the area is full.
    capacity_per_driver: float = 0.20
    min_capacity: float = 2.0
    # The classes: hours from the win to the last pickup (rows of `cost`) and to the car's ready time (columns).
    last_pickup_hours: tuple[int, ...] = (8, 14, 24, 36, 60)
    ready_hours: tuple[int, ...] = (3, 8)
    # The driver cost over the typical fee at a dealer site. A row for each class of hours to the last pickup, the
    # last row open-ended; in a row, the car is ready within 3 hours, within 8, or later.
    cost: tuple[tuple[float, ...], ...] = (
        (2.40, 2.40, 2.40),
        (1.77, 1.77, 1.77),
        (1.44, 1.25, 1.06),
        (1.25, 1.10, 1.03),
        (1.25, 1.10, 1.05),
        (1.20, 1.10, 1.13),
    )
    private_pickup: tuple[float, ...] = (1.05, 1.30, 1.30)  # a private pickup costs this much more, by ready class
    private_delivery: tuple[float, ...] = (1.03, 1.10, 1.10)  # and a private delivery
    scarce_pickup: float = 0.8  # the cost rises by this share where no driver lives near the pickup
    scarce_delivery: float = 0.3  # and by this share where none lives near the delivery
    short_drive: int = 30  # a drive under this many road minutes ...
    short_cost: float = 1.12  # ... costs this much more over its typical fee
    premium_cost: float = 1.10  # a premium car needs an experienced driver
    note_cost: float = 1.05  # a note that asks for something a driver can miss
    return_leg: float = 0.95  # a timed return leg of one of our transports
    # A dealer who is offered a faster option takes a slower one from us about half as often at the same price.
    slower_win: float = 1.0  # the weight of an option's margin when the request has a faster one; 1 ignores it


class LeadCostAdmission(ChainAdmission):
    """The ceiling system's admission with the driver cost of the lead times and the option of the most margin."""

    params: Params

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())

    def assess(self, request: dict, held: Iterable[Held] = (), now: int | None = None) -> Verdict:
        """The verdict of this admission, with the ceiling system's bookkeeping of return legs around it."""
        held = list(held)
        self.now = request["arrivedAt"] if now is None else now
        verdict = self.verdict(request, held, self.now)
        transport = self.chain(request, held, self.now)
        if not verdict.accept:
            self.counts["declined"] += 1
            self.counts["cost"] += verdict.reason.startswith("cost")
        else:
            self.counts["taken"] += 1
            self.counts[f"taken {verdict.options[0]}"] += 1
            if transport is not None:
                self.claims[transport] = (request["id"], request["respondBy"])
                self.counts["return legs"] += 1
        return verdict

    def verdict(self, request: dict, held: list[Held], now: int) -> Verdict:
        """As strategies/admission: the area must have room and an option must leave time for the drive. Then the
        option is the one with the most margin over its lead cost, and it must leave `min_margin` of its price."""
        p = self.params
        self._expire(now)
        leg = request["legs"][0]
        pickup, day = leg["pickup"]["placeId"], leg["pickup"]["window"]["from"] // DAY
        premium = any(leg["car"]["premium"] for leg in request["legs"])
        supply = self.supply(pickup, "experienced" if premium else "all") / self.stress(pickup)
        squeeze = self.tightening(self.on_time_share(held, now))
        per_driver = p.capacity_per_driver_posting if self.level == 1 else p.capacity_per_driver
        capacity = max(p.min_capacity, per_driver * supply) * squeeze
        load = self.load(pickup, day, held)
        weight = 0.5 if self.pairs(request, held) else 1.0
        if load + weight > capacity:
            return Verdict(False, [], 0, -1.0, f"area full: {load:.1f} waiting of {capacity:.1f}")
        min_slack = p.min_slack / max(squeeze, 0.5)
        usable = [o for o in request["options"] if self.option_slack(request, o, now) >= min_slack]
        if self.level == 1:  # every quote wins the request's first option, whichever option it prices
            usable = [o for o in usable[:1] if o is request["options"][0]]
        if not usable:
            return Verdict(False, [], self.expected_cost(request, held), -1.0, "no option leaves time for the drive")
        costs = {o["kind"]: self.lead_cost(request, o, held, now) for o in usable}
        fastest = min(o["deadline"] for o in request["options"])

        def worth(o: dict) -> float:
            """The option's margin, counted less when the dealer could have a faster one: it then wins less often."""
            margin = o["listPriceCents"] * p.price_factor - costs[o["kind"]]
            return margin * (p.slower_win if o["deadline"] > fastest and margin > 0 else 1.0)

        option = max(usable, key=worth)
        price, cost = option["listPriceCents"] * p.price_factor, costs[option["kind"]]
        margin = (price - cost) / price
        if margin < p.min_margin:
            return Verdict(False, [], cost, margin, f"cost {cost / 100:.0f} over price {price / 100:.0f}")
        self.pending[request["id"]] = (request["respondBy"], pickup, day, weight)
        return Verdict(True, [option["kind"]], cost, margin, "ok")

    def lead_cost(self, request: dict, option: dict, held: Iterable[Held], now: int) -> int:
        """What we expect to pay drivers when the dealer takes `option`, in cents: the typical fee times the cost of
        its lead-time class, and what the addresses, the drivers near both ends, the car and the note add."""
        p = self.params
        legs = request["legs"]
        first, last = legs[0]["pickup"], legs[-1]["delivery"]
        won = max(now, request["respondBy"])  # the dealer decides then, and the gig is posted
        column = band((first["window"]["from"] - won) / HOUR, p.ready_hours)
        row = band((self.last_pickup(request, option) - won) / HOUR, p.last_pickup_hours)
        cost = self.typical(request) * p.cost[row][column]
        if any(leg["pickup"]["privateAddress"] for leg in legs):
            cost *= p.private_pickup[column]
        elif any(leg["delivery"]["privateAddress"] for leg in legs):
            cost *= p.private_delivery[column]
        cost *= 1 + p.scarce_pickup * math.exp(-self.supply(first["placeId"]) / 15)
        cost *= 1 + p.scarce_delivery * math.exp(-self.supply(last["placeId"]) / 15)
        if self.drive_minutes(legs) < p.short_drive:
            cost *= p.short_cost
        if any(leg["car"]["premium"] for leg in legs):
            cost *= p.premium_cost
        if risky_note(request.get("note")):
            cost *= p.note_cost
        if self.pairs(request, held):
            cost *= p.return_leg
        return int(cost + 0.5)

    def typical(self, request: dict) -> float:
        """The typical fee that the cost is counted from, in cents: the request's own."""
        return request["referenceFeeCents"]

    def last_pickup(self, request: dict, option: dict) -> int:
        """About the order's `lastPickupAt` when the dealer takes `option`: the last minute the first car can be
        collected and still arrive by the deadline, when its site is open or inside a private seller's slot."""
        first = request["legs"][0]["pickup"]
        latest = option["deadline"] - self.drive_minutes(request["legs"])
        if first["privateAddress"] or not first.get("hours"):
            return min(latest, first["window"]["to"])
        for day in range(latest // DAY, latest // DAY - 7, -1):
            span = open_hours(first["hours"], day)
            if span is not None and latest >= day * DAY + span[0]:
                return min(latest, day * DAY + span[1])
        return latest

    def summary(self) -> str:
        c = self.counts
        options = ", ".join(f"{c[key]} {key[6:]}" for key in sorted(c) if key.startswith("taken "))
        return super().summary() + (f"\nLead cost: options quoted: {options}" if options else "")


def band(hours: float, ends: tuple[int, ...]) -> int:
    """The class of `hours`: the first whose upper end it is under, or the open-ended last one."""
    return next((i for i, end in enumerate(ends) if hours < end), len(ends))


def open_hours(hours: dict, day: int) -> tuple[int, int] | None:
    """When a dealer site opens and closes on a day, in minutes of that day, or None when it is closed."""
    weekday = day % 7
    if weekday in hours.get("weekdays", ()):
        return hours["opens"], hours["closes"]
    if weekday == SATURDAY and hours.get("saturday"):
        return hours["saturday"]["opens"], hours["saturday"]["closes"]
    return None
