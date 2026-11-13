"""Admission: which requests to take, and which of their options to quote.

A request is taken when its rung is one we take, its timing leaves a driver time to book it, and the drivers near its
pickup are not already busy with our other cars. The timing rule comes from the starter's level 8 week (`smoke-1`):
a car that is ready on a later day than its request arrives, with a drive of up to 4 hours, was on time 62% to 80% of
the time and booked at its opening fee within minutes, while a car ready at once was on time 30% of the time.
README.md has the numbers.
"""

from __future__ import annotations

from collections import Counter

from spread.types import DeskEvent, PriceRequest

from ladder.market import Market
from ladder.rides import REMOTE_RUNG, Ride, next_morning

HOUR, DAY = 60, 24 * 60
MIN_SLACK = 5 * HOUR  # an option needs this much time beyond the drive, from when the car can go to its deadline
PRIVATE_SLACK = HOUR  # a private delivery is due in its booked hour: the time to spare is the hour itself
# A long or remote ride (rung 6) needs a long search: from now to its deadline, beyond the drive, at least this. That
# leaves 18 hours before its deadline warning: such rides found a driver only with a day to look (README.md).
REMOTE_SEARCH = 21 * HOUR
LONGEST = 8 * HOUR  # a longer drive is never taken: on time 18% of the time in the starter's week
AREA = 60  # road minutes between two pickups that draw on the same drivers
SHARE = 0.10  # we let drivers' supply near a pickup (Market.supply) carry this many waiting cars of ours each day
LEAST = 3  # but at least this many
WIN = 0.5  # a quote that waits for its answer counts as this much of a car
TARGET = 0.95  # below this share of orders on time, admission takes fewer cars
FLOOR = 0.90  # the delivery minimum: at this share admission takes a quarter of the cars
PRIOR = 10  # the on-time share starts at TARGET with the weight of this many orders
WARNED = 0.25  # a deadline warning counts as this much of a late order


class Admission:
    """Decides which requests to quote, from the rung, the timing and the load near the pickup."""

    def __init__(self, market: Market, level: int, rung: int):
        self.market, self.level, self.rung = market, level, rung
        self.pending: dict[str, Ride] = {}  # request id -> ride, for quotes that wait for an answer
        self.on_time, self.late = TARGET * PRIOR, (1 - TARGET) * PRIOR
        self.declined: Counter[str] = Counter()  # reason -> requests, for the summary

    def observe(self, event: DeskEvent, now: int) -> None:
        if event["kind"] == "order_won":
            self.pending.pop(event["order"]["id"], None)
        elif event["kind"] == "order_lost":
            self.pending.pop(event["requestId"], None)
        elif event["kind"] == "deadline_close":
            self.late += WARNED  # a car without a driver 3 hours before its last pickup may well be late

    def delivered(self, ride: Ride, on_time: bool) -> None:
        if on_time:
            self.on_time += 1
        else:
            self.late += 1

    def quoted(self, request: PriceRequest, ride: Ride) -> None:
        self.pending[request["id"]] = ride

    def tightening(self) -> float:
        """1 while our on-time share is at TARGET or more, falling to a quarter at the delivery minimum."""
        share = self.on_time / (self.on_time + self.late)
        return max(0.25, min(1.0, 0.25 + 0.75 * (share - FLOOR) / (TARGET - FLOOR)))

    def options(self, request: PriceRequest, ride: Ride, now: int, load: list[Ride]) -> list[str]:
        """The option kinds to quote, or none to decline."""
        if ride.rung > self.rung:
            return self.decline(f"rung {ride.rung}: {ride.why}")
        if ride.drive > LONGEST:
            return self.decline("a drive over 8 hours")
        if ride.today and request["legs"][0]["pickup"]["privateAddress"]:
            # A private seller's slot is today: the car cannot go as a gig for the next morning.
            return self.decline("a private pickup today")
        kinds = [option["kind"] for option in request["options"] if self.fits(option, ride, now)]
        if self.level <= 3 and request["options"][0]["kind"] not in kinds:
            return self.decline("first option too tight")  # up to level 3 the dealer takes the first option
        if not kinds:
            return self.decline("no option with time to spare")
        if self.busy(ride, load):
            return self.decline("drivers near the pickup are busy")
        return kinds[:1] if self.level <= 3 else kinds

    def fits(self, option: dict, ride: Ride, now: int) -> bool:
        """True when the option leaves a driver time: enough beyond the drive from when the car can go, and for a
        long or remote ride a day's search from now. A car ready today goes on a later option only: it needs the
        evening to find a driver."""
        deadline = self.deadline(option["deadline"], ride)
        slack = deadline - max(ride.ready, now) - ride.drive
        if slack < (PRIVATE_SLACK if ride.private else MIN_SLACK):
            return False
        if ride.rung >= REMOTE_RUNG and deadline - now - ride.drive < REMOTE_SEARCH:
            return False
        return not (ride.today and option["kind"] == "same_day")

    @staticmethod
    def deadline(stated: int, ride: Ride) -> int:
        """An option's deadline for the order: moved by a note that makes the car ready a day or more later, and
        cut by a tighter deadline in the note."""
        moved = stated + ride.shift
        return moved if ride.note_deadline is None else min(moved, ride.note_deadline)

    def busy(self, ride: Ride, load: list[Ride]) -> bool:
        """True when our cars that wait for a driver near this pickup, on its day, fill what its drivers carry."""
        day = pickup_day(ride)
        near = [r for r in load if self.near(r, ride, day)]
        waiting = len(near) + WIN * sum(1 for r in self.pending.values() if self.near(r, ride, day))
        capacity = max(LEAST, SHARE * ride.pickup_supply) * self.tightening()
        return waiting + 1 > capacity

    def near(self, other: Ride, ride: Ride, day: int) -> bool:
        return pickup_day(other) == day and self.market.drive(other.pickup, ride.pickup) <= AREA

    def decline(self, reason: str) -> list[str]:
        self.declined[reason] += 1
        return []

    def summary(self) -> str:
        share = self.on_time / (self.on_time + self.late)
        reasons = ", ".join(f"{reason} {n:,}" for reason, n in self.declined.most_common())
        return f"Admission: on-time estimate {share:.1%}; declined: {reasons}"


def pickup_day(ride: Ride) -> int:
    """The day a driver collects the car: a car ready today goes as a gig for the next business morning (rung 4)."""
    return next_morning(ride.ready) // DAY if ride.today else ride.ready // DAY
