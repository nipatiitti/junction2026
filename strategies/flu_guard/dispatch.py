"""The flu-guard system: the soft-top system with the admission of this folder. See README.md next to this file.

Fees, pricing and everything else are the soft-top system's (strategies/soft_top). The one change is a guard in
admission against the week's flu day, on which about a third of the drivers stay at home: while that day has not
shown, Friday takes no more cars than the week's busiest day so far, and on the day it shows no car is promised for
the same day. A car that misses a Friday deadline waits for Monday, and one such Friday can cost the week its rank.

Run it from the repository root: uv run strategies/flu_guard/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World

import dispatch as root
from strategies.flu_guard import FluGuardAdmission
from strategies.soft_top import dispatch as soft_top
from strategies.strategy import Strategy
from tools import record

POLICY = "flu-guard"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `flu-guard`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(soft_top.Desk):
    """The soft-top desk with the flu-guard admission."""

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.admission.roster, self.admission.world_map  # loaded once by the root desk
        self.admission = FluGuardAdmission(roster, world_map, level, lane=self.lane)  # the guard on Friday
        self.strategies: list[Strategy] = [
            self.notes,
            self.lane,
            self.admission,
            self.pricing,
            self.fees,
            self.offers,
            self.bundler,
        ]


# The root loop (play_practice, play_final) plays with this desk, and main() saves its weeks as `flu-guard`.
root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
