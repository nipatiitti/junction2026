"""Ladder pricing: the price of a quote as one shared multiple of the list price, walked down when we lose a quote
and up when we win one, inside a clamped range.

It builds on the adaptive quoting of strategies/pricing (#13), unchanged there: the same price war, outage and
dealer trust, but a different rule for the world's multiplier. The adaptive model tracks a quantile of the winning
price and settles where half of the quotes win; the ladder has a position in a range and every outcome moves it. No
network: `price` takes a request and returns a price for each option, and `observe` takes the `order_won`,
`order_lost` and `ledger` events. README.md next to this file has the ladder and its bench.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from spread.types import DriverProfile, WorldMap

from strategies.pricing.model import DAY, Outcome, PricingModel, in_hours
from strategies.pricing.model import Params as PricingParams


@dataclass(frozen=True)
class Params(PricingParams):
    """The knobs of the ladder, next to those of the adaptive quoting (`strategies/pricing`)."""

    floor: float = 1.0  # the lowest multiple of the list price the ladder quotes
    ceiling: float = 1.5  # the highest
    start: float = 1.5  # where the ladder starts: at the top of its range
    win_step: float = 0.01  # the price rises by this share after a win
    loss_step: float = 0.03  # and falls by this share after a loss


class LadderPricing(PricingModel):
    """The adaptive quoting with a ladder for the world's multiplier, instead of a learned quantile.

    The ladder's position is a multiple of the list price, shared by every request: each request gets essentially
    one final quote, so a per-lane state would only add noise. It starts at the top of its range, falls by
    `loss_step` after a quote we lost and rises by `win_step` after one we won, and never leaves [`floor`,
    `ceiling`]. The steps are unequal, so it settles where the wins balance the losses:
    `loss_step / (win_step + loss_step)` of the quotes win, 75% with the default steps. The price war, the outage
    and dealer trust work as in the adaptive model; the per-lane offsets do not, since the point is one position.
    """

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())
        self.log_m = math.log(self.params.start)  # the ladder starts at the top of its range
        self.quoted = 0  # the quotes we sent
        self.won = 0  # the quotes we won
        self.at_floor = 0  # the quotes sent with the ladder at the bottom of its range
        self.at_ceiling = 0  # and at the top

    def price(self, request: dict, now: int) -> dict[str, int]:
        """A price in cents for each option, and a count of the quotes at either end of the ladder's range."""
        prices = super().price(request, now)
        if self.level > 3:
            self.quoted += 1
            m = math.exp(self.log_m)
            if m <= self.params.floor * 1.001:
                self.at_floor += 1
            elif m >= self.params.ceiling * 0.999:
                self.at_ceiling += 1
        return prices

    def outcome(self, request_id: str, won: bool) -> None:
        """The ladder's step after an outcome: down on a loss, up on a win, in logs so that the price moves by a
        share of itself. No offsets: one shared position for the whole week."""
        quote = self.quotes.pop(request_id, None)
        if quote is None:
            return
        if won:
            self.won += 1
        step = math.log(1 + self.params.win_step) if won else math.log(1 - self.params.loss_step)
        day = quote.at // DAY
        if quote.outage:  # the outage boost keeps learning from the error, as in the adaptive model
            error = (1.0 if won else 0.0) - self.params.target_win
            self.outage_log = min(math.log(1.5), max(0.0, self.outage_log + 2 * self.params.key_step * error))
            return
        if day == self.war_day and in_hours(quote.at):
            if not self.params.war_decline and not self.war_over:  # follow the war, but leave the lanes alone
                self.apply([("", step)])
            return
        if in_hours(quote.at):
            self.day_open.setdefault(day, self.log_m)
        updates = [("", step)]
        self.apply(updates)
        self.seen += 1
        if not in_hours(quote.at):
            return
        outcomes = self.today.setdefault(day, [])
        outcomes.append(Outcome(won, quote.pickup, updates))
        # One outage and one price war a week, never on the same day.
        if self.level >= 6 and self.outage is None and day != self.war_day:
            self.detect_outage(day, outcomes)
        if self.level >= 8 and day > 0 and self.war_day is None and (self.outage is None or self.outage[0] != day):
            self.detect_war(day, outcomes)

    def summary(self) -> str:
        """One line about the ladder at the end of the week."""
        won = f"{self.won / self.quoted:.0%}" if self.quoted else "-"
        return (
            f"Ladder: {math.exp(self.log_m):.2f} x list, {self.quoted} quotes, {won} won, "
            f"{self.at_floor} at the floor, {self.at_ceiling} at the top"
        )
