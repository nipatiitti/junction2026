"""The headroom system: the ceiling system with four strategies of issue #200. See README.md next to this file.

Everything not named here is the ceiling system's (strategies/ceiling), which is the root dispatch.py with ceiling
pricing. Four strategies change:

- the lane fee (strategies/lane_fee): the typical fee of a lane without the noise of one request, which admission and
  fees count from;
- admission (strategies/lead_cost): the driver cost of a request by its lead times, and the option of the most margin;
- fees (strategies/dawn_fees): a low fee held through the day of the post, a ladder from 06:00 on the last morning,
  and a short ladder for a gig with no morning to wait for;
- pricing (this folder): the learned price aims to win 45% of its quotes, and the maximum of ceiling pricing moves
  with the wins and losses at it.

Run it from the repository root: uv run strategies/headroom/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World

import dispatch as root
from strategies.ceiling import dispatch as ceiling
from strategies.headroom import HeadroomPricing
from strategies.lane_fee import LaneCostAdmission, LaneFee, LaneFeePlanner
from strategies.strategy import Strategy
from tools import record

POLICY = "headroom"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `headroom`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(ceiling.Desk):
    """The ceiling desk with the lane fee, the lead-cost admission, the dawn fee schedule and the headroom pricing."""

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.admission.roster, self.admission.world_map  # loaded once by the root desk
        self.lane = LaneFee(roster, world_map, level)  # the typical fee of a lane, for the two below
        self.admission = LaneCostAdmission(roster, world_map, level, lane=self.lane)  # the driver cost by lead time
        self.fees = LaneFeePlanner(roster, world_map, level, lane=self.lane)  # the fee schedule, by the drivers' day
        self.pricing = HeadroomPricing(roster, world_map, level)  # the price, under a maximum that moves
        self.strategies: list[Strategy] = [
            self.notes,
            self.lane,
            self.admission,
            self.pricing,
            self.fees,
            self.offers,
            self.bundler,
        ]


# The root loop (play_practice, play_final) plays with this desk, and main() saves its weeks as `headroom`.
root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
