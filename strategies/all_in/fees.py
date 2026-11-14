"""All-in fees: the soft-top schedule with the three variables that a comparison over 22 weeks moved.

A strategy (strategies/strategy.py) built on the soft-top fee planner of strategies/soft_top, unchanged there.
README.md next to this file has the comparison.
"""

from __future__ import annotations

from dataclasses import dataclass

from spread.types import DriverProfile, WorldMap

from strategies.lane_fee import LaneFee
from strategies.soft_top import SoftTopParams, SoftTopPlanner

HOUR = 60


@dataclass(frozen=True)
class Params(SoftTopParams):
    """The variables of the soft-top schedule, with the three that this system changes."""

    top: float = 1.7  # the top fee over the lane fee: lower again than soft top's 2.0
    dawn: float = 1.05  # the fee at the last dawn: the morning takes what the app shows
    patience: int = HOUR  # the opening fee stays this long before the one raise to the hold fee


class AllInPlanner(SoftTopPlanner):
    """The soft-top fee planner with a lower top, a lower dawn fee and an earlier raise to the hold fee."""

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
