"""Soft top: the dawn fee schedule with a top fee of twice the lane fee, not 2.5 times.

A strategy (strategies/strategy.py) built on the lane fee planner of strategies/lane_fee, unchanged there. The top fee
is what a gig pays when nothing lower found a driver: on its last morning, after a drop, or after its deadline
warning. README.md next to this file has what the saved weeks paid at the top, and what a late car costs instead.
"""

from __future__ import annotations

from dataclasses import dataclass

from spread.types import DriverProfile, WorldMap

from strategies.dawn_fees import DawnParams
from strategies.lane_fee import LaneFee, LaneFeePlanner


@dataclass(frozen=True)
class Params(DawnParams):
    """The variables of the dawn schedule, with the top fee that this strategy changes."""

    top: float = 2.0  # the top fee over the lane fee, before the ceiling of strategies/fees cuts it


class SoftTopPlanner(LaneFeePlanner):
    """The lane fee planner whose schedules end at twice the lane fee."""

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
