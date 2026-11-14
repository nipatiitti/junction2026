"""Chains (`chains.ts`): several of our open cars as one gig for one driver. The cars are the nodes of a graph, and an
edge goes from one car to the next when the next is collected near where the first is delivered. A path through it is
a day of work: the driver pays one trip to the first car and one trip home from the last, where the same cars as
single gigs pay a trip out and a trip home each. A path that ends where it started pays no trip home at all. The
search walks every path of up to `max_cars` cars, keeps the ones a driver can do inside every window, and takes the
paths that save the most, each car once.

One change against chains.ts, with the same result: the walk judges a path without the search for its last start
(`start_by`), which only the chains chosen need, and the chosen chains get it after the choice. The choice never reads
`start_by`, so the chains are the same, in a fraction of the time Python would take."""

from __future__ import annotations

import math
from dataclasses import dataclass

from strategies.lean.js import js_round
from strategies.lean.ops import Roads, next_open

HOUR = 60
MAX_DRIVE = 8 * HOUR  # a gig of several cars may plan 12 hours of driving; we plan 8
FIXED = 1572  # the measured typical fee of one car: 15.72 euros and 0.387 a road minute
PER_MINUTE = 38.7
HOME_SHARE = 0.3  # the trip home by public transport costs a driver much less than the wheel
HANDLING = 15  # a driver takes this long at a stop
SPARE = 45  # a delivery must arrive this long before it is due
DRIVE = 1.2  # real drives take up to this × the road minutes
SLACK = 30  # a later car is reached this long before its last pickup
LEAD = 2 * HOUR  # a chain's driver starts no sooner than this from now
MAX_WAIT = 2 * HOUR
MAX_DAY = 14 * HOUR


@dataclass(eq=False)
class Car:
    """One open car of ours: a single gig that no driver holds, or a car that waits for a partner."""

    gig_id: str | None
    order_id: str
    start: str  # the pickup place
    end: str  # the delivery place
    ready: float  # the first minute it can be collected
    collect_by: float  # the last
    due: float  # the last minute it may arrive
    drive: float  # road minutes
    typical: int  # its typical fee as a single gig, in cents
    pickup_hours: dict | None
    delivery_hours: dict | None
    stops: list[dict]  # its pickup and its delivery, as posted
    audience: dict


@dataclass(eq=False)
class Chain:
    cars: list[Car]
    drive: float  # road minutes with the hops between the cars
    start_by: float  # the last minute a driver can start it and meet every window
    typical: int  # what the chain is worth to a driver, in cents: the fee schedule's unit
    singles: float  # the cars' typical fees as single gigs, summed


def find_chains(
    cars: list[Car], roads: Roads, now: int, max_hop: float, max_cars: int, min_saving: float
) -> list[Chain]:
    """The chains worth posting among `cars`, best saving first, each car in one chain at most."""
    found: list[Chain] = []
    following = {
        a: [b for b in cars if b is not a and roads.minutes(a.end, b.start) <= max_hop and b.due > a.ready]
        for a in cars
    }

    def walk(path: list[Car], drive: float) -> None:
        if len(path) >= 2:
            chain = judge(path, drive, roads, now, quick=True)
            if chain and chain.typical <= (1 - min_saving) * chain.singles:
                found.append(chain)
        if len(path) >= max_cars:
            return
        last = path[-1]
        for b in following.get(last, []):
            if any(b is c for c in path):
                continue
            more = drive + roads.minutes(last.end, b.start) + b.drive
            if more <= MAX_DRIVE:
                walk([*path, b], more)

    for car in cars:
        walk([car], car.drive)
    found.sort(key=lambda chain: -(chain.singles - chain.typical))
    used: set[int] = set()
    chosen: list[Chain] = []
    for chain in found:
        if any(id(car) in used for car in chain.cars):
            continue
        used.update(id(car) for car in chain.cars)
        chosen.append(chain)
    return [full for chain in chosen if (full := judge(chain.cars, chain.drive, roads, now)) is not None]


def best_chain_with(
    car: Car, others: list[Car], roads: Roads, now: int, max_hop: float, max_cars: int, min_saving: float
) -> Chain | None:
    """The chain that saves the most among those that hold `car` and some of `others`. None when it fits no chain."""
    cars = [car, *others]
    best: list[Chain | None] = [None]

    def near(a: Car, b: Car) -> bool:
        return roads.minutes(a.end, b.start) <= max_hop and b.due > a.ready

    def walk(path: list[Car], drive: float) -> None:
        if len(path) >= 2 and any(c is car for c in path):
            chain = judge(path, drive, roads, now, quick=True)
            good = chain is not None and chain.typical <= (1 - min_saving) * chain.singles
            current = best[0]
            if (
                chain
                and good
                and (current is None or chain.typical / chain.singles < current.typical / current.singles)
            ):
                best[0] = chain
        if len(path) >= min(max_cars, 3):
            return
        last = path[-1]
        for b in cars:
            if any(b is c for c in path) or not near(last, b):
                continue
            more = drive + roads.minutes(last.end, b.start) + b.drive
            if more <= MAX_DRIVE:
                walk([*path, b], more)

    walk([car], car.drive)
    for other in others:
        if near(other, car):
            walk([other], other.drive)
    found = best[0]
    return judge(found.cars, found.drive, roads, now) if found else None


def judge(path: list[Car], drive: float, roads: Roads, now: int, quick: bool = False) -> Chain | None:
    """The chain of a path, or None when no driver can do it inside every window."""
    first, last = path[0], path[-1]
    earliest = max(now + LEAD, first.ready)
    if not feasible(path, earliest, roads):
        return None
    start_by = earliest
    start = earliest + 30
    while not quick and start <= earliest + 48 * HOUR:
        if feasible(path, start, roads):
            start_by = start
        elif start > start_by + 16 * HOUR:  # a night between two days that work
            break
        start += 30
    singles = sum(car.typical for car in path)
    modelled = sum(FIXED + PER_MINUTE * car.drive for car in path)
    home = roads.minutes(last.end, first.start)
    cost = FIXED + PER_MINUTE * ((1 - HOME_SHARE) * drive + HOME_SHARE * (home if math.isfinite(home) else drive))
    return Chain(path, drive, start_by, js_round((cost * singles) / modelled), singles)


def feasible(path: list[Car], start: float, roads: Roads) -> bool:
    """Whether a driver who collects the first car at `start` meets every window, without long waits."""
    at = start
    waited: float = 0
    here = None
    for car in path:
        if here is not None:
            at += roads.minutes(here, car.start)
        opened = next_open(max(at, car.ready), car.pickup_hours)
        if here is not None:
            waited += opened - at
        at = opened
        if not at <= car.collect_by - (0 if here is None else SLACK) or waited > MAX_WAIT:
            return False
        at += HANDLING + DRIVE * car.drive
        if not next_open(at, car.delivery_hours) <= car.due - SPARE:
            return False
        at += HANDLING
        here = car.end
    return at - start <= MAX_DAY
