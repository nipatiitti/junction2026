"""The radar-broker system: the all-in system whose quotes surge with the live balance of our work and our drivers near
the pickup. See README.md next to this file.

Everything not named here is the all-in system's (strategies/all_in). One strategy changes:

- pricing (pricing.py): the lane-prior pricing of all_in, times a surge read from the desk's direct offers, which know
  where each of our drivers will be free and which of our gigs still wait for one.

Run it from the repository root: uv run strategies/radar_broker/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World

import dispatch as root
from strategies.all_in import dispatch as all_in
from strategies.radar_broker import RadarPricing
from strategies.strategy import Strategy
from tools import record

POLICY = "radar-broker"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `radar-broker`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(all_in.Desk):
    """The all-in desk with the radar pricing."""

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.admission.roster, self.admission.world_map  # loaded once by the root desk
        self.pricing = RadarPricing(roster, world_map, level, radar=self.offers)  # the all-in price, with the surge
        self.strategies: list[Strategy] = [
            self.notes,
            self.lane,
            self.admission,
            self.pricing,
            self.fees,
            self.offers,
            self.bundler,
        ]


# The root loop (play_practice, play_final) plays with this desk, and main() saves its weeks as `radar-broker`.
root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
