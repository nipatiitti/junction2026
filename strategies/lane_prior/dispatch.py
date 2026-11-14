"""The lane-prior system: the headroom system with the pricing of this folder. See README.md next to this file.

Admission, fees and everything else are the headroom system's (strategies/headroom). The one change is where each
price starts: the price and the maximum of a request are lifted by the offset of its delivery place, fitted on the
saved weeks. A car to a town where few drivers live is quoted higher from Monday morning, and a car into the Helsinki
area lower, instead of learning both from the week's own wins and losses.

Run it from the repository root: uv run strategies/lane_prior/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World

import dispatch as root
from strategies.headroom import dispatch as headroom
from strategies.lane_prior import PriorPricing
from strategies.strategy import Strategy
from tools import record

POLICY = "lane-prior"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `lane-prior`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(headroom.Desk):
    """The headroom desk with the lane-prior pricing."""

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.admission.roster, self.admission.world_map  # loaded once by the root desk
        self.pricing = PriorPricing(roster, world_map, level)  # the price, lifted by the delivery place's offset
        self.strategies: list[Strategy] = [
            self.notes,
            self.admission,
            self.pricing,
            self.fees,
            self.offers,
            self.bundler,
        ]


# The root loop (play_practice, play_final) plays with this desk, and main() saves its weeks as `lane-prior`.
root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
