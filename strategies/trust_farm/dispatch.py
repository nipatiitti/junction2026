"""The trust-farm system: farm trust with discounted easy orders, then harvest the dealer's full price uplift.

The headroom desk (strategies/headroom), with this folder's pricing and admission. Pricing selects the busiest
dealers and discounts them until their trust reaches the target. Admission filters their farm-phase orders. Every
other dealer, and every farmed dealer in the harvest phase, behaves as headroom. The desk tells admission about new
gigs so their booking times can identify easy pickup towns.

Run it from the repository root: uv run strategies/trust_farm/dispatch.py --level 8 --seed spread-1
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
from strategies.strategy import Strategy
from strategies.trust_farm import TrustFarmAdmission, TrustFarmPricing
from tools import record

POLICY = "trust-farm"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `trust-farm`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(headroom.Desk):
    """The headroom desk with trust-farm pricing and admission."""

    admission: TrustFarmAdmission
    pricing: TrustFarmPricing

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.admission.roster, self.admission.world_map  # loaded once by the root desk
        self.admission = TrustFarmAdmission(roster, world_map, level, lane=self.lane)
        self.pricing = TrustFarmPricing(roster, world_map, level)
        self.admission.is_farming = self.pricing.farming
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
        """Remembers the gig as headroom does, and times a newly seen gig from its first pickup town. A gig learned
        again after a restart is not timed: its original post is long past.
        """
        known = gig_id in self.posts
        super().carry(action, gig_id)
        first = action["stops"][0]
        order = self.orders.get(first["orderId"])
        if not known and order is not None:
            self.admission.posted(gig_id, order["legs"][first["leg"]]["pickup"]["placeId"], self.now)


# The root loop (play_practice, play_final) plays with this desk, and main() saves its weeks as `trust-farm`.
root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
