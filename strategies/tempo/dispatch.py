"""The tempo system: the ceiling system (strategies/ceiling) whose admission sizes each area by how fast our gigs
book there. See README.md next to this file.

The desk tells admission each gig it posts, with its first pickup. Admission times the gig to its booking, and an area
where drivers take our gigs quickly holds more cars, one where they wait holds fewer. Everything else is the ceiling
system's.

Run it from the repository root: uv run strategies/tempo/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World
from spread.types import PostAction

import dispatch as root
from strategies.ceiling import dispatch as ceiling
from strategies.tempo import TempoAdmission
from tools import record

POLICY = "tempo"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `tempo`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(ceiling.Desk):
    """The ceiling desk, whose admission learns each area's tempo from our gigs."""

    admission: TempoAdmission

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        self.admission = TempoAdmission(self.admission.roster, self.admission.world_map, level)
        self.strategies = [self.notes, self.admission, self.pricing, self.fees, self.offers, self.bundler]

    def carry(self, action: PostAction, gig_id: str) -> None:
        """Remembers the gig as the ceiling desk does, and tells admission where it starts, so it is timed. A gig
        that the desk learns of again after a restart is not timed: its post is long past."""
        known = gig_id in self.posts
        super().carry(action, gig_id)
        first = action["stops"][0]
        order = self.orders.get(first["orderId"])
        if not known and order is not None:
            self.admission.posted(gig_id, order["legs"][first["leg"]]["pickup"]["placeId"], self.now)


root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
