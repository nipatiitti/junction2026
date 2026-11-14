"""The low-opening system: the slack-fees system (strategies/slack_fees) whose first post of a car that can wait opens
under the plan's opening fee. See README.md next to this file.

Only the first fee step of a patient gig's first post changes: it opens at 0.8 x the typical fee and reaches the
plan's 0.9 x half an hour later. Everything else is the slack-fees system's, and so the ceiling system's.

Run it from the repository root: uv run strategies/low_opening/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World

import dispatch as root
from strategies.low_opening.fees import LowOpeningPlanner
from strategies.slack_fees import dispatch as slack_fees
from tools import record

POLICY = "low-opening"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `low-opening`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(slack_fees.Desk):
    """The slack-fees desk, whose patient gigs open low on their first post."""

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        self.fees = LowOpeningPlanner(self.admission.roster, self.admission.world_map, level)
        self.strategies = [self.notes, self.admission, self.pricing, self.fees, self.offers, self.bundler]


# Importing slack_fees set the root loop's desk to its own; this system's replaces it.
root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
