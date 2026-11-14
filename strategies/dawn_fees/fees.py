"""Dawn fees: a fee schedule that follows the drivers' day. A gig that has a morning before its last pickup holds a
low fee through the day it is posted, and rises on a short ladder from 06:00 on its last morning, when the drivers
plan their day.

A strategy (strategies/strategy.py) built on the fee planner of strategies/fees, unchanged there: a gig without such
a morning, a late car and a level 1 gig get that planner's schedule. `dawn_plan` is a pure function of the gig's facts
and the time; README.md next to this file explains the schedule and what the saved weeks show.
"""

from __future__ import annotations

from dataclasses import dataclass

from spread.types import DriverProfile, FeeStep, Order, PriceRequest, WorldMap

from strategies.fees import FeePlanner, Gig
from strategies.fees import plan as urgent_plan
from strategies.fees.schedule import DROP_SPAN, DROP_STEP, before_night, ceiling, margin, valid, worth

HOUR, DAY = 60, 24 * 60


@dataclass(frozen=True)
class Params:
    """The variables of the dawn schedule. Each fee is a multiple of the gig's typical fee."""

    open: float = 0.9  # the opening fee
    hold: float = 1.0  # the fee after `patience`, held until the last morning
    patience: int = 2 * HOUR  # the opening fee stays this long
    quiet_from: int = 22 * HOUR  # no raise on the posting day from this hour: few drivers still look
    evening_at: int = 20 * HOUR  # the evening before the last morning: the hold fee at the latest, or `tight`
    tight: float = 1.4  # that evening's fee when the top is due before dawn: some drivers must travel the night before
    dawn_at: int = 6 * HOUR  # when the drivers plan their day
    dawn: float = 1.15  # the fee at dawn on the last morning
    reach: int = 3 * HOUR  # a driver who books at dawn needs this long to get to the car
    step: int = HOUR  # the ladder from the dawn fee to the top fee rises this often
    top: float = 2.5  # the top fee, before the ceiling of strategies/fees cuts it
    # A gig with no morning to wait for: instead of opening near its top, it climbs to it on a short ladder.
    sprint: int = 2 * HOUR  # the ladder reaches the top this long after the post at the latest; 0 turns it off
    sprint_open: float = 1.1  # where that ladder opens
    sprint_step: int = 15  # how often it rises


class DawnFeePlanner(FeePlanner):
    """The fee planner of strategies/fees with the dawn schedule for every gig that has a morning to wait for."""

    params: Params  # type: ignore[assignment]

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level)
        self.params = params or Params()
        self.counts = {"dawn": 0, "urgent": 0}  # the week's schedules, for the summary

    def schedule(self, order: Order, request: PriceRequest, cars: int, now: int) -> list[FeeStep]:
        gig = self.gig(order, request, cars, now)
        self.counts["dawn" if last_dawn(now, gig.last_pickup_at, self.params) is not None else "urgent"] += 1
        return dawn_plan(now, gig, self.level, self.params)

    def after_drop(
        self, order: Order, request: PriceRequest, cars: int, now: int, dropped_fee: int
    ) -> list[FeeStep] | None:
        """As in strategies/fees: with little time left the gig steps up from the dropped fee, on the dawn schedule
        when a morning is still to come."""
        gig = self.gig(order, request, cars, now)
        if before_night(gig.last_pickup_at - margin(gig), now) - now >= DROP_SPAN:
            return None
        return dawn_plan(now, gig, self.level, self.params, floor=min(ceiling(gig), dropped_fee * (1 + DROP_STEP)))

    def summary(self) -> str:
        if not sum(self.counts.values()):
            return ""
        return f"Dawn fees: {self.counts['dawn']} schedules with a dawn ladder, {self.counts['urgent']} without"


def last_dawn(now: int, last_pickup_at: int, p: Params) -> int | None:
    """The last dawn from which a driver can still reach the car before `last_pickup_at`, or None when it is not
    after `now`: the gig then has no morning to wait for."""
    dawn = (last_pickup_at - p.reach - p.dawn_at) // DAY * DAY + p.dawn_at
    return dawn if dawn > now else None


def dawn_plan(now: int, gig: Gig, level: int, p: Params, floor: float = 0) -> list[FeeStep]:
    """The fee schedule from `now`. `floor` is the least opening fee, after a drop.

    1. It opens at `open` and rises once, to `hold`, after `patience`.
    2. It holds that fee until the last morning. When the top is due before that dawn, it rises to `tight` the
       evening before, for the drivers who must set out then.
    3. From dawn it climbs from `dawn` to the top in even ratios, one step each `step`, and reaches the top a travel
       margin before the last pickup, an hour after dawn at the earliest.
    No step before the top goes above the order's price, as in strategies/fees."""
    dawn = last_dawn(now, gig.last_pickup_at, p)
    if level < 2:
        return urgent_plan(now, gig, level, floor)
    if dawn is None:
        return sprint_plan(now, gig, level, p, floor)
    top = max(1.0, min(max(gig.typical * p.top, floor), ceiling(gig)))
    opening = min(max(gig.typical * p.open, floor), top)
    cap = max(opening, min(top, worth(gig)))

    def fee(multiple: float) -> float:
        return min(max(gig.typical * multiple, opening), cap)

    steps = [(now, opening)]
    held = now + p.patience
    if held // DAY == now // DAY and held % DAY < p.quiet_from and held < dawn:
        steps.append((held, fee(p.hold)))
    top_due = gig.last_pickup_at - margin(gig)
    tight = top_due < dawn
    evening = dawn - p.dawn_at - DAY + p.evening_at
    if evening > now:
        steps.append((evening, fee(p.tight if tight else p.hold)))
    top_due = max(dawn + HOUR, min(top_due, gig.last_pickup_at - p.reach))
    start = fee(max(p.dawn, p.tight) if tight else p.dawn)
    rungs = max(1, round((top_due - dawn) / p.step))
    for k in range(rungs):
        steps.append((dawn + (top_due - dawn) * k // rungs, min(cap, start * (top / start) ** (k / rungs))))
    steps.append((top_due, top))
    return valid(steps, level)


def sprint_plan(now: int, gig: Gig, level: int, p: Params, floor: float = 0) -> list[FeeStep]:
    """The schedule of a gig with no morning to wait for: a car to collect today, or a gig that came back after a
    drop on its last morning. The schedule of strategies/fees opens such a gig close to its top fee, and a driver
    takes it within minutes: it never learns what a lower fee would have found. This one opens at `sprint_open` and
    climbs to the top in even ratios, one step each `sprint_step`, by `reach` before the last pickup and `sprint`
    after the post at the latest. With less than `reach` left, and for a late car, the schedule is that of
    strategies/fees: the top at once."""
    top_due = min(gig.last_pickup_at - p.reach, now + p.sprint)
    if p.sprint <= 0 or top_due - now < p.sprint_step:
        return urgent_plan(now, gig, level, floor)
    top = max(1.0, min(max(gig.typical * p.top, floor), ceiling(gig)))
    start = min(max(gig.typical * p.sprint_open, floor), top)
    cap = max(start, min(top, worth(gig)))
    rungs = max(1, (top_due - now) // p.sprint_step)
    steps = [(now + (top_due - now) * k // rungs, min(cap, start * (top / start) ** (k / rungs))) for k in range(rungs)]
    return valid([*steps, (top_due, top)], level)
