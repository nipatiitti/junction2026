"""The ratchet system: the root dispatch.py with the pricing strategy of issue #70. See README.md next to this file.

Each dealer's quote price starts at the maximum markup, falls only after a lost quote and climbs back after a win,
never under the cost floor; at level 8 a dealer whose trust can still grow may take a small loss. Each gig gets one
flat fee, priced by distance, place and the risk of finding no driver, which rises only once the car is late.
Everything else (the loop, posting, bundling, notes, retries, direct offers, the final) is the root dispatch.py.

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
from strategies.bundling import audience as bundle_audience
from strategies.ratchet.admission import TrustAdmission
from strategies.ratchet.fees import RiskFees
from strategies.ratchet.pricing import RatchetPricing

POLICY = "ratchet"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `ratchet`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(root.Desk):
    """The root desk with the ratchet's quotes and fees."""

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.admission.roster, self.admission.world_map  # loaded once by the root desk
        self.admission = TrustAdmission(roster, world_map, level)
        self.pricing = RatchetPricing(level)
        self.fees = RiskFees(self.fees.market)

    def rejoin(self, snapshot: DeskSnapshot, history: list[DeskEvent]) -> None:
        super().rejoin(snapshot, history)
        gig_orders = {gig["id"]: root.orders_in(gig) for gig in snapshot["gigs"]}
        for event in history:
            self.learn_risk(event, gig_orders)

    def handle(self, event: DeskEvent) -> None:
        self.learn_risk(event)
        super().handle(event)

    def learn_risk(self, event: DeskEvent, gig_orders: dict[str, list[str]] | None = None) -> None:
        """Tells the fee planner whether an order's gig found a driver before its deadline warning: the first
        booking or the first warning of each order counts, for each order of a bundle. `gig_orders` maps gig ids
        to their orders on a rejoin."""
        if event["kind"] == "deadline_close":
            order_ids, found = [event["orderId"]], False
        elif event["kind"] == "gig_booked" or event["kind"] == "offer_answered" and event["answer"] == "accepted":
            action = self.posts.get(event["gigId"])
            order_ids = root.orders_in(action) if action else (gig_orders or {}).get(event["gigId"], [])
            found = True
        else:
            return
        for order_id in order_ids:
            if order_id in self.orders:
                self.fees.learn(self.orders[order_id], found)

    def quote(self, request: PriceRequest) -> None:
        """Quotes the options that admission picks at the dealer's price, but never under admission's floor: the
        least price at which the cars are worth moving, which at level 8 lets a dealer whose trust can still grow
        take a small loss. A request admission declines gets a price far above the list price, which loses at no
        cost; up to level 3 every quote wins, so no quote."""
        self.requests[request["id"]] = request
        self.bundler.request(request)
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

    def post_due(self) -> None:
        """Posts the new orders that bundling lets go now, as the root desk does, but a bundle of several orders'
        cars gets this system's flat fee too."""
        for group in self.bundler.due(self.now, self.unit):
            if len(group) == 1:
                self.post(self.orders[group[0].order_id], group[0].legs)
            else:
                stops = [stop for unit in group for stop in unit.stops]
                gig = self.bundler.gig(group, self.now)
                schedule = self.fees.bundle(gig, group[0].places[0], group[-1].places[-1], self.now, self.level)
                self.outbox.append(
                    {"type": "post", "stops": stops, "audience": bundle_audience(group), "schedule": schedule}
                )

    def raise_fees(self, order_id: str) -> None:
        """At the order's deadline warning the fee stays: it rises only once the car is late, and the schedule in
        the app already holds those raises. Direct offers go to drivers near the pickup instead. As in the root
        desk, an order still waiting for a bundle goes alone now, and a bundle that no driver holds is split into
        one gig for each order, at its own flat fee."""
        order = self.orders.get(order_id)
        if order is None:
            return
        if self.bundler.holds(order_id):
            self.bundler.forget(order_id)
            self.post(order, root.undelivered(order))
            return
        self.send_post_of(order_id)
        for gig_id in self.gigs_of(order_id):
            if gig_id in self.booked:
                continue
            if gig_id in self.posts and len(root.orders_in(self.posts[gig_id])) > 1:
                self.bundler.counts["split at warning"] += 1
                self.split(gig_id)
            else:
                self.offers.rescue(gig_id)

    def dropped(self, gig_id: str) -> None:
        """After a drop the schedule in the app stays: the fee rises only once the car is late."""


# The root loop (play_practice, play_final) plays with this desk, and main() saves its weeks as `ratchet`.
root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
