"""The hazard-fee system: headroom with opening fees chosen from the week's booking hazard.

Admission, pricing and everything else are the headroom system's (strategies/headroom). The one change is the opening
fee of a one-order gig. Accepted posts and reprices are reported to the planner so its exposure uses the actual fees.

Run it from the repository root: uv run strategies/hazard_fee/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World
from spread.types import Action, ActionResult, PostAction

import dispatch as root
from strategies.hazard_fee import HazardFeePlanner
from strategies.headroom import dispatch as headroom
from strategies.strategy import Strategy
from tools import record

POLICY = "hazard-fee"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `hazard-fee`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(headroom.Desk):
    """The headroom desk with the hazard-priced fee planner."""

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.admission.roster, self.admission.world_map  # loaded once by the root desk
        self.fees = HazardFeePlanner(roster, world_map, level, lane=self.lane)
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
        """Remember the post as usual, and give the hazard estimator an accepted one-order gig's fee scale."""
        super().carry(action, gig_id)
        orders = root.orders_in(action)
        order = self.orders.get(orders[0])
        if len(orders) != 1 or gig_id in self.booked or order is None or order["id"] not in self.requests:
            return
        typical = self.fees.typical(order, self.requests[order["id"]]) * root.pickups(action) / len(order["legs"])
        self.fees.posted(gig_id, action["schedule"], typical, action["schedule"][0]["at"])

    def read_results(self, actions: list[Action], results: list[ActionResult]) -> None:
        """Report accepted reprices and withdraws too: they change or end exposure without a desk event."""
        super().read_results(actions, results)
        for action, result in zip(actions, results):
            if not result["ok"]:
                continue
            if action["type"] == "reprice":
                self.fees.repriced(action["gigId"], action["schedule"], action["schedule"][0]["at"])
            elif action["type"] == "withdraw":
                self.fees.withdrawn(action["gigId"], self.now)


# The root loop (play_practice, play_final) plays with this desk, and main() saves its weeks as `hazard-fee`.
root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
