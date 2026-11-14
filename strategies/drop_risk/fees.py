"""Drop-risk fees: headroom's lane-fee schedule, raised and flattened where booked drivers give gigs back.

A strategy (strategies/strategy.py) built on the lane fee planner of strategies/lane_fee, unchanged there. Each pickup
town has a fading count of bookings and of `gig_dropped` and `no_show` events. Their ratio lifts every fee, and a high
ratio leaves fewer, earlier raises. A town with no failures keeps the base schedule exactly. README.md explains the
estimator and the pricing rules.
"""

from __future__ import annotations

from dataclasses import dataclass

from spread.types import DeskEvent, DriverProfile, FeeStep, Order, PriceRequest, WorldMap

from strategies.dawn_fees import DawnParams
from strategies.fees.schedule import valid
from strategies.lane_fee import LaneFee, LaneFeePlanner


@dataclass(frozen=True)
class Params(DawnParams):
    """The variables of the dawn schedule, plus the drop-rate estimate and its effect on fees."""

    drop_premium: float = 0.75  # at a drop rate of 1, fees are 75% higher before the base schedule's cap
    fade: float = 0.9  # the weight left of an old booking and its failures when the next booking arrives
    high_risk: float = 0.08  # a town at this drop rate or above gets fewer, earlier raises
    earlier: float = 0.5  # high-risk intermediate raises move this share of the way back towards the post


class DropRiskFeePlanner(LaneFeePlanner):
    """The lane fee planner with a per-pickup-town premium for drops and no-shows."""

    params: Params

    def __init__(
        self,
        roster: list[DriverProfile],
        world_map: WorldMap,
        level: int = 8,
        params: Params | None = None,
        lane: LaneFee | None = None,
    ) -> None:
        super().__init__(roster, world_map, level, params or Params(), lane)
        self.bookings: dict[str, float] = {}  # pickup place -> faded booking count, the denominator
        self.failures: dict[str, float] = {}  # pickup place -> faded drops and no-shows, the numerator
        self.gig_places: dict[str, str] = {}  # gig id -> its first pickup place, registered by the desk

    def register(self, gig_id: str, place: str) -> None:
        """Remembers where a posted gig starts, so its bookings and failures teach that town's rate."""
        self.gig_places[gig_id] = place

    def observe(self, event: DeskEvent) -> None:
        """Counts each booking once; a gig booked again after a failure is a new booking. Old observations fade per
        booking, while each `gig_dropped` or `no_show` adds one event to the numerator."""
        kind = event["kind"]
        booked = kind == "gig_booked" or kind == "offer_answered" and event.get("answer") == "accepted"
        if not booked and kind not in ("gig_dropped", "no_show"):
            return
        place = self.gig_places.get(event["gigId"])
        if place is None:
            return
        if booked:
            fade = self.params.fade
            self.bookings[place] = self.bookings.get(place, 0.0) * fade + 1
            self.failures[place] = self.failures.get(place, 0.0) * fade
        else:
            self.failures[place] = self.failures.get(place, 0.0) + 1

    def rate(self, order: Order) -> float:
        """The faded drop and no-show events per booking at the order's first undelivered pickup, capped at 1."""
        first = next((leg for leg, at in zip(order["legs"], order["deliveredAt"]) if at is None), order["legs"][0])
        place = first["pickup"]["placeId"]
        bookings = self.bookings.get(place, 0.0)
        if bookings <= 0:
            return 0.0
        return min(1.0, self.failures.get(place, 0.0) / bookings)

    def schedule(self, order: Order, request: PriceRequest, cars: int, now: int) -> list[FeeStep]:
        return self.reprice(super().schedule(order, request, cars, now), self.rate(order), now)

    def after_drop(
        self, order: Order, request: PriceRequest, cars: int, now: int, dropped_fee: int
    ) -> list[FeeStep] | None:
        """The base planner's after-drop schedule, with the town's premium when the base planner reprices at all."""
        base = super().after_drop(order, request, cars, now, dropped_fee)
        return None if base is None else self.reprice(base, self.rate(order), now)

    def reprice(self, base: list[FeeStep], rate: float, now: int) -> list[FeeStep]:
        """Multiplies the base fees by one plus the drop premium. The unmodified opening fee is the floor and its top
        fee the cap. At high risk, keep every other intermediate raise and move the kept ones earlier; opening and top
        keep their base times. With no observed failures the exact base schedule, not a rebuilt one, is returned."""
        if rate <= 0 or not base:
            return base
        floor, cap = base[0]["feeCents"], base[-1]["feeCents"]
        factor = 1 + self.params.drop_premium * rate
        priced = [(step["at"], min(cap, max(floor, step["feeCents"] * factor))) for step in base]
        if rate < self.params.high_risk or len(priced) < 3:
            return valid(priced, self.level)
        earlier = [(now + (at - now) * (1 - self.params.earlier), fee) for at, fee in priced[1:-1:2]]
        return valid([priced[0], *earlier, priced[-1]], self.level)
