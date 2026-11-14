"""The fees of the baseline with fee tiers: a rise from a low first fee, back to the first fee some hours before
the last on-time pickup, and the baseline's steep fees from the order's deadline warning. The tier depends on who may
drive the car.

No network: `schedule` takes an order, its request and the minute, as `BaselineFees.schedule` does. README.md next
to this file has the rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

from spread.types import DeskEvent, DriverProfile, FeeStep, Order, PriceRequest, WorldMap

from strategies.baseline.fees import steep
from strategies.notes import read_note
from strategies.strategy import Strategy

MAX_STEPS = 48  # the most steps a fee schedule may have


class Tier(NamedTuple):
    """The fees of one kind of gig, as shares of the request's typical fee."""

    first: float  # when the order is won
    usual: float  # where the first rise ends
    top: float  # when the gig looks like nobody will take it


ANYONE = Tier(1.0, 1.3, 1.3)
MANUAL = Tier(1.1, 1.3, 1.3)
EXPERIENCED = Tier(1.2, 1.3, 1.3)


@dataclass(frozen=True)
class Params:
    """The knobs of the fees: a tier for each kind of gig, and the minutes of the rise."""

    anyone: Tier = ANYONE  # a gig that every driver may take
    manual: Tier = MANUAL  # a manual car: drivers with a manual licence only
    experienced: Tier = EXPERIENCED  # a premium car: experienced drivers only
    give_up: int = 120  # a gig still open this many minutes after the order is won goes to its top fee
    give_up_share: float = 0.5  # or after this share of the time to the last on-time pickup, when that is sooner
    rise_share: float = 0.5  # the rise from `first` to `usual` takes this share of the time to the top fee
    back_before_last_pickup: int = 4 * 60  # the fee is `first` again this long before the last on-time pickup
    least_gap: int = 5  # the least minutes between two steps of a schedule


class TierFees(Strategy[Params]):
    """One line for each order, as a share of its typical fee: `first` when the order is won, rising evenly to
    `usual`, and `top` once the gig looks like nobody will take it. That is `give_up` minutes after the win, or
    `give_up_share` of the way to the order's last on-time pickup (`lastPickupAt`) when that comes first. From
    `back_before_last_pickup` minutes before that last on-time pickup the fee is `first` again.

    From the order's deadline warning on, its fees are the baseline's steep ones instead, whatever the minute: 1.5
    times the typical fee at once, then a quarter of it more every half hour, up to 2.5 times.

    The tier is by who may drive the car: `experienced` for a premium car, `manual` for a manual one, and `anyone`
    otherwise. Before the warning the fee depends on the minute only, so a gig posted again goes on at the fee the
    line has reached. A fee schedule cannot fall, so the desk reprices the open gigs at `back_at`.
    """

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())
        self.urgent: set[str] = set()  # the orders whose deadline warning has come
        self.manual_orders: set[str] = set()  # the orders with a car that a visit found to be manual

    def observe(self, event: DeskEvent) -> None:
        """Learns the deadline warnings, and the cars that a failed visit showed to be manual."""
        if event["kind"] == "deadline_close":
            self.urgent.add(event["orderId"])
        elif event["kind"] == "visit_failed" and event["reason"] == "licence":
            self.manual_orders.add(event["orderId"])

    def warned(self, order_id: str) -> None:
        """The order's deadline warning has come: its further schedules are steep."""
        self.urgent.add(order_id)

    def manual(self, order: Order, request: PriceRequest) -> bool:
        """Whether the order has a manual car: its note says so, or a visit failed for the licence."""
        note = request["note"]
        return order["id"] in self.manual_orders or read_note(note and note["text"], request["arrivedAt"]).manual

    def tier(self, order: Order, request: PriceRequest) -> Tier:
        """The order's tier. A premium manual car is in the experienced one."""
        if any(leg["car"]["premium"] for leg in order["legs"]):
            return self.params.experienced
        return self.params.manual if self.manual(order, request) else self.params.anyone

    def top_at(self, order: Order, request: PriceRequest) -> int:
        """The minute the order's gig goes to its top fee when no driver has taken it."""
        won = request["respondBy"]
        to_last_pickup = max(0, order["lastPickupAt"] - won)
        return won + min(self.params.give_up, int(to_last_pickup * self.params.give_up_share))

    def back_at(self, order: Order) -> int:
        """The minute the order's fee is `first` again."""
        return order["lastPickupAt"] - self.params.back_before_last_pickup

    def share(self, order: Order, request: PriceRequest, at: int) -> float:
        """The fee at the minute `at` of an order without a deadline warning, as a share of the typical fee."""
        tier, won, top_at = self.tier(order, request), request["respondBy"], self.top_at(order, request)
        if at >= self.back_at(order):
            return tier.first
        if at >= top_at:
            return tier.top
        rise = (top_at - won) * self.params.rise_share
        return tier.first + (tier.usual - tier.first) * min(1.0, max(0, at - won) / rise)

    def schedule(self, order: Order, request: PriceRequest, cars: int, now: int) -> list[FeeStep]:
        """The fees for some of the order's cars from now: the baseline's steep fees once the deadline warning has
        come, and otherwise the line's fee at once, then its fee at each step until the top. The fall at `back_at`
        is not in it: a schedule cannot fall. Level 1 takes one fee only."""
        fee = request["referenceFeeCents"] * cars / len(order["legs"])
        if order["id"] in self.urgent:
            return steep(now, fee, self.level)
        top_at = self.top_at(order, request)
        if self.level == 1 or now >= top_at:
            times = [now]
        else:  # as many steps as the schedule may have, and the last one at the top
            gap = max(self.params.least_gap, -(-(top_at - now) // (MAX_STEPS - 1)))
            times = [*range(now, top_at, gap), top_at]
        steps: list[FeeStep] = []
        for at in times:
            cents = max(1, int(fee * self.share(order, request, at) + 0.5))
            if not steps or cents > steps[-1]["feeCents"]:  # only the minutes where the fee rises
                steps.append({"at": at, "feeCents": cents})
        return steps
