"""Joint bid pricing: the quote's driver cost comes from the fee schedule the desk plans to post.

A strategy (strategies/strategy.py) built on headroom pricing, unchanged there: the learned price, the moving
maximum, trust and outage lifts, and a decline when the cost floor is above the maximum. The only change is the
cost supplied to that floor. Before pricing, the desk reads the fee planner's schedule; its opening and top fees,
blended by `expected_step`, replace admission's generic driver-cost estimate. README.md explains the estimate and
its fallback.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from spread.types import DriverProfile, FeeStep, WorldMap

from strategies.headroom.pricing import HeadroomPricing
from strategies.headroom.pricing import Params as HeadroomParams


@dataclass(frozen=True)
class Params(HeadroomParams):
    """The variables of headroom pricing, plus where the expected paid fee sits on its schedule."""

    expected_step: float = 0.5  # 0 expects the opening fee, 1 the top fee, and values between blend them


class JointPricing(HeadroomPricing):
    """Headroom pricing whose driver-cost floor is the expected fee of the schedule to be posted."""

    params: Params

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())

    def price(
        self,
        request: dict,
        now: int,
        cost: float = 0,
        kinds: Iterable[str] | None = None,
        schedule: list[FeeStep] | None = None,
    ) -> dict[str, int]:
        """Prices as headroom does, over the schedule's expected fee when one is available. The expected fee is
        opening + expected_step x (top - opening). Without a schedule, `cost` remains admission's estimate."""
        if schedule:
            opening, top = schedule[0]["feeCents"], schedule[-1]["feeCents"]
            cost = opening + self.params.expected_step * (top - opening)
        return super().price(request, now, cost, kinds)
