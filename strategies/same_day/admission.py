"""Same-day admission: quotes the fastest option that a dealer asks for when the car can still be moved today at a
fee that pays.

A strategy (strategies/strategy.py) built on the lane-cost admission of strategies/lane_fee, unchanged there. It is
that admission with two variables changed: an option counts for half of its margin when the request has a faster one,
and the driver cost of a car to collect within 14 hours is the cost of the sprint ladder, not of a gig that opens at
its top fee. README.md next to this file has what the saved weeks show.
"""

from __future__ import annotations

from dataclasses import dataclass

from spread.types import DriverProfile, WorldMap

from strategies.lane_fee import LaneCostAdmission, LaneFee
from strategies.lead_cost import LeadCostParams


@dataclass(frozen=True)
class Params(LeadCostParams):
    """The variables of the lead-cost admission, with the two that same-day quoting changes."""

    # A dealer who is offered a faster option takes a slower one from us about half as often at the same price.
    slower_win: float = 0.5
    # The driver cost over the lane fee, as in strategies/lead_cost, but for its first two rows: a car to collect
    # within 8 and within 14 hours. The saved weeks paid 2.40 and 1.77 there, with gigs that opened near their top
    # fee; these are an estimate for the sprint ladder of strategies/dawn_fees. The third row's middle cell is 1.15.
    cost: tuple[tuple[float, ...], ...] = (
        (1.60, 1.60, 1.60),
        (1.35, 1.35, 1.35),
        (1.25, 1.15, 1.06),
        (1.25, 1.10, 1.03),
        (1.25, 1.10, 1.05),
        (1.20, 1.10, 1.13),
    )


class SameDayAdmission(LaneCostAdmission):
    """The lane-cost admission that weighs a slower option by how often it wins, with a same-day cost that pays."""

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
