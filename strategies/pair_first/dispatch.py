"""The pair-first system: the headroom system with admission that prices a possible shared gig into each quote.

Pricing, fees and everything else are the headroom system's (strategies/headroom). The one change is admission: when
one of our undelivered orders ends near a request's pickup and its driver can get there in time, the request gets a
driver-cost discount and takes only part of an area-capacity place. The partner need not be a timed return leg.

Run it from the repository root: uv run strategies/pair_first/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World

import dispatch as root
from strategies.headroom import dispatch as headroom
from strategies.pair_first import PairFirstAdmission
from strategies.strategy import Strategy
from tools import record

POLICY = "pair-first"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `pair-first`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(headroom.Desk):
    """The headroom desk with pair-first admission."""

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.admission.roster, self.admission.world_map  # loaded once by the root desk
        self.admission = PairFirstAdmission(roster, world_map, level, lane=self.lane)  # prefer a possible shared gig
        self.strategies: list[Strategy] = [
            self.notes,
            self.lane,
            self.admission,
            self.pricing,
            self.fees,
            self.offers,
            self.bundler,
        ]


# The root loop (play_practice, play_final) plays with this desk, and main() saves its weeks as `pair-first`.
root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
