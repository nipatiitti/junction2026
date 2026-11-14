"""The chain book (`planner.ts`): which of our open cars go out together, and what happens to a chain that no driver
takes. It holds every piece of chain state, so the strategy only asks it five things: what a request costs as part of
a chain (`share`), whether a new car waits for a partner (`hold`), what to post and withdraw now (`actions`), what a
gig's fee schedule counts in (`typical`), and what the world answered (`sent`, `booked`, `expired`)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from strategies.lean.chains import Car, Chain, best_chain_with, find_chains
from strategies.lean.fees import BOOK_AHEAD, awake, plan_by, slow
from strategies.lean.note import earliest_pickup, read_note
from strategies.lean.ops import FIRST_TRY, Context, Roads, day_of, gig_shape, low_battery, shift_by_business_days

HOUR = 60


def pickups(stops: list[dict]) -> list[dict]:
    return [stop for stop in stops if stop["kind"] == "pickup"]


def key_of(stops: list[dict]) -> str:
    return " ".join(f"{s['orderId']}/{s['leg']}/{s['kind']}" for s in stops)


class Planner:
    def __init__(
        self,
        params: Any,
        roads: Roads,
        on: bool,
        context: Callable[[], Context],
        troubled: Callable[[str, str | None], bool],
    ) -> None:
        self.p, self.roads, self.on = params, roads, on
        self.context, self.troubled = context, troubled
        self.planned: dict[str, Chain] = {}  # the key of a chain's stops -> the chain
        self.posted: dict[str, tuple[Chain, int]] = {}  # gig id -> the chain and the minute it was posted
        self.claims: dict[str, str] = {}  # our car's order id -> the pending request whose bid counts on it
        self.single: set[str] = set()  # the orders that were in a chain no driver took: they stay single
        self.held_since: dict[str, int] = {}  # order id -> the minute it first waited for a partner
        self.released: set[str] = set()  # the orders whose wait is over
        self.tally = {"posted": 0, "cars": 0, "booked": 0, "bookedCars": 0, "ratios": 0.0, "undone": 0}

    def chain_args(self) -> tuple[float, int, float]:
        return self.p.maxHop, self.p.maxCars, self.p.minSaving

    def share(self, request: dict, option: dict, facts: Any, books: Any) -> float:
        """What an option's car costs as part of the best chain with the cars we hold or have open, over its cost
        alone; 1 when it fits no chain. The partners are claimed for this request until the dealer answers."""
        legs = request["legs"]
        if not self.on or not self.p.chainBid:
            return 1
        leg = legs[0] if legs else None
        if not leg or len(legs) != 1 or leg["car"]["premium"] or leg["pickup"]["privateAddress"]:
            return 1
        drive = self.roads.drive([leg])
        stated = leg["pickup"]["window"]["from"]
        moved = shift_by_business_days(option["deadline"], day_of(stated), day_of(max(stated, facts.ready_at or 0)))
        due = min(moved, facts.deadline if facts.deadline is not None else float("inf"))
        room = (self.p.chainHours + 4) * HOUR
        if drive == float("inf") or due - drive < books.now + room:
            return 1
        car = Car(
            gig_id=None,
            order_id=request["id"],
            start=leg["pickup"]["placeId"],
            end=leg["delivery"]["placeId"],
            ready=max(leg["pickup"]["window"]["from"], earliest_pickup(facts) or 0),
            collect_by=min(leg["pickup"]["window"]["to"], due - drive),
            due=min(due, leg["delivery"]["window"]["to"]) if leg["delivery"]["privateAddress"] else due,
            drive=drive,
            typical=request["referenceFeeCents"],
            pickup_hours=leg["pickup"]["hours"],
            delivery_hours=leg["delivery"]["hours"],
            delivery_from=leg["delivery"]["window"]["from"] if leg["delivery"]["privateAddress"] else 0,
            stops=[{"kind": "pickup", "withPlates": facts.plates, "withCharging": low_battery(leg["car"])}],
            audience={"experienced": False, "manualLicence": facts.manual},
        )
        free = [
            other for other in self.open_cars(books) if self.claims.get(other.order_id, request["id"]) == request["id"]
        ]
        chain = best_chain_with(car, free, self.roads, books.now, *self.chain_args())
        if not chain or chain.start_by - books.now < room:
            return 1
        for other in chain.cars:
            if other is not car:
                self.claims[other.order_id] = request["id"]
        return chain.typical / chain.singles

    def release(self, request_id: str) -> None:
        """The dealer answered a request: its claims on our cars end."""
        for order_id in [o for o, by in self.claims.items() if by == request_id]:
            del self.claims[order_id]

    def actions(self, books: Any) -> list[dict]:
        """Takes apart the chains that no driver took in time, and posts the new chains among the open single cars."""
        if not self.on:
            return []
        p, now = self.p, books.now
        actions: list[dict] = []
        for gig_id, (chain, at) in list(self.posted.items()):
            live = any(gig_id in books.gigs_of(car.order_id) for car in chain.cars)
            if not live:
                self.posted.pop(gig_id, None)
            patient = not (p.chainPatience > 0) or awake(at, now) < p.chainPatience * HOUR
            planned = not p.spread or awake(now, plan_by(now, chain.start_by)) >= 3 * HOUR
            if (
                not live
                or gig_id in books.booked
                or (patient and planned and now < chain.start_by - p.chainHours * HOUR)
            ):
                continue
            for car in chain.cars:
                self.single.add(car.order_id)
            self.posted.pop(gig_id, None)
            self.tally["undone"] += 1
            actions.append({"type": "withdraw", "gigId": gig_id})  # the harness posts each car again, alone
        found = find_chains(self.open_cars(books), self.roads, now, *self.chain_args())
        for chain in [c for c in found if c.start_by - now >= (p.chainHours + 3) * HOUR][:5]:
            stops = [stop for car in chain.cars for stop in car.stops]
            first = stops[0] if stops else None
            # The first pickup ends at the chain's last start: a driver who starts later misses a later car's window.
            if p.spread and first and not first.get("window") and chain.start_by > chain.cars[0].ready:
                stops[0] = {**first, "window": {"from": chain.cars[0].ready, "to": chain.start_by}}
            self.planned[key_of(stops)] = chain
            actions += [{"type": "withdraw", "gigId": car.gig_id} for car in chain.cars if car.gig_id]
            actions.append(
                {
                    "type": "post",
                    "stops": stops,
                    "audience": {
                        "experienced": False,
                        "manualLicence": any(car.audience["manualLicence"] for car in chain.cars),
                    },
                    "schedule": slow(now, chain.typical, chain.start_by - BOOK_AHEAD, p.open, 1.3),
                }
            )
        return actions

    def hold(self, need: dict, books: Any) -> bool:
        """A new car that may join a chain waits `holdHours` for a partner, while it has time to spare after the wait."""
        order, p = need["order"], self.p
        if not self.on or not (p.holdHours > 0):
            return False
        if need["why"] not in ("won", "lost") or order["id"] in self.released:
            return False
        if not self.chainable(order, books) or books.gigs_of(order["id"]):
            return False
        since = self.held_since.setdefault(order["id"], books.now)
        planned = (
            not p.spread or awake(books.now, plan_by(books.now, order["lastPickupAt"])) >= (p.holdHours + 5) * HOUR
        )
        holds = (
            planned
            and books.now < since + p.holdHours * HOUR
            and books.now < order["lastPickupAt"] - (p.chainHours + 6) * HOUR
        )
        if not holds:
            self.released.add(order["id"])
        return holds

    def typical(self, stops: list[dict]) -> int | None:
        """What a posted chain is worth to its driver, in cents: the unit of its fee schedule. None for other gigs."""
        chain = self.planned.get(key_of(stops))
        return chain.typical if chain else None

    def sent(self, action: dict, result: dict, books: Any) -> None:
        """The world's answer to a post: a chain that it refuses leaves its cars to single gigs."""
        chain = self.planned.get(key_of(action["stops"])) if action["type"] == "post" else None
        if not chain:
            return
        if not result.get("ok"):
            self.single.update(car.order_id for car in chain.cars)
        else:
            self.posted[result["id"]] = (chain, books.now)
            self.tally["posted"] += 1
            self.tally["cars"] += len(chain.cars)

    def booked(self, gig_id: str, ratio: float) -> None:
        """A driver booked a gig at `ratio` × its cars' typical fees."""
        entry = self.posted.get(gig_id)
        if not entry:
            return
        self.tally["booked"] += 1
        self.tally["bookedCars"] += len(entry[0].cars)
        self.tally["ratios"] += ratio

    def expired(self, gig_id: str, stops: list[dict]) -> None:
        """A gig's window ended without a driver: a chain's cars stay single from here."""
        if gig_id in self.posted:
            self.single.update(stop["orderId"] for stop in pickups(stops))

    def summary(self) -> str:
        c = self.tally
        ratio = f"{c['ratios'] / c['booked'] if c['booked'] > 0 else 0:.2f}"
        return (
            f"Chains: {c['posted']} posted with {c['cars']} cars, {c['booked']} booked with {c['bookedCars']} cars "
            f"at {ratio} × their cars' typical, {c['undone']} taken apart."
        )

    def chainable(self, order: dict, books: Any) -> bool:
        """Whether an order's car may join a chain: one car, no setback, no warning, a dealer's yard, and time left."""
        legs = order["legs"]
        if len(legs) != 1 or order["deliveredAt"][0] is not None or order["id"] in books.urgent:
            return False
        if order["id"] in self.single or self.troubled(order["id"], None):
            return False
        leg = legs[0]
        if leg["car"]["premium"] or leg["pickup"]["privateAddress"]:
            return False
        return books.now <= order["lastPickupAt"] - (self.p.chainHours + 3) * HOUR

    def open_cars(self, books: Any) -> list[Car]:
        """Our open cars that may join a chain: the cars that wait for a partner, and the single gigs that any driver
        may take and none holds."""
        now = books.now
        cars: list[Car] = []
        for order in list(books.orders.values()):
            request = books.requests.get(order["id"])
            gigs = books.gigs_of(order["id"])
            gig_id = gigs[0] if gigs else None
            if not order["legs"] or not request or len(gigs) > 1 or not self.chainable(order, books):
                continue
            if not gig_id and not (order["id"] in self.held_since and order["id"] not in self.released):
                continue
            if gig_id and (gig_id in books.booked or self.troubled(order["id"], gig_id)):
                continue
            if gig_id:
                post = books.posts.get(gig_id)
            else:
                facts = read_note(request.get("note"), request["arrivedAt"])
                shaped = gig_shape(order, [0], facts, FIRST_TRY, now, self.context())
                post = shaped[0] if shaped else None
            if not post or len(post["stops"]) != 2 or post["audience"]["experienced"]:
                continue
            pickup, delivery = post["stops"]
            leg = order["legs"][0]
            drive = self.roads.drive([leg])
            if pickup["kind"] != "pickup" or delivery["kind"] != "delivery" or drive == float("inf"):
                continue
            pickup_window = pickup.get("window") or leg["pickup"]["window"]
            delivery_window = delivery.get("window")
            cars.append(
                Car(
                    gig_id=gig_id,
                    order_id=order["id"],
                    start=leg["pickup"]["placeId"],
                    end=leg["delivery"]["placeId"],
                    ready=pickup_window["from"],
                    collect_by=min(pickup_window["to"], order["lastPickupAt"]),
                    due=delivery_window["to"]
                    if delivery_window
                    else (leg["delivery"]["window"]["to"] if leg["delivery"]["privateAddress"] else order["deadline"]),
                    drive=drive,
                    typical=request["referenceFeeCents"],
                    pickup_hours=leg["pickup"]["hours"],
                    delivery_hours=leg["delivery"]["hours"],
                    delivery_from=leg["delivery"]["window"]["from"] if leg["delivery"]["privateAddress"] else 0,
                    stops=[pickup, delivery],
                    audience=post["audience"],
                )
            )
        return cars
