"""The fees strategy: turns an order and its request into the facts of a gig, and plans its fee schedule with the
pure functions of schedule.py. See README.md next to this file."""

from __future__ import annotations

from spread.types import DeskEvent, DriverProfile, FeeStep, Leg, Order, PriceRequest, WorldMap

from strategies.fees.market import Market
from strategies.fees.schedule import Gig, after_drop, ladder, plan, trip_fee
from strategies.strategy import NoParams, Strategy


class FeePlanner(Strategy[NoParams]):
    """Turns an order and its request into the facts of a gig, and plans its fee schedule. Its thresholds are the
    constants of schedule.py, which `results/bench.py` changes one at a time, so its `params` are empty."""

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: NoParams | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or NoParams())
        self.market = Market(world_map, roster)

    def observe(self, event: DeskEvent) -> None:
        """Learns nothing from the week: each schedule is planned from its gig's facts and the time alone."""

    def schedule(self, order: Order, request: PriceRequest, cars: int, now: int) -> list[FeeStep]:
        return plan(now, self.gig(order, request, cars, now), self.level)

    def after_drop(
        self, order: Order, request: PriceRequest, cars: int, now: int, dropped_fee: int
    ) -> list[FeeStep] | None:
        return after_drop(now, self.gig(order, request, cars, now), self.level, dropped_fee)

    def ladder(self, order: Order, request: PriceRequest, cars: int, now: int) -> list[FeeStep]:
        """Level 1: the fees of a gig posted now, while no driver books it (see `ladder`)."""
        return ladder(now, self.gig(order, request, cars, now))

    def typical(self, order: Order, request: PriceRequest) -> float:
        """The typical fee of all the order's cars, for the trips they make now. The request's typical fee
        is for the trips it asked for. After a change of plan (`order_changed`), the order's legs go to the
        new place and the request's keep the old one: the typical fee is then that of the first car's trip."""
        if all(trip(asked) == trip(now) for asked, now in zip(request["legs"], order["legs"])):
            return request["referenceFeeCents"]
        return trip_fee(self.market.minutes(*trip(order["legs"][0])))

    def gig(self, order: Order, request: PriceRequest, cars: int, now: int) -> Gig:
        """The facts of a gig with `cars` of the order's cars, read from its first undelivered car."""
        share = cars / len(order["legs"])
        first = next((leg for leg, at in zip(order["legs"], order["deliveredAt"]) if at is None), order["legs"][0])
        pickup, delivery = first["pickup"]["placeId"], first["delivery"]["placeId"]
        return Gig(
            typical=self.typical(order, request) * share,
            price=order["priceCents"] * share,
            last_pickup_at=order["lastPickupAt"],
            starts_at=max(now, first["pickup"]["window"]["from"]),
            drive_minutes=self.market.minutes(pickup, delivery),
            scarcity=self.market.scarcity(pickup),
            travel_minutes=self.market.travel_minutes(pickup),
        )


def trip(leg: Leg) -> tuple[str, str]:
    """The places a car goes from and to."""
    return leg["pickup"]["placeId"], leg["delivery"]["placeId"]
