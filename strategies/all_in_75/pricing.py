"""All-in 75 pricing: the all-in system's lane-prior pricing, aiming to win 75% of its quotes, not 45%.

A strategy (strategies/strategy.py) built on the lane-prior pricing of strategies/lane_prior, unchanged there. The
only change is the two win shares that the price settles to. README.md next to this file has the system.
"""

from __future__ import annotations

from dataclasses import dataclass

from spread.types import DriverProfile, WorldMap

from strategies.lane_prior import PriorParams, PriorPricing


@dataclass(frozen=True)
class Params(PriorParams):
    """The variables of the lane-prior pricing, with the two win shares that this system aims at."""

    target_win: float = 0.75  # the learned price settles where this share of its quotes win: headroom's is 0.45
    cap_win: float = 0.80  # ... and the maximum where this share of the quotes at it win: headroom's is 0.50


class AllIn75Pricing(PriorPricing):
    """The lane-prior pricing that aims to win 75% of its quotes, 80% at the maximum."""

    params: Params

    def __init__(
        self,
        roster: list[DriverProfile],
        world_map: WorldMap,
        level: int = 8,
        params: Params | None = None,
        priors: dict[str, float] | None = None,
    ) -> None:
        super().__init__(roster, world_map, level, params or Params(), priors)
