"""The combined-fees system: soft top with the on-time and homecoming discounts. See README.md next to this file.

Run it from the repository root: uv run strategies/combined_fees/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World

import dispatch as root
from strategies.combined_fees import CombinedTopPlanner
from strategies.soft_top import dispatch as soft_top
from strategies.strategy import Strategy
from tools import record

POLICY = "combined-fees"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `combined-fees`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(soft_top.Desk):
    """The soft-top desk with the combined fee planner; admission, pricing and lane handling stay unchanged."""

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.fees.roster, self.fees.world_map  # loaded once by the root desk
        self.fees = CombinedTopPlanner(roster, world_map, level, lane=self.lane)
        self.strategies: list[Strategy] = [
            self.notes,
            self.lane,
            self.admission,
            self.pricing,
            self.fees,
            self.offers,
            self.bundler,
        ]


# The root loop (play_practice, play_final) plays with this desk, and main() saves its weeks as `combined-fees`.
root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
