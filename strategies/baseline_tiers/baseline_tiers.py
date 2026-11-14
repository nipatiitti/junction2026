"""The baseline with a fixed quote multiple and fee tiers: the desk of strategies/baseline/baseline.py, with
`FixedMultiplePricing` in the place of `BaselinePricing` and `TierFees` in the place of `BaselineFees`. A car whose
note says it is manual is posted to drivers with a manual licence, and the open gigs of an order are repriced when
its fee falls back. Admission, the note reader and the retry are the baseline's. See README.md next to this file.

Run it with `uv run python strategies/baseline_tiers/baseline_tiers.py --level 2 --seed spread-1`, or bench it
against the baseline with
`uv run python -m strategies.bench strategies/baseline_tiers/baseline_tiers.py strategies/baseline/baseline.py`.
"""

from __future__ import annotations

import sys
from functools import partial
from pathlib import Path

# Run as a file, Python looks for modules next to it; tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World
from spread.types import DeskEvent, Order

from strategies.baseline import baseline
from strategies.baseline.retry import FIRST_TRY, Retry
from strategies.baseline_tiers.fees import TierFees
from strategies.baseline_tiers.pricing import FixedMultiplePricing
from tools import record

POLICY = "baseline-tiers"  # the policy of the weeks this system saves, so they form their own group in the data


class Desk(baseline.Desk):
    """The baseline's desk, with the fixed quote multiple and the fee tiers. Everything else is the baseline's."""

    fees: TierFees

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.pricing.roster, self.pricing.world_map  # as the baseline's desk loaded them
        pricing, fees = FixedMultiplePricing(roster, world_map, level), TierFees(roster, world_map, level)
        swaps = {id(self.pricing): pricing, id(self.fees): fees}
        self.strategies = [swaps.get(id(strategy), strategy) for strategy in self.strategies]
        self.pricing, self.fees = pricing, fees  # type: ignore[assignment]
        self.low: set[str] = set()  # the gigs repriced to their first fee again
        self.fell_at = -1  # the minute `fall_back` last ran

    def post(self, order: Order, legs: list[int], retry: Retry = FIRST_TRY) -> None:
        """The baseline's post. A manual car goes to drivers with a manual licence from its first post, not only
        after a failed visit: the note speaks of the first car, and a failed visit of any."""
        manual = 0 in legs and self.fees.manual(order, self.requests[order["id"]])
        super().post(order, legs, retry._replace(manual_licence=retry.manual_licence or manual))

    def handle(self, event: DeskEvent) -> None:
        super().handle(event)
        self.fall_back()

    def falling(self) -> list[Order]:
        """The orders whose fee can still fall back: those without a deadline warning, which has its own fees."""
        return [order for order in self.orders.values() if order["id"] not in self.fees.urgent]

    def fall_back(self) -> None:
        """Reprices to the first fee again the open gigs of each order whose `back_at` has come (strategies/
        baseline_tiers/fees.py). A fee schedule cannot fall, so this takes a reprice. Once a minute."""
        if self.now == self.fell_at:
            return
        self.fell_at = self.now
        for order in self.falling():
            if self.now < self.fees.back_at(order):
                continue
            for gig_id in self.gigs_of(order["id"]):
                if gig_id not in self.booked and gig_id not in self.low:
                    self.low.add(gig_id)
                    schedule = self.fees_for(order, baseline.pickups(self.posts[gig_id]))
                    self.outbox.append({"type": "reprice", "gigId": gig_id, "schedule": schedule})

    def next_fall(self) -> float:
        """The next minute an order's fee falls back, for the clock to stop at. Infinity when there is none."""
        backs = (self.fees.back_at(order) for order in self.falling() if self.gigs_of(order["id"]))
        return min((at for at in backs if at > self.now), default=float("inf"))


def play_practice(world: World, level: int) -> None:
    """The baseline's practice loop, which also stops the clock when an order's fee falls back."""
    snapshot = world.snapshot()
    desk, ends_at = Desk(world, level, snapshot["now"]), snapshot["endsAt"]
    while desk.now < ends_at:
        day, midnight = desk.now // baseline.DAY, (desk.now // baseline.DAY + 1) * baseline.DAY
        # One request a step: the advance applies the outbox, then moves the clock.
        actions, desk.outbox = desk.outbox, []
        until = int(min(ends_at, midnight, desk.next_fall()))
        step = world.advance(until=baseline.WAKE_ON, max=until, actions=actions)
        desk.read_results(actions, step["results"])
        desk.now = step["now"]
        for event in step["events"]:
            desk.handle(event)
        desk.fall_back()  # also when the clock stopped for it, without an event
        if desk.now // baseline.DAY > day:
            baseline.report(baseline.WEEKDAYS[day % 7], world.score())


def main() -> None:
    """The baseline's runner, with this file's desk and practice loop in the place of the baseline's, and the weeks
    saved under this system's policy. The baseline's runner finds the desk, the loop and the recorder by name."""
    baseline.Desk = Desk  # type: ignore[misc]
    baseline.play_practice = play_practice
    record.Recorder = partial(record.Recorder, policy=POLICY)  # type: ignore[assignment,misc]
    baseline.main()


if __name__ == "__main__":
    main()
