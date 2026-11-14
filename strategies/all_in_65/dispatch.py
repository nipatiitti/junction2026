"""The all-in 65 system: the all-in system whose prices aim to win 65% of its quotes. See README.md next to this file.

Every other decision is the all-in system's (strategies/all_in): the same admission, fees, lane priors and bundle fees.
The one change is the two win shares of the pricing (pricing.py): where all-in settles at 45% of its quotes won, and
50% at its maximum, this system aims at 65% and 70%, so it wins more orders at a lower price on each.

Run it from the repository root: uv run strategies/all_in_65/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World

import dispatch as root
from strategies.all_in import dispatch as all_in
from strategies.all_in_65 import AllIn65Pricing
from strategies.strategy import Strategy
from tools import record

POLICY = "all-in-65"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `all-in-65`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(all_in.Desk):
    """The all-in desk with prices that aim to win 65% of its quotes."""

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.admission.roster, self.admission.world_map  # loaded once by the root desk
        self.pricing = AllIn65Pricing(roster, world_map, level)  # the price, aiming at 65% of the quotes won
        self.strategies: list[Strategy] = [
            self.notes,
            self.lane,
            self.admission,
            self.pricing,
            self.fees,
            self.offers,
            self.bundler,
        ]


# The root loop (play_practice, play_final) plays with this desk, and main() saves its weeks as `all-in-65`.
root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
