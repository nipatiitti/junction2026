"""The offer-probe system: headroom with targeted direct offers whose fee ratios learn from their answers.

Everything else is the headroom system's (strategies/headroom). Admission, fee schedules and pricing do not change.
Run it from the repository root: uv run strategies/offer_probe/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World

import dispatch as root
from strategies.headroom import dispatch as headroom
from strategies.offer_probe import ProbeOffers
from strategies.strategy import Strategy
from tools import record

POLICY = "offer-probe"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `offer-probe`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(headroom.Desk):
    """The headroom desk with direct offers sent only as targeted price probes."""

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.admission.roster, self.admission.world_map  # loaded once by the root desk
        self.offers = ProbeOffers(roster, world_map, level)
        self.strategies: list[Strategy] = [
            self.notes,
            self.lane,
            self.admission,
            self.pricing,
            self.fees,
            self.offers,
            self.bundler,
        ]


# The root loop plays with this desk, and main() saves its weeks as `offer-probe`.
root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
