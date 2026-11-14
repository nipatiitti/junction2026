"""Streak-scaled ladder pricing: the price of a quote as one shared multiple of the list price, walked down when we
lose a quote and up when we win one, with a step that grows with the run of consecutive outcomes.

It builds on the ladder of strategies/price_ladder (#126), which builds on the adaptive quoting of
strategies/pricing (#13): the same price war, outage and dealer trust, but a different step. The price ladder moves by
a fixed share after every outcome, so it reacts at the same speed whether it is one quote out of step or ten. Here the
step is `clamp(streak, -streak_cap, streak_cap) x streak_step`, so a run of the same outcome moves the price further
and the ladder finds the market faster after a sudden change. No network: `price` takes a request and returns a price
for each option, and `observe` takes the `order_won`, `order_lost` and `ledger` events. README.md next to this file has
the step and its bench.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from spread.types import DriverProfile, WorldMap

from strategies.price_ladder.pricing import LadderPricing
from strategies.price_ladder.pricing import Params as LadderParams
from strategies.pricing.model import DAY, Outcome, in_hours


@dataclass(frozen=True)
class Params(LadderParams):
    """The streak ladder's knobs: the price-ladder range and war, plus the streak-scaled step."""

    streak_step: float = 0.02  # log step per consecutive outcome: the first win moves it, the second twice as far
    streak_cap: int = 5  # a run of wins or losses stops growing the step past this many


class StreakLadderPricing(LadderPricing):
    """The price ladder with a step that scales with the run of consecutive wins or losses.

    One position on the list price for the whole week, as in strategies/price_ladder, inside [`floor`, `ceiling`] and
    starting at the top of its range. A win raises it and a loss lowers it, but the step is
    `clamp(streak, -streak_cap, streak_cap) x streak_step`, where `streak` is the current run of consecutive wins
    (positive) or losses (negative): the first step is `streak_step`, the second in a row twice that, up to the cap. A
    change of direction resets the run to one. The price war, the outage and dealer trust work as in the parent.
    """

    params: Params

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())
        self.streak = 0  # the run of consecutive wins (positive) or losses (negative)
        self.best = 0  # the longest run of wins this week
        self.worst = 0  # and the longest run of losses, as a negative number

    def bump(self, won: bool) -> int:
        """The run after this outcome: a win grows a winning run and a loss grows a losing one, and either resets the
        other to one. The count is capped at `streak_cap`, so one long run cannot move the price by the whole range."""
        if won:
            self.streak = self.streak + 1 if self.streak > 0 else 1
        else:
            self.streak = self.streak - 1 if self.streak < 0 else -1
        self.best, self.worst = max(self.best, self.streak), min(self.worst, self.streak)
        cap = self.params.streak_cap
        return max(-cap, min(cap, self.streak))

    def outcome(self, request_id: str, won: bool) -> None:
        """The ladder's step after an outcome: down on a loss, up on a win, in logs so that the price moves by a share
        of itself, with the step scaled by the run of consecutive outcomes. No offsets: one shared position for the
        whole week, as in the price ladder."""
        quote = self.quotes.pop(request_id, None)
        if quote is None:
            return
        if won:
            self.won += 1
        step = self.bump(won) * self.params.streak_step
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
        """One line about the streak ladder at the end of the week, with its longest runs of wins and losses."""
        won = f"{self.won / self.quoted:.0%}" if self.quoted else "-"
        return (
            f"Streak ladder: {math.exp(self.log_m):.2f} x list, {self.quoted} quotes, {won} won, "
            f"{self.at_floor} at the floor, {self.at_ceiling} at the top, "
            f"longest runs +{self.best}/-{abs(self.worst)}"
        )
