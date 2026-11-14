"""Fee schedules discounted where delivering the car also gets many drivers close to home."""

from __future__ import annotations

from dataclasses import dataclass, replace

from spread.types import DriverProfile, Order, PriceRequest, WorldMap

from strategies.fees import FeePlanner
from strategies.fees.schedule import Gig
from strategies.strategy import NoParams


@dataclass(frozen=True)
class Params(NoParams):
    """The discount at a delivery town whose homes are `full_share` or more of the roster."""

    discount: float = 0.15
    full_share: float = 0.05


class HomeReturnFees(FeePlanner):
    """Lowers the typical fee as a delivery town's share of driver homes rises.

    A driver who finishes near home does not pay for a trip back from another town, so the same booking
    should be available more cheaply there. The discount is proportional to the town's share of homes,
    up to `discount`, and only changes the fee planner's typical fee, not the order's price or its
    admission cost.
    """

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())
        self.home_total = max(1, sum(self.market.homes.values()))

    def gig(self, order: Order, request: PriceRequest, cars: int, now: int) -> Gig:
        """The usual gig, with its typical fee discounted by `discount` at the full home share."""
        gig = super().gig(order, request, cars, now)
        delivery = order["legs"][-1]["delivery"]["placeId"]
        share = self.market.homes[delivery] / self.home_total
        discount = self.params.discount * min(1.0, share / self.params.full_share)
        return replace(gig, typical=gig.typical * (1 - discount))
