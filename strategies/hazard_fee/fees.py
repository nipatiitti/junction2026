"""Hazard-priced fees: choose an opening fee from this week's observed booking hazard.

A strategy (strategies/strategy.py) on the lane fee planner of strategies/lane_fee. The desk tells the planner which
schedules its one-order gigs received; open daytime spells and bookings then teach a fading rate per fee-ratio band.
Only the opening fee changes: the dawn schedule, its raise times, caps and after-drop floor stay with the base planner.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from itertools import pairwise

from spread.types import DeskEvent, DriverProfile, FeeStep, Order, PriceRequest, WorldMap

from strategies.dawn_fees import DawnParams, dawn_plan
from strategies.lane_fee import LaneFee, LaneFeePlanner

HOUR, DAY = 60, 24 * 60
DAY_FROM, DAY_TO = 7 * HOUR, 23 * HOUR


@dataclass(frozen=True)
class Params(DawnParams):
    """The dawn schedule, plus the online hazard estimate and the opening fees it may choose."""

    band_width: float = 0.25  # fee over the lane fee: [0.75, 1.0), [1.0, 1.25), and so on
    ratios: tuple[float, ...] = (0.75, 0.9, 1.0, 1.15, 1.4, 1.75, 2.25)  # candidate opening fees
    target_prob: float = 0.9  # required probability of a booking before the last on-time pickup
    min_hours: float = 6.0  # faded daytime hours a band needs before its rate can choose a fee
    half_life_hours: float = 36.0  # old exposure and bookings fade with this half-life; 0 keeps them all


@dataclass
class Band:
    """Faded sufficient statistics of one fee-ratio band."""

    hours: float = 0.0
    bookings: float = 0.0
    at: int = 0


@dataclass
class TrackedGig:
    """The fee scale and latest accepted schedule of one of this planner's gigs."""

    typical: float
    schedule: list[FeeStep]


