"""The town-opening system: the headroom system with the opening fees of this folder. See README.md next to this
file.

Admission, pricing and everything else are the headroom system's (strategies/headroom). The one change is the opening
fee of each gig: instead of 0.9 times the lane fee everywhere, each pickup town has its own multiple, which falls
while its gigs book within minutes at the opening fee and rises when they need a raise. Level 8 gives each town its
own share of the drivers, new in every world, and the driver list does not say who works: the bookings do.

Run it from the repository root: uv run strategies/town_open/dispatch.py --level 8 --seed spread-1
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
from strategies.town_open import TownFeePlanner, TownOpening, pickup_place
from tools import record

POLICY = "town-open"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `town-open`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(headroom.Desk):
    """The headroom desk with an opening fee for each pickup town."""

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.admission.roster, self.admission.world_map  # loaded once by the root desk
        self.opening = TownOpening(roster, world_map, level)  # the opening fee of each pickup town
        # The dawn schedule on the lane fee, opened at the town's fee.
        self.fees = TownFeePlanner(roster, world_map, level, lane=self.lane, opening=self.opening)
        self.strategies: list[Strategy] = [
            self.notes,
            self.lane,
            self.admission,
            self.pricing,
            self.fees,
            self.opening,
            self.offers,
            self.bundler,
        ]

    def carry(self, action: PostAction, gig_id: str) -> None:
        """Remembers the gig as the root desk does, and tells the opening fees each gig of one order: where it
        starts, when it was posted and what it opened at, over the lane fee of its cars."""
        super().carry(action, gig_id)
        orders = root.orders_in(action)
        order = self.orders.get(orders[0])
        if len(orders) != 1 or order is None or order["id"] not in self.requests:
            return
        typical = self.fees.typical(order, self.requests[order["id"]]) * root.pickups(action) / len(order["legs"])
        first = action["schedule"][0]
        if typical > 0:
            self.opening.posted(
                gig_id, pickup_place(order), first["at"], first["feeCents"], first["feeCents"] / typical
            )


# The root loop (play_practice, play_final) plays with this desk, and main() saves its weeks as `town-open`.
root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
