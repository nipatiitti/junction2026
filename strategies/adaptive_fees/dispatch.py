"""The root dispatch.py with fees that spend on-time slack. See README.md next to this file.

Run it from the repository root: uv run strategies/adaptive_fees/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World

import dispatch as root
from strategies.adaptive_fees import AdaptiveFees
from tools import record

POLICY = "adaptive-fees"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `adaptive-fees`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(root.Desk):
    """The root desk with fees whose discount follows the week's on-time share."""

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.fees.roster, self.fees.world_map  # loaded once by the root desk
        self.fees = AdaptiveFees(roster, world_map, level)
        self.strategies = [
            self.notes,
            self.admission,
            self.pricing,
            self.fees,
            self.offers,
            self.bundler,
        ]


root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
