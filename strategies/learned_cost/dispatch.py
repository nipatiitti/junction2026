"""The learned-cost system: the ceiling system (strategies/ceiling) whose admission corrects its driver cost with the
week's own bookings. See README.md next to this file.

Each time a driver books a gig of one order, the desk tells admission the fee. Admission compares it with the cost it
expected for that car, and corrects later estimates at that pickup and in the world. The corrected cost is also the
floor of ceiling pricing, so the price follows. Everything else is the ceiling system's.

Run it from the repository root: uv run strategies/learned_cost/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World
from spread.types import DeskEvent

import dispatch as root
from strategies.ceiling import dispatch as ceiling
from strategies.learned_cost import LearnedCostAdmission
from tools import record

POLICY = "learned-cost"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `learned-cost`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(ceiling.Desk):
    """The ceiling desk, whose admission learns the driver cost from our bookings."""

    admission: LearnedCostAdmission

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        self.admission = LearnedCostAdmission(self.admission.roster, self.admission.world_map, level)
        self.strategies = [self.notes, self.admission, self.pricing, self.fees, self.offers, self.bundler]

    def handle(self, event: DeskEvent) -> None:
        """The ceiling desk's answer, then: a gig of one order booked at a known fee teaches admission its cost."""
        super().handle(event)
        if event["kind"] != "gig_booked" or "feeCents" not in event:
            return
        action = self.posts.get(event["gigId"])
        if action is None or len(root.orders_in(action)) != 1:
            return
        order = self.orders.get(root.orders_in(action)[0])
        if order is not None:
            self.admission.booked(order["id"], event["feeCents"], root.pickups(action) / len(order["legs"]))


root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
