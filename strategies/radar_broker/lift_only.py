"""The radar broker with a lift-only surge: quotes rise where our work piles up near the pickup and never fall below
the all-in price. See README.md next to this file.

Run it from the repository root: uv run strategies/radar_broker/lift_only.py --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World

import dispatch as root
from strategies.radar_broker import RadarParams, RadarPricing
from strategies.radar_broker import dispatch as radar
from tools import record

POLICY = "radar-lift"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `radar-lift`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(radar.Desk):
    """The radar-broker desk whose surge never lowers a price."""

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.admission.roster, self.admission.world_map
        lift_only = RadarParams(surge_down=0.0)  # no cut where our drivers will be free
        self.pricing = RadarPricing(roster, world_map, level, lift_only, radar=self.offers)
        self.strategies = [self.pricing if s.__class__ is RadarPricing else s for s in self.strategies]


# The root loop (play_practice, play_final) plays with this desk, and main() saves its weeks as `radar-lift`.
root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
