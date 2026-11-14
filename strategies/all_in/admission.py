"""All-in admission: the flu guard of strategies/flu_guard with the same-day variables of strategies/same_day.

A strategy (strategies/strategy.py) that adds nothing of its own: the two folders change different things in the
lane-cost admission (one keeps options off a quote, the other changes two variables of the cost and the choice of
option), so their sum is the guard's class with both sets of variables. README.md next to this file has the system.
"""

from __future__ import annotations

from dataclasses import dataclass

from spread.types import DriverProfile, WorldMap

from strategies.flu_guard import FluGuardAdmission, FluGuardParams
from strategies.lane_fee import LaneFee
from strategies.same_day import SameDayParams


@dataclass(frozen=True)
class Params(SameDayParams, FluGuardParams):
    """The variables of the flu guard, with the cost rows and the slower-option weight of same-day quoting. The two
    sets do not overlap but for those, which same-day quoting sets: it comes first in the bases for that."""


class AllInAdmission(FluGuardAdmission):
    """The flu-guard admission with the same-day variables."""

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
