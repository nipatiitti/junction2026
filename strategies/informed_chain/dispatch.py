"""E3 — demand-density-aware hold before one chain attempt for an unbooked car.

Dense follow-on towns get 60 minutes to form a better bundle for an order with >= 6 hours of pickup slack, lighter
ones 45. Other orders use the root's normal immediate solo behavior. Where no partner arrives, its ordinary fee
schedule and post deadlines remain unchanged. Admission, pricing and dawn fees are exactly those of all_in.

Run from the repository root: uv run strategies/informed_chain/dispatch.py --level 8 --seed tour-r1-d0cceb91
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World

import dispatch as root
from strategies.bundle_experiments.base import SoloChainDesk
from strategies.informed_chain.bundling import InformedBundler

POLICY = "informed-chain"


class Recorder(root.Recorder):
    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(SoloChainDesk):
    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        self.bundler = InformedBundler(self.admission.roster, self.admission.world_map, level)
        self.strategies[-1] = self.bundler


root.Desk = Desk
root.Recorder = Recorder
if __name__ == "__main__":
    root.main()
