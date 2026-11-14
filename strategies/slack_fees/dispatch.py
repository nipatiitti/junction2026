"""The slack-fees system: the ceiling system (strategies/ceiling) whose gigs hold their early fee when the car has a
day or more to wait. See README.md next to this file.

Only the fee schedule of a gig posted for one order changes: with at least 16 hours before its top fee is due, the
raises after the first hour wait until 3 hours before the top. Everything else is the ceiling system's.

Run it from the repository root: uv run strategies/slack_fees/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World

import dispatch as root
from strategies.ceiling import dispatch as ceiling
from strategies.slack_fees import SlackFeePlanner
from tools import record

POLICY = "slack-fees"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `slack-fees`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(ceiling.Desk):
    """The ceiling desk, with patient fees for cars that can wait."""

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        self.fees = SlackFeePlanner(self.admission.roster, self.admission.world_map, level)
        self.strategies = [self.notes, self.admission, self.pricing, self.fees, self.offers, self.bundler]


root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
