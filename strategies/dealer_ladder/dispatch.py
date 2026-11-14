"""Our dispatch system with a price ladder per dealer and a capacity shadow price: a copy of the price-ladder
dispatch.py whose quotes carry one ladder position for each dealer and whose admission charges the driver capacity an
order uses (README.md next to this file). The root dispatch.py and the strategies it builds stay as they are.

Run it from the repository root: uv run strategies/dealer_ladder/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import argparse
import time
from collections import Counter
from dataclasses import replace
from itertools import pairwise
from typing import Any, NamedTuple

from spread.client import Client, SpreadError, Unreachable, World
from spread.types import (
    Action,
    ActionResult,
    Audience,
    DeskEvent,
    DeskEventKind,
    DeskSnapshot,
    FeeStep,
    Gig,
    Order,
    PostAction,
    PriceRequest,
    Score,
    StopRef,
    TimeWindow,
)

from strategies.admission import Held
from strategies.bundling import Bundler, Unit
from strategies.bundling import audience as bundle_audience
from strategies.dealer_ladder import DealerLadderPricing
from strategies.fees import FeePlanner
from strategies.fees import after_drop as fees_after_drop
from strategies.fees import plan as fees_plan
from strategies.fees.schedule import LADDER_STEP
from strategies.notes import NO_FACTS, NoteFacts, NoteReader, Snow, delivery_window, pickup_window
from strategies.offers import GigInfo, Offers
from strategies.price_ladder import ShadowAdmission
from strategies.strategy import Strategy
from tools import record
from tools.record import Recorder
from tools.spread_proxy import ProxyClient

# The weeks this system plays are saved with the policy "dealer-ladder", so they form their own group in the data.
record.POLICY = "dealer-ladder"

HOUR, DAY = 60, 24 * 60
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
# The events that need an answer. Views and account lines arrive with the next event that needs an answer.
WAKE_ON: list[DeskEventKind] = [
    "price_request",
    "order_won",
    "order_changed",
    "order_cancelled",
    "visit_failed",
    "gig_expired",
    "deadline_close",
]
# While price requests keep coming, the loop does not stop for each one: the dealer decides at the request's
# respondBy, 15 minutes after it, on the last quote. So the loop looks at least every POLL minutes instead and
# quotes every request it finds then, together with the answers to the other events.
WAKE_ON_BUSY: list[DeskEventKind] = [kind for kind in WAKE_ON if kind != "price_request"]
POLL = 14  # a request that comes a minute after a stop is quoted at the latest a minute before its respondBy


class Retry(NamedTuple):
    """How to post a leg again after a failed visit."""

    pickup_from: int = 0
    manual_licence: bool = False
    plates: bool = False


FIRST_TRY = Retry()


class Desk:
    """What the starter remembers, and its answer to each event. The answers wait in the outbox
    until the starter sends them, and the world applies them at the current minute."""

    def __init__(self, world: World, level: int, now: int):
        self.world, self.level, self.now = world, level, now
        self.outbox: list[Action] = []  # the actions decided since the starter last sent
        self.requests: dict[str, PriceRequest] = {}
        self.orders: dict[str, Order] = {}  # the orders won and not cancelled
        self.leg_gigs: dict[str, dict[int, str]] = {}  # order id -> leg -> the gig that carries the leg
        self.booked: set[str] = set()  # the gigs that a driver holds now
        self.posts: dict[str, PostAction] = {}  # gig id -> the post that made it
        self.booked_fees: dict[str, int] = {}  # gig id -> the fee that its driver booked it at
        # Level 1: gig id -> the raises still to come while no driver books it (strategies/fees, `ladder`).
        self.ladders: dict[str, list[FeeStep]] = {}
        # The driver list and the map, loaded once. Every strategy is built from them and the level, the same way
        # (strategies/strategy.py), and `handle` feeds each one every event.
        roster, world_map = world.roster(), world.client.map()
        self.notes = NoteReader(roster, world_map, level)  # what each note says, and the snow (strategies/notes)
        self.admission = ShadowAdmission(roster, world_map, level)  # which requests to take (strategies/price_ladder)
        self.pricing = DealerLadderPricing(roster, world_map, level)  # the price of a quote (strategies/dealer_ladder)
        self.fees = FeePlanner(roster, world_map, level)  # plans each gig's fee schedule (strategies/fees)
        self.offers = Offers(roster, world_map, level)  # sends gigs to drivers near their pickup (strategies/offers)
        self.bundler = Bundler(roster, world_map, level)  # puts several orders' cars in one gig (strategies/bundling)
        self.strategies: list[Strategy] = [
            self.notes,
            self.admission,
            self.pricing,
            self.fees,
            self.offers,
            self.bundler,
        ]

    def rejoin(self, snapshot: DeskSnapshot, history: list[DeskEvent]) -> None:
        """Rebuilds what it knows from the world, so a starter that stopped keeps its orders. Then answers
        what it missed: open requests, orders without a gig, and failed visits without a new gig."""
        posted: dict[str, list[Gig]] = {}  # order id -> its gigs, oldest first
        self.booked = {gig["id"] for gig in snapshot["gigs"] if gig["status"] in ("booked", "working", "done")}
        for gig in snapshot["gigs"]:
            for order_id in orders_in(gig):
                posted.setdefault(order_id, []).append(gig)
            if gig["status"] in ("open", "booked", "working"):
                self.carry(
                    {"type": "post", "stops": gig["stops"], "audience": gig["audience"], "schedule": gig["schedule"]},
                    gig["id"],
                )
        self.requests = {e["request"]["id"]: e["request"] for e in history if e["kind"] == "price_request"}
        # Every strategy learns the week so far, but offers, which learn it below, once they know the posted gigs.
        # The history rebuilds dealer trust. It cannot tell the quotes admission declined from the others,
        # so the price multiplier learns again from the level's start.
        for event in history:
            for strategy in self.strategies:
                if strategy is not self.offers:
                    strategy.observe(event)
        self.orders = {
            o["id"]: o for o in snapshot["orders"] if o["id"] in self.requests and o["status"] != "cancelled"
        }
        for order in self.orders.values():
            if order["status"] == "waiting" and not self.gigs_of(order["id"]):
                self.post(order, undelivered(order))
        for event in history:
            order = self.orders.get(event.get("orderId", ""))
            if order is None:
                continue
            if event["kind"] == "visit_failed" and order["deliveredAt"][event["leg"]] is None:
                later = [
                    g for g in posted.get(order["id"], []) if g["postedAt"] >= event["at"] and g["id"] != event["gigId"]
                ]
                if not any(stop["leg"] == event["leg"] for gig in later for stop in gig["stops"]):
                    self.retry(order["id"], event["leg"], event["reason"])
        for gig_id, action in list(self.posts.items()):  # now that the orders are known
            self.carry(action, gig_id)
        for event in history:
            self.offers.observe(event)
        self.offers.open -= self.booked
        for request in snapshot["openRequests"]:
            self.quote(request)

    def handle(self, event: DeskEvent) -> None:
        for strategy in self.strategies:  # each learns what it needs from the event, then the desk answers it
            strategy.observe(event)
        if event["kind"] == "price_request":
            self.quote(event["request"])
        elif event["kind"] == "order_won":
            self.win(event["order"])
        elif event["kind"] == "order_changed":
            self.change(event["order"])
        elif event["kind"] == "order_cancelled":  # the world has stopped the car and told each of its gigs what happens
            for gig in event["gigs"]:
                self.ladders.pop(gig["gigId"], None)
            for books in (self.orders, self.leg_gigs):
                books.pop(event["orderId"], None)
            for gig in event["gigs"]:  # a withdrawn bundle: post its other cars again
                if gig["outcome"] == "withdrawn":
                    self.post_rest(gig["gigId"], event["orderId"])
        elif event["kind"] == "visit_failed":
            self.retry(event["orderId"], event["leg"], event["reason"])
        elif event["kind"] == "gig_expired":
            self.ladders.pop(event["gigId"], None)
            self.repost(event["gigId"])
        elif event["kind"] == "deadline_close":  # it comes again when a driver drops the car after the first warning
            self.raise_fees(event["orderId"])
        elif event["kind"] == "gig_booked" or event["kind"] == "offer_answered" and event["answer"] == "accepted":
            self.booked.add(event["gigId"])
            self.ladders.pop(event["gigId"], None)
            if event["gigId"] in self.posts and len(orders_in(self.posts[event["gigId"]])) > 1:
                self.bundler.counts["bundle bookings"] += 1
            if "feeCents" in event:  # an accepted offer does not say its fee
                self.booked_fees[event["gigId"]] = event["feeCents"]
        elif event["kind"] == "gig_dropped":
            self.booked.discard(event["gigId"])
            self.dropped(event["gigId"])
        elif event["kind"] == "no_show":  # the gig is open again; a late driver still comes
            self.booked.discard(event["gigId"])
        elif event["kind"] == "delivered":
            self.delivered(event["orderId"], event["leg"], event["at"])

    def facts_of(self, request_id: str) -> NoteFacts:
        """What the request's note says, read once (strategies/notes)."""
        return self.notes.read(self.requests[request_id])

    def delivered(self, order_id: str, leg: int, at: int) -> None:
        self.leg_gigs.get(order_id, {}).pop(leg, None)
        if order_id in self.orders:
            self.orders[order_id]["deliveredAt"][leg] = at

    def quote(self, request: PriceRequest) -> None:
        """Quotes the options that admission picks, at the price that strategies/pricing learns. A request
        admission declines gets a price far above the list price, which loses at no cost; up to level 3
        every quote wins, so no quote."""
        self.requests[request["id"]] = request
        held = [
            Held(o, bool(g := self.gigs_of(o["id"])) and all(x in self.booked for x in g)) for o in self.orders.values()
        ]
        # Admission weighs the margin at the price we would quote, and pricing prices the options it picks.
        # Params is frozen, so swap in a copy with the new factor.
        self.admission.params = replace(self.admission.params, price_factor=self.pricing.multiplier(request, self.now))
        verdict = self.admission.assess(request, held, self.now)
        facts = self.facts_of(request["id"])
        # The note's deadline passes before the car can be collected (strategies/notes): decline.
        hopeless = facts.deadline is not None and facts.deadline <= (facts.earliest_pickup or request["arrivedAt"])
        if verdict.accept and not hopeless:
            priced = self.pricing.price(request, self.now)
            prices = {kind: cents for kind, cents in priced.items() if kind in verdict.options}
        elif self.level > 3:
            prices = {o["kind"]: 10 * o["listPriceCents"] for o in request["options"][:1]}
        else:
            return
        self.outbox.append({"type": "quote", "requestId": request["id"], "prices": prices})

    def win(self, order: Order) -> None:
        if order["id"] in self.requests and order["id"] not in self.orders:  # rejoin can know it already
            self.orders[order["id"]] = order
            if self.level >= 3:  # gigs with several cars: bundling posts it, perhaps with other orders
                batch = self.requests[order["id"]].get("batchId")
                self.bundler.hold(order["id"], batch, order["lastPickupAt"], self.now)
            else:
                self.post(order, undelivered(order))

    def post_due(self) -> None:
        """Posts the new orders that bundling lets go now: each alone, or several in one gig (strategies/bundling)."""
        for group in self.bundler.due(self.now, self.unit):
            if len(group) == 1:
                self.post(self.orders[group[0].order_id], group[0].legs)
            else:
                stops = [stop for unit in group for stop in unit.stops]
                schedule = fees_plan(self.now, self.bundler.gig(group, self.now), self.level)
                self.outbox.append(
                    {"type": "post", "stops": stops, "audience": bundle_audience(group), "schedule": schedule}
                )

    def unit(self, order_id: str) -> Unit | None:
        """An order's undelivered cars as bundling sees them: the stops that `post` would send for them alone,
        with each stop's place, window and stated hours, or None when the order is gone."""
        order = self.orders.get(order_id)
        legs = undelivered(order) if order is not None else []
        if order is None or not legs:
            return None
        facts = self.facts_of(order_id)
        stops = without_windows(stops_for(order, legs, facts, FIRST_TRY, self.now, self.notes.snow), self.now)
        places, windows, hours = [], [], []
        for stop in stops:
            leg = order["legs"][stop["leg"]]
            side = leg["pickup"] if stop["kind"] == "pickup" else leg["delivery"]
            own: TimeWindow = (
                side["window"]
                if stop["kind"] == "pickup"
                else {"from": side["window"]["from"], "to": max(side["window"]["from"], order["deadline"])}
            )
            places.append(side["placeId"])
            windows.append(stop.get("window", own))
            hours.append(side["hours"])
        share = len(legs) / len(order["legs"])
        return Unit(
            order_id=order_id,
            legs=legs,
            stops=stops,
            places=places,
            windows=windows,
            hours=hours,
            audience=audience_for(order, legs, facts),
            typical=self.fees.typical(order, self.requests[order_id]) * share,
            price=order["priceCents"] * share,
            last_pickup_at=order["lastPickupAt"],
        )

    def change(self, order: Order) -> None:
        if order["id"] in self.orders:
            self.orders[order["id"]] = order
            if self.bundler.holds(order["id"]):  # not posted yet: it goes from the pool with the new plan
                return
            if self.withdraw(order["id"]):
                self.post(order, undelivered(order))

    def repost(self, gig_id: str) -> None:
        """Posts a gig again when one of its windows ended before a driver booked it. A bundle goes again as
        one gig for each order."""
        action = self.posts.get(gig_id)
        if action is None:
            return
        if len(orders_in(action)) > 1:
            self.bundler.counts["expired"] += 1
        for order_id in orders_in(action):
            own = [stop for stop in action["stops"] if stop["orderId"] == order_id]
            # A gig the starter has already taken off and posted again, after a change of plan, needs nothing.
            if not any(self.leg_gigs.get(order_id, {}).get(stop["leg"]) == gig_id for stop in own):
                continue
            for stop in own:
                self.leg_gigs.get(order_id, {}).pop(stop["leg"], None)
            order = self.orders.get(order_id)
            if order is None:
                continue
            # One of its windows has ended, perhaps at a site's closing time before the window's own end: post
            # without its own stop windows, except the pickup window that the note still needs.
            stops = [self.noted_pickup(stop) for stop in without_windows(own, float("inf"))]
            cars = sum(1 for stop in own if stop["kind"] == "pickup")
            self.outbox.append({**action, "stops": stops, "schedule": self.fees_for(order, cars)})

    def noted_pickup(self, stop: StopRef) -> StopRef:
        """A pickup inside what the note says, from now on: after the car is ready and inside the real hours."""
        order = self.orders.get(stop["orderId"])
        if stop["kind"] != "pickup" or stop["leg"] != 0 or order is None:
            return stop
        leg = order["legs"][0]
        snow = self.notes.snow_at(leg["pickup"]["placeId"], leg["delivery"]["placeId"])
        window = pickup_window(
            leg["pickup"]["window"], leg["pickup"]["hours"], self.facts_of(order["id"]), self.now, snow=snow
        )
        return {**stop, "window": window} if window else stop

    def raise_fees(self, order_id: str) -> None:
        """At the order's deadline warning, its gigs that no driver holds go at the fees planned from now."""
        order = self.orders.get(order_id)
        if order is None:
            return
        if self.bundler.holds(order_id):  # still waiting for a bundle: it goes alone now
            self.bundler.forget(order_id)
            self.post(order, undelivered(order))
            return
        self.send_post_of(order_id)
        for gig_id in self.gigs_of(order_id):
            if gig_id in self.posts and len(orders_in(self.posts[gig_id])) > 1 and gig_id not in self.booked:
                self.bundler.counts["split at warning"] += 1
                self.split(gig_id)  # a bundle that found no driver: each order's cars go alone, at their own fees
            elif gig_id not in self.booked:
                schedule = self.fees_for(order, pickups(self.posts[gig_id]))
                self.outbox.append({"type": "reprice", "gigId": gig_id, "schedule": schedule})
                self.ladders.pop(gig_id, None)  # the warning's fee replaces the ladder's
                self.offers.reschedule(gig_id, schedule)
                self.offers.rescue(gig_id)

    def fees_for(self, order: Order, cars: int) -> list[FeeStep]:
        """The fees for some of the order's cars from now, planned back from its last pickup."""
        return self.fees.schedule(order, self.requests[order["id"]], cars, self.now)

    def dropped(self, gig_id: str) -> None:
        """After a drop, steps the fee up from the dropped one when the schedule has little time left."""
        action, fee = self.posts.get(gig_id), self.booked_fees.pop(gig_id, None)
        order = self.orders.get(action["stops"][0]["orderId"]) if action else None
        if action is None or fee is None or order is None or gig_id not in self.gigs_of(order["id"]):
            return
        if len(orders_in(action)) > 1:
            group = [unit for order_id in orders_in(action) if (unit := self.unit(order_id)) is not None]
            schedule = fees_after_drop(self.now, self.bundler.gig(group, self.now), self.level, fee) if group else None
        else:
            schedule = self.fees.after_drop(order, self.requests[order["id"]], pickups(action), self.now, fee)
        if schedule:
            self.outbox.append({"type": "reprice", "gigId": gig_id, "schedule": schedule})
            self.offers.reschedule(gig_id, schedule)

    def retry(self, order_id: str, leg: int, reason: str) -> None:
        if order_id in self.orders:
            order = self.orders[order_id]
            self.leg_gigs.get(order_id, {}).pop(leg, None)  # the world has taken the car out of the failed gig
            car_not_there = reason in ("not_ready", "closed")
            pickup_from = retry_from(order, self.requests[order_id], leg, self.now) if car_not_there else 0
            self.post(
                order, [leg], Retry(pickup_from, manual_licence=reason == "licence", plates=reason == "no_plates")
            )

    def post(self, order: Order, legs: list[int], retry: Retry = FIRST_TRY) -> None:
        facts = self.facts_of(order["id"])
        audience = audience_for(order, legs, facts, retry)
        stops = without_windows(stops_for(order, legs, facts, retry, self.now, self.notes.snow), self.now)
        self.outbox.append(
            {"type": "post", "stops": stops, "audience": audience, "schedule": self.fees_for(order, len(legs))}
        )
        if len(legs) == 1:
            return
        # A trade-in over the 12-hour limit for a gig with two cars goes as one gig per car.
        self.send()
        if not self.gigs_of(order["id"]):
            for leg in legs:
                self.post(order, [leg], retry)

    def gigs_of(self, order_id: str) -> list[str]:
        """The gigs that carry the order's undelivered legs: one, or one for each leg of a split trade-in."""
        return list(dict.fromkeys(self.leg_gigs.get(order_id, {}).values()))

    def carry(self, action: PostAction, gig_id: str) -> None:
        """Remembers a gig that the world accepted: the post that made it, and the legs it carries."""
        for stop in action["stops"]:
            self.leg_gigs.setdefault(stop["orderId"], {})[stop["leg"]] = gig_id
        self.posts[gig_id] = action
        if all(order_id in self.orders for order_id in orders_in(action)):
            self.offers.register(gig_id, gig_info(self.orders, action, self.admission.minutes), action["schedule"])
        if self.level == 1 and len(orders_in(action)) == 1 and (order := self.orders.get(orders_in(action)[0])):
            # The post went at the ladder's first fee: remember its raises (strategies/fees).
            posted = action["schedule"][0]
            steps = self.fees.ladder(order, self.requests[order["id"]], pickups(action), posted["at"])
            if len(steps) > 1 and steps[0]["feeCents"] == posted["feeCents"]:
                self.ladders[gig_id] = steps[1:]

    def withdraw(self, order_id: str) -> bool:
        """Takes an order's gigs out of the drivers' app. False, and nothing withdrawn, when a driver holds one of them.
        The other orders of a withdrawn bundle go again alone."""
        self.send_post_of(order_id)
        gigs = self.gigs_of(order_id)
        if any(gig_id in self.booked for gig_id in gigs):
            return False
        self.leg_gigs.pop(order_id, None)
        self.outbox += [{"type": "withdraw", "gigId": gig_id} for gig_id in gigs]
        for gig_id in gigs:
            self.offers.forget(gig_id)
            self.ladders.pop(gig_id, None)
            self.post_rest(gig_id, order_id)
        return True

    def split(self, gig_id: str) -> None:
        """Takes a bundle that no driver holds out of the app, and posts each of its orders' cars alone."""
        self.outbox.append({"type": "withdraw", "gigId": gig_id})
        self.offers.forget(gig_id)
        self.post_rest(gig_id, None)

    def post_rest(self, gig_id: str, skip: str | None) -> None:
        """Posts alone the cars that the gig carried for each order but `skip`: the gig has left the app."""
        action = self.posts.get(gig_id)
        for order_id in orders_in(action) if action else []:
            carried = self.leg_gigs.get(order_id, {})
            legs = [leg for leg, gig in carried.items() if gig == gig_id]
            if order_id == skip or not legs or order_id not in self.orders:
                continue
            for leg in legs:
                carried.pop(leg)
            self.post(self.orders[order_id], sorted(legs))

    def raises_due(self) -> list[Action]:
        """Level 1: reprices each gig that no driver has booked to its ladder's fee, once the raise is due."""
        actions: list[Action] = []
        for gig_id, steps in list(self.ladders.items()):
            due = [step for step in steps if step["at"] <= self.now]
            if not due:
                continue
            action, rest = self.posts.get(gig_id), steps[len(due) :]
            live = action is not None and any(gig_id in self.gigs_of(order_id) for order_id in orders_in(action))
            if rest and live:
                self.ladders[gig_id] = rest
            else:
                del self.ladders[gig_id]
            if live and gig_id not in self.booked:
                fee = due[-1]["feeCents"]
                actions.append({"type": "reprice", "gigId": gig_id, "schedule": [{"at": self.now, "feeCents": fee}]})
        return actions

    def next_raise(self) -> int | None:
        """The minute of the next ladder raise, or None. A post still in the outbox gets its ladder once the
        world accepts it, so the clock also stops at the next raise minute for it."""
        due = [steps[0]["at"] for steps in self.ladders.values()]
        if self.level == 1 and any(action["type"] == "post" for action in self.outbox):
            due.append((self.now // LADDER_STEP + 1) * LADDER_STEP)
        return min(due, default=None)

    def send_post_of(self, order_id: str) -> None:
        """A post of the order still in the outbox goes to the world now, so the starter knows its gig."""
        if any(action["type"] == "post" and order_id in orders_in(action) for action in self.outbox):
            self.send()

    def send(self) -> None:
        """Sends the outbox now. In practice, the outbox goes with the next advance instead."""
        actions, self.outbox = self.outbox, []
        if actions:
            self.read_results(actions, self.world.act(actions))

    def read_results(self, actions: list[Action], results: list[ActionResult]) -> None:
        """Remembers the gig of each post that the world accepted, and counts the offers it refused."""
        for action, result in zip(actions, results):
            if action["type"] == "post" and result["ok"] is True:
                self.carry(action, result["id"])
            elif action["type"] == "post" and len(orders_in(action)) > 1:  # a bundle the world refused: each alone
                self.bundler.counts["refused"] += 1
                print(f"Bundle refused: {result['reason']}", file=sys.stderr, flush=True)
                for order_id in orders_in(action):
                    if order_id in self.orders:
                        cars = [s["leg"] for s in action["stops"] if s["orderId"] == order_id and s["kind"] == "pickup"]
                        self.post(self.orders[order_id], cars)
            elif action["type"] == "offer" and result["ok"] is False:
                self.offers.refused(result["reason"])


def gig_info(orders: dict[str, Order], action: PostAction, minutes: dict[tuple[str, str], int]) -> GigInfo:
    """What offers need to know of a gig: where it starts and ends, by when, the drive, and who may take it."""
    stops = action["stops"]
    places = [
        orders[s["orderId"]]["legs"][s["leg"]]["pickup" if s["kind"] == "pickup" else "delivery"]["placeId"]
        for s in stops
    ]
    drive = sum(minutes.get((a, b), 0) for a, b in pairwise(places))
    return GigInfo(
        pickup=places[0],
        pickup_until=min(orders[order_id]["lastPickupAt"] for order_id in orders_in(action)),
        end=places[-1],
        drive=drive,
        manual=action["audience"]["manualLicence"],
        experienced=action["audience"]["experienced"],
    )


def retry_from(order: Order, request: PriceRequest, leg: int, now: int) -> int:
    """When to try a car again after a visit found it not ready or the site closed: two hours on, or,
    when the dealer moved the deadline for a car that is late, when the car should be ready by the
    same delay."""
    promised = next((o["deadline"] for o in request["options"] if o["kind"] == order["option"]), order["deadline"])
    delay = max(0, order["deadline"] - promised)
    return max(now + 2 * HOUR, order["legs"][leg]["pickup"]["window"]["from"] + delay)


def orders_in(action: PostAction | Gig) -> list[str]:
    """The orders whose cars a gig carries, in stop order: one, or several in a bundle."""
    return list(dict.fromkeys(stop["orderId"] for stop in action["stops"]))


def audience_for(order: Order, legs: list[int], facts: NoteFacts, retry: Retry = FIRST_TRY) -> Audience:
    """Who may take the order's cars: a premium car needs an experienced driver (the fine is €150 a car), and
    a manual car, by the note or a failed visit, a manual licence."""
    return {
        "experienced": any(leg["car"]["premium"] for leg in order["legs"]),
        "manualLicence": retry.manual_licence or (0 in legs and facts.manual),
    }


def undelivered(order: Order) -> list[int]:
    return [leg for leg in range(len(order["legs"])) if order["deliveredAt"][leg] is None]


def pickups(action: PostAction) -> int:
    """The cars a post carries."""
    return sum(1 for stop in action["stops"] if stop["kind"] == "pickup")


def without_windows(stops: list[StopRef], before: float) -> list[StopRef]:
    """Leaves out the stop windows that end before `before`, so the world's window applies: once the order's
    window has ended, it runs to the end of the world."""
    return [
        {k: v for k, v in stop.items() if k != "window"} if "window" in stop and stop["window"]["to"] < before else stop
        for stop in stops
    ]


def stops_for(
    order: Order, legs: list[int], facts: NoteFacts, retry: Retry, now: int, snow: dict[str, list[Snow]]
) -> list[StopRef]:
    """A pickup and a delivery for each leg. An electric car under 30% gets a charging stop.
    A stop has its own window only when the note or the retry makes it narrower. Without
    one, the world plans the pickup in the order's window and the delivery by the deadline.
    The note's facts are about the first car (strategies/notes)."""
    stops: list[StopRef] = []
    for leg in legs:
        car, pickup, delivery = order["legs"][leg]["car"], order["legs"][leg]["pickup"], order["legs"][leg]["delivery"]
        noted = facts if leg == 0 else NO_FACTS
        snowfalls = snow.get(pickup["placeId"], []) + snow.get(delivery["placeId"], [])
        pickup_window_ = pickup_window(pickup["window"], pickup["hours"], noted, now, retry.pickup_from, snowfalls)
        delivery_base: TimeWindow = {
            "from": delivery["window"]["from"],
            "to": max(delivery["window"]["from"], order["deadline"]),
        }
        delivery_window_ = delivery_window(delivery_base, delivery["hours"], noted)
        if pickup_window_ and pickup_window_["from"] > delivery_window_["to"]:
            delivery_window_ = delivery_base  # the car is late whatever: deliver it when the driver can
        low_battery = car["electric"] and car["chargePercent"] is not None and car["chargePercent"] < 30
        first: StopRef = {
            "orderId": order["id"],
            "leg": leg,
            "kind": "pickup",
            "withPlates": retry.plates or noted.plates,
            "withCharging": low_battery,
        }
        if pickup_window_:
            first["window"] = pickup_window_
        second: StopRef = {"orderId": order["id"], "leg": leg, "kind": "delivery"}
        stops += [first, narrower(second, delivery_window_, delivery_base)]
    return stops


def narrower(stop: StopRef, window: TimeWindow, base: TimeWindow) -> StopRef:
    return {**stop, "window": window} if window["from"] > base["from"] or window["to"] < base["to"] else stop


def play_practice(world: World, level: int) -> Counter[str]:
    """Steps the world from one event that needs an answer to the next, and stops at each midnight for a report.
    While price requests keep coming, it looks every POLL minutes instead of stopping at each one. Returns the
    reason for each stop: the kind of event that stopped it, "poll", "midnight" or "end"."""
    snapshot = world.snapshot()
    desk, ends_at = Desk(world, level, snapshot["now"]), snapshot["endsAt"]
    stops: Counter[str] = Counter()
    busy = False  # price requests came at the last stop, so more may follow
    while desk.now < ends_at:
        day, midnight = desk.now // DAY, (desk.now // DAY + 1) * DAY
        until, poll_at = (WAKE_ON_BUSY, desk.now + POLL) if busy else (WAKE_ON, ends_at)
        held_until = desk.bundler.next_due()  # an order waiting for a bundle must go when its wait ends
        if held_until is not None:
            poll_at = min(poll_at, max(desk.now + 1, held_until))
        raise_at = desk.next_raise()  # level 1: a gig that no driver has booked rises on its ladder
        if raise_at is not None:
            poll_at = min(poll_at, max(desk.now + 1, raise_at))
        # One request a step: the advance applies the outbox, then moves the clock.
        actions, desk.outbox = desk.outbox, []
        step = world.advance(until=until, max=min(ends_at, midnight, poll_at), actions=actions)
        desk.now = step["now"]  # what the results add to the outbox goes out at this minute
        desk.read_results(actions, step["results"])
        woke = next((e["kind"] for e in step["events"] if e["kind"] in until and e["at"] == desk.now), None)
        stops[woke or ("end" if desk.now >= ends_at else "midnight" if desk.now == midnight else "poll")] += 1
        busy = any(event["kind"] == "price_request" for event in step["events"])
        for event in step["events"]:
            desk.handle(event)
        desk.post_due()  # the new orders that bundling lets go now
        desk.outbox += desk.offers.due(desk.now)  # once all the step's events are read
        desk.outbox += desk.raises_due()
        if desk.now // DAY > day:
            report(WEEKDAYS[day % 7], world.score())
    for strategy in desk.strategies:  # a line on the week from each strategy that keeps one: offers, bundling
        if line := strategy.summary():
            print(line, flush=True)
    return stops


def play_final(world: World) -> None:
    """Rebuilds the books, then answers events as they come. After a second without an event,
    it reads the clock."""
    history = world.events()
    snapshot = world.snapshot()
    if snapshot["now"] >= snapshot["endsAt"]:
        return
    level = next((w["level"] for w in world.client.worlds() if w["worldId"] == world.id), 8)
    desk = Desk(world, level, snapshot["now"])
    desk.rejoin(snapshot, history)
    desk.send()
    for event in world.stream(after=history[-1]["seq"] if history else -1, idle=1.0):
        day = desk.now // DAY
        desk.now = world.client.final()["now"] if event is None else max(desk.now, event["at"])
        if event is not None:
            desk.handle(event)
        desk.post_due()
        desk.outbox += desk.offers.due(desk.now)
        desk.send()
        if desk.now // DAY > day:
            report(WEEKDAYS[day % 7], world.score())
        if desk.now >= snapshot["endsAt"]:
            return


def report(label: str, score: Score) -> None:
    orders = f"{score['wonOrders']:>4} orders  {score['onTimeShare']:6.1%} on time  {score['undeliveredShare']:5.1%} not delivered"
    print(
        f"{label:<9}  margin €{score['marginCents'] / 100:>11,.2f}  revenue €{score['revenueCents'] / 100:>11,.2f}  {orders}",
        flush=True,
    )


def count_requests(client: Client) -> Counter[str]:
    """Counts the client's requests from now on, by route: advance, actions, score, and so on."""
    counts: Counter[str] = Counter()
    call = client.call

    def counted(method: str, path: str, body: Any = None, actions: int = 0) -> Any:
        counts[path.split("?")[0].rstrip("/").rsplit("/", 1)[-1]] += 1
        return call(method, path, body, actions)

    client.call = counted  # type: ignore[method-assign]
    return counts


def report_requests(requests: Counter[str], stops: Counter[str]) -> None:
    """One line for the requests of the week, and one for the reasons of its advances."""
    print(f"Requests  {requests.total():,}: " + ", ".join(f"{route} {n:,}" for route, n in requests.most_common()))
    print(f"Stops     {stops.total():,}: " + ", ".join(f"{reason} {n:,}" for reason, n in stops.most_common()))


def next_final(client: Client) -> World:
    """Your copy of the final that is set or runs now. Waits while none is set and while the last one has
    ended: the organisers set a test final 15 minutes before its start, and the final 30 minutes before."""
    said = False
    while True:
        try:
            world: World | None = client.world(client.final()["worldId"])
        except SpreadError as error:
            if error.status != 404:
                raise
            world = None
        if world is not None:
            snapshot = world.snapshot()
            if snapshot["now"] < snapshot["endsAt"]:
                return world
        if not said:
            print(
                "No final is set. Waiting for it: the organisers set a test final 15 minutes before its start, and the final 30 minutes before.",
                flush=True,
            )
            said = True
        time.sleep(10)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plays a Spread world with a price ladder per dealer and a capacity shadow price. Set SPREAD_URL and SPREAD_KEY first."
    )
    parser.add_argument(
        "--level", type=int, choices=range(1, 9), default=8, help="the practice level, 1 to 8 (default 8)"
    )
    parser.add_argument("--seed", help="any text; the same seed gives the same world")
    parser.add_argument(
        "--board",
        action="store_true",
        help="play your next ranking run at the level; it counts in the practice rankings",
    )
    parser.add_argument("--final", action="store_true", help="play your copy of the final from the live stream")
    args = parser.parse_args()
    try:
        client = ProxyClient()
        requests = count_requests(client)
        score, stop_reasons = None, None
        recorder: Recorder | None = None  # saves the week to data/scrape/runs and the database once it has ended
        if args.final:
            world = None
            # A server restart drops every connection. The desk then rebuilds its books from the server, as after its own restart.
            while True:
                try:
                    if world is None:
                        world = next_final(client)
                        print(f"Final world {world.id}.", flush=True)
                        level = next((w["level"] for w in client.worlds() if w["worldId"] == world.id), 8)
                        recorder = Recorder(world, level, None, "final")
                    play_final(world)
                    score = world.score()
                    break
                except Unreachable as error:
                    print(f"spread: {error}. Trying again in 5 seconds.", file=sys.stderr, flush=True)
                    time.sleep(5)
        else:
            world = client.create(level=args.level, seed=args.seed, board=args.board)
            # A ranking run that a team deletes plays to its end without the team's system, and counts.
            name = f"{'Ranking run' if args.board else 'Practice world'} {world.id}"
            stops = (
                "Ctrl-C or an error stops your system: the run then plays to its end without it, and counts."
                if args.board
                else "Ctrl-C or an error stops the run and deletes the world."
            )
            print(f"{name}, level {args.level}. {stops}", flush=True)
            try:
                recorder = Recorder(world, args.level, args.seed, "board" if args.board else "practice")
                stop_reasons = play_practice(world, args.level)
            except BaseException as error:  # a world left behind holds one of the team's eight practice slots
                try:
                    world.delete()
                    deleted = True
                except SpreadError:
                    deleted = False
                after = (
                    f"{name} plays to its end without your system, and counts."
                    if args.board
                    else f"{name} is deleted."
                    if deleted
                    else f"{name} is not deleted: it holds one of your eight practice slots."
                )
                if isinstance(error, KeyboardInterrupt):
                    sys.exit(f"Stopped. {after}")
                print(f"Stopped by the error below. {after}", file=sys.stderr)
                raise
        score = score or world.score()
        report("End", score)
        if stop_reasons is not None:
            report_requests(requests, stop_reasons)
        print(
            "Ranked."
            if score["ranked"]
            else "Not ranked: no order won."
            if score["wonOrders"] == 0
            else "Not ranked: the delivery minimum is 90% of the orders on time."
        )
        if recorder is not None:
            recorder.save()
    except SpreadError as error:
        sys.exit(f"spread: {error}")
    except KeyboardInterrupt:
        sys.exit("Stopped. The final world keeps running without your system; start it again with --final.")


if __name__ == "__main__":
    main()
