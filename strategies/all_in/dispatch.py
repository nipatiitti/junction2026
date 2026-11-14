"""The all-in system: the soft-top system with every strategy of issue #200 that held over 22 weeks. See README.md
next to this file.

On the headroom desk (the lane fee, the lead-cost admission, dawn fees and a price maximum that moves), it plays:

- the fees of strategies/soft_top with three variables moved (fees.py), also for a bundle of several orders;
- the pricing of strategies/lane_prior: a lift for each dear delivery place;
- the admission of strategies/same_day and strategies/flu_guard together: the fastest option that still pays, and a
  guard against the week's flu day.

Run it from the repository root: uv run strategies/all_in/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World

import dispatch as root
from strategies.all_in import AllInAdmission, AllInPlanner
from strategies.bundling import audience as bundle_audience
from strategies.dawn_fees import dawn_plan
from strategies.lane_prior import PriorPricing
from strategies.soft_top import dispatch as soft_top
from strategies.strategy import Strategy
from tools import record

POLICY = "all-in"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `all-in`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(soft_top.Desk):
    """The soft-top desk with the lane-prior pricing and the same-day and flu-guard admission."""

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.admission.roster, self.admission.world_map  # loaded once by the root desk
        self.admission = AllInAdmission(roster, world_map, level, lane=self.lane)  # same-day quotes, flu guard
        self.pricing = PriorPricing(roster, world_map, level)  # the price, lifted by the delivery place's offset
        self.fees = AllInPlanner(roster, world_map, level, lane=self.lane)  # the dawn schedule, tuned on 22 weeks
        self.strategies: list[Strategy] = [
            self.notes,
            self.lane,
            self.admission,
            self.pricing,
            self.fees,
            self.offers,
            self.bundler,
        ]

    def post_due(self) -> None:
        """Posts the new orders that bundling lets go now, as the root desk does, but plans the fees of a bundle of
        several orders with the dawn schedule too: the root desk plans them with the schedule of strategies/fees."""
        for group in self.bundler.due(self.now, self.unit):
            if len(group) == 1:
                self.post(self.orders[group[0].order_id], group[0].legs)
            else:
                stops = [stop for unit in group for stop in unit.stops]
                schedule = dawn_plan(self.now, self.bundler.gig(group, self.now), self.level, self.fees.params)
                self.outbox.append(
                    {"type": "post", "stops": stops, "audience": bundle_audience(group), "schedule": schedule}
                )


# The root loop (play_practice, play_final) plays with this desk, and main() saves its weeks as `all-in`.
root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
