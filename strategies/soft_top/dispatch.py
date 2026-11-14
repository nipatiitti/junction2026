"""The soft-top system: the headroom system with the fee planner of this folder. See README.md next to this file.

Admission, pricing and everything else are the headroom system's (strategies/headroom). The one change is the top fee
of every schedule: twice the lane fee, not 2.5 times. The last driver of a hard car is paid less, and a few more cars
may arrive late: with 98% of the orders on time against a minimum of 90%, that is room the week can use.

Run it from the repository root: uv run strategies/soft_top/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World

import dispatch as root
from strategies.headroom import dispatch as headroom
from strategies.soft_top import SoftTopPlanner
from strategies.strategy import Strategy
from tools import record

POLICY = "soft-top"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `soft-top`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(headroom.Desk):
    """The headroom desk with the soft-top fee planner."""

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.admission.roster, self.admission.world_map  # loaded once by the root desk
        self.fees = SoftTopPlanner(roster, world_map, level, lane=self.lane)  # the dawn schedule, with a lower top
        self.strategies: list[Strategy] = [
            self.notes,
            self.lane,
            self.admission,
            self.pricing,
            self.fees,
            self.offers,
            self.bundler,
        ]


# The root loop (play_practice, play_final) plays with this desk, and main() saves its weeks as `soft-top`.
root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
