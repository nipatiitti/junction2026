"""The slack-budget system: the headroom system with on-time slack admission. See README.md next to this file.

Pricing, fees and everything else are headroom's (strategies/headroom). Admission alone changes: unused room above
90% on time permits bounded cost easing, while the reserve declines requests with known delivery risks. The desk
also tells admission where each gig starts, so a town whose gigs book slowly counts as a risk.

Run it from the repository root: uv run strategies/slack_budget/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World
from spread.types import PostAction

import dispatch as root
from strategies.headroom import dispatch as headroom
from strategies.slack_budget import SlackBudgetAdmission
from strategies.strategy import Strategy
from tools import record

POLICY = "slack-budget"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `slack-budget`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(headroom.Desk):
    """The headroom desk whose admission spends slack and protects its reserve."""

    admission: SlackBudgetAdmission

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.admission.roster, self.admission.world_map  # loaded once by the root desk
        self.admission = SlackBudgetAdmission(roster, world_map, level, lane=self.lane, notes=self.notes)
        self.strategies: list[Strategy] = [
            self.notes,
            self.lane,
            self.admission,
            self.pricing,
            self.fees,
            self.offers,
            self.bundler,
        ]

    def carry(self, action: PostAction, gig_id: str) -> None:
        """Remembers a post as headroom does and tells admission its first pickup. A post rebuilt after a restart is
        not timed: its actual posting minute is long past."""
        known = gig_id in self.posts
        super().carry(action, gig_id)
        first = action["stops"][0]
        order = self.orders.get(first["orderId"])
        if not known and order is not None:
            self.admission.posted(gig_id, order["legs"][first["leg"]]["pickup"]["placeId"], self.now)


# The root loop plays with this desk, and main() saves its weeks as `slack-budget`.
root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
