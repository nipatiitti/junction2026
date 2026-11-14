"""Headroom pricing: ceiling pricing whose maximum moves with the wins and losses at it, so each world gets the
maximum that its competitor allows.

A strategy (strategies/strategy.py) built on the ceiling pricing of strategies/ceiling, unchanged there. That pricing
quotes at most 1.39 times the list price, a fixed number. At level 8 the competitor's price level is from 26% to 54%
above the list price, new in every world, so the fixed maximum is under the market in one world and over it in the
next. README.md next to this file explains the rule and what the saved weeks show.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, replace

from spread.types import DriverProfile, WorldMap

from strategies.ceiling.pricing import CeilingPricing
from strategies.ceiling.pricing import Params as CeilingParams
from strategies.pricing.model import DAY, in_hours


@dataclass(frozen=True)
class Params(CeilingParams):
    """The variables of ceiling pricing, plus how its maximum moves. `max_markup` is where the maximum starts."""

    target_win: float = 0.45  # the share of quotes the learned price settles to win: under half (README.md)
    cap_win: float = 0.5  # the share of the quotes at the maximum that the maximum settles to win
    cap_step: float = 0.012  # the step of the maximum per outcome at it, in logs: +0.6% a win, -0.6% a loss
    cap_low: float = 0.20  # the maximum never falls below the list price x (1 + cap_low) ...
    cap_high: float = 0.62  # ... and never rises above the list price x (1 + cap_high)


class HeadroomPricing(CeilingPricing):
    """Ceiling pricing with a maximum that a win at it raises and a loss at it lowers."""

    params: Params

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())
        self.cap_moves: Counter[str] = Counter()  # the week's moves of the maximum, for the summary

    def outcome(self, request_id: str, won: bool) -> None:
        """Moves the maximum on the outcome of a quote at it, then learns as ceiling pricing does. A win at the
        maximum also counts as a usual win, so the learned price follows the maximum up. The outage boost and the
        price war have their own rules, and a quote at the driver cost floor says nothing of the maximum."""
        quote = self.quotes.get(request_id)
        if quote is not None and getattr(quote, "capped", False) and not getattr(quote, "floored", False):
            war = quote.at // DAY == self.war_day and in_hours(quote.at)
            if not quote.outage and not war:
                self.move_cap(won)
                if won:
                    quote.capped = False  # the maximum has risen: this win may raise the learned price to it
        super().outcome(request_id, won)

    def move_cap(self, won: bool) -> None:
        """One step of the maximum: up after a win at it, down after a loss, so it settles where `cap_win` of the
        quotes at it win. The params are frozen, so the maximum is set in a copy."""
        p = self.params
        cap = math.log(1 + p.max_markup) + p.cap_step * ((1.0 if won else 0.0) - p.cap_win)
        cap = min(math.log(1 + p.cap_high), max(math.log(1 + p.cap_low), cap))
        self.params = replace(p, max_markup=math.exp(cap) - 1)
        self.cap_moves["up" if won else "down"] += 1

    def summary(self) -> str:
        line = super().summary()
        if not line:
            return ""
        moves = self.cap_moves
        return (
            f"{line}\nHeadroom: the maximum ends at x{1 + self.params.max_markup:.3f} of the list price, "
            f"after {moves['up']} wins and {moves['down']} losses at it"
        )
