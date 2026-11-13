"""Fee schedules for a driver shortage, planned back from the pickup deadline. See README.md."""

from __future__ import annotations

from spread.client import World
from spread.types import FeeStep, Order, PriceRequest

from .market import Market
from .schedule import Gig, after_drop, plan

__all__ = ["FeePlanner", "Gig", "Market", "after_drop", "plan"]


class FeePlanner:
    """Turns an order and its request into the facts of a gig, and plans its fee schedule."""

    def __init__(self, market: Market):
        self.market = market

    @classmethod
    def for_world(cls, world: World) -> FeePlanner:
        """Reads the map and the driver list once: two requests."""
        return cls(Market(world.client.map(), world.roster()))

    def schedule(self, order: Order, request: PriceRequest, cars: int, now: int, level: int) -> list[FeeStep]:
        return plan(now, self.gig(order, request, cars, now), level)

    def after_drop(
        self, order: Order, request: PriceRequest, cars: int, now: int, level: int, dropped_fee: int
    ) -> list[FeeStep] | None:
        return after_drop(now, self.gig(order, request, cars, now), level, dropped_fee)

    def gig(self, order: Order, request: PriceRequest, cars: int, now: int) -> Gig:
        """The facts of a gig with `cars` of the order's cars, read from its first undelivered car."""
        share = cars / len(order["legs"])
        first = next((leg for leg, at in zip(order["legs"], order["deliveredAt"]) if at is None), order["legs"][0])
        pickup, delivery = first["pickup"]["placeId"], first["delivery"]["placeId"]
        return Gig(
            typical=request["referenceFeeCents"] * share,
            price=order["priceCents"] * share,
            last_pickup_at=order["lastPickupAt"],
            starts_at=max(now, first["pickup"]["window"]["from"]),
            drive_minutes=self.market.minutes(pickup, delivery),
            scarcity=self.market.scarcity(pickup),
            travel_minutes=self.market.travel_minutes(pickup),
        )
