"""E2 — short cheap-solo window, then one return-leg attempt for anything still unbooked.

`all_in` with the same pricing/admission, with bundling/fallback timing only. An order with at least six hours of
slack waits 45 minutes with its normal solo gig; if still unbooked then, it is withdrawn and put in the chain pool.
Safe pickup timing, route feasibility and fee schedules are unchanged.

Run from the repository root: uv run strategies/solo_chain/dispatch.py --level 8 --seed tour-r1-d0cceb91
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World

import dispatch as root
from strategies.bundle_experiments.base import SoloChainDesk
from strategies.solo_chain.bundling import SoloFirstBundler

POLICY = "solo-chain"


class Recorder(root.Recorder):
    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(SoloChainDesk):
    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        self.bundler = SoloFirstBundler(self.admission.roster, self.admission.world_map, level)
        self.strategies[-1] = self.bundler


root.Desk = Desk
root.Recorder = Recorder
if __name__ == "__main__":
    root.main()
