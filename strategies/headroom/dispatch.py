"""The headroom system: the lead-cost system with the pricing of this folder. See README.md next to this file.

Admission, fees and everything else are the lead-cost system's (strategies/lead_cost). The one change is the maximum
of ceiling pricing: it starts at 1.39 times the list price, rises after each quote won at it and falls after each
quote lost at it, so it settles where about 62% of the quotes at the maximum win, in the world being played.

Run it from the repository root: uv run strategies/headroom/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World

import dispatch as root
from strategies.headroom import HeadroomPricing
from strategies.lead_cost import dispatch as lead_cost
from strategies.strategy import Strategy
from tools import record

POLICY = "headroom"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `headroom`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(lead_cost.Desk):
    """The lead-cost desk with the headroom pricing."""

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.admission.roster, self.admission.world_map  # loaded once by the root desk
        self.pricing = HeadroomPricing(roster, world_map, level)  # the price, under a maximum that moves
        self.strategies: list[Strategy] = [
            self.notes,
            self.admission,
            self.pricing,
            self.fees,
            self.offers,
            self.bundler,
        ]


# The root loop (play_practice, play_final) plays with this desk, and main() saves its weeks as `headroom`.
root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
