"""The ladder: how hard a price request is to move, as a rung. A system that takes rung n takes every ride of rungs 1
to n, with the handling each of them needs.

The order of the rungs follows how often such cars reached their dealers on time (README.md has the tables): in the
starter's level 8 week (`smoke-1`) a plain car ready on a later day was on time 62% to 80% of the time; premium cars,
private addresses and cars ready at once 23% to 41%; trade-ins and drives over 4 hours under 31%. On the ladder's own
bench, long rides quoted with a day to search were late 2 times in 63, trade-ins 7 times in 20: trade-ins come last.
"""

from __future__ import annotations

from dataclasses import dataclass

from spread.types import PriceRequest

from ladder.market import Market
from strategies.notes import NoteFacts

DAY = 24 * 60
RUNGS = [
    "easy rides",  # one plain car between dealer sites, no note, ready on a later day, a drive of up to 4 hours
    "notes",  # the note reader sets the windows, the licence and the plates
    "special cars",  # premium cars, electric cars that need a charging stop, private addresses
    "rides ready today",  # the car is ready on the day its request arrives: a later option, posted for the next morning
    "long and remote rides",  # a drive over 4 hours, or few drivers near either end: quoted with a day to search
    "trade-ins",  # two cars in one gig, or two gigs over the 12-hour limit
]
TOP_RUNG = 4  # the default of --rung: the best rung on the bench so far (README.md)
NOTES_RUNG, SPECIAL_RUNG, TODAY_RUNG, REMOTE_RUNG, TRADE_IN_RUNG = 2, 3, 4, 5, 6

MORNING = 7 * 60  # rung 4 posts a car ready today for 07:00 on the next business day
CHARGE_KM = 200  # an electric car under 30% on a route over this needs a charging stop (rule 3)
REMOTE_SUPPLY = 8.0  # fewer drivers than this within reach of the pickup (Market.supply) makes a ride remote
# Fewer drivers than this within reach of the delivery makes a ride remote too: its driver has a dear trip home. Easy
# rides into such towns booked at their opening fee 37% of the time in the starter's week, against 84% to 96%.
REMOTE_DELIVERY = 20.0
LONG_DRIVE = 4 * 60  # a longer drive, in road minutes, makes a ride long


@dataclass(frozen=True)
class Ride:
    """What a price request asks of us, read once when it arrives."""

    request_id: str
    rung: int  # the lowest rung that takes it, 1 to len(RUNGS)
    why: str  # what puts it on its rung, for the summary
    legs: int
    pickup: str  # the first car's pickup place
    delivery: str  # the last car's delivery place
    ready: int  # when the first car can be collected: by the request, or later by its note
    today: bool  # ready on the day its request arrives
    remote: bool  # a drive over 4 hours, or few drivers near either end: it needs a day to find a driver
    shift: int  # minutes the order's deadlines move because the note makes the car ready a day or more later
    note_deadline: int | None  # a tighter deadline from the note
    drive: int  # road minutes of all legs, from each pickup to its delivery
    km: float
    pickup_supply: float  # drivers within reach of the first pickup (Market.supply)
    delivery_supply: float  # drivers within reach of the last delivery: a cheap trip home
    premium: bool
    charging: bool  # an electric car needs a charging stop
    private: bool  # a stop at a private address
    private_delivery: bool  # the last car is delivered at a private address, in its booked hour
    note: bool
    bulk: bool  # one of a dealer group's cars from one yard (batchId)


def next_morning(now: int) -> int:
    """07:00 on the next business day (Monday to Friday) after `now`."""
    day = now // DAY + 1
    while day % 7 in (5, 6):
        day += 1
    return day * DAY + MORNING


def needs_charging(market: Market, leg: dict) -> bool:
    """An electric car under 30% on a route over 200 km needs a charging stop: without one it is 90 minutes late."""
    car = leg["car"]
    low = car["electric"] and car["chargePercent"] is not None and car["chargePercent"] < 30
    return low and market.road_km(leg["pickup"]["placeId"], leg["delivery"]["placeId"]) > CHARGE_KM


def classify(request: PriceRequest, market: Market, facts: NoteFacts) -> Ride:
    """The ride of a request, and its rung: the hardest thing it asks for. `facts` is what its note says, which
    speaks of the first car."""
    legs = request["legs"]
    first, last = legs[0], legs[-1]
    pickup, delivery = first["pickup"]["placeId"], last["delivery"]["placeId"]
    stated = first["pickup"]["window"]["from"]
    ready = max(stated, facts.earliest_pickup or 0)
    # RULES.md: a car ready a day or more later than the request says moves the order's deadline by the same days.
    shift = max(0, ready // DAY - stated // DAY) * DAY
    drive = sum(market.drive(leg["pickup"]["placeId"], leg["delivery"]["placeId"]) for leg in legs)
    km = sum(market.road_km(leg["pickup"]["placeId"], leg["delivery"]["placeId"]) for leg in legs)
    premium = any(leg["car"]["premium"] for leg in legs)
    charging = any(needs_charging(market, leg) for leg in legs)
    private = any(leg[stop]["privateAddress"] for leg in legs for stop in ("pickup", "delivery"))
    note = bool(request["note"] and request["note"]["text"].strip())
    today = ready // DAY <= request["arrivedAt"] // DAY
    supply = market.supply(pickup, "experienced" if premium else "all")
    remote = supply < REMOTE_SUPPLY or market.supply(delivery) < REMOTE_DELIVERY or drive > LONG_DRIVE
    needs = [
        (TRADE_IN_RUNG, len(legs) > 1, "a trade-in"),
        (REMOTE_RUNG, supply < REMOTE_SUPPLY, "few drivers near the pickup"),
        (REMOTE_RUNG, market.supply(delivery) < REMOTE_DELIVERY, "few drivers near the delivery"),
        (REMOTE_RUNG, drive > LONG_DRIVE, "a drive over 4 hours"),
        (TODAY_RUNG, today, "ready today"),
        (SPECIAL_RUNG, private, "a private address"),
        (SPECIAL_RUNG, premium, "a premium car"),
        (SPECIAL_RUNG, charging, "a charging stop"),
        (NOTES_RUNG, note, "a note"),
    ]
    # The hardest thing the ride asks for sets its rung; the first reason listed for that rung names it.
    rung, why = next(((n, reason) for n, hit, reason in needs if hit), (1, "easy"))
    return Ride(
        request_id=request["id"],
        rung=rung,
        why=why,
        legs=len(legs),
        pickup=pickup,
        delivery=delivery,
        ready=ready,
        today=today,
        remote=remote,
        shift=shift,
        note_deadline=facts.deadline,
        drive=drive,
        km=km,
        pickup_supply=supply,
        delivery_supply=market.supply(delivery),
        premium=premium,
        charging=charging,
        private=private,
        private_delivery=last["delivery"]["privateAddress"],
        note=note,
        bulk=request["batchId"] is not None,
    )
