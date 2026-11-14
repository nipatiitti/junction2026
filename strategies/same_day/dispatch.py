"""The same-day system: the headroom system with the admission of this folder. See README.md next to this file.

Pricing, fees and everything else are the headroom system's (strategies/headroom). The one change is which option
admission quotes: a dealer who asks for same-day delivery takes a slower option from us about half as often, so the
fastest option is quoted whenever its driver cost, on the sprint ladder, still leaves a margin.

Run it from the repository root: uv run strategies/same_day/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World

import dispatch as root
from strategies.headroom import dispatch as headroom
from strategies.same_day import SameDayAdmission
from strategies.strategy import Strategy
from tools import record

POLICY = "same-day"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `same-day`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(headroom.Desk):
    """The headroom desk with the same-day admission."""

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.admission.roster, self.admission.world_map  # loaded once by the root desk
        self.admission = SameDayAdmission(roster, world_map, level, lane=self.lane)  # the fastest option that pays
        self.strategies: list[Strategy] = [
            self.notes,
            self.lane,
            self.admission,
            self.pricing,
            self.fees,
            self.offers,
            self.bundler,
        ]


# The root loop (play_practice, play_final) plays with this desk, and main() saves its weeks as `same-day`.
root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
