"""The starter: a whole dispatch system that you can read in five minutes, then change. HANDBOOK.md says
what it does and how to run it (`spread-starter --help` lists the options).

To change it, copy this file and run the copy: python dispatch.py
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from typing import Any, NamedTuple

from spread.client import Client, SpreadError, Unreachable, World
from spread.starter import window_from_note  # noqa: F401  # the starter's reader, which tests/test_dispatch.py imports
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

from record import Recorder
from spread_proxy import ProxyClient
from strategies.admission import Admission, Held
from strategies.notes import NO_FACTS, NoteFacts, Snow, delivery_window, pickup_window, read_note
from strategies.pricing import PricingModel, places_from_map

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
        self.urgent: set[str] = set()  # the orders whose deadline warning has come
        self.facts: dict[str, NoteFacts] = {}  # request id -> what its note says
        self.snow: dict[str, list[Snow]] = {}  # place id -> the snowfalls forecast there
        # Decides which requests to take, from the driver list and the map, loaded once (strategies/admission).
        world_map = world.client.map()
        self.admission = Admission(world.roster(), world_map, level)
        self.pricing = PricingModel(level, places_from_map(world_map))  # the price of a quote (strategies/pricing)

    def rejoin(self, snapshot: DeskSnapshot, history: list[DeskEvent]) -> None:
        """Rebuilds what it knows from the world, so a starter that stopped keeps its orders. Then answers
        what it missed: open requests, orders without a gig, failed visits without a new gig, and the
        deadline warnings, so the orders that had one keep their steep fees."""
        posted: dict[str, list[Gig]] = {}  # order id -> its gigs, oldest first
        self.booked = {gig["id"] for gig in snapshot["gigs"] if gig["status"] in ("booked", "working", "done")}
        for gig in snapshot["gigs"]:
            posted.setdefault(gig["stops"][0]["orderId"], []).append(gig)
            if gig["status"] in ("open", "booked", "working"):
                self.carry(
                    {"type": "post", "stops": gig["stops"], "audience": gig["audience"], "schedule": gig["schedule"]},
                    gig["id"],
                )
        self.requests = {e["request"]["id"]: e["request"] for e in history if e["kind"] == "price_request"}
        # The history rebuilds dealer trust. It cannot tell the quotes admission declined from the others,
        # so the price multiplier learns again from the level's start.
        for event in history:
            self.pricing.observe(event)
            if event["kind"] == "forecast":
                self.forecast(event)
        self.urgent = {e["orderId"] for e in history if e["kind"] == "deadline_close"}
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
        for event in history:
            self.admission.observe(event)
        for request in snapshot["openRequests"]:
            self.quote(request)

    def handle(self, event: DeskEvent) -> None:
        self.admission.observe(event)
        self.pricing.observe(event)
        if event["kind"] == "price_request":
            self.quote(event["request"])
        elif event["kind"] == "order_won":
            self.win(event["order"])
        elif event["kind"] == "order_changed":
            self.change(event["order"])
        elif event["kind"] == "order_cancelled":  # the world has stopped the car and told each of its gigs what happens
            for books in (self.orders, self.leg_gigs):
                books.pop(event["orderId"], None)
        elif event["kind"] == "visit_failed":
            self.retry(event["orderId"], event["leg"], event["reason"])
        elif event["kind"] == "gig_expired":
            self.repost(event["gigId"])
        elif event["kind"] == "deadline_close":  # it comes again when a driver drops the car after the first warning
            self.raise_fees(event["orderId"])
        elif event["kind"] == "gig_booked":
            self.booked.add(event["gigId"])
        elif event["kind"] in (
            "gig_dropped",
            "no_show",
        ):  # after a no-show the gig is open again; a late driver still comes
            self.booked.discard(event["gigId"])
        elif event["kind"] == "delivered":
            self.delivered(event["orderId"], event["leg"], event["at"])
        elif event["kind"] == "forecast":
            self.forecast(event)

    def forecast(self, event: DeskEvent) -> None:
        for place in event["placeIds"]:
            self.snow.setdefault(place, []).append((event["from"], event["to"]))

    def facts_of(self, request_id: str) -> NoteFacts:
        """What the request's note says, read once. The note speaks of the first car: in a trade-in, the new car."""
        if request_id not in self.facts:
            request = self.requests[request_id]
            self.facts[request_id] = read_note(request["note"] and request["note"]["text"], request["arrivedAt"])
        return self.facts[request_id]

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
        self.admission.params.price_factor = self.pricing.multiplier(request, self.now)
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
            self.post(order, undelivered(order))

    def change(self, order: Order) -> None:
        if order["id"] in self.orders:
            self.orders[order["id"]] = order
            if self.withdraw(order["id"]):
                self.post(order, undelivered(order))

    def repost(self, gig_id: str) -> None:
        """Posts a gig again when one of its windows ended before a driver booked it."""
        action = self.posts.get(gig_id)
        # A gig the starter has already taken off and posted again, after a change of plan, needs nothing.
        if action is None or not any(
            self.leg_gigs.get(s["orderId"], {}).get(s["leg"]) == gig_id for s in action["stops"]
        ):
            return
        for stop in action["stops"]:
            self.leg_gigs.get(stop["orderId"], {}).pop(stop["leg"], None)
        order = self.orders.get(action["stops"][0]["orderId"])
        if order is None:
            return
        # One of its windows has ended, perhaps at a site's closing time before the window's own end: post without its own stop windows,
        # except the pickup window that the note still needs.
        stops = [self.noted_pickup(stop) for stop in without_windows(action["stops"], float("inf"))]
        self.outbox.append({**action, "stops": stops, "schedule": self.fees_for(order, pickups(action))})

    def noted_pickup(self, stop: StopRef) -> StopRef:
        """A pickup inside what the note says, from now on: after the car is ready and inside the real hours."""
        order = self.orders.get(stop["orderId"])
        if stop["kind"] != "pickup" or stop["leg"] != 0 or order is None:
            return stop
        leg = order["legs"][0]
        snow = self.snow.get(leg["pickup"]["placeId"], []) + self.snow.get(leg["delivery"]["placeId"], [])
        window = pickup_window(
            leg["pickup"]["window"], leg["pickup"]["hours"], self.facts_of(order["id"]), self.now, snow=snow
        )
        return {**stop, "window": window} if window else stop

    def raise_fees(self, order_id: str) -> None:
        """From the order's deadline warning on, its gigs that no driver holds go at the steep fees."""
        order = self.orders.get(order_id)
        if order is None:
            return
        self.urgent.add(order_id)
        self.send_post_of(order_id)
        for gig_id in self.gigs_of(order_id):
            if gig_id not in self.booked:
                self.outbox.append(
                    {"type": "reprice", "gigId": gig_id, "schedule": self.fees_for(order, pickups(self.posts[gig_id]))}
                )

    def fees_for(self, order: Order, cars: int) -> list[FeeStep]:
        """The fees for some of the order's cars from now: rising, or steep once its deadline warning has come."""
        fee = self.requests[order["id"]]["referenceFeeCents"] * cars / len(order["legs"])
        return steep(self.now, fee, self.level) if order["id"] in self.urgent else rising(self.now, fee, self.level)

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
        # A premium car needs an experienced driver: the fine is €150 a car.
        facts = self.facts_of(order["id"])
        audience: Audience = {
            "experienced": any(leg["car"]["premium"] for leg in order["legs"]),
            "manualLicence": retry.manual_licence or (0 in legs and facts.manual),
        }
        stops = without_windows(stops_for(order, legs, facts, retry, self.now, self.snow), self.now)
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

    def withdraw(self, order_id: str) -> bool:
        """Takes an order's gigs out of the drivers' app. False, and nothing withdrawn, when a driver holds one of them."""
        self.send_post_of(order_id)
        gigs = self.gigs_of(order_id)
        if any(gig_id in self.booked for gig_id in gigs):
            return False
        self.leg_gigs.pop(order_id, None)
        self.outbox += [{"type": "withdraw", "gigId": gig_id} for gig_id in gigs]
        return True

    def send_post_of(self, order_id: str) -> None:
        """A post of the order still in the outbox goes to the world now, so the starter knows its gig. Each gig carries one order."""
        if any(action["type"] == "post" and action["stops"][0]["orderId"] == order_id for action in self.outbox):
            self.send()

    def send(self) -> None:
        """Sends the outbox now. In practice, the outbox goes with the next advance instead."""
        actions, self.outbox = self.outbox, []
        if actions:
            self.read_results(actions, self.world.act(actions))

    def read_results(self, actions: list[Action], results: list[ActionResult]) -> None:
        """Remembers the gig of each post that the world accepted."""
        for action, result in zip(actions, results):
            if action["type"] == "post" and result["ok"] is True:
                self.carry(action, result["id"])


