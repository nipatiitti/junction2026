"""The tight-margin system: the max-margin system (strategies/max_margin) that prices like ceiling until the week's
drivers fall behind. See README.md next to this file.

Its pricing starts with ceiling's maximum of 1.39 x the list price and turns into max-margin pricing after four
deadline warnings or expired gigs. Its fees are slack fees', and its price war and outage war guard's, all week.

Run it from the repository root: uv run strategies/tight_margin/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World

import dispatch as root
from strategies.max_margin import dispatch as max_margin
from strategies.tight_margin.pricing import TightPricing
from tools import record

POLICY = "tight-margin"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `tight-margin`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(max_margin.Desk):
    """The max-margin desk, whose pricing waits for the drivers to fall behind."""

    pricing: TightPricing

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        self.pricing = TightPricing(self.admission.roster, self.admission.world_map, level)
        self.strategies = [self.notes, self.admission, self.pricing, self.fees, self.offers, self.bundler]


# Importing max_margin set the root loop's desk to its own; this system's replaces it.
root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
