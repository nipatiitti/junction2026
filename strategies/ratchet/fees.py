"""Fee schedules: one flat fee, priced by the distance, the place and the risk that no driver comes, which rises
only once the car is late. The schedule functions are pure: no network, no world.

A raise teaches drivers to wait for the next one, so the fee does not move while the car can still arrive on time.
Once it is late, the fee climbs every daytime hour until a driver takes the car: a car that is never delivered costs
twice its price, so every car must move.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from spread.types import FeeStep, Leg, Order, PriceRequest

from strategies.fees import FeePlanner, Market
from strategies.fees import Gig as BundleGig
from strategies.fees.schedule import valid

from .risk import Risk

HOUR, DAY = 60, 24 * 60

# The opening fee, as a multiple of the typical fee. The typical fee already grows with the distance: it is the
# drive, the trip to the pickup and the trip home of a driver who lives in the pickup town. On top come the place
# and the hour:
OPEN_TRAVEL = 0.10  # per hour of road from the homes of the pickup's nearest drivers: their trip to the car
TRAVEL_CAP = 4 * HOUR  # a longer trip counts as this long
OPEN_SCARCE_END = 0.15  # at a delivery with no drivers within reach: a long trip home from it
OPEN_EVENING = 0.10  # the drive ends after 18:00, when the trip home is dear
OPEN_SATURDAY = 0.15  # Saturday work
OPEN_LONG = 0.05  # a drive of 3 hours or more
LONG_DRIVE = 3 * HOUR
# The probability that no driver books a gig at its pickup before the deadline warning, times this multiplier,
# raises the opening fee: where half of our gigs find nobody in time, the fee opens RISK_WEIGHT / 2 higher.
RISK_WEIGHT = 0.5
# The opening fee stays at or under the price for the gig's cars plus the refund for a car late by more than
# 24 hours, so an on-time car never costs more than a late one; but it may always reach the typical fee of the
# trip, for a car that the dealer sent farther than the request said.
OPEN_CEILING = 1.5
# The fee stays flat while the car can still be on time. From LATE_FROM minutes after `lastPickupAt` (negative:
# before it), every daytime hour adds LATE_RAISE times the opening fee, up to LATE_CEILING times the price (a car
# never delivered costs twice its price as a penalty) or LATE_TYPICAL times the typical fee of the trip, whichever
# is higher: a car that the dealer sent farther must move too.
LATE_FROM = 0
LATE_RAISE = 0.25
LATE_EVERY = HOUR
LATE_CEILING = 2.0
LATE_TYPICAL = 3.0
# No raise at night or on Sunday: no driver books then, so a raise would only meet the next driver higher.
NIGHT_FROM, NIGHT_TO = 23 * HOUR, 7 * HOUR
SUNDAY = 6
MAX_STEPS = 48


@dataclass(frozen=True)
class Gig:
    """What a schedule is planned from, for the cars of one gig."""

    typical: float  # the typical fee for the gig's cars, for the trip they make now, in cents
    price: float  # the order's price for the gig's cars, in cents
    last_pickup_at: int  # the order's `lastPickupAt`
    starts_at: int  # the earliest pickup: the later of now and the car's ready time
    drive_minutes: int  # road minutes from the pickup to the delivery
    travel_minutes: int  # road minutes from the nearest drivers' homes to the pickup
    scarcity_end: float  # 0 where drivers are as near the delivery as at the world's median place, 1 where none are
    risk: float  # the probability that no driver books a gig at the pickup before the deadline warning


def opening_multiple(gig: Gig) -> float:
    """The opening fee over the typical fee: the distance, the place and the hour, then the risk of no driver."""
    multiple = 1 + OPEN_TRAVEL * min(gig.travel_minutes, TRAVEL_CAP) / HOUR
    multiple += OPEN_SCARCE_END * min(1.0, max(0.0, gig.scarcity_end))
    ends = gig.starts_at + gig.drive_minutes
    if ends % DAY >= 18 * HOUR or ends // DAY > gig.starts_at // DAY:
        multiple += OPEN_EVENING
    if gig.starts_at // DAY % 7 == 5:
        multiple += OPEN_SATURDAY
    if gig.drive_minutes >= LONG_DRIVE:
        multiple += OPEN_LONG
    return multiple * (1 + RISK_WEIGHT * min(1.0, max(0.0, gig.risk)))


def plan(now: int, gig: Gig, level: int, opening: float | None = None) -> list[FeeStep]:
    """The fee schedule from `now`: the opening fee (`opening` cents, or the one the gig's facts give), flat while
    the car can be on time, then a raise every daytime hour once it is late."""
    fee = gig.typical * opening_multiple(gig) if opening is None else opening
    fee = max(1.0, min(fee, max(gig.price * OPEN_CEILING, gig.typical)))
    steps = [(now, fee), *late_steps(gig, fee)]
    current = max(f for at, f in steps if at <= now)  # a car posted late starts at the fee its lateness has reached
    return valid([(now, current), *((at, f) for at, f in steps if at > now)], level)


def late_steps(gig: Gig, opening: float) -> list[tuple[int, float]]:
    """The raises once the car is late: one every daytime hour from `lastPickupAt` + LATE_FROM, each LATE_RAISE
    times the opening fee, up to LATE_CEILING times the price or LATE_TYPICAL times the typical fee."""
    top = max(opening, gig.price * LATE_CEILING, gig.typical * LATE_TYPICAL)
    steps: list[tuple[int, float]] = []
    at, raises = gig.last_pickup_at + LATE_FROM, 0
    while len(steps) < MAX_STEPS and LATE_RAISE > 0:
        if daytime(at):
            raises += 1
            steps.append((at, min(top, opening * (1 + LATE_RAISE * raises))))
            if steps[-1][1] >= top:
                break
        at += LATE_EVERY
    return steps


def daytime(at: int) -> bool:
    """Drivers book from 07:00 to 23:00, and not on Sunday, when every site is closed."""
    return NIGHT_TO <= at % DAY < NIGHT_FROM and at // DAY % 7 != SUNDAY


class RiskFees:
    """Plans each gig's fee schedule, and learns place by place how often our gigs find no driver before their
    deadline warning. It takes the place of `strategies/fees`' `FeePlanner` in the desk."""

    def __init__(self, market: Market):
        self.market = market
        self.risk = Risk(market)
        self.planner = FeePlanner(market)  # the typical fee of the trip a car makes now (strategies/fees)
        # (Order id, pickup, delivery) -> the order's opening fee over its typical fee, set at its first post for
        # that trip: every later post, repost and retry of the order opens at the same fee, so the fee rises only
        # once the car is late. A car that the dealer sends elsewhere is a new trip, with a new opening fee.
        self.openings: dict[tuple[str, str, str], float] = {}

    def schedule(self, order: Order, request: PriceRequest, cars: int, now: int, level: int) -> list[FeeStep]:
        gig = self.gig(order, request, cars, now)
        leg = first(order)
        key = (order["id"], leg["pickup"]["placeId"], leg["delivery"]["placeId"])
        multiple = self.openings.setdefault(key, opening_multiple(gig))
        return plan(now, gig, level, opening=gig.typical * multiple)

    def bundle(self, gig: BundleGig, pickup: str, delivery: str, now: int, level: int) -> list[FeeStep]:
        """The schedule of a bundle of several orders' cars (`strategies/bundling`), from the facts that bundling
        sums for it: the same flat fee and late raises, from its first pickup to its last delivery."""
        facts = self.facts(pickup, delivery, gig.typical, gig.price, gig.last_pickup_at, gig.starts_at)
        return plan(now, replace(facts, drive_minutes=gig.drive_minutes), level)

    def typical(self, order: Order, request: PriceRequest) -> float:
        """The typical fee of all the order's cars for the trips they make now: the request's, or after a change
        of plan the fee of the new trip (`strategies/fees`)."""
        return self.planner.typical(order, request)

    def estimate(self, request: PriceRequest, now: int) -> float:
        """The opening fee we would post now for all of the request's cars, in cents."""
        leg = request["legs"][0]
        typical = request["referenceFeeCents"]
        starts_at = max(now, leg["pickup"]["window"]["from"])
        facts = self.facts(leg["pickup"]["placeId"], leg["delivery"]["placeId"], typical, 0, 0, starts_at)
        return typical * opening_multiple(facts)

    def learn(self, order: Order, found: bool) -> None:
        """The order's gig was booked (`found`) or reached its deadline warning with no driver, whichever came
        first: the risk of its pickup place learns from it."""
        self.risk.learn(order["id"], first(order)["pickup"]["placeId"], found)

    def gig(self, order: Order, request: PriceRequest, cars: int, now: int) -> Gig:
        """The facts of a gig with `cars` of the order's cars, read from its first undelivered car."""
        share = cars / len(order["legs"])
        leg = first(order)
        return self.facts(
            leg["pickup"]["placeId"],
            leg["delivery"]["placeId"],
            self.typical(order, request) * share,
            order["priceCents"] * share,
            order["lastPickupAt"],
            max(now, leg["pickup"]["window"]["from"]),
        )

    def facts(
        self, pickup: str, delivery: str, typical: float, price: float, last_pickup_at: int, starts_at: int
    ) -> Gig:
        return Gig(
            typical=typical,
            price=price,
            last_pickup_at=last_pickup_at,
            starts_at=starts_at,
            drive_minutes=self.market.minutes(pickup, delivery),
            travel_minutes=self.market.travel_minutes(pickup),
            scarcity_end=self.market.scarcity(delivery),
            risk=self.risk.of(pickup),
        )


def first(order: Order) -> Leg:
    """The order's first car that is not delivered yet."""
    return next((leg for leg, at in zip(order["legs"], order["deliveredAt"]) if at is None), order["legs"][0])
