"""The contextual-mix system: the headroom desk whose pricing follows each pickup town's booking rate.

Base HeadroomPricing handles every request except pickups in towns where few of our observed gigs booked quickly.
Those requests use another shared pricing policy, by default HeadroomPricing with a lower maximum markup. The desk
only adds the gig-post observations needed for that choice: admission, fees, bundling and offers are unchanged.

Run it from the repository root: uv run strategies/contextual_mix/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World
from spread.types import PostAction

import dispatch as root
from strategies.contextual_mix import ContextualPricing
from strategies.headroom import dispatch as headroom
from strategies.strategy import Strategy
from tools import record

POLICY = "contextual-mix"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `contextual-mix`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(headroom.Desk):
    """The headroom desk with contextual pricing and the post times its booking estimate needs."""

    pricing: ContextualPricing

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.admission.roster, self.admission.world_map  # loaded once by the root desk
        self.pricing = ContextualPricing(roster, world_map, level)
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
        """Remembers the gig as the headroom desk does, and tells pricing where and when a new gig starts. A gig
        learned of again after a restart is not timed: its original post is long past."""
        known = gig_id in self.posts
        super().carry(action, gig_id)
        first = action["stops"][0]
        order = self.orders.get(first["orderId"])
        if not known and order is not None:
            self.pricing.posted(gig_id, order["legs"][first["leg"]]["pickup"]["placeId"], self.now)


# The root loop (play_practice, play_final) plays with this desk, and main() saves its weeks as `contextual-mix`.
root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
