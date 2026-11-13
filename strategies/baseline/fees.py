"""The baseline's fee schedules: the starter's own `rising` and `steep` fees, re-homed as a strategy.

They are the organisers' code from `spread/starter.py`, unchanged. README.md next to this file says so.
"""

from __future__ import annotations

from spread.types import DeskEvent, DriverProfile, FeeStep, Order, PriceRequest, WorldMap

from strategies.strategy import NoParams, Strategy

HOUR = 60


class BaselineFees(Strategy[NoParams]):
    """The starter's fees: rising, or steep once the order's deadline warning has come."""

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: NoParams | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or NoParams())
        self.urgent: set[str] = set()  # the orders whose deadline warning has come

    def observe(self, event: DeskEvent) -> None:
        """Learns the deadline warnings: from then on an order's schedules are steep."""
        if event["kind"] == "deadline_close":
            self.urgent.add(event["orderId"])

    def warned(self, order_id: str) -> None:
        """The order's deadline warning has come: its further schedules are steep."""
        self.urgent.add(order_id)

    def schedule(self, order: Order, request: PriceRequest, cars: int, now: int) -> list[FeeStep]:
        """The fees for some of the order's cars from now, as the starter plans them."""
        fee = request["referenceFeeCents"] * cars / len(order["legs"])
        return steep(now, fee, self.level) if order["id"] in self.urgent else rising(now, fee, self.level)


def rising(now: int, fee: float, level: int) -> list[FeeStep]:
    """The fee at once, then 10% of it more every hour: six steps, up to 1.5 times. Level 1 takes one fee only."""
    # int(x + 0.5) rounds halves up, as JavaScript's Math.round does, so both starters post the same fees.
    return [
        {"at": now + k * HOUR, "feeCents": max(1, int(fee * (1 + k / 10) + 0.5))} for k in range(1 if level == 1 else 6)
    ]


def steep(now: int, fee: float, level: int) -> list[FeeStep]:
    """1.5 times the fee at once, then a quarter of it more every half hour, up to 2.5 times. Level 1 takes one fee only."""
    return [
        {"at": now + k * 30, "feeCents": max(1, int(fee * (1.5 + k / 4) + 0.5))} for k in range(1 if level == 1 else 5)
    ]
