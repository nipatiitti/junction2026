"""The learned-hold system: the headroom system with a bundler that learns each pickup town's booking tempo.

Admission, pricing, fees and everything else are the headroom system's (strategies/headroom). Every order waits for
a chain, for 15 to 120 minutes according to how fast the town's gigs book. The base bundler's quiet-batch and safety
rules still apply. README.md next to this file explains the learning rule.

Run it from the repository root: uv run strategies/learned_hold/dispatch.py --level 8 --seed spread-1
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
from strategies.learned_hold import AdaptiveHoldBundler
from strategies.strategy import Strategy
from tools import record

POLICY = "learned-hold"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `learned-hold`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(headroom.Desk):
    """The headroom desk whose order waits follow their pickup towns' bookings."""

    bundler: AdaptiveHoldBundler

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.admission.roster, self.admission.world_map  # loaded once by the root desk
        self.bundler = AdaptiveHoldBundler(roster, world_map, level)
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
        """Remembers the gig as the headroom desk does, and times a newly accepted post from its first pickup."""
        known = gig_id in self.posts
        super().carry(action, gig_id)
        first = action["stops"][0]
        order = self.orders.get(first["orderId"])
        if known or order is None:
            return
        side = order["legs"][first["leg"]]["pickup" if first["kind"] == "pickup" else "delivery"]
        self.bundler.posted(gig_id, side["placeId"], self.now)


# The root loop (play_practice, play_final) plays with this desk, and main() saves its weeks as `learned-hold`.
root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
