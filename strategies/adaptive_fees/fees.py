"""Fee schedules that spend the week's on-time headroom and return to normal when it runs out."""

from __future__ import annotations

from dataclasses import dataclass, replace

from spread.types import DeskEvent, DriverProfile, Order, PriceRequest, WorldMap

from strategies.fees import FeePlanner
from strategies.fees.schedule import Gig
from strategies.strategy import NoParams


@dataclass(frozen=True)
class Params(NoParams):
    """Start with a prior at `target_on_time`; discount fees only at or above that share."""

    target_on_time: float = 0.95
    discount: float = 0.15
    prior_orders: float = 10.0


class AdaptiveFees(FeePlanner):
    """Discounts `Gig.typical` while enough of the week's completed orders arrived on time.

    This is the on-time-slack experiment: the normal target is 95%, five points above the 90% delivery
    minimum. The typical fee falls by 15% at that target or better, and returns to normal below it. An order
    past its deadline counts as late even before it is eventually delivered or left undelivered.
    """

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())
        self.orders: dict[str, tuple[int, list[int | None]]] = {}
        self.on_time = 0
        self.late = 0
        self.cheap = 0

    def observe(self, event: DeskEvent) -> None:
        """Counts completed orders on time or late, and expires those already past their deadline."""
        kind, at = event["kind"], event["at"]
        if kind == "order_won":
            order = event["order"]
            self.orders[order["id"]] = (order["deadline"], list(order["deliveredAt"]))
        elif kind == "order_changed":
            if order := self.orders.get(event["order"]["id"]):
                self.orders[event["order"]["id"]] = (event["order"]["deadline"], order[1])
        elif kind == "order_cancelled":
            self.orders.pop(event["orderId"], None)
        elif kind == "delivered" and (order := self.orders.get(event["orderId"])):
            order[1][event["leg"]] = at
            if all(t is not None for t in order[1]):
                self.resolve(event["orderId"], order[0] >= max(order[1]))
        self.expire(at)

    def resolve(self, order_id: str, on_time: bool) -> None:
        self.orders.pop(order_id, None)
        if on_time:
            self.on_time += 1
        else:
            self.late += 1

    def expire(self, now: int) -> None:
        for order_id in [order_id for order_id, (deadline, _) in self.orders.items() if now > deadline]:
            self.resolve(order_id, False)

    def on_time_share(self) -> float:
        """The completed-order share, shrunk towards the target so an empty week starts there."""
        prior = self.params.prior_orders
        return (self.on_time + prior * self.params.target_on_time) / (self.on_time + self.late + prior)

    def gig(self, order: Order, request: PriceRequest, cars: int, now: int) -> Gig:
        """The usual gig, cheaper only while `on_time_share` is at least the target."""
        gig = super().gig(order, request, cars, now)
        if self.on_time_share() < self.params.target_on_time:
            return gig
        self.cheap += 1
        return replace(gig, typical=gig.typical * (1 - self.params.discount))

    def summary(self) -> str:
        return f"Adaptive fees: {self.cheap} schedules discounted; on time {self.on_time_share():.1%}"
