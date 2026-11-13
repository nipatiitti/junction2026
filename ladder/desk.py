"""The desk: what we know of the week, and our answer to it.

Events only update what we know (`handle`). Decisions come once a step, after all of its events (`tick`): quote the
requests that wait for an answer, post every car that has no live gig, and reprice the gigs whose plan changed. A
step that missed something, or a desk that restarts in the final, catches up at its next tick.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path

from spread.client import World
from spread.types import (
    Action,
    ActionResult,
    Audience,
    DeskEvent,
    DeskEventKind,
    DeskSnapshot,
    FeeStep,
    Order,
    PostAction,
    PriceRequest,
    StopRef,
)

from ladder import fees
from ladder.admission import Admission
from ladder.market import Market
from ladder.pricing import Pricing
from ladder.rides import RUNGS, Ride, classify, needs_charging, next_morning
from strategies.notes import NO_FACTS, NoteFacts, Snow, delivery_window, pickup_window, read_note

HOUR, DAY = 60, 24 * 60
# The events that need an answer. The rest (views, bookings, deliveries, account lines) arrive with the next stop.
WAKE_ON: list[DeskEventKind] = [
    "price_request",
    "order_won",
    "order_changed",
    "order_cancelled",
    "visit_failed",
    "gig_expired",
    "deadline_close",
    "gig_dropped",
    "no_show",
]
# While requests keep coming, the clock stops at least every POLL minutes instead of at each request or win: the
# dealer decides at respondBy, 15 minutes after the request, so a request seen at the next stop is still in time.
WAKE_ON_BUSY: list[DeskEventKind] = [k for k in WAKE_ON if k not in ("price_request", "order_won")]
POLL = 14
RETRY_AFTER = 2 * HOUR  # a car that was not ready, or a closed site, is tried again this much later
TWELVE_HOURS = 12 * HOUR  # a gig with more than one car may plan at most this much driving
REFUSALS = 3  # posts of one car the world may refuse in a row before the desk pauses between posts of it
TOMORROW = True  # rung 4: post a car ready today as a gig for the next business morning


LIVE = ("open", "booked", "working", "withdrawing")


@dataclass
class Gig:
    """One of our gigs, as we posted it, and what has happened to it."""

    id: str
    order_id: str
    legs: list[int]
    action: PostAction
    status: str = "open"  # open, booked, working, done, gone
    booked_fee: int = 0  # the fee its driver booked it at
    first: bool = True  # the first gig of its car, at a normal schedule: its booking teaches the opening fee
    opened: int = 0  # the fee it opened at, before any reprice

    @property
    def schedule(self) -> list[FeeStep]:
        return self.action["schedule"]


@dataclass
class Job:
    """One of our orders: the order as the world last told it, and the gig of each undelivered leg."""

    order: Order
    request: PriceRequest
    ride: Ride
    gigs: dict[int, str] = field(default_factory=dict)  # leg -> the live gig that carries it
    warned: bool = False  # deadline_close has come and no driver has held the car since
    # After a failed visit: when to try the pickup again, and what the driver needs.
    pickup_from: dict[int, int] = field(default_factory=dict)
    manual: set[int] = field(default_factory=set)
    plates: set[int] = field(default_factory=set)
    posted: set[int] = field(default_factory=set)  # legs that have had a gig
    plain: set[int] = field(default_factory=set)  # legs to post without windows of their own, after a refusal
    refusals: dict[int, int] = field(default_factory=dict)  # leg -> posts of it the world refused
    next_try: dict[int, int] = field(default_factory=dict)  # leg -> no post before this minute, after refusals

    def undelivered(self) -> list[int]:
        return [leg for leg, at in enumerate(self.order["deliveredAt"]) if at is None]


class Desk:
    def __init__(self, world: World, level: int, now: int, rung: int, journal: Path | None = None):
        self.world, self.level, self.now, self.rung = world, level, now, rung
        # In the final, each real quote that the world accepts goes to this file, so a desk that restarts learns its
        # price again from the outcomes of those quotes only: a decline, or a request that came while no desk ran,
        # always loses.
        self.journal = journal
        self.meant: set[str] = set()  # requests we quote for real (not declines), until the world answers the quote
        self.market = Market(world.client.map(), world.roster())
        self.pricing = Pricing(level)
        self.admission = Admission(self.market, level, rung)
        self.opening = fees.Opening()
        self.outbox: list[Action] = []
        self.requests: dict[str, PriceRequest] = {}
        self.rides: dict[str, Ride] = {}
        self.facts: dict[str, NoteFacts] = {}  # request id -> what its note says, read once
        self.snow: dict[str, list[Snow]] = {}  # place id -> the snowfalls forecast there
        self.answered: set[str] = set()  # requests we have quoted or declined
        self.jobs: dict[str, Job] = {}  # order id -> our order, while it is not cancelled
        self.gigs: dict[str, Gig] = {}
        self.posting: set[tuple[str, int]] = set()  # (order, leg) with a post on its way to the world
        self.reprice: set[str] = set()  # gigs to reprice at the next tick
        self.revenue: set[str] = set()  # orders whose revenue line came in this step: trust counts them at the tick
        self.refunded: set[str] = set()  # orders with a late refund or an undelivered penalty
        self.busy = False  # requests came at the last stop, so more may follow
        self.count: Counter[str] = Counter()  # for the summary at the end

    # The loop

    def waking(self) -> tuple[list[DeskEventKind], int]:
        """The event kinds that stop the clock, and the minute to look at the latest."""
        return (WAKE_ON_BUSY, self.now + POLL) if self.busy else (WAKE_ON, self.now + 7 * DAY)

    def send(self) -> None:
        """Sends the outbox now, as the final does. In practice the outbox goes with the next advance."""
        actions, self.outbox = self.outbox, []
        if actions:
            self.read_results(actions, self.world.act(actions))

    def read_results(self, actions: list[Action], results: list[ActionResult]) -> None:
        for action, result in zip(actions, results):
            kind = action["type"]
            self.count[f"{kind}{'' if result['ok'] else ' refused'}"] += 1
            if kind == "post":
                for stop in action["stops"]:
                    self.posting.discard((stop["orderId"], stop["leg"]))
                if result["ok"] is True:
                    self.carry(action, result["id"])
                else:
                    self.refused(action, result["reason"])
            elif kind == "quote" and action["requestId"] in self.meant:
                self.meant.discard(action["requestId"])
                if result["ok"]:
                    self.note_quote(action["requestId"])
            elif kind == "withdraw" and action["gigId"] in self.gigs:
                gig = self.gigs[action["gigId"]]
                if gig.status == "withdrawing":  # gone: its cars go again; refused: a driver had booked it
                    gig.status = "gone" if result["ok"] else "booked"

    def save_opening(self) -> None:
        """In the final, the learned opening fees go next to the journal, so a desk that restarts keeps them."""
        if self.journal is None:
            return
        try:
            self.journal.with_suffix(".opening.json").write_text(json.dumps(self.opening.state()))
        except OSError:
            pass  # a restart then starts the opening fees again from their priors

    def load_opening(self) -> None:
        try:
            if self.journal is not None and self.journal.with_suffix(".opening.json").exists():
                self.opening.load(json.loads(self.journal.with_suffix(".opening.json").read_text()))
        except OSError, ValueError:
            pass

    def note_quote(self, request_id: str) -> None:
        """Writes a real quote to the journal. A journal that cannot be written is given up, not a crash."""
        if self.journal is None:
            return
        try:
            with self.journal.open("a") as journal:
                journal.write(request_id + "\n")
        except OSError as error:
            print(f"Cannot write {self.journal}: {error}. Going on without it.", file=sys.stderr, flush=True)
            self.journal = None

    def refused(self, action: PostAction, reason: str) -> None:
        """A post the world refused, usually for a stop window. The car goes again at the next tick without windows
        of its own, so the order's windows apply, or run to the end of the world. After REFUSALS refusals in a row it
        goes again only after a pause that doubles each time, from an hour: a post the world keeps refusing never
        loops, and the car is never given up, since a car not delivered costs twice its price."""
        print(f"Post refused: {reason}", file=sys.stderr, flush=True)
        job = self.jobs.get(action["stops"][0]["orderId"])
        if job is not None:
            for leg in {stop["leg"] for stop in action["stops"]}:
                job.pickup_from.pop(leg, None)
                job.plain.add(leg)
                job.refusals[leg] = job.refusals.get(leg, 0) + 1
                if job.refusals[leg] >= REFUSALS:
                    job.next_try[leg] = self.now + HOUR * 2 ** min(6, job.refusals[leg] - REFUSALS)

    # What we know

    def handle(self, event: DeskEvent) -> None:
        kind = event["kind"]
        self.pricing.observe(event)
        self.admission.observe(event, self.now)
        if kind == "price_request":
            self.busy = True
            self.requests[event["request"]["id"]] = event["request"]
        elif kind == "order_won":
            self.won(event["order"])
        elif kind == "order_changed":
            job = self.jobs.get(event["order"]["id"])
            if job is not None:
                job.order = event["order"]  # an open gig follows its order's places and windows
                job.warned = False  # a new last pickup minute: a new warning comes if it needs one
                for gig_id in set(job.gigs.values()):
                    if self.gigs[gig_id].status == "open":
                        self.changed(job, self.gigs[gig_id])
        elif kind == "order_cancelled":
            if self.jobs.pop(event["orderId"], None) is not None:
                self.count["cancelled"] += 1
            for gig in event["gigs"]:
                if gig["gigId"] in self.gigs and gig["outcome"] != "shortened":
                    self.gigs[gig["gigId"]].status = "gone"
        elif kind in ("gig_booked", "offer_answered"):
            gig = self.gigs.get(event["gigId"])
            if gig is not None and (kind == "gig_booked" or event["answer"] == "accepted"):
                gig.status, gig.booked_fee = "booked", event.get("feeCents", gig.booked_fee)
                self.reprice.discard(gig.id)
                job = self.jobs.get(gig.order_id)
                if job is not None:
                    job.warned = False
                    if gig.first and kind == "gig_booked":
                        self.opening.booked(job.ride.rung, gig.opened, gig.booked_fee)
                        gig.first = False
                        self.save_opening()
        elif kind in ("gig_dropped", "no_show"):
            gig = self.gigs.get(event["gigId"])
            if gig is not None and gig.status in ("booked", "open"):
                gig.status = "open"  # the gig is in the app again with its schedule
                self.reprice.add(gig.id)
                self.count[kind.replace("_", " ")] += 1
        elif kind == "gig_started":
            if event["gigId"] in self.gigs:
                self.gigs[event["gigId"]].status = "working"
        elif kind == "gig_expired":
            gig = self.gigs.get(event["gigId"])
            if gig is not None and gig.status == "open":
                gig.status = "gone"  # its cars go again at the next tick
                self.count["expired"] += 1
                job = self.jobs.get(gig.order_id)
                if job is not None and gig.first:
                    self.opening.expired(job.ride.rung)
                    self.save_opening()
        elif kind == "visit_failed":
            self.failed(event["orderId"], event["leg"], event["reason"])
        elif kind == "delivered":
            job = self.jobs.get(event["orderId"])
            if job is not None:
                job.order["deliveredAt"][event["leg"]] = event["at"]
                job.gigs.pop(event["leg"], None)
                gig = self.gigs.get(event["gigId"])
                if gig is not None and not job.gigs.keys() & set(gig.legs):
                    gig.status = "done"
        elif kind == "deadline_close":
            job = self.jobs.get(event["orderId"])
            if job is not None:
                job.order["lastPickupAt"] = event["lastPickupAt"]
                job.warned = True
                self.reprice.update(g for g in job.gigs.values() if self.gigs[g].status == "open")
                self.count["warnings"] += 1
        elif kind == "forecast":
            for place in event["placeIds"]:
                self.snow.setdefault(place, []).append((event["from"], event["to"]))
        elif kind == "ledger":
            line = event["line"]
            if line["orderId"] and line["kind"] == "revenue":
                self.revenue.add(line["orderId"])
            elif line["orderId"] and line["kind"] in ("late_refund", "undelivered_penalty"):
                self.refunded.add(line["orderId"])

    def won(self, order: Order) -> None:
        request = self.requests.get(order["id"])
        if request is None or order["id"] in self.jobs:
            return
        ride = self.rides.get(order["id"]) or classify(request, self.market, self.facts_of(request))
        self.jobs[order["id"]] = Job(order, request, ride)
        self.count[f"won rung {ride.rung}"] += 1

    def failed(self, order_id: str, leg: int, reason: str) -> None:
        """The driver could not collect the car, and the world took it out of the gig. It goes again at the next
        tick, without the cause."""
        job = self.jobs.get(order_id)
        if job is None:
            return
        gig = self.gigs.get(job.gigs.pop(leg, ""))
        if gig is not None and not job.gigs.keys() & set(gig.legs):
            gig.status = "gone"
        if reason in ("not_ready", "closed"):
            job.pickup_from[leg] = self.now + RETRY_AFTER
        elif reason == "licence":
            job.manual.add(leg)
        elif reason == "no_plates":
            job.plates.add(leg)
        self.count[f"failed visits ({reason})"] += 1

    # Decisions

    def tick(self) -> None:
        """Answers everything that waits: quotes, posts, reprices, and the dealers' trust."""
        waiting = [r for r in self.requests.values() if r["id"] not in self.answered and r["respondBy"] > self.now]
        for request in waiting:
            self.quote(request)
        self.busy = bool(waiting) or self.busy and any(r["respondBy"] > self.now for r in self.requests.values())
        for job in list(self.jobs.values()):
            self.post(job)
        for gig_id in sorted(self.reprice):
            self.repriced(gig_id)
        self.reprice.clear()
        for order_id in self.revenue:
            job = self.jobs.get(order_id)
            if job is not None:
                on_time = order_id not in self.refunded
                self.pricing.delivered(job.order["dealerId"], on_time)
                self.admission.delivered(job.ride, on_time)
        self.revenue.clear()

    def quote(self, request: PriceRequest) -> None:
        """Quotes the options that admission picks, at the learned price; declines the rest."""
        self.answered.add(request["id"])
        ride = self.rides.setdefault(request["id"], classify(request, self.market, self.facts_of(request)))
        kinds = self.admission.options(request, ride, self.now, self.load())
        self.count[f"requests rung {ride.rung}"] += 1
        if kinds:
            prices = self.pricing.prices(request, kinds, ride.rung)
            self.pricing.sent(request, kinds, ride.rung)
            self.admission.quoted(request, ride)
            self.meant.add(request["id"])
            self.outbox.append({"type": "quote", "requestId": request["id"], "prices": prices})
            self.count[f"quoted rung {ride.rung}"] += 1
        elif self.level > 3:  # a price far above the list price loses at no cost; up to level 3 every quote wins
            first = request["options"][0]
            self.outbox.append(
                {"type": "quote", "requestId": request["id"], "prices": {first["kind"]: 10 * first["listPriceCents"]}}
            )

    def load(self) -> list[Ride]:
        """Our rides that still wait for a driver, for admission to weigh a new request against."""
        waiting = []
        for job in self.jobs.values():
            held = bool(job.gigs) and all(self.gigs[g].status in ("booked", "working") for g in job.gigs.values())
            if job.undelivered() and not held:
                waiting.append(job.ride)
        return waiting

    def post(self, job: Job) -> None:
        """Posts the undelivered cars of the order that have no live gig. A trade-in whose two cars both wait goes
        as one gig when its drive fits the 12-hour rule: the old car's pickup comes right after the new car's
        delivery, so the driver collects it in the same visit. Every other car goes in a gig of its own."""
        order = job.order
        waiting = []
        for leg in job.undelivered():
            gig_id = job.gigs.get(leg)
            if gig_id is not None and self.gigs[gig_id].status in LIVE:
                continue
            job.gigs.pop(leg, None)
            if (order["id"], leg) not in self.posting and job.next_try.get(leg, 0) <= self.now:
                waiting.append(leg)
        together = self.level >= 3 and not job.refusals  # gigs with several cars start at level 3
        if waiting == [0, 1] and together and self.trade_in_drive(order) <= TWELVE_HOURS:
            self.post_legs(job, [0, 1])
        else:
            for leg in waiting:
                self.post_legs(job, [leg])

    def post_legs(self, job: Job, legs: list[int]) -> None:
        order = job.order
        action: PostAction = {
            "type": "post",
            "stops": [stop for leg in legs for stop in self.stops(job, leg)],
            "audience": {
                "experienced": any(self.audience(job, leg)["experienced"] for leg in legs),
                "manualLicence": any(self.audience(job, leg)["manualLicence"] for leg in legs),
            },
            "schedule": self.schedule(job, legs),
        }
        self.outbox.append(action)
        self.posting.update((order["id"], leg) for leg in legs)
        self.count["late posts" if self.now >= order["lastPickupAt"] else "posts"] += 1

    def fee_base(self, job: Job, legs: list[int]) -> float:
        """The typical fee for some of the order's cars. When the dealer has sent a car farther than the request
        said (order_changed), it grows with the drive: the driver of a farther car wants more."""
        share = job.request["referenceFeeCents"] * len(legs) / len(job.order["legs"])
        asked = sum(self.leg_drive(job.request["legs"][leg]) for leg in legs)
        now = sum(self.leg_drive(job.order["legs"][leg]) for leg in legs)
        return share * max(1.0, now / asked) if asked else share

    def leg_drive(self, leg: dict) -> int:
        return self.market.drive(leg["pickup"]["placeId"], leg["delivery"]["placeId"])

    def trade_in_drive(self, order: Order) -> int:
        """Road minutes of a trade-in in one gig: new car out, to the old car's pickup, old car back."""
        places = [order["legs"][leg][stop]["placeId"] for leg in (0, 1) for stop in ("pickup", "delivery")]
        return sum(self.market.drive(a, b) for a, b in pairwise(places))

    def stops(self, job: Job, leg: int) -> list[StopRef]:
        """A pickup and a delivery. Without a note they have no windows of their own: the world plans them in the
        order's windows, cut to the sites' stated hours, and once those have ended they run to the end of the world.
        The note of the first car narrows them (strategies/notes): the pickup from when the car is ready or released,
        inside the site's real hours and after snow for a car on summer tyres, the delivery by the note's deadline
        and inside real hours. A pickup tried again after a failed visit starts later. An electric car under 30%
        on a route over 200 km gets a charging stop (rule 3), and a car without plates gets them on the way."""
        order, facts = job.order, self.facts_of(job.request) if leg == 0 else NO_FACTS
        pickup_place, delivery_place = order["legs"][leg]["pickup"], order["legs"][leg]["delivery"]
        pickup: StopRef = {
            "orderId": order["id"],
            "leg": leg,
            "kind": "pickup",
            "withPlates": leg in job.plates or facts.plates,
            "withCharging": needs_charging(self.market, order["legs"][leg]),
        }
        delivery: StopRef = {"orderId": order["id"], "leg": leg, "kind": "delivery"}
        late = self.now >= order["lastPickupAt"]
        # A late car's pickup may run on after the order's window: only the note's start and hours still hold.
        stated = pickup_place["window"]
        if late:
            stated = {"from": stated["from"], "to": max(stated["to"], self.now + 7 * DAY)}
        snow = self.snow.get(pickup_place["placeId"], []) + self.snow.get(delivery_place["placeId"], [])
        if leg in job.plain:  # the world refused this car's windows: the order's own apply
            return [pickup, delivery]
        not_before = job.pickup_from.get(leg, 0)
        if not late and self.tomorrow(job, leg):
            not_before = max(not_before, next_morning(self.now))
        window = pickup_window(stated, pickup_place["hours"], facts, self.now, not_before, snow)
        if window is None and not_before > self.now:
            window = {"from": not_before, "to": max(stated["to"], not_before + 7 * DAY)}
        # A private seller's slot is fixed: the world plans the pickup in it, and books the next business day's
        # slot itself when it passes (order_changed). A window of our own there could only be refused.
        if window is not None and window["to"] > self.now and not pickup_place["privateAddress"]:
            pickup["window"] = window
        if facts and not late:
            base = {
                "from": delivery_place["window"]["from"],
                "to": max(delivery_place["window"]["from"], order["deadline"]),
            }
            narrow = delivery_window(base, delivery_place["hours"], facts)
            if narrow != base and narrow["to"] > self.now and narrow["to"] >= pickup.get("window", stated)["from"]:
                delivery["window"] = narrow
        return [pickup, delivery]

    def tomorrow(self, job: Job, leg: int) -> bool:
        """Rung 4: a car that is ready today, won on a later option, goes as a gig for the next business morning.
        Drivers book a gig for the next day at once and rarely book one that is ready now (README.md)."""
        if not TOMORROW or leg != 0 or not job.ride.today or job.order["option"] == "same_day":
            return False
        if job.order["legs"][0]["pickup"]["privateAddress"]:
            return False  # a private seller's slot is fixed
        morning = next_morning(self.now)
        return job.order["legs"][0]["pickup"]["window"]["to"] - morning >= job.ride.drive + HOUR

    def audience(self, job: Job, leg: int) -> Audience:
        """A premium car needs an experienced driver (a fine of €150 otherwise); a manual car a manual licence."""
        manual = leg in job.manual or (leg == 0 and self.facts_of(job.request).manual)
        return {"experienced": job.order["legs"][leg]["car"]["premium"], "manualLicence": manual}

    def facts_of(self, request: PriceRequest) -> NoteFacts:
        """What the request's note says, read once (strategies/notes). It speaks of the first car."""
        if request["id"] not in self.facts:
            note = request["note"]
            self.facts[request["id"]] = read_note(note and note["text"], request["arrivedAt"])
        return self.facts[request["id"]]

    def schedule(self, job: Job, legs: list[int], floor: int = 0) -> list[FeeStep]:
        """The fee plan from now for a gig of some of the order's cars: normal while the car can be on time, steep
        after its deadline warning, and the late plan once its last pickup minute has passed."""
        fee, last_pickup = self.fee_base(job, legs), job.order["lastPickupAt"]
        price = job.order["priceCents"] * len(legs) / len(job.order["legs"])  # the price of the gig's cars
        if self.now >= last_pickup:
            return fees.late(self.now, fee, self.level, floor, price)
        if job.warned:
            return fees.warned(self.now, fee, self.level, floor)
        # A short ride's typical fee is a small share of its price and can be less than the trip there and home
        # costs a driver: such cars got deadline warnings ten times as often. They open at a share of the price.
        opening = max(self.opening.multiple(job.ride.rung), fees.PRICE_SHARE * price / fee)
        return fees.normal(self.now, fee, last_pickup, self.level, opening, floor)

    def carry(self, action: PostAction, gig_id: str) -> None:
        """Remembers a gig the world accepted, and the legs it carries."""
        order_id = action["stops"][0]["orderId"]
        legs = sorted({stop["leg"] for stop in action["stops"]})
        job = self.jobs.get(order_id)
        # Only a car's first gig, posted at the normal plan, teaches the opening fee.
        first = (
            job is not None and not job.warned and not job.posted & set(legs) and self.now < job.order["lastPickupAt"]
        )
        self.gigs[gig_id] = Gig(gig_id, order_id, legs, action, first=first, opened=action["schedule"][0]["feeCents"])
        if job is not None:
            for leg in legs:
                job.gigs[leg] = gig_id
                job.posted.add(leg)
                job.pickup_from.pop(leg, None)
                job.refusals.pop(leg, None)
                job.next_try.pop(leg, None)

    def repriced(self, gig_id: str) -> None:
        """A new schedule for an open gig: after a drop or a no-show (that driver wants more), a deadline warning,
        or a change of plan that moved the last pickup minute. No fee falls below the fee in the app now."""
        gig = self.gigs.get(gig_id)
        job = self.jobs.get(gig.order_id) if gig else None
        if gig is None or job is None or gig.status != "open":
            return
        floor = max(fees.now_fee(gig.schedule, self.now), int(gig.booked_fee * fees.REBOOK))
        schedule = self.schedule(job, gig.legs, floor)
        gig.action = {**gig.action, "schedule": schedule}
        self.outbox.append({"type": "reprice", "gigId": gig_id, "schedule": schedule})

    def changed(self, job: Job, gig: Gig) -> None:
        """After a change of plan, an open gig keeps its stops: when a car now needs a charging stop it did not
        (it goes farther), the gig is withdrawn and the car goes again at the next tick. Else it is repriced."""
        stale = any(
            stop["kind"] == "pickup"
            and stop.get("withCharging", False) != needs_charging(self.market, job.order["legs"][stop["leg"]])
            for stop in gig.action["stops"]
        )
        if not stale:
            self.reprice.add(gig.id)
            return
        # The car goes again once the world confirms the withdrawal (read_results): a driver may book the gig first.
        self.outbox.append({"type": "withdraw", "gigId": gig.id})
        gig.status = "withdrawing"

    # The final: rebuild what we know from the world

    def rejoin(self, snapshot: DeskSnapshot, history: list[DeskEvent]) -> None:
        """Rebuilds the books from the world's events and its snapshot, so a desk that stopped in the final keeps
        its orders, its learned prices and the dealers' trust. The next tick answers whatever waits."""
        refunded = {
            e["line"]["orderId"]
            for e in history
            if e["kind"] == "ledger" and e["line"]["kind"] in ("late_refund", "undelivered_penalty")
        }
        self.load_opening()
        try:
            quoted = set(self.journal.read_text().split()) if self.journal and self.journal.exists() else set()
        except OSError:
            quoted = set()
        for event in history:
            if event["kind"] == "price_request":
                self.requests[event["request"]["id"]] = event["request"]
                self.answered.add(event["request"]["id"])
            elif event["kind"] in ("order_won", "order_lost"):
                request_id = event["order"]["id"] if event["kind"] == "order_won" else event["requestId"]
                request = self.requests.get(request_id)
                if request is not None and request_id in quoted:  # learn again from our real quotes only
                    rung = classify(request, self.market, self.facts_of(request)).rung
                    self.pricing.sent(request, [o["kind"] for o in request["options"]], rung)
                self.pricing.observe(event)
            elif event["kind"] == "deadline_close":
                self.admission.observe(event, event["at"])
            elif event["kind"] == "ledger" and event["line"]["kind"] == "revenue" and event["line"]["orderId"]:
                request = self.requests.get(event["line"]["orderId"])
                if request is not None:
                    on_time = event["line"]["orderId"] not in refunded
                    self.pricing.delivered(request["dealerId"], on_time)
                    self.admission.delivered(classify(request, self.market, self.facts_of(request)), on_time)
        for request in snapshot["openRequests"]:
            self.requests[request["id"]] = request
            self.answered.discard(request["id"])
        for order in snapshot["orders"]:
            request = self.requests.get(order["id"])
            if request is not None and order["status"] != "cancelled":
                self.jobs[order["id"]] = Job(order, request, classify(request, self.market, self.facts_of(request)))
        for gig in snapshot["gigs"]:
            if gig["status"] in LIVE:
                action: PostAction = {
                    "type": "post",
                    "stops": gig["stops"],
                    "audience": gig["audience"],
                    "schedule": gig["schedule"],
                }
                self.carry(action, gig["id"])
                self.gigs[gig["id"]].first = False  # its first schedule is unknown: it teaches nothing
                self.gigs[gig["id"]].status = gig["status"]
                self.gigs[gig["id"]].booked_fee = gig["feeCents"] if gig["status"] != "open" else 0
        # An order is warned when its last deadline warning came after its last change of plan and booking.
        gig_order = {gig["id"]: gig["stops"][0]["orderId"] for gig in snapshot["gigs"]}
        warned: dict[str, bool] = {}
        for event in history:
            if event["kind"] == "deadline_close":
                warned[event["orderId"]] = True
            elif event["kind"] == "order_changed":
                warned[event["order"]["id"]] = False
            elif event["kind"] == "gig_booked" and event["gigId"] in gig_order:
                warned[gig_order[event["gigId"]]] = False
        for order_id in {o for o, w in warned.items() if w} & self.jobs.keys():
            job = self.jobs[order_id]
            job.warned = all(self.gigs[g].status == "open" for g in job.gigs.values())
        for event in history:
            if event["kind"] == "forecast":
                self.handle(event)
            elif event["kind"] == "visit_failed" and event["orderId"] in self.jobs:
                # What the driver needed: a car without a live gig now goes again with it.
                job, leg = self.jobs[event["orderId"]], event["leg"]
                if event["reason"] == "licence":
                    job.manual.add(leg)
                elif event["reason"] == "no_plates":
                    job.plates.add(leg)
                elif leg not in job.gigs:
                    job.pickup_from[leg] = max(self.now, event["at"] + RETRY_AFTER)

    def summary(self) -> str:
        counts = ", ".join(f"{name} {n:,}" for name, n in sorted(self.count.items()))
        rungs = ", ".join(RUNGS[: self.rung])
        return "\n".join(
            [
                f"Ladder, rung {self.rung} ({rungs}): {counts}",
                self.admission.summary(),
                self.pricing.summary(),
                self.opening.summary(),
            ]
        )
