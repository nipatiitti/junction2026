"""The war-guard system: the ceiling system (strategies/ceiling) with admission that knows the price war and the
outage. See README.md next to this file.

Ceiling pricing flags both days. Before each quote the desk tells admission whether the war is on, with the price we
will quote then, and whether the request's pickup is in the outage region, where an area holds more cars. Pricing
takes back what the war day taught its lanes and dealers once it flags the war, and starts the outage's boost at 1.3,
the backup's markup over the competitor, instead of 1.2. Everything else is the ceiling system's.

Run it from the repository root: uv run strategies/war_guard/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World
from spread.types import PriceRequest

import dispatch as root
from strategies.ceiling import dispatch as ceiling
from strategies.war_guard import WarGuardAdmission, WarGuardPricing
from tools import record

POLICY = "war-guard"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `war-guard`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(ceiling.Desk):
    """The ceiling desk, whose admission knows the price war and the outage."""

    admission: WarGuardAdmission

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.admission.roster, self.admission.world_map
        self.admission = WarGuardAdmission(roster, world_map, level)
        self.pricing = WarGuardPricing(roster, world_map, level)
        self.strategies = [self.notes, self.admission, self.pricing, self.fees, self.offers, self.bundler]

    def quote(self, request: PriceRequest) -> None:
        """The ceiling desk's quote, with admission told the war price and the outage first."""
        self.pricing.end_war(self.now)
        war = self.level >= 8 and self.pricing.in_war(self.now)
        learned, _ = self.pricing.learned(request)
        self.admission.war_price = learned * self.pricing.uplift(request, self.now) if war else None
        self.admission.outage = self.level >= 6 and self.pricing.in_outage(request, self.now)
        super().quote(request)


root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
