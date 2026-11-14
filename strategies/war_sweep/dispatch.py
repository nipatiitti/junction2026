"""The war-sweep system: the headroom desk with the war pricing of this folder. See README.md next to this file.

Admission, fees and everything else are the headroom system's. In particular admission keeps its existing area
capacity: the sweep can win more of the requests that fit, not create room for extra cars. Its margin check receives
the temporary war ceiling from pricing, so it still declines a request whose driver cost cannot fit under the cap.

Run it from the repository root: uv run strategies/war_sweep/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World

import dispatch as root
from strategies.headroom import dispatch as headroom
from strategies.strategy import Strategy
from strategies.war_sweep import WarSweepPricing
from tools import record

POLICY = "war-sweep"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `war-sweep`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(headroom.Desk):
    """The headroom desk with intraday war-sweep pricing and unchanged admission capacity."""

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.admission.roster, self.admission.world_map  # loaded once by the root desk
        self.pricing = WarSweepPricing(roster, world_map, level)
        self.strategies: list[Strategy] = [
            self.notes,
            self.lane,
            self.admission,
            self.pricing,
            self.fees,
            self.offers,
            self.bundler,
        ]


# The root loop (play_practice, play_final) plays with this desk, and main() saves its weeks as `war-sweep`.
root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
