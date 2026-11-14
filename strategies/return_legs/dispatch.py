"""E1 — immediate compatible return-leg bundles, without deliberately holding orders.

The leading all_in system with the cheapest-insertion route builder of strategies/chain_opt. No hold is added: an
order that finds a compatible partner immediately is composed into a chain at once, just as it does not linger for
one that has not arrived yet. Admission, pricing and dawn fees are unchanged.

Run from the repository root: uv run strategies/return_legs/dispatch.py --level 8 --seed tour-r1-d0cceb91
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World

import dispatch as root
from strategies.bundle_experiments.base import InstantChainDesk
from strategies.chain_opt.bundling import RouteBundler

POLICY = "return-legs"


class Recorder(root.Recorder):
    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(InstantChainDesk):
    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        self.bundler = RouteBundler(self.admission.roster, self.admission.world_map, level)
        self.strategies[-1] = self.bundler


root.Desk = Desk
root.Recorder = Recorder
if __name__ == "__main__":
    root.main()
