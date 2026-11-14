"""Admission whose driver cost is corrected by our own bookings: each booked fee against the cost that admission
expected for that car teaches, for the car's pickup town and for the world, how far off the estimate runs.

A strategy (strategies/strategy.py) built on the timed return leg of strategies/ceiling, unchanged there. The base
estimate (strategies/admission) scales the typical fee by a fixed 1.15 and by the drivers the roster puts near both
ends. Level 8 reshuffles where drivers really work, so the same estimate is too high in some towns and too low in
others. Here every booking corrects it: the expected cost is the base estimate times a correction learned in the week,
by pickup place, shrunk to the world's correction while a place has few bookings. README.md next to this file has the
formula.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from spread.types import DriverProfile, WorldMap

from strategies.admission import Held, Verdict
from strategies.ceiling.admission import ChainAdmission
from strategies.ceiling.admission import Params as ChainParams


@dataclass(frozen=True)
class Params(ChainParams):
    """The thresholds of the timed return leg, plus how the correction learns."""

    town_prior: float = 4.0  # a place's correction counts this many bookings at the world's correction
    world_prior: float = 10.0  # the world's correction counts this many bookings at 1: the base estimate
    low: float = 0.6  # a correction never goes below this
    high: float = 1.6  # nor above this
    pool: int = 20  # bookings at pickups within this drive of the place teach its correction too


class LearnedCostAdmission(ChainAdmission):
    """The ceiling system's admission, with its expected driver cost corrected by the week's bookings."""

    params: Params

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())
        self.expected: dict[str, tuple[int, str]] = {}  # request id -> (expected cost before the correction, pickup)
        self.ratios: list[tuple[str, float]] = []  # (pickup place, booked fee over the expected cost), one a booking

    # --- learning ------------------------------------------------------------------------------------

    def booked(self, order_id: str, fee_cents: int, share: float) -> None:
        """A driver booked a gig with `share` of the order's cars, alone, at `fee_cents`: what that teaches about
        the estimate. The desk calls this; a bundle's fee is shared with other orders and teaches nothing here."""
        expected = self.expected.get(order_id)
        if expected is None or expected[0] <= 0 or share <= 0:
            return
        self.ratios.append((expected[1], fee_cents / (expected[0] * share)))
        self.counts["bookings learned"] += 1

    def world_correction(self) -> float:
        """The world's correction: the mean of every booking's ratio, shrunk to 1 (the base estimate)."""
        prior = self.params.world_prior
        return (sum(r for _, r in self.ratios) + prior) / (len(self.ratios) + prior)

    def correction(self, place: str) -> float:
        """The place's correction: the mean ratio of the bookings at or near it, shrunk to the world's."""
        world = self.world_correction()
        near = [r for town, r in self.ratios if self.minutes.get((town, place), 10**6) <= self.params.pool]
        prior = self.params.town_prior
        value = (sum(near) + prior * world) / (len(near) + prior)
        return min(self.params.high, max(self.params.low, value))

    # --- the estimate --------------------------------------------------------------------------------

    def expected_cost(self, request: dict, held: Iterable[Held] = ()) -> int:
        """The base estimate times the correction of the request's pickup place."""
        base = super().expected_cost(request, held)
        pickup = request["legs"][0]["pickup"]["placeId"]
        self.expected[request["id"]] = (base, pickup)
        return int(base * self.correction(pickup) + 0.5)

    def assess(self, request: dict, held: Iterable[Held] = (), now: int | None = None) -> Verdict:
        """The base's verdict, with the corrected cost. Counts whether the correction raised or lowered it."""
        verdict = super().assess(request, held, now)
        if request["id"] in self.expected and verdict.expected_cost:
            factor = self.correction(self.expected[request["id"]][1])
            self.counts["cost raised"] += factor > 1.005
            self.counts["cost lowered"] += factor < 0.995
        return verdict

    def summary(self) -> str:
        """The chain admission line, plus what the bookings taught."""
        line = super().summary()
        if not line:
            return ""
        c = self.counts
        return (
            f"{line}; learned cost: {c['bookings learned']} bookings, world x{self.world_correction():.2f}, "
            f"{c['cost lowered']} estimates lowered and {c['cost raised']} raised"
        ).replace("Chain admission:", "Learned-cost admission:", 1)
