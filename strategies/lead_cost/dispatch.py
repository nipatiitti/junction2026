"""The lead-cost system: the dawn-fees system with the admission of this folder. See README.md next to this file.

Fees, pricing and everything else are the dawn-fees system's (strategies/dawn_fees), which is the ceiling system with
the dawn fee schedule. The one change is admission: the expected driver cost of a request comes from its lead times,
as the saved weeks paid for them, and the option quoted is the one that leaves the most margin over that cost. So a car
that must be collected within hours is priced at what it costs or declined, and a car with a night to wait is priced
as the cheap car it is.

Run it from the repository root: uv run strategies/lead_cost/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World

import dispatch as root
from strategies.dawn_fees import dispatch as dawn_fees
from strategies.lead_cost import LeadCostAdmission
from strategies.strategy import Strategy
from tools import record

POLICY = "lead-cost"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `lead-cost`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(dawn_fees.Desk):
    """The dawn-fees desk with the lead-cost admission."""

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.admission.roster, self.admission.world_map  # loaded once by the root desk
        self.admission = LeadCostAdmission(roster, world_map, level)  # the driver cost by lead time
        self.strategies: list[Strategy] = [
            self.notes,
            self.admission,
            self.pricing,
            self.fees,
            self.offers,
            self.bundler,
        ]


# The root loop (play_practice, play_final) plays with this desk, and main() saves its weeks as `lead-cost`.
root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
