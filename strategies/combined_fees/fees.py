"""The best compatible fee levers in one planner: soft top, homecoming and on-time slack.

`SoftTopPlanner` already uses the lane-corrected typical fee and a lower 2.0 top. This subclass adds the two
independent discounts of `AdaptiveFees` and `HomeReturnFees`, rather than duplicating their desks. The lane fee,
headroom admission and pricing remain those of `soft_top`.
"""

from __future__ import annotations

from dataclasses import dataclass

from spread.types import DriverProfile, Order, PriceRequest, WorldMap

from strategies.adaptive_fees import AdaptiveFees
from strategies.dawn_fees import DawnFeePlanner
from strategies.lane_fee import LaneFee
from strategies.soft_top import SoftTopParams, SoftTopPlanner


@dataclass(frozen=True)
class Params(SoftTopParams):
    """Soft top's dawn schedule, plus the two discounts, which stay independently configurable."""

    target_on_time: float = 0.95
    discount: float = 0.15  # AdaptiveFees' multiplier while the running on-time share is at least the target
    prior_orders: float = 10.0
    home_discount: float = 0.15  # the full discount at a delivery town with home_full_share of driver homes
    home_full_share: float = 0.05


class CombinedTopPlanner(AdaptiveFees, SoftTopPlanner):
    """The soft-top dawn planner with independently scaled home-return and on-time discounts.

    `AdaptiveFees.gig` applies the on-time multiplier after `FeePlanner.gig` has assembled the gig; that call
    resolves to `typical` here, on the lane fee. So the lane/homecoming/on-time effects multiply, not replace
    each other. `observe`, `resolve`, `expire` and `on_time_share` all come from `AdaptiveFees`.
    """

    params: Params

    def __init__(
        self,
        roster: list[DriverProfile],
        world_map: WorldMap,
        level: int = 8,
        params: Params | None = None,
        lane: LaneFee | None = None,
    ) -> None:
        # Initialise the dawn/lane side directly. AdaptiveFees' small event counters are then added here;
        # calling both parent constructors would build the same roster-derived fee market twice.
        SoftTopPlanner.__init__(self, roster, world_map, level, params or Params(), lane)
        self.orders: dict[str, tuple[int, list[int | None]]] = {}
        self.on_time = 0
        self.late = 0
        self.cheap = 0
        self.home_total = max(1, sum(self.market.homes.values()))

    def typical(self, order: Order, request: PriceRequest) -> float:
        """The lane fee with the homecoming discount, before AdaptiveFees' gig applies on-time slack."""
        typical = super().typical(order, request)
        delivery = order["legs"][-1]["delivery"]["placeId"]
        share = self.market.homes[delivery] / self.home_total
        discount = self.params.home_discount * min(1.0, share / self.params.home_full_share)
        return typical * (1 - discount)

    def summary(self) -> str:
        """The dawn counts and the on-time discount count from the two parent planners."""
        return "\n".join(line for line in (DawnFeePlanner.summary(self), AdaptiveFees.summary(self)) if line)
