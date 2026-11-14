"""The robust-tune system: the headroom desk with reduced-parameter pricing. See README.md next to this file.

The lane fee, lead-cost admission, dawn fees and everything else are the headroom system's, unchanged. Only pricing
changes: place and dealer offsets are off by default, and the world estimate and moving maximum take smaller steps.

Run it from the repository root: uv run strategies/robust_tune/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World

import dispatch as root
from strategies.headroom import dispatch as headroom
from strategies.robust_tune import RobustPricing
from strategies.strategy import Strategy
from tools import record

POLICY = "robust-tune"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `robust-tune`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(headroom.Desk):
    """The headroom desk with robust pricing; its lane fee, lead-cost admission and dawn fees are unchanged."""

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.admission.roster, self.admission.world_map  # loaded once by the root desk
        self.pricing = RobustPricing(roster, world_map, level)
        self.strategies: list[Strategy] = [
            self.notes,
            self.lane,
            self.admission,
            self.pricing,
            self.fees,
            self.offers,
            self.bundler,
        ]


# The root loop (play_practice, play_final) plays with this desk, and main() saves its weeks as `robust-tune`.
root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
