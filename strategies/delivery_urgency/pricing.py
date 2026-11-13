"""Urgency pricing: the ladder's quote, priced per delivery option so a faster option costs more.

It builds on the ladder of strategies/price_ladder (#126), unchanged there: the same price war, outage and dealer
trust. The one change is the quotation. Instead of each option carrying its own list price times the ladder's
multiple, a request's options keep a fixed relationship: the longest option the request offers is the anchor, and
`next_day` is `1 + next_day_premium` times it while `same_day` is that times `1 + same_day_premium`. No network:
`price` takes a request and returns a price for each option, and `observe` takes the `order_won`, `order_lost` and
`ledger` events. README.md next to this file has the schedule and how to run it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from spread.types import DriverProfile, WorldMap

from strategies.price_ladder.pricing import LadderPricing as BaseLadderPricing
from strategies.price_ladder.pricing import Params as BaseLadderParams

# The delivery option kinds, from the slowest to the fastest. The longer the dealer waits, the cheaper we quote.
KINDS = ("within_3_days", "next_day", "same_day")


@dataclass(frozen=True)
class Schedule:
    """How much more a faster delivery option costs than the next slower one.

    `next_day_premium` is next day over within three days and `same_day_premium` is same day over next day; `factor`
    turns the two numbers into a multiple of the within-three-days price. They are the one place to tune the quote.
    """

    next_day_premium: float = 0.02  # next day costs this much more than within three days
    same_day_premium: float = 0.08  # same day costs this much more than next day

    def factor(self, kind: str) -> float:
        """A kind's price as a multiple of the within-three-days price."""
        rank = KINDS.index(kind)
        if rank == 0:
            return 1.0
        return (1 + self.next_day_premium) * (1 + self.same_day_premium) ** (rank - 1)


def anchor_kind(options: list[dict]) -> str:
    """The longest option the request offers: within three days when it has one, else the next longest."""
    return min((o["kind"] for o in options), key=KINDS.index)


def urgency_factor(schedule: Schedule, kind: str, anchor: str) -> float:
    """A kind's price against the anchor's: 1 for the anchor, the schedule's ratio for a faster kind."""
    return schedule.factor(kind) / schedule.factor(anchor)


def quote_price(request: dict, kind: str, factor: float, schedule: Schedule) -> float:
    """One option's price before rounding: the anchor's price (the ladder's `factor` times its list price, in whole
    cents) times the schedule's ratio for the kind. `UrgencyPricing.price` quotes the same, rounded to cents."""
    options = {o["kind"]: o for o in request["options"]}
    anchor = anchor_kind(request["options"])
    base = max(1, int(options[anchor]["listPriceCents"] * factor + 0.5))
    return base * urgency_factor(schedule, kind, anchor)


@dataclass(frozen=True)
class Params(BaseLadderParams):
    """The ladder's knobs, plus the schedule of the delivery options."""

    schedule: Schedule = field(default_factory=Schedule)


class UrgencyPricing(BaseLadderPricing):
    """The ladder, with each request's options priced by the schedule instead of their own list prices.

    The ladder's multiple of the list price applies to the anchor, the longest option the request offers, and the
    faster options are derived from it, so their ratios are exactly the schedule's. A request with a single option,
    and every quote up to level 3, is priced as the base does.
    """

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())

    def price(self, request: dict, now: int) -> dict[str, int]:
        """A price in cents for each option: the ladder's multiple of the anchor's list price, times the schedule's
        ratio for the option's kind."""
        prices = super().price(request, now)
        if len(prices) <= 1:
            return prices
        anchor = anchor_kind(request["options"])
        base, schedule = prices[anchor], self.params.schedule
        return {kind: max(1, int(base * urgency_factor(schedule, kind, anchor) + 0.5)) for kind in prices}
