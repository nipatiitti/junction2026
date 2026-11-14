"""The max-margin system: the war-guard system (strategies/war_guard) with max-margin pricing and the patient fees of
strategies/slack_fees. See README.md next to this file.

Pricing may charge up to 2.0 x the list price (lifted for trust and the outage) and aims to win 40% of its quotes, so
each world, lane and dealer is charged what it accepts; admission counts on the learned price with headroom; the
gigs of cars that can wait hold their early fee; the war and the outage are war-guard's. The rest is ceiling's.

Run it from the repository root: uv run strategies/max_margin/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World

import dispatch as root
from strategies.max_margin.pricing import MaxPricing
from strategies.slack_fees import SlackFeePlanner
from strategies.war_guard import dispatch as war_guard
from tools import record

POLICY = "max-margin"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `max-margin`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(war_guard.Desk):
    """The war-guard desk, with max-margin pricing and patient fees."""

    pricing: MaxPricing

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.admission.roster, self.admission.world_map
        self.pricing = MaxPricing(roster, world_map, level)
        self.fees = SlackFeePlanner(roster, world_map, level)
        self.strategies = [self.notes, self.admission, self.pricing, self.fees, self.offers, self.bundler]


# Importing war_guard set the root loop's desk to its own; this system's replaces it.
root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