def retry_from(order: Order, request: PriceRequest, leg: int, now: int) -> int:
    """When to try a car again after a visit found it not ready or the site closed: two hours on, or,
    when the dealer moved the deadline for a car that is late, when the car should be ready by the
    same delay."""
    promised = next((o["deadline"] for o in request["options"] if o["kind"] == order["option"]), order["deadline"])
    delay = max(0, order["deadline"] - promised)
    return max(now + 2 * HOUR, order["legs"][leg]["pickup"]["window"]["from"] + delay)


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


def rising(now: int, fee: float, level: int) -> list[FeeStep]:
    """The fee at once, then 10% of it more every hour: six steps, up to 1.5 times. Level 1 takes one fee only."""
    # int(x + 0.5) rounds halves up, as JavaScript's Math.round does, so both starters post the same fees.
    return [
        {"at": now + k * HOUR, "feeCents": max(1, int(fee * (1 + k / 10) + 0.5))} for k in range(1 if level == 1 else 6)
    ]


def steep(now: int, fee: float, level: int) -> list[FeeStep]:
    """1.5 times the fee at once, then a quarter of it more every half hour, up to 2.5 times. Level 1 takes one fee only."""
    return [
        {"at": now + k * 30, "feeCents": max(1, int(fee * (1.5 + k / 4) + 0.5))} for k in range(1 if level == 1 else 5)
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
        # One request a step: the advance applies the outbox, then moves the clock.
        actions, desk.outbox = desk.outbox, []
        step = world.advance(until=until, max=min(ends_at, midnight, poll_at), actions=actions)
        desk.read_results(actions, step["results"])
        desk.now = step["now"]
        woke = next((e["kind"] for e in step["events"] if e["kind"] in until and e["at"] == desk.now), None)
        stops[woke or ("end" if desk.now >= ends_at else "midnight" if desk.now == midnight else "poll")] += 1
        busy = any(event["kind"] == "price_request" for event in step["events"])
        for event in step["events"]:
            desk.handle(event)
        if desk.now // DAY > day:
            report(WEEKDAYS[day % 7], world.score())
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
        description="Plays a Spread world with the starter. Set SPREAD_URL and SPREAD_KEY first."
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
