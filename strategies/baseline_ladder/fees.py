"""The fees of the baseline with a ladder: a ramp from half the typical fee to 2.5 times it, by the clock.

No network: `schedule` takes an order, its request and the minute, as `BaselineFees.schedule` does. README.md next
to this file has the rule.
"""

from __future__ import annotations

from dataclasses import dataclass

from spread.types import DeskEvent, DriverProfile, FeeStep, Order, PriceRequest, WorldMap

from strategies.strategy import Strategy

MAX_STEPS = 48  # the most steps a fee schedule may have


@dataclass(frozen=True)
class Params:
    """The knobs of the ramp, as shares of the request's typical fee and minutes."""

    first: float = 0.5  # the fee when the order is won
    top: float = 2.5  # the highest fee
    before_deadline: int = 6 * 60  # the fee reaches `top` this many minutes before the order's delivery deadline
    before_last_pickup: int = 60  # or this many minutes before the order's last on-time pickup, when that is sooner
    least_ramp: int = 60  # but never sooner than this many minutes after the order is won
    least_gap: int = 5  # the least minutes between two steps of a schedule


class RampFees(Strategy[Params]):
    """One line for each order: `first` times the typical fee when the order is won, rising evenly to `top` times
    it at `before_deadline` minutes before the delivery deadline, and `top` from then on. An order whose last
    on-time pickup (`lastPickupAt`) comes first reaches `top` `before_last_pickup` minutes before that instead: a
    driver who books later cannot deliver on time. An order won with less time than that still starts at `first`,
    and rises in `least_ramp` minutes.

    The fee depends on the minute only, so a gig posted again, after a failed visit or an ended window, goes on at
    the fee the line has reached. The deadline warning changes nothing: no fee passes `top`.
    """

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())

    def observe(self, event: DeskEvent) -> None:
        """Learns nothing from the week: the fee follows the clock."""

    def warned(self, order_id: str) -> None:
        """The order's deadline warning has come. The ramp is the same after it."""

    def share(self, order: Order, request: PriceRequest, at: int) -> float:
        """The fee at the minute `at`, as a share of the typical fee."""
        start, end = request["respondBy"], self.top_at(order, request)  # won at `respondBy`
        if at >= end or end <= start:
            return self.params.top
        return self.params.first + (self.params.top - self.params.first) * max(0, at - start) / (end - start)

    def top_at(self, order: Order, request: PriceRequest) -> int:
        """The minute the order's fee reaches `top`."""
        target = min(
            order["deadline"] - self.params.before_deadline, order["lastPickupAt"] - self.params.before_last_pickup
        )
        return max(target, request["respondBy"] + self.params.least_ramp)

    def schedule(self, order: Order, request: PriceRequest, cars: int, now: int) -> list[FeeStep]:
        """The fees for some of the order's cars from now: the ramp's fee at once, then its fee at each step until
        it reaches `top`. Level 1 takes one fee only."""
        fee = request["referenceFeeCents"] * cars / len(order["legs"])
        end = self.top_at(order, request)
        if self.level == 1 or now >= end:
            times = [now]
        else:  # as many steps as the schedule may have, and the last one at the top
            gap = max(self.params.least_gap, -(-(end - now) // (MAX_STEPS - 1)))
            times = [*range(now, end, gap), end]
        return [{"at": at, "feeCents": max(1, int(fee * self.share(order, request, at) + 0.5))} for at in times]
