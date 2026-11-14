"""The profit-max system: the ceiling system (strategies/ceiling) with expected-profit pricing. See README.md next to
this file.

Each quote goes to the price where (price - driver cost) x the chance that the dealer takes it is highest, on a win
curve whose middle is the price ceiling pricing learns. Everything else (admission with its timed return leg, the
loop, posting, fees, bundling, notes, retries, direct offers, the final) is the ceiling system's.

Run it from the repository root: uv run strategies/profit_max/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World

import dispatch as root
from strategies.ceiling import dispatch as ceiling
from strategies.profit_max import ProfitPricing
from tools import record

POLICY = "profit-max"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `profit-max`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(ceiling.Desk):
    """The ceiling desk, quoting at the price with the most expected margin."""

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        self.pricing = ProfitPricing(self.admission.roster, self.admission.world_map, level)
        self.strategies = [self.notes, self.admission, self.pricing, self.fees, self.offers, self.bundler]


root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
