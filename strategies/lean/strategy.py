"""The lean strategy (`src/strategies/lean/index.ts`): the whole policy in three decisions, each from the measured
level 8 facts (src/strategies/lean/README.md).

1. Price. Each option is quoted at the price that earns the most: the chance that the dealer takes it (demand.py,
   learned from this week's wins and losses) times what the win leaves after the drivers.
2. Fee. A gig holds `open` × typical and raises only a few times, by the drivers' planning (fees.py): drivers who
   see fees rise wait for the rise. It climbs fast only when the last pickup is near.
3. Serve. Only options that can arrive on time with room to spare are quoted, and the note decides the windows,
   plates and licence of every gig (ops.py). Open cars that one driver can take in a row go out as one gig
   (planner.py, chains.py).

All state is rebuilt from `observe` and `sent`, so a restart in the final loses nothing. The harness (harness.py)
gives every call the books: the desk, read-only."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, fields, replace
from typing import Any

from spread.types import DriverProfile, WorldMap

from strategies.lean.demand import Demand, best_price
from strategies.lean.fees import BOOK_AHEAD, SHORT, awake, fast, fee_at, stepped
from strategies.lean.js import INF, clamp, js_round
from strategies.lean.note import earliest_pickup, read_note
from strategies.lean.offers import Offers
from strategies.lean.ops import FIRST_TRY, Context, Retry, Roads, can_serve, features, gig_shape, retry_after
from strategies.lean.outlook import Work, load_orders, outlook
from strategies.lean.planner import Planner, pickups
from strategies.lean.supply import Supply
from strategies.strategy import Strategy

HOUR, DAY = 60, 24 * 60


@dataclass(frozen=True)
class Params:
    """The defaults of `lean`, named as in index.ts so `--set key=value` and the saved settings read the same."""

    target: float = 0.3  # the share of the week's requests to win, in a world with 777 drivers
    capacity: float = 0  # the worth of an order's place in the week × typical; 0 with `gain` 0: off
    gain: float = 0
    flatShare: float = 0.5  # how much of that worth is the same for every order (`flatEuros` × `capacity`)
    flatEuros: float = 60
    open: float = 0.88  # the fee a gig opens at, × typical
    jitter: float = 1  # each gig's raises move by up to 1.5 hours and 5%, drawn from the order id
    spread: bool = True  # time the raises by the drivers' planning (fees.plan_by)
    premium: float = 3  # a premium car's cost × this
    privatePickup: float = 0.25  # what a private pickup and a private delivery add × typical
    privateDelivery: float = 0.25
    early: float = 0.8  # the fee a gig for a later day shows in its first hour, × typical
    feeRatio: float = 0.84  # what a booking costs × typical before this week's bookings say
    supply: bool = True  # learn the booking cost by pickup place, delivery place and today's pickups
    order: bool = True  # price each request by the order model (outlook.py)
    lateCost: float = 1  # × the list price for each unit of chance to be late
    overhead: float = 0.06  # added to the cost × typical for drops, failed visits and refunds
    minHours: float = 4  # waking hours an option needs to book a driver, or we do not quote it
    minMargin: float = 1.05  # never quote under this × the expected cost
    noise: float = 0.28  # the noise that stays in one request's threshold, as a logistic scale in log price
    trust: float = 0.7  # how much of the dealer's trust goes into the price
    feeBrake: float = 1.5  # how much the target falls for each 1.0 × typical that bookings cost over `feeRatio`
    lateSoft: float = 0.04  # the late share from which we win less
    lateHard: float = 0.05  # and the one from which options need twice the room
    openGigs: float = 40  # open gigs without a driver from which we win less
    offers: float = 0  # direct offers at the app's fee × this; 0 sends none
    urgentTop: float = 2  # the top of the fast climb × typical
    lateTop: float = 1.7  # and for a car that is late already
    chains: bool = True  # post open cars together when one driver can take them one after the other
    maxHop: float = 60
    maxCars: int = 4
    minSaving: float = 0.15
    chainHours: float = 5
    holdHours: float = 2  # a new car that may join a chain waits this many hours for a partner
    chainPatience: float = 0
    chainBid: bool = False  # plan the chain before the bid
    pairCharge: float = 1


def with_overrides(params: Params, pairs: list[str]) -> Params:
    """The params with each `key=value` set, as `--set` does in the TypeScript system: the key must be a param, and
    the value of the same type (a number, true or false)."""
    kinds = {f.name: type(getattr(params, f.name)) for f in fields(params)}
    changes: dict[str, Any] = {}
    for pair in pairs:
        key, sep, text = pair.partition("=")
        if not sep:
            raise SystemExit(f'"{pair}" is not key=value')
        if key not in kinds:
            raise SystemExit(f'lean has no param "{key}": {", ".join(kinds)}')
        try:
            value = json.loads(text)
        except ValueError:
            value = text
        kind = kinds[key]
        if kind is bool and not isinstance(value, bool) or kind is not bool and isinstance(value, bool):
            raise SystemExit(f"lean param {key} takes a {'boolean' if kind is bool else 'number'}")
        if kind is not bool and not isinstance(value, int | float):
            raise SystemExit(f"lean param {key} takes a number")
        changes[key] = value
    return replace(params, **changes)


class Lean(Strategy[Params]):
    every = 15  # minutes between two ticks

    def __init__(self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None):
        super().__init__(roster, world_map, level, params or Params())
        p = self.params
        self.books: Any = None  # the desk, which the harness sets before it asks anything
        self.roads = Roads(dict(world_map))
        self.supply = Supply(p.feeRatio)
        self.outlooks = load_orders() if p.order and level >= 7 else None
        self.homes: dict[str, int] = {}  # place id -> the drivers who live there
        for driver in roster:
            self.homes[driver["homePlaceId"]] = self.homes.get(driver["homePlaceId"], 0) + 1
        self.won_on: dict[int, int] = {}  # day -> the orders won on it
        self.offers = Offers(self.roads, list(roster))
        self.demand = Demand(level, p.noise)
        self.drivers = len(roster) / 777 if roster else 1
        self.capacity = p.capacity
        self.fee_ratio = p.feeRatio
        self.planner = Planner(
            p,
            self.roads,
            p.chains and level >= 3,
            context=lambda: self.context(),
            troubled=lambda order_id, gig_id: (
                f"{order_id} 0" in self.retries or (gig_id is not None and gig_id in self.dropped)
            ),
        )
        self.pending: dict[str, dict] = {}  # our quotes that wait for the dealer: request id -> prices
        self.asked: list[tuple[str, str | None, int]] = []  # waiting requests: id, the first car's yard, respondBy
        self.schedules: dict[str, list[dict]] = {}  # gig id -> the schedule in the app
        self.dropped: dict[str, int] = {}  # gig id -> the fee its driver booked at, for gigs a driver gave back
        self.booked_at: dict[str, int] = {}
        self.retries: dict[str, Retry] = {}  # "<order id> <leg>" -> what the car's setbacks taught
        self.floors: dict[str, int] = {}  # order id -> the fee that its last gig showed when its window ended
        self.forecasts: list[dict] = []
        self.delivered: dict[str, list[str]] = {}  # dealer id -> its delivered orders, in order
        self.late: set[str] = set()
        self.done = 0
        self.tally = {"requests": 0, "quoted": 0, "won": 0, "multiples": 0.0, "bookings": 0, "ratios": 0.0}

    # ----------------------------------------------------------------------------------------------- the price

    def quote(self, request: dict, books: Any) -> dict | None:
        now = books.now
        p = self.params
        late_share = self.late_share(books)
        context = self.context(0.5 if late_share > p.lateHard else 1)
        facts = read_note(request.get("note"), request["arrivedAt"])
        options = request["options"][:1] if self.level <= 3 else request["options"]
        quotes: dict[str, int] = {}
        for option in options:
            if not can_serve(request, option, now, context):
                continue
            if self.level <= 3:
                return {option["kind"]: option["listPriceCents"]}
            alone = self.cost(request, option, facts, now, books)
            if alone is None:
                continue
            share = self.planner.share(request, option, facts, books)
            cost = alone * share
            belief = self.demand.belief(Demand.keys(request, option["kind"]), self.trust_offset(request["dealerId"]))
            crowd = 1 + 0.04 * max(0, self.asked_from(request) - 4)
            place = (1 - p.flatShare) * request["referenceFeeCents"] + p.flatShare * p.flatEuros * 100
            charge = cost + self.capacity * crowd * place * (p.pairCharge if share < 1 else 1)
            best = best_price(belief, option["listPriceCents"], charge)
            if best is None:
                continue
            quotes[option["kind"]] = js_round(max(best, cost * p.minMargin))
        return quotes or None

    def cost(self, request: dict, option: dict, facts: Any, now: int, books: Any) -> float | None:
        """What the drivers of an option cost: the typical fee × what bookings pay this week, more when the gig has
        little time to find its driver or is work that drivers ask more for."""
        p = self.params
        f = features(request, self.roads, option)
        deadline = min(option["deadline"], INF if facts.deadline is None else facts.deadline)
        last_pickup = deadline - 1.1 * self.roads.drive(request["legs"]) - 30
        if awake(now + 15, last_pickup - BOOK_AHEAD) < p.minHours * HOUR:
            return None  # too little time for the raises to find a driver
        leg = request["legs"][0] if request["legs"] else None
        today = last_pickup < (now // DAY + 1) * DAY
        learned = self.supply.ratio(
            self.supply.keys(
                leg["pickup"]["placeId"] if leg else None, leg["delivery"]["placeId"] if leg else None, today
            )
        )
        ratio = (learned if p.supply else self.fee_ratio) + p.overhead
        if self.outlooks:
            ready = max(leg["pickup"]["window"]["from"] if leg else now, earliest_pickup(facts) or 0)
            cost, late = outlook(
                self.outlooks,
                Work(
                    typical_cents=request["referenceFeeCents"],
                    at=now,
                    ready_at=ready,
                    last_pickup_at=last_pickup,
                    deadline=deadline,
                    drive_minutes=self.roads.drive([leg]) if leg else 0,
                    private_pickup=f.private_pickup,
                    private_delivery=f.private_delivery,
                    premium=f.premium,
                    electric=any(leg_["car"]["electric"] for leg_ in request["legs"]),
                    trade_in=f.trade_in,
                    has_note=bool(request.get("note")),
                    home_pickup=self.homes.get(leg["pickup"]["placeId"] if leg else "", 0),
                    home_delivery=self.homes.get(leg["delivery"]["placeId"] if leg else "", 0),
                    drivers=len(self.roster) or 777,
                    won=self.tally["won"],
                    won_today=self.won_on.get(now // DAY, 0),
                    open=self.open_gigs(books),
                ),
            )
            ratio *= cost
            if f.premium:
                ratio *= p.premium
            return request["referenceFeeCents"] * ratio + late * p.lateCost * option["listPriceCents"]
        if f.private_pickup:
            ratio += p.privatePickup
        elif f.private_delivery:
            ratio += p.privateDelivery
        if f.trade_in:
            ratio += 0.05
        if f.weekend_delivery:
            ratio += 0.05
        if facts.deadline is not None or facts.pickup_hours is not None or facts.delivery_hours is not None:
            ratio += 0.03
        if f.premium:
            ratio *= p.premium
        return request["referenceFeeCents"] * ratio

    @staticmethod
    def open_gigs(books: Any) -> int:
        """Our gigs open without a driver now."""
        return sum(
            1 for order in books.orders.values() for gig_id in books.gigs_of(order["id"]) if gig_id not in books.booked
        )

    def target(self, books: Any) -> float:
        """The share of the requests to win now: less when bookings cost more than planned, when gigs wait without a
        driver, and when orders arrive late."""
        p = self.params
        return (
            p.target
            * self.drivers
            * clamp(1 - p.feeBrake * (self.fee_ratio - p.feeRatio), 0.5, 1.25)
            * clamp(2 - self.open_gigs(books) / p.openGigs, 0.4, 1)
            * clamp(1 - 10 * max(0, self.late_share(books) - p.lateSoft), 0.2, 1)
        )

    def late_share(self, books: Any) -> float:
        """Late orders, and half of each one warned without a driver, over the orders done (and 20 on time)."""
        at_risk = 0
        for order_id in books.urgent:
            order = books.orders.get(order_id)
            waits = (
                order is not None
                and any(at is None for at in order["deliveredAt"])
                and not any(g in books.booked for g in books.gigs_of(order_id))
            )
            if waits:
                at_risk += 1
        return (len(self.late) + 0.5 * at_risk) / (self.done + at_risk + 20)

    def trust_offset(self, dealer_id: str) -> float:
        """The dealer's trust as a move of its threshold: each order on time adds 1%, a late one halves the count."""
        return self.params.trust * math.log(1 + self.trust_count(dealer_id) / 100)

    def trust_count(self, dealer_id: str) -> int:
        count = 0
        for order_id in self.delivered.get(dealer_id, []):
            count = count // 2 if order_id in self.late else min(25, count + 1)
        return count

    def asked_from(self, request: dict) -> int:
        """The other requests from the same yard that wait for their dealer: a bulk order asks for 30 to 40 at once."""
        yard = request["legs"][0]["pickup"]["placeId"] if request["legs"] else None
        return sum(1 for other, at, _ in self.asked if at == yard and other != request["id"])

    def outcome(self, request_id: str, won: str | None, books: Any) -> None:
        """A quote won (with the option the dealer took) or lost: the demand learns."""
        self.planner.release(request_id)
        prices = self.pending.pop(request_id, None)
        request = books.requests.get(request_id)
        if not prices or not request:
            return
        offset = self.trust_offset(request["dealerId"])
        for option in request["options"]:
            cents = prices.get(option["kind"])
            if cents is None or (won and option["kind"] != won):
                continue
            multiple = cents / option["listPriceCents"]
            self.demand.learn(Demand.keys(request, option["kind"]), offset, multiple, won is not None)
            if won:
                self.tally["multiples"] += multiple
        if won:
            self.tally["won"] += 1
            day = books.now // DAY
            self.won_on[day] = self.won_on.get(day, 0) + 1
        self.capacity = clamp(self.capacity + self.params.gain * ((1 if won else 0) - self.target(books)), 0, 2)

    # ------------------------------------------------------------------------------------------------- the gig

    def gig(self, need: dict, books: Any) -> list[dict]:
        order, legs, previous = need["order"], need["legs"], need.get("previous")
        request = books.requests.get(order["id"])
        if not request:
            raise ValueError(f"no request for order {order['id']}")
        now = books.now
        if need["why"] == "urgent" and previous:
            gig_id = next((g for g in books.gigs_of(order["id"]) if books.posts.get(g) is previous), None)
            # A gig that a driver gave back starts again from the fee that booked it.
            if gig_id is None:
                shown = 0
            elif gig_id in self.dropped:
                shown = self.dropped[gig_id]
            else:
                known = self.schedules.get(gig_id)
                shown = fee_at(previous["schedule"] if known is None else known, now)
            schedule = self.fees(order, self.typical_of(previous["stops"], books), now, shown, True)
            return [{"stops": previous["stops"], "audience": previous["audience"], "schedule": schedule}]
        facts = read_note(request.get("note"), request["arrivedAt"])
        shapes = gig_shape(order, legs, facts, self.retry_of(order["id"], legs), now, self.context())
        if not shapes:
            raise ValueError(f"cannot read order {order['id']}")
        floor = self.floors.get(order["id"], 0)
        return [
            {**shape, "schedule": self.fees(order, self.typical_of(shape["stops"], books), now, floor)}
            for shape in shapes
        ]

    def fees(self, order: dict, typical: float, now: int, floor: float, warned: bool = False) -> list[dict]:
        """The schedule of a gig from now, never under `floor` cents."""
        p = self.params
        shown = floor / typical
        if now > order["lastPickupAt"]:
            return fast(now, typical, max(shown, 1.1), 0.05, 30, p.lateTop)
        if warned or awake(now, order["lastPickupAt"] - BOOK_AHEAD) < SHORT:
            return fast(now, typical, max(shown + 0.05, 1.15), 0.12, 15, max(p.urgentTop, shown + 0.05))
        return stepped(now, typical, order["lastPickupAt"], p.open, shown, p.jitter, order["id"], p.spread, p.early)

    def retry_of(self, order_id: str, legs: list[int]) -> Retry:
        tries = [self.retries.get(f"{order_id} {leg}", FIRST_TRY) for leg in legs] or [FIRST_TRY]
        combined = tries[0]
        for other in tries[1:]:
            combined = Retry(
                pickup_from=max(combined.pickup_from, other.pickup_from),
                manual_licence=combined.manual_licence or other.manual_licence,
                plates=combined.plates or other.plates,
                late=combined.late or other.late,
            )
        return combined

    def setback(self, order_id: str, leg: int, reason: str, books: Any) -> None:
        order = books.orders.get(order_id)
        if not order:
            return
        key = f"{order_id} {leg}"
        before = self.retries.get(key, FIRST_TRY)
        self.retries[key] = retry_after(reason, order, books.requests.get(order_id), leg, books.now, before)

    def tick(self, books: Any) -> list[dict]:
        """A gig that a driver gave back takes a new schedule from the fee that booked it; then the chains."""
        actions: list[dict] = []
        for gig_id, fee in list(self.dropped.items()):
            del self.dropped[gig_id]
            post = books.posts.get(gig_id)
            order = books.orders.get(post["stops"][0]["orderId"]) if post and post["stops"] else None
            request = books.requests.get(order["id"]) if order else None
            if not post or not order or not request or gig_id in books.booked:
                continue
            if gig_id not in books.gigs_of(order["id"]):
                continue
            schedule = self.fees(order, self.typical_of(post["stops"], books), books.now, fee)
            if schedule:
                actions.append({"type": "reprice", "gigId": gig_id, "schedule": schedule})
        if self.params.offers > 0 and self.level >= 3:
            actions += self.offers.actions(
                books, lambda gig_id: self.params.offers * fee_at(self.schedules.get(gig_id, []), books.now)
            )
        return [*actions, *self.planner.actions(books)]

    def hold(self, need: dict, books: Any) -> bool:
        return self.planner.hold(need, books)

    def singles_of(self, stops: list[dict], books: Any) -> float:
        """The typical fees of a gig's cars as single gigs, summed."""
        total = 0.0
        for stop in pickups(stops):
            request = books.requests.get(stop["orderId"])
            if request:
                order = books.orders.get(stop["orderId"])
                cars = len(order["legs"]) if order else len(request["legs"])
                total += request["referenceFeeCents"] / cars
        return total

    def typical_of(self, stops: list[dict], books: Any) -> float:
        """The unit of a gig's fee schedule: what a chain is worth to its driver, or the cars' typical fees."""
        chained = self.planner.typical(stops)
        return chained if chained is not None else self.singles_of(stops, books)

    # ----------------------------------------------------------------------------------------------- the books

    def observe(self, event: dict) -> None:
        books, kind = self.books, event["kind"]
        if kind == "price_request":
            request = event["request"]
            self.tally["requests"] += 1
            self.demand.dawn(event["at"] // DAY)
            self.asked = [entry for entry in self.asked if entry[2] > event["at"]]
            yard = request["legs"][0]["pickup"]["placeId"] if request["legs"] else None
            self.asked.append((request["id"], yard, request["respondBy"]))
        elif kind == "gig_viewed":
            if self.params.offers > 0:
                self.offers.viewed(event["gigId"], event["driverId"])
        elif kind == "offer_answered":
            self.offers.answered(event["answer"] == "accepted")
        elif kind == "order_won":
            self.outcome(event["order"]["id"], event["order"]["option"], books)
        elif kind == "order_lost":
            self.outcome(event["requestId"], None, books)
        elif kind == "gig_booked":
            self.booked(event, books)
        elif kind in ("gig_dropped", "no_show"):
            self.dropped[event["gigId"]] = self.booked_at.get(event["gigId"], 0)
        elif kind == "visit_failed":
            self.setback(event["orderId"], event["leg"], event["reason"], books)
        elif kind == "gig_expired":
            post = books.posts.get(event["gigId"])
            stops = post["stops"] if post else []
            self.planner.expired(event["gigId"], stops)
            for stop in pickups(stops):
                self.setback(stop["orderId"], stop["leg"], "expired", books)
                schedule = self.schedules.get(event["gigId"])
                if schedule is None:
                    schedule = post["schedule"] if post else []
                self.floors[stop["orderId"]] = fee_at(schedule, event["at"])
        elif kind == "forecast":
            self.forecasts.append({"from": event["from"], "to": event["to"], "placeIds": event["placeIds"]})
        elif kind == "ledger":
            line = event["line"]
            order_id = line.get("orderId")
            if not order_id:
                return
            if line["kind"] in ("late_refund", "undelivered_penalty"):
                self.late.add(order_id)
            request = books.requests.get(order_id)
            if line["kind"] == "revenue" and request:
                self.done += 1
                self.delivered.setdefault(request["dealerId"], []).append(order_id)

    def booked(self, event: dict, books: Any) -> None:
        gig_id = event["gigId"]
        self.dropped.pop(gig_id, None)
        self.booked_at[gig_id] = event["feeCents"]
        post = books.posts.get(gig_id)
        singles = self.singles_of(post["stops"], books) if post else 0
        if not post or not singles > 0:
            return
        self.planner.booked(gig_id, event["feeCents"] / singles)
        ratio = clamp(event["feeCents"] / singles, 0.3, 2.5)
        for stop in pickups(post["stops"]):
            order = books.orders.get(stop["orderId"])
            if not order or stop["leg"] >= len(order["legs"]):
                continue
            leg = order["legs"][stop["leg"]]
            today = order["lastPickupAt"] < (event["at"] // DAY + 1) * DAY
            self.supply.learn(self.supply.keys(leg["pickup"]["placeId"], leg["delivery"]["placeId"], today), ratio)
        # A chain counts once for each of its cars: the cost behind a bid is a car's, not a booking's.
        for _ in pickups(post["stops"]):
            self.fee_ratio += 0.04 * (ratio - self.fee_ratio)
        self.tally["bookings"] += 1
        self.tally["ratios"] += ratio

    def sent(self, action: dict, result: dict, books: Any) -> None:
        self.planner.sent(action, result, books)
        if not result.get("ok"):
            return
        if action["type"] == "quote":
            self.pending[action["requestId"]] = action["prices"]
            self.tally["quoted"] += 1
        elif action["type"] == "post":
            self.schedules[result["id"]] = action["schedule"]
        elif action["type"] == "reprice":
            self.schedules[action["gigId"]] = action["schedule"]

    def summary(self) -> str:
        t = self.tally
        share = 100 * t["won"] / t["requests"] if t["requests"] > 0 else 0
        multiple = t["multiples"] / t["won"] if t["won"] > 0 else 0
        paid = t["ratios"] / t["bookings"] if t["bookings"] > 0 else 0
        return (
            f"lean: won {t['won']} of {t['requests']} requests ({share:.1f}%) at {multiple:.2f} × list, "
            f"{t['bookings']} bookings at {paid:.2f} × typical, capacity worth {self.capacity:.2f} × typical at the end, "
            f"{len(self.late)} late of {self.done} done. {self.planner.summary()} "
            f"Offers: {self.offers.accepted} accepted of {self.offers.sent}."
        )

    def context(self, tightening: float = 1) -> Context:
        return Context(self.roads, self.forecasts, self.level, tightening)
