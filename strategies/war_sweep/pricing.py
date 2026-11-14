"""Headroom pricing that spots the unannounced price war intraday and sweeps its profitable orders at a thin cap.

A strategy (strategies/strategy.py) built on strategies/headroom, unchanged there. A cluster of losses of quotes not
held at the driver-cost floor, together with a fall in win share from the earlier weekdays, flags the war. Until 18:00
quotes are capped at the list price times one plus `war_markup`, without the usual trust or outage lift, and a request
whose driver-cost floor is over that cap is declined as usual. The war day's moves of the learned world, lane and
dealer offsets and moving maximum are restored, so the next day does not inherit the war's prices. README.md next to
this file explains the detector and its false positives.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, replace

from spread.types import DriverProfile, WorldMap

from strategies.headroom.pricing import HeadroomPricing
from strategies.headroom.pricing import Params as HeadroomParams
from strategies.pricing.model import DAY, WORK_TO, Outcome, in_hours

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


@dataclass(frozen=True)
class Params(HeadroomParams):
    """Headroom pricing's variables, plus the war detector and its temporary maximum."""

    war_markup: float = 0.10  # during the war, quote at most the list price x (1 + war_markup)
    war_window: int = 12  # the detector looks at this many recent eligible outcomes of the day
    war_losses: int = 8  # at least this many of those outcomes must be losses
    war_share_drop: float = 0.20  # today's win share must be this far under the earlier weekdays'
    war_history: int = 30  # eligible outcomes needed from the earlier weekdays before a war can be flagged


@dataclass
class DayState:
    """The learned prices before a day's first working-hours outcome, restored if that day is the war."""

    log_m: float
    offset: dict[str, float]
    max_markup: float
    cap_moves: Counter[str]


class WarSweepPricing(HeadroomPricing):
    """Headroom pricing with an intraday loss detector, a temporary low maximum and a full war-day restore."""

    params: Params

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())
        self.samples: dict[int, list[bool]] = {}  # weekday -> outcomes of quotes not at the cost floor or in an outage
        self.day_states: dict[int, DayState] = {}
        self.detected: tuple[int, float, float, int] | None = None  # day, today's share, earlier share, recent losses
        self.war_quotes = 0

    # --- prices -------------------------------------------------------------------------------

    def ceiling(self, request: dict, now: int) -> float:
        """The war cap while the war is on, otherwise headroom's lifted maximum. Admission uses this same ceiling."""
        self.end_war(now)
        if self.in_war(now) and not self.war_over:
            return 1 + self.params.war_markup
        return super().ceiling(request, now)

    def uplift(self, request: dict, now: int) -> float:
        """No trust or outage lift above the war cap; the usual lift everywhere else."""
        if self.in_war(now) and not self.war_over:
            return 1.0
        return super().uplift(request, now)

    def price(self, request: dict, now: int, cost: float = 0, kinds: Iterable[str] | None = None) -> dict[str, int]:
        """Headroom's price with its maximum temporarily replaced by the war cap. Its driver-cost floor still wins
        over the cap: an option whose floor is dearer gets no price, exactly as at the usual maximum."""
        self.end_war(now)
        if not self.in_war(now) or self.war_over:
            return super().price(request, now, cost, kinds)
        usual = self.params
        self.params = replace(usual, max_markup=usual.war_markup, war_decline=False)
        try:
            prices = super().price(request, now, cost, kinds)
        finally:
            self.params = usual
        self.war_quotes += bool(prices)
        return prices

    # --- detection and restore ----------------------------------------------------------------

    def outcome(self, request_id: str, won: bool) -> None:
        """Keeps the detector's outcomes and the day's opening learned state around headroom's usual learning. Once
        the war is flagged, every outcome of that working day is followed by a restore, including its earlier steps."""
        quote = self.quotes.get(request_id)
        day = -1
        if quote is not None and in_hours(quote.at) and quote.at // DAY % 7 < 5:
            day = quote.at // DAY
            self.day_states.setdefault(
                day, DayState(self.log_m, dict(self.offset), self.params.max_markup, Counter(self.cap_moves))
            )
            eligible = not quote.outage and not getattr(quote, "floored", False) and self.war_day is None
            if eligible:
                self.samples.setdefault(day, []).append(won)
        super().outcome(request_id, won)
        if day >= 0 and self.war_day == day:
            self.restore(day)

    def detect_war(self, day: int, outcomes: list[Outcome]) -> None:
        """Flags a weekday war when the last `war_window` eligible outcomes contain `war_losses` losses and today's
        eligible win share is `war_share_drop` under the pooled earlier weekdays. The base caller already excludes
        Monday, other levels and an outage day; `outcomes` is headroom's full day, while the signal excludes floors."""
        if day % 7 >= 5:
            return
        p = self.params
        today = self.samples.get(day, [])
        recent = today[-p.war_window :]
        losses = sum(not won for won in recent)
        if len(recent) < p.war_window or losses < p.war_losses:
            return
        history = [won for earlier, samples in self.samples.items() if earlier < day for won in samples]
        if len(history) < p.war_history:
            return
        share, earlier_share = sum(today) / len(today), sum(history) / len(history)
        if share > earlier_share - p.war_share_drop:
            return
        self.war_day = day
        self.detected = day, share, earlier_share, losses

    def restore(self, day: int) -> None:
        """Takes back all of the day's learning: the world, pickup, delivery and dealer offsets, and the moving
        maximum. Repeating this after war outcomes keeps them from teaching the normal price a second time."""
        state = self.day_states.get(day)
        if state is None:
            return
        self.log_m = state.log_m
        self.offset = dict(state.offset)
        self.params = replace(self.params, max_markup=state.max_markup)
        self.cap_moves = Counter(state.cap_moves)

    def end_war(self, now: int) -> None:
        """At or after 18:00 restores every learned value as well as the base's world multiplier, then resumes
        headroom pricing. The same rule handles the next request after the day has ended."""
        if self.war_day is not None and not self.war_over and now >= self.war_day * DAY + WORK_TO:
            self.restore(self.war_day)
        super().end_war(now)

    def summary(self) -> str:
        line = super().summary()
        if not line or self.detected is None:
            return line
        day, share, earlier, losses = self.detected
        return (
            f"{line}\nWar sweep: {WEEKDAYS[day % 7]} flagged after {losses} losses in the last "
            f"{self.params.war_window} eligible outcomes, win share {share:.0%} against {earlier:.0%} earlier; "
            f"{self.war_quotes} capped quotes, the day's learning restored"
        )
