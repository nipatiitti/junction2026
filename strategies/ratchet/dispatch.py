"""The ratchet system: the root dispatch.py with the pricing strategy of issue #70. See README.md next to this file.

Each dealer's quote price starts at the maximum markup, falls only after a lost quote and climbs back after a win,
never under the cost floor; at level 8 a dealer whose trust can still grow may take a small loss. Each gig gets one
flat fee, priced by distance, place and the risk of finding no driver, which rises only once the car is late.
Everything else (the loop, posting, notes, retries, direct offers, the final) is the root dispatch.py.

Run it from the repository root: uv run strategies/ratchet/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, record.py and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World
from spread.types import DeskEvent, DeskSnapshot, PriceRequest

import dispatch as root
import record
from strategies.admission import Held
from strategies.fees import Market
from strategies.ratchet.admission import TrustAdmission
from strategies.ratchet.fees import RiskFees
from strategies.ratchet.pricing import RatchetPricing

record.POLICY = "ratchet"  # its saved weeks form their own group in out/spread.sqlite


class Desk(root.Desk):
    """The root desk with the ratchet's quotes and fees."""

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.admission.roster, self.admission.world_map  # loaded once by the root desk
        self.admission = TrustAdmission(roster, world_map, level)
        self.pricing = RatchetPricing(level)
        self.fees = RiskFees(Market(world_map, roster))

    def rejoin(self, snapshot: DeskSnapshot, history: list[DeskEvent]) -> None:
        super().rejoin(snapshot, history)
        gig_orders = {gig["id"]: gig["stops"][0]["orderId"] for gig in snapshot["gigs"]}
        for event in history:
            self.learn_risk(event, gig_orders)

    def handle(self, event: DeskEvent) -> None:
        self.learn_risk(event)
        super().handle(event)

    def learn_risk(self, event: DeskEvent, gig_orders: dict[str, str] | None = None) -> None:
        """Tells the fee planner whether an order's gig found a driver before its deadline warning: the first
        booking or the first warning of each order counts. `gig_orders` maps gig ids to orders on a rejoin."""
        if event["kind"] == "deadline_close":
            order_id, found = event["orderId"], False
        elif event["kind"] == "gig_booked" or event["kind"] == "offer_answered" and event["answer"] == "accepted":
            action = self.posts.get(event["gigId"])
            order_id = action["stops"][0]["orderId"] if action else (gig_orders or {}).get(event["gigId"], "")
            found = True
        else:
            return
        order = self.orders.get(order_id)
        if order is not None:
            self.fees.learn(order, found)

    def quote(self, request: PriceRequest) -> None:
        """Quotes the options that admission picks at the dealer's price, but never under admission's floor: the
        least price at which the cars are worth moving, which at level 8 lets a dealer whose trust can still grow
        take a small loss. A request admission declines gets a price far above the list price, which loses at no
        cost; up to level 3 every quote wins, so no quote."""
        self.requests[request["id"]] = request
        held = [
            Held(o, bool(g := self.gigs_of(o["id"])) and all(x in self.booked for x in g)) for o in self.orders.values()
        ]
        verdict = self.admission.assess(request, held, self.now, self.pricing.multiplier(request, self.now))
        facts = self.facts_of(request["id"])
        # The note's deadline passes before the car can be collected (strategies/notes): decline.
        hopeless = facts.deadline is not None and facts.deadline <= (facts.earliest_pickup or request["arrivedAt"])
        if verdict.accept and not hopeless:
            trust = self.pricing.trust_of(request["dealerId"], self.now)
            floor = self.admission.floor(request, verdict, trust, self.fees.estimate(request, self.now))
            priced = self.pricing.price(request, self.now, verdict.options, floor)
            prices = {kind: cents for kind, cents in priced.items() if kind in verdict.options}
        elif self.level > 3:
            prices = {o["kind"]: 10 * o["listPriceCents"] for o in request["options"][:1]}
        else:
            return
        self.outbox.append({"type": "quote", "requestId": request["id"], "prices": prices})

    def raise_fees(self, order_id: str) -> None:
        """At the order's deadline warning the fee stays: it rises only once the car is late, and the schedule in
        the app already holds those raises. Direct offers go to drivers near the pickup instead."""
        if order_id not in self.orders:
            return
        self.send_post_of(order_id)
        for gig_id in self.gigs_of(order_id):
            if gig_id not in self.booked:
                self.offers.rescue(gig_id)

    def dropped(self, gig_id: str) -> None:
        """After a drop the schedule in the app stays: the fee rises only once the car is late."""


root.Desk = Desk  # the root loop (play_practice, play_final) plays with this desk

if __name__ == "__main__":
    root.main()
