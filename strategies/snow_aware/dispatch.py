"""The snow-aware system: the headroom desk with forecast-shared fees and bundling. See README.md next to this file.

Admission, pricing, the note reader, offers and the root play loop stay as they are. One `SnowState` feeds the
`SnowPlanner` and `SnowBundler`: snowy pickup days open dearer and skip a batch's remaining wait, and only chain legs
that meet snow use the slower timing and larger delivery buffer.

Run it from the repository root: uv run strategies/snow_aware/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World

import dispatch as root
from strategies.headroom import dispatch as headroom
from strategies.snow_aware import SnowBundler, SnowPlanner, SnowState
from strategies.strategy import Strategy
from tools import record

POLICY = "snow-aware"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `snow-aware`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(headroom.Desk):
    """The headroom desk whose fee planner and bundler share the forecast snow."""

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.admission.roster, self.admission.world_map  # loaded once by the root desk
        self.snow = SnowState()
        self.fees = SnowPlanner(roster, world_map, level, lane=self.lane, snow=self.snow)
        self.bundler = SnowBundler(roster, world_map, level, snow=self.snow)
        self.strategies: list[Strategy] = [
            self.notes,
            self.lane,
            self.admission,
            self.pricing,
            self.fees,
            self.offers,
            self.bundler,
        ]


# Do not replace the root desk or recorder on import; other systems import this module to compose with it.
if __name__ == "__main__":
    root.Desk = Desk
    root.Recorder = Recorder
    root.main()
