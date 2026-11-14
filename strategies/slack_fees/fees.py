"""Fee schedules that wait when the car can wait: a gig with a day or more before its last pickup holds its early fee
until the pickup day, instead of climbing 3 hours after it was posted.

A strategy (strategies/strategy.py) built on the fee planner of strategies/fees, unchanged there. Its plan opens at
0.9 x the typical fee, raises 10% of the way to the top an hour later, 30% of the way 3 hours after the post, and
reaches the top a travel margin before `lastPickupAt`. On the saved ceiling weeks, gigs posted 16 to 50 hours before
their last pickup mostly booked within minutes, at the opening fee or the first raise, but 20% to 40% of them paid the
second raise, about 1.38 x the typical fee, though the car had most of a day left. Here, with at least `patient_span`
before the top fee is due, every raise after the first hour waits until `hold_lead` before the top: a driver who plans
the pickup day still sees the early fee in the evening, and the fee climbs on the pickup day's morning. A bundle's
fees and the fees after a drop or a deadline warning are planned as before. README.md next to this file has the
numbers.
"""

from __future__ import annotations

from collections import Counter

from spread.types import DriverProfile, FeeStep, Order, PriceRequest, WorldMap

from strategies.fees import FeePlanner
from strategies.fees.schedule import HOUR, before_night, margin, plan, valid
from strategies.strategy import NoParams

PATIENT_SPAN = 16 * HOUR  # with this long before the top fee is due, the schedule waits
HOLD_LEAD = 3 * HOUR  # the raises after the first hour come this long before the top fee
FIRST_RAISE = 90  # minutes: a step due this soon after the post is the first raise, which stays as it is


def patient(now: int, steps: list[FeeStep], top_at: int, level: int) -> list[FeeStep]:
    """The schedule with every raise between the first hour and the top fee moved to `HOLD_LEAD` before the top,
    when that is later; at night, to 22:00 the evening before, as every step of the plan."""
    hold_at = before_night(top_at - HOLD_LEAD, now)
    moved = [
        (max(step["at"], hold_at) if now + FIRST_RAISE < step["at"] < top_at else step["at"], step["feeCents"])
        for step in steps
    ]
    return valid(moved, level)


class SlackFeePlanner(FeePlanner):
    """The fee planner, holding the early fee of a gig that has a day or more to wait."""

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: NoParams | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params)
        self.counts: Counter[str] = Counter()

    def schedule(self, order: Order, request: PriceRequest, cars: int, now: int) -> list[FeeStep]:
        """The base plan, patient when the top fee is at least `PATIENT_SPAN` away."""
        gig = self.gig(order, request, cars, now)
        steps = plan(now, gig, self.level)
        if self.level == 1 or len(steps) < 3:
            return steps
        top_at = before_night(gig.last_pickup_at - margin(gig), now)
        self.counts["planned"] += 1
        if top_at - now < PATIENT_SPAN:
            return steps
        self.counts["patient"] += 1
        return patient(now, steps, top_at, self.level)

    def summary(self) -> str:
        """How many gigs held their early fee."""
        c = self.counts
        if not c["planned"]:
            return ""
        return f"Slack fees: {c['patient']} of {c['planned']} schedules held their early fee for the pickup day"