class HazardFeePlanner(LaneFeePlanner):
    """Pick the cheapest observed opening fee that meets the booking-probability target."""

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
        self.bands: dict[int, Band] = {}
        self.gigs: dict[str, TrackedGig] = {}
        self.open: dict[str, int] = {}  # gig id -> when its current open spell began

    def schedule(self, order: Order, request: PriceRequest, cars: int, now: int) -> list[FeeStep]:
        """Return the base schedule unless an observed candidate meets `target_prob` at a lower fee than the others.

        The base opening fee is the floor. A candidate only changes `open` and `sprint_open`, so the base planner
        still applies its fee cap, and its existing raises either stay in place or collapse into the higher opening.
        """
        base = super().schedule(order, request, cars, now)
        gig = self.gig(order, request, cars, now)
        floor = base[0]["feeCents"] / max(1.0, gig.typical)
        seen: set[int] = set()
        for ratio in (floor, *sorted(self.params.ratios)):
            if ratio <= floor:
                candidate = base
            else:
                changed = replace(self.params, open=ratio, sprint_open=ratio)
                candidate = dawn_plan(now, gig, self.level, changed)
            fee = candidate[0]["feeCents"]
            if fee in seen:
                continue
            seen.add(fee)
            rate = self.rate(fee / max(1.0, gig.typical), now)
            if rate is None:
                continue
            hours = daytime_hours(now, gig.last_pickup_at)
            if -math.expm1(-rate * hours) >= self.params.target_prob:
                return candidate
        return base

    def rate(self, ratio: float, now: int) -> float | None:
        """Faded bookings per open daytime hour in a ratio's band, or None while it has too little exposure."""
        band = self.bands.get(self.band(ratio))
        if band is None:
            return None
        hours, bookings = self.faded(band, now)
        return bookings / hours if hours >= self.params.min_hours and hours > 0 else None

    def band(self, ratio: float) -> int:
        return max(0, math.floor(ratio / self.params.band_width))

    def faded(self, band: Band, now: int) -> tuple[float, float]:
        """Exponentially fade old data lazily, so a band needs no clock events of its own."""
        if self.params.half_life_hours <= 0:
            return band.hours, band.bookings
        weight = 0.5 ** (max(0, now - band.at) / HOUR / self.params.half_life_hours)
        return band.hours * weight, band.bookings * weight

    def add(self, ratio: float, at: int, hours: float = 0.0, booking: bool = False) -> None:
        """Add an exposure segment or a booking, decaying the band to their common timestamp first."""
        key = self.band(ratio)
        band = self.bands.setdefault(key, Band(at=at))
        band.hours, band.bookings = self.faded(band, at)
        band.hours += hours
        band.bookings += booking
        band.at = max(band.at, at)

    def posted(self, gig_id: str, schedule: list[FeeStep], typical: float, at: int) -> None:
        """Remember an accepted one-order gig and open its first spell."""
        self.gigs[gig_id] = TrackedGig(typical, schedule)
        self.open.setdefault(gig_id, at)

    def repriced(self, gig_id: str, schedule: list[FeeStep], at: int) -> None:
        """Close the old fee's exposure and continue the same open spell on an accepted new schedule."""
        gig = self.gigs.get(gig_id)
        if gig is None:
            return
        if (start := self.open.get(gig_id)) is not None:
            self.expose(gig, start, at)
            self.open[gig_id] = max(start, at)
        gig.schedule = schedule

    def withdrawn(self, gig_id: str, at: int) -> None:
        """End an open spell when the world accepts a withdraw, which has no event of its own."""
        self.close(gig_id, at)
        self.gigs.pop(gig_id, None)

    def observe(self, event: DeskEvent) -> None:
        """Learn exposure while our gigs are open and one booking at the end of a successful spell."""
        kind, at = event["kind"], event["at"]
        if kind == "gig_booked" or kind == "offer_answered" and event.get("answer") == "accepted":
            self.close(event["gigId"], at, event.get("feeCents"), booked=True)
        elif kind in ("gig_dropped", "no_show"):
            if event["gigId"] in self.gigs:
                self.open[event["gigId"]] = at
        elif kind == "gig_expired":
            self.close(event["gigId"], at)
            self.gigs.pop(event["gigId"], None)
        elif kind == "order_cancelled":
            for cancelled in event["gigs"]:
                self.close(cancelled["gigId"], at)
                self.gigs.pop(cancelled["gigId"], None)

    def close(self, gig_id: str, at: int, fee: int | None = None, booked: bool = False) -> None:
        """Accrue an open spell, then count its booking at the actual fee when one ended it."""
        start = self.open.pop(gig_id, None)
        gig = self.gigs.get(gig_id)
        if start is None or gig is None or gig.typical <= 0:
            return
        self.expose(gig, start, at)
        if booked:
            booked_fee = fee if fee is not None else fee_at(gig.schedule, at)
            self.add(booked_fee / gig.typical, at, booking=True)

    def expose(self, gig: TrackedGig, start: int, end: int) -> None:
        """Split a spell at raises and clock boundaries; only 07:00–23:00 contributes exposure."""
        if end <= start:
            return
        boundaries = {start, end}
        boundaries.update(step["at"] for step in gig.schedule if start < step["at"] < end)
        for day in range(start // DAY, end // DAY + 1):
            boundaries.update(t for t in (day * DAY + DAY_FROM, day * DAY + DAY_TO) if start < t < end)
        ordered = sorted(boundaries)
        for a, b in pairwise(ordered):
            hours = daytime_hours(a, b)
            if hours > 0:
                self.add(fee_at(gig.schedule, a) / gig.typical, b, hours=hours)


def fee_at(schedule: list[FeeStep], at: int) -> int:
    """The accepted schedule's fee at a minute."""
    fee = schedule[0]["feeCents"]
    for step in schedule:
        if step["at"] > at:
            break
        fee = step["feeCents"]
    return fee


def daytime_hours(start: int, end: int) -> float:
    """Open hours between 07:00 and 23:00 in an interval."""
    minutes = 0
    for day in range(start // DAY, end // DAY + 1):
        minutes += max(0, min(end, day * DAY + DAY_TO) - max(start, day * DAY + DAY_FROM))
    return minutes / HOUR
