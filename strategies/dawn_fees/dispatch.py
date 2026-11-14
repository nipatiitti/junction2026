"""The dawn-fees system: the ceiling system with the fee schedule of this folder. See README.md next to this file.

Quotes, admission and everything else are the ceiling system's (strategies/ceiling), which is the root dispatch.py
with ceiling pricing. The one change is the fee schedule of each gig: a gig that has a morning before its last pickup
holds a low fee through the day it is posted and climbs from 06:00 on its last morning, instead of rising to 1.38
times the typical fee within 3 hours and to the top at 22:00 the evening before.

Run it from the repository root: uv run strategies/dawn_fees/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World

import dispatch as root
from strategies.ceiling import dispatch as ceiling
from strategies.dawn_fees import DawnFeePlanner
from strategies.strategy import Strategy
from tools import record

POLICY = "dawn-fees"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `dawn-fees`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(ceiling.Desk):
    """The ceiling desk with the dawn fee schedule."""

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.admission.roster, self.admission.world_map  # loaded once by the root desk
        self.fees = DawnFeePlanner(roster, world_map, level)  # the fee schedule of each gig, by the drivers' day
        self.strategies: list[Strategy] = [
            self.notes,
            self.admission,
            self.pricing,
            self.fees,
            self.offers,
            self.bundler,
        ]


# The root loop (play_practice, play_final) plays with this desk, and main() saves its weeks as `dawn-fees`.
root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
