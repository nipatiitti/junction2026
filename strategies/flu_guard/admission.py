"""Flu-guard admission: keeps Friday from filling up while the week's flu day has not shown, and promises no car for
today on the day it shows.

A strategy (strategies/strategy.py) built on the lane-cost admission of strategies/lane_fee, unchanged there. At
levels 7 and 8 every week has a day on which about a third of the drivers stay at home. It shows a minute after
midnight: the drivers who are ill give their bookings for that day back. README.md next to this file has what the
saved weeks show.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from spread.types import DeskEvent, DriverProfile, WorldMap

from strategies.admission import Held, Verdict
from strategies.admission.admission import DAY, HOUR
from strategies.lane_fee import LaneCostAdmission, LaneFee
from strategies.lead_cost import LeadCostParams

FRIDAY = 4
NEVER = -(10**9)  # the slack of an option that the guard keeps off a quote


@dataclass(frozen=True)
class Params(LeadCostParams):
    """The variables of the lead-cost admission, plus the guard against the flu day."""

    night: int = HOUR  # bookings given back within this of midnight are the flu's
    storm: int = 5  # this many of them in one night is the flu day: an usual night has two at most
    friday_share: float = 1.0  # Friday holds this share of the week's busiest day so far, until the flu has shown
    friday_least: int = 40  # ... and never fewer cars than this


class FluGuardAdmission(LaneCostAdmission):
    """The lane-cost admission, with no more cars due on Friday than the week's busiest day while the flu day has not
    shown, and none due today on the day it shows."""

    params: Params

    def __init__(
        self,
        roster: list[DriverProfile],
        world_map: WorldMap,
        level: int = 8,
        params: Params | None = None,
        lane: LaneFee | None = None,
    ) -> None:
        super().__init__(roster, world_map, level, params or Params(), lane)
        self.night_drops: Counter[int] = Counter()  # day -> bookings given back in its first hour
        self.due: Counter[int] = Counter()  # day -> the orders won that are due on it
        self.due_day: dict[str, int] = {}  # order id -> the day it is due
        self.asked: dict[str, int] = {}  # request id -> respondBy, for a quote of an option due on Friday
        self.guarded_quotes = 0  # the week's options that the guard kept off a quote, for the summary

    def observe(self, event: DeskEvent) -> None:
        """The base's learning, plus the bookings given back at night and the day each order is due."""
        super().observe(event)
        kind, at = event["kind"], event["at"]
        if kind == "gig_dropped" and at % DAY < self.params.night:
            self.night_drops[at // DAY] += 1
        elif kind in ("order_won", "order_changed"):
            order = event["order"]
            self.asked.pop(order["id"], None)
            self.move(order["id"], order["deadline"] // DAY)
        elif kind == "order_lost":
            self.asked.pop(event["requestId"], None)
        elif kind == "order_cancelled":
            self.move(event["orderId"], None)

    def move(self, order_id: str, day: int | None) -> None:
        """The order is due on `day` now, or not at all."""
        was = self.due_day.pop(order_id, None)
        if was is not None:
            self.due[was] -= 1
        if day is not None:
            self.due_day[order_id] = day
            self.due[day] += 1

    def flu_day(self) -> int | None:
        """The day the week's flu showed on, or None while it has not."""
        return next((day for day, n in sorted(self.night_drops.items()) if n >= self.params.storm), None)

    def guarded(self, option: dict, now: int) -> bool:
        """Whether the guard keeps `option` off a quote now: a car due today on the flu day, or one more car due on
        Friday when Friday already holds the week's busiest day, on Thursday or Friday with the flu not shown yet."""
        p = self.params
        today, due = now // DAY, option["deadline"] // DAY
        if self.level < 7:
            return False
        if self.night_drops[today] >= p.storm and due == today:
            return True
        if due != FRIDAY or today < FRIDAY - 1 or self.flu_day() is not None:
            return False
        waiting = sum(1 for respond_by in self.asked.values() if respond_by >= now)
        busiest = max((n for day, n in self.due.items() if day < FRIDAY), default=0)
        return self.due[FRIDAY] + waiting >= max(p.friday_least, p.friday_share * busiest)

    def option_slack(self, request: dict, option: dict, now: int) -> int:
        """The slack of strategies/admission, or none for an option that the guard keeps off the quote."""
        if self.guarded(option, now):
            self.guarded_quotes += 1
            return NEVER
        return super().option_slack(request, option, now)

    def assess(self, request: dict, held: Iterable[Held] = (), now: int | None = None) -> Verdict:
        """The base's verdict. A quote of an option due on Friday counts towards Friday until the dealer answers."""
        verdict = super().assess(request, held, now)
        if verdict.accept:
            option = next(o for o in request["options"] if o["kind"] == verdict.options[0])
            if option["deadline"] // DAY == FRIDAY:
                self.asked[request["id"]] = request["respondBy"]
        return verdict

    def release(self, request_id: str) -> None:
        super().release(request_id)
        self.asked.pop(request_id, None)

    def summary(self) -> str:
        flu = self.flu_day()
        shown = f"the flu day showed on day {flu}" if flu is not None else "no flu day showed"
        return f"{super().summary()}\nFlu guard: {shown}; {self.guarded_quotes} options kept off a quote"
