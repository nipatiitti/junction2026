"""Ladder pricing per dealer with a streak-scaled step: the price of a quote as a multiple of the list price, with one
ladder position and one run of consecutive wins and losses for each dealer.

It builds on the dealer ladder of strategies/dealer_ladder (#193), which builds on the ladder of
strategies/price_ladder (#126): the same clamped range, the same price war, outage and dealer trust, and one position
per dealer. The change is the step. The dealer ladder moves a dealer's position by a fixed share after every outcome;
here the step is `clamp(streak, -streak_cap, streak_cap)` times a share that differs by outcome — `win_rate` up on a
win and `loss_rate` down on a loss — where `streak` is the dealer's own run of consecutive wins and losses. So a run
against one dealer moves that dealer's price further, and a loss moves it further than a win. No network: `price` takes
a request and returns a price for each option, and `observe` takes the `order_won`, `order_lost` and `ledger` events.
README.md next to this file has the model and how to run it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from spread.types import DriverProfile, WorldMap

from strategies.dealer_ladder.pricing import DealerLadderPricing
from strategies.dealer_ladder.pricing import Params as DealerParams
from strategies.pricing.model import DAY, Outcome, in_hours


@dataclass(frozen=True)
class Params(DealerParams):
    """The dealer ladder's knobs — the price-ladder range and war — plus the two streak-scaled step shares."""

    win_rate: float = 0.009  # share per consecutive win: the first win moves the dealer, the second twice as far
    loss_rate: float = 0.02  # share per consecutive loss, which moves the price further than a win
    streak_cap: int = 5  # a dealer's run of wins or losses stops growing the step past this many


class DealerStreakPricing(DealerLadderPricing):
    """The price ladder with one position per dealer and a step that scales with that dealer's run of outcomes.

    Each dealer has its own position on the list price, inside [`floor`, `ceiling`] and starting at the top of its
    range, and its own run of consecutive wins (positive) or losses (negative). A win raises that dealer's position by
    `clamp(streak, +/-streak_cap) x win_rate` and a loss lowers it by `clamp(streak, +/-streak_cap) x loss_rate`, so a
    run of the same outcome moves that dealer's price further and a loss moves it further than a win of the same run. A
    change of direction resets that dealer's run to one; the other dealers are not moved. The world ladder still moves
    on every outcome, so the price war and outage detectors stay the dealer ladder's, and the dealer trust works as
    before.
    """

    params: Params

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())
        self.streaks: dict[str, int] = {}  # dealer id -> the dealer's run of consecutive wins (positive) or losses
        self.best = 0  # the longest run of wins any dealer had this week
        self.worst = 0  # and the longest run of losses, as a negative number

    def bump(self, key: str, won: bool) -> int:
        """A dealer's run after this outcome: a win grows a winning run and a loss grows a losing one, and either
        resets the other to one for that dealer. The count is capped at `streak_cap`, so one long run cannot move the
        dealer's price by the whole range."""
        streak = self.streaks.get(key, 0)
        if won:
            streak = streak + 1 if streak > 0 else 1
        else:
            streak = streak - 1 if streak < 0 else -1
        self.streaks[key] = streak
        self.best, self.worst = max(self.best, streak), min(self.worst, streak)
        cap = self.params.streak_cap
        return max(-cap, min(cap, streak))

    def outcome(self, request_id: str, won: bool) -> None:
        """The dealer's ladder step after an outcome: down on a loss, up on a win, in logs so that the price moves by
        a share of itself, with the step scaled by the dealer's own run of consecutive outcomes and a share that
        differs by outcome. The world ladder moves too, so the war and outage detectors stay the parent's; only the
        dealer's ladder prices."""
        quote = self.quotes.pop(request_id, None)
        if quote is None:
            return
        if won:
            self.won += 1
        key = quote.key
        run = abs(self.bump(key, won))  # the dealer's run, capped at streak_cap
        share = math.log(1 + self.params.win_rate) if won else math.log(1 - self.params.loss_rate)
        step = run * share
        day = quote.at // DAY
        if quote.outage:  # the outage boost keeps learning from the error, as in the adaptive model
            error = (1.0 if won else 0.0) - self.params.target_win
            self.outage_log = min(math.log(1.5), max(0.0, self.outage_log + 2 * self.params.key_step * error))
            return
        if day == self.war_day and in_hours(quote.at):
            if not self.params.war_decline and not self.war_over:  # follow the war, in the dealer and the world
                self.apply([("", step), (key, step)])
            return
        if in_hours(quote.at):
            self.day_open.setdefault(day, self.log_m)
        updates = [("", step), (key, step)]
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
        """One line about the dealers' ladders at the end of the week, with the longest runs of wins and losses."""
        won = f"{self.won / self.quoted:.0%}" if self.quoted else "-"
        if not self.log_ms:
            return f"Dealer streak: {self.quoted} quotes, {won} won, no dealer moved"
        values = [math.exp(v) for v in self.log_ms.values()]
        floor = sum(1 for v in values if v <= self.params.floor * 1.001)
        ceiling = sum(1 for v in values if v >= self.params.ceiling * 0.999)
        return (
            f"Dealer streak: {len(values)} dealers, {self.quoted} quotes, {won} won, "
            f"{min(values):.2f} to {max(values):.2f} x list, {floor} at the floor, {ceiling} at the top, "
            f"longest runs +{self.best}/-{abs(self.worst)}"
        )
