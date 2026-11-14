"""The drop-risk system: the headroom system with the fee planner of this folder. See README.md next to this file.

Admission, pricing and everything else are the headroom system's (strategies/headroom). Fees rise where booked drivers
give gigs back or do not show, and a high-risk town gets fewer, earlier raises.

Run it from the repository root: uv run strategies/drop_risk/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World
from spread.types import PostAction

import dispatch as root
from strategies.drop_risk import DropRiskFeePlanner
from strategies.headroom import dispatch as headroom
from strategies.strategy import Strategy
from tools import record

POLICY = "drop-risk"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `drop-risk`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(headroom.Desk):
    """The headroom desk with drop-risk fees, and the gig registration their per-town estimator needs."""

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.admission.roster, self.admission.world_map  # loaded once by the root desk
        self.fees = DropRiskFeePlanner(roster, world_map, level, lane=self.lane)
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
        """Remembers the gig as the headroom desk does, and tells the fee planner its first pickup town. A bundle's
        booking and failures count at that town, the same first pickup whose lane sets its single-order schedule."""
        super().carry(action, gig_id)
        first = next((stop for stop in action["stops"] if stop["kind"] == "pickup"), None)
        order = self.orders.get(first["orderId"]) if first is not None else None
        if first is not None and order is not None:
            self.fees.register(gig_id, order["legs"][first["leg"]]["pickup"]["placeId"])


# The root loop (play_practice, play_final) plays with this desk, and main() saves its weeks as `drop-risk`.
root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
