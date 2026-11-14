"""The outage-harvest system: the headroom desk that reserves shared capacity for a flagged outage region.

The existing outage detector in strategies/pricing supplies the region. Admission reserves part of each shared
pickup area for requests that touch it and asks outside requests for a wider margin. Pricing reuses ceiling's
existing outage uplift with a configurable opening markup. Everything else is the headroom system's.

Run it from the repository root: uv run strategies/outage_harvest/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World

import dispatch as root
from strategies.headroom import dispatch as headroom
from strategies.outage_harvest import OutageAdmission, OutagePricing
from strategies.strategy import Strategy
from tools import record

POLICY = "outage-harvest"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `outage-harvest`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(headroom.Desk):
    """The headroom desk whose admission and pricing share the existing outage flag."""

    admission: OutageAdmission
    pricing: OutagePricing

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.admission.roster, self.admission.world_map  # loaded once by the root desk
        self.pricing = OutagePricing(roster, world_map, level)
        self.admission = OutageAdmission(roster, world_map, level, lane=self.lane, pricing=self.pricing)
        self.strategies: list[Strategy] = [
            self.notes,
            self.lane,
            self.admission,
            self.pricing,
            self.fees,
            self.offers,
            self.bundler,
        ]


# The root loop (play_practice, play_final) plays with this desk, and main() saves its weeks as `outage-harvest`.
root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
