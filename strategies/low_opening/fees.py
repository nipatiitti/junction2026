"""Patient fees that open low: the first post of a car that can wait opens under the plan's opening fee, and reaches it
within `ramp` minutes; from there the schedule is slack fees' (strategies/slack_fees), unchanged there.

A strategy (strategies/strategy.py) built on SlackFeePlanner. The plan of strategies/fees opens every gig at 0.9 x the
typical fee. On the three slack-fees weeks of the bench in #188, 749 of the 816 one-car orders were posted 19 hours or
more before their last pickup, and 417 of those booked at the opening fee within 30 minutes: their drivers took the
first fee they saw, and some would have taken less. No saved week opened a gig under 0.85 x the typical fee, so how
much less is unknown. Here the first post of an order whose top fee is `PATIENT_SPAN` or more away opens at `low` x
the typical fee and rises to the plan's opening fee `ramp` minutes later; a driver who would have booked at the
opening fee still finds it then, and every later step is slack fees'. A re-post, a reprice after a deadline warning,
a bundle and a gig with less time are planned as before. README.md next to this file has the numbers.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from spread.types import DriverProfile, FeeStep, Order, PriceRequest, WorldMap

from strategies.fees.schedule import before_night, margin, valid
from strategies.slack_fees import SlackFeePlanner
from strategies.slack_fees.fees import PATIENT_SPAN


@dataclass(frozen=True)
class Params:
    """The low opening of a patient gig's first post."""

    low: float = 0.8  # the opening fee over the typical fee (the plan opens at 0.9)
    ramp: int = 30  # minutes from the post until the fee reaches the plan's opening fee


class LowOpeningPlanner(SlackFeePlanner):
    """Slack fees, with the first post of a patient gig opening at `low` x the typical fee."""

    params: Params  # type: ignore[assignment]

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level)
        self.params = params or Params()  # type: ignore[assignment]
        self.posted: set[str] = set()  # the orders whose first post has been planned
        self.low: Counter[str] = Counter()

    def schedule(self, order: Order, request: PriceRequest, cars: int, now: int) -> list[FeeStep]:
        """Slack fees' schedule; for the first post of a patient order, opened at `low` and ramped to its opening."""
        steps = super().schedule(order, request, cars, now)
        first = order["id"] not in self.posted
        self.posted.add(order["id"])
        if not first or self.level == 1 or len(steps) < 2:
            return steps
        gig = self.gig(order, request, cars, now)
        if before_night(gig.last_pickup_at - margin(gig), now) - now < PATIENT_SPAN:
            return steps
        opening, low = steps[0]["feeCents"], gig.typical * self.params.low
        if low >= opening or steps[1]["at"] <= now + self.params.ramp:
            return steps
        self.low["opened low"] += 1
        self.low["cents under"] += opening - int(low + 0.5)
        ramped = [(now, low), (now + self.params.ramp, opening)] + [(s["at"], s["feeCents"]) for s in steps[1:]]
        return valid(ramped, self.level)

    def summary(self) -> str:
        """Slack fees' line, plus the first posts that opened low."""
        line = super().summary()
        n = self.low["opened low"]
        if not line or not n:
            return line
        return (
            f"{line}; {n} first posts opened at x{self.params.low:.2f} the typical fee, "
            f"€{self.low['cents under'] / n / 100:.2f} under the plan's opening on average"
        )
