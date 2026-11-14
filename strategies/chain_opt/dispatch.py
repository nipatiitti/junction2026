"""The chain-opt system: the headroom system with cheapest-insertion bundling. See README.md next to this file.

Admission, pricing, fees, notes, offers and the desk loop are the headroom system's. Only the order and position in
which a chain takes its orders changes.

Run it from the repository root: uv run strategies/chain_opt/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World

import dispatch as root
from strategies.chain_opt import RouteBundler
from strategies.headroom import dispatch as headroom
from strategies.strategy import Strategy
from tools import record

POLICY = "chain-opt"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `chain-opt`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(headroom.Desk):
    """The headroom desk with route-optimised bundling."""

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.admission.roster, self.admission.world_map  # loaded once by the root desk
        self.bundler = RouteBundler(roster, world_map, level)
        self.strategies: list[Strategy] = [
            self.notes,
            self.lane,
            self.admission,
            self.pricing,
            self.fees,
            self.offers,
            self.bundler,
        ]


# The root loop (play_practice, play_final) plays with this desk, and main() saves its weeks as `chain-opt`.
root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
