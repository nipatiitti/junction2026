"""Fee schedules. A gig opens at a learned opening fee and stays flat while there is time, so drivers learn that our
fees do not rise and book when a fee pays them. It rises once on the morning of the last day it can be collected,
then steeply from the deadline warning, 3 hours before its last pickup minute. A car that is already late gets a
plan of its own: it must arrive, because a car never delivered costs twice its price.

Fees are multiples of the typical fee for the gig's cars (`fee`). Every schedule keeps the world's rules: whole
minutes and cents, steps in time order, fees that never fall, 1 to 48 steps, one step at level 1.
"""

from __future__ import annotations

import math
from collections import Counter

from spread.types import FeeStep

HOUR, DAY = 60, 24 * 60
# The opening fee of each rung at the start of the week. A next-day gig gets its driver from the first wave of
# notifications or not at all: on rung 1 an opening of 1.0 booked 88 of 93 gigs at once, all on time, while openings
# that the learner had cut to 0.72 left cars that no raise up to 2.2 found a driver for (README.md).
OPENING = {1: 1.0, 2: 1.0, 3: 1.1, 4: 1.05, 5: 1.2, 6: 1.1}
LOWER, HIGHER = 0.005, 0.05  # the opening falls this much (in log) after a booking at it, rises this after a raise
FLOOR_SHARE = 0.95  # the opening stays at least this share of its start
PRICE_SHARE = 0.5  # and a gig opens at no less than this share of the price of its cars
HIGHEST = 1.5  # and at most this
MORNING = 1.2  # times the opening, from 07:00 on the day of the last pickup minute, while no driver has booked
MORNING_HOUR = 7  # drivers read nothing from 23:00 to 07:00
WARNING_LEAD = 3 * HOUR  # deadline_close comes this long before the last pickup minute
WARNING = 1.5  # from the deadline warning
WARNING_RAISE, WARNING_EVERY, WARNING_TOP = 0.2, 30, 2.2  # then this much more every 30 minutes, up to this
LATE, LATE_RAISE, LATE_EVERY, LATE_TOP = 1.6, 0.2, HOUR, 2.6  # a car that is already late
REBOOK = 1.1  # after a drop, the gig opens at least this times the dropped fee: that driver wants more
MAX_STEPS = 48


class Opening:
    """The opening fee of each rung, as a multiple of the typical fee, learned from our own gigs: it falls a little
    after each gig that books at its opening fee and rises more after each gig that books only after a raise, or
    expires. So it would settle where about 90% of the gigs book at their opening fee (HIGHER / (LOWER + HIGHER)),
    but it never falls more than 5% under its start: a car missed by the first wave costs far more than it saves."""

    def __init__(self) -> None:
        self.log: Counter[int] = Counter({rung: math.log(multiple) for rung, multiple in OPENING.items()})

    def multiple(self, rung: int) -> float:
        return math.exp(self.log[rung])

    def booked(self, rung: int, opening_fee: int, booked_fee: int) -> None:
        self.move(rung, -LOWER if booked_fee <= opening_fee else HIGHER)

    def expired(self, rung: int) -> None:
        self.move(rung, HIGHER)

    def move(self, rung: int, by: float) -> None:
        lowest = math.log(OPENING.get(rung, 1.0) * FLOOR_SHARE)
        self.log[rung] = min(math.log(HIGHEST), max(lowest, self.log[rung] + by))

    def state(self) -> dict[str, float]:
        return {str(rung): log for rung, log in self.log.items()}

    def load(self, state: dict[str, float]) -> None:
        for rung, log in state.items():
            self.log[int(rung)] = float(log)

    def summary(self) -> str:
        return "Opening fees: " + ", ".join(f"rung {r} {self.multiple(r):.2f}" for r in sorted(OPENING))


def cents(fee: float, multiple: float) -> int:
    return max(1, int(fee * multiple + 0.5))


def normal(now: int, fee: float, last_pickup: int, level: int, opening: float, floor: int = 0) -> list[FeeStep]:
    """The schedule of a gig whose car can still be on time: flat at the opening fee, a raise on the morning of the
    last pickup day, then steep from the deadline warning. `floor` is the least fee now, after a drop."""
    warning = last_pickup - WARNING_LEAD
    morning = last_pickup // DAY * DAY + MORNING_HOUR * HOUR
    steps = [(now, cents(fee, opening)), (min(morning, warning - HOUR), cents(fee, opening * MORNING))]
    return tidy(steps + steep(warning, fee, WARNING, WARNING_RAISE, WARNING_EVERY, WARNING_TOP), now, level, floor)


def warned(now: int, fee: float, level: int, floor: int = 0) -> list[FeeStep]:
    """From a deadline warning: steep at once, rising every 30 minutes to the top."""
    return tidy(steep(now, fee, WARNING, WARNING_RAISE, WARNING_EVERY, WARNING_TOP), now, level, floor)


def late(now: int, fee: float, level: int, floor: int = 0, price: float = 0) -> list[FeeStep]:
    """The schedule of a car that can no longer be on time: high at once, rising every hour to the top, which is
    LATE_TOP times the typical fee or twice the price of the gig's cars, whichever is more: a car never delivered
    costs twice its price, so any fee under that is worth paying."""
    top = max(LATE_TOP, 2 * price / fee if fee else 0)
    raise_by = max(LATE_RAISE, (top - LATE) / (MAX_STEPS - 1))  # reach the top within 48 steps
    return tidy(steep(now, fee, LATE, raise_by, LATE_EVERY, top), now, level, floor)


def steep(start: int, fee: float, multiple: float, raise_by: float, every: int, top: float) -> list[tuple[int, int]]:
    steps, at = [], start
    while multiple <= top + 1e-9:
        steps.append((at, cents(fee, multiple)))
        multiple, at = multiple + raise_by, at + every
    return steps


def tidy(steps: list[tuple[int, int]], now: int, level: int, floor: int) -> list[FeeStep]:
    """Keeps the world's rules: the steps that have started fold into one step now, times rise, fees never fall,
    at most 48 steps, and one step at level 1. No fee is under `floor`."""
    started = [fee for at, fee in steps if at <= now]
    later = sorted((at, fee) for at, fee in steps if at > now)
    first = max(started) if started else later[0][1]
    out: list[FeeStep] = [{"at": now, "feeCents": max(floor, first)}]
    for at, fee in later:
        if fee > out[-1]["feeCents"] and at > out[-1]["at"]:
            out.append({"at": at, "feeCents": fee})
    return out[:1] if level <= 1 else out[:MAX_STEPS]


def now_fee(schedule: list[FeeStep], now: int) -> int:
    """The fee that the app shows now: the latest step that has started, or the first step before it starts."""
    shown = schedule[0]["feeCents"]
    for step in schedule:
        if step["at"] <= now:
            shown = step["feeCents"]
    return shown
