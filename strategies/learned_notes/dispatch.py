"""The learned-notes system: the headroom desk with reviewed note phrases loaded from this folder's JSON data.

Pricing, admission, fees and everything else are the headroom system's (strategies/headroom). The only change is the
note reader: the usual rules run first, then literal phrases and regular expressions from phrases.json fill facts the
rules missed. The fitted data never replaces a fact the rules already supplied.

Run it from the repository root: uv run strategies/learned_notes/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World

import dispatch as root
from strategies.headroom import dispatch as headroom
from strategies.learned_notes import LearnedNoteReader
from strategies.strategy import Strategy
from tools import record

POLICY = "learned-notes"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `learned-notes`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(headroom.Desk):
    """The headroom desk whose note reader has an additional reviewed-data layer."""

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.admission.roster, self.admission.world_map
        self.notes = LearnedNoteReader(roster, world_map, level)
        self.strategies: list[Strategy] = [
            self.notes,
            self.lane,
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
