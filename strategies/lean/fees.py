"""Fee schedules (`fees.ts`). The measured facts: the lowest fee that books a gig within three hours is 0.76 × the
typical fee at the median, and two bookers in three had seen the gig before at a lower fee and waited for the rise. So
a gig holds one fee and raises it only at a few hours of its own (`stepped`); a chain holds and then creeps (`slow`);
and only when the time runs out does a fee climb fast (`fast`). A schedule is a list of {at, feeCents}."""

from __future__ import annotations

import math
from collections.abc import Callable

from strategies.lean.js import INF, i32, imul, js_round, u32

HOUR, DAY = 60, 24 * 60
HOLD = 6 * HOUR  # the slow schedule holds its opening fee for half of the time a gig has, this long at most
LAST = 1.3  # after the hold, the fee creeps on to this × typical, then to the top by the last minute to book
STEP = 20  # minutes between two steps of the climb
WAKE, SLEEP = 7 * HOUR, 21 * HOUR  # drivers read the app between these minutes of the day
BOOK_AHEAD = 90  # a gig needs a driver this long before its last pickup, to reach the car
SHORT = 45  # with less time than this left to book, only a fast climb finds a driver
STEPS = [(24, 1.05), (16, 1.25), (10, 1.55), (6, 2)]
PLAN = [0.3, 0.55, 0.8]
PLAN_AHEAD = 28 * HOUR
EARLY = 60  # with `early`: the minutes a gig shows its early fee

Points = list[tuple[float, float]]


def awake(start: float, end: float) -> float:
    """The minutes from `start` to `end` when drivers are awake."""
    if not end > start:
        return 0
    if not math.isfinite(end):
        return INF
    total: float = 0
    for day in range(math.floor(start / DAY), math.floor(end / DAY) + 1):
        total += max(0, min(end, day * DAY + SLEEP) - max(start, day * DAY + WAKE))
    return total


def later(start: float, minutes: float) -> float:
    """The minute that lies `minutes` awake minutes after `start`."""
    left = minutes
    first = math.floor(start / DAY)
    for day in range(first, first + 30):
        begin = max(start, day * DAY + WAKE)
        room = day * DAY + SLEEP - begin
        if room <= 0:
            continue
        if room >= left:
            return begin + left
        left -= room
    return start + minutes


def slow(now: int, typical: float, book_by: float, opening: float, top: float) -> list[dict]:
    """The slow schedule from `now`, for chains: `opening` × typical for half of the awake time to `book_by` (HOLD at
    most), then up to LAST when four fifths of the time are gone, and to `top` at `book_by`."""
    time = awake(now, book_by)
    points: Points = [(now, opening)]

    def phase(begin: float, end: float, low: float, high: float, most: int, every: int) -> None:
        steps = min(most, math.floor((end - begin) / every)) if high > low else 0
        for i in range(1, steps + 1):
            points.append((later(now, begin + ((end - begin) * i) / steps), low + ((high - low) * i) / steps))

    last = max(opening, LAST)
    phase(min(time / 2, HOLD), 0.8 * time, opening, last, 10, STEP)
    phase(0.8 * time, time, last, max(last, top), 12, 10)
    return schedule(points, typical)


def stepped(
    now: int,
    typical: float,
    last_pickup: int,
    opening: float,
    floor: float = 0,
    jitter: float = 0,
    seed: str = "",
    spread: bool = False,
    early: float = 0,
) -> list[dict]:
    """The opening fee, then a raise only at a few hours before the last pickup (or, with `spread`, by the drivers'
    planning). Steps that have passed fold into the opening.

    `floor` is a multiple of the typical fee. The early-fee test compares it with `early × typical` in cents, as
    fees.ts does, so a floor never blocks the early fee; the port keeps that to decide as the TypeScript does."""
    random = rng(seed)
    points: Points = [(now, max(opening, floor))]
    if 0 < early < opening and math.floor(last_pickup / DAY) > math.floor(now / DAY) and floor < early * typical:
        points[0] = (now, early)
        points.append((now + EARLY, opening))
    plan = plan_by(now, last_pickup)
    time = min(awake(now, plan), PLAN_AHEAD)
    start = later(now, awake(now, plan) - time)
    for i, (hours, ratio) in enumerate(STEPS):
        shift = random() - 0.5
        to = ratio * (1 + (random() - 0.5) * 0.1 * jitter)
        at = last_pickup - hours * HOUR + shift * 3 * HOUR * jitter
        if spread:
            top = plan if plan > last_pickup - 6 * HOUR else min(later(plan, 1), last_pickup - 3 * HOUR)
            at = later(start, PLAN[i] * time) + shift * 40 * jitter if i < 3 else top
        if at <= now:
            points[0] = (now, max(points[0][1], to))
        else:
            points.append((at, to))
    return schedule(sorted(points, key=lambda point: point[0]), typical)


def plan_by(now: float, last_pickup: float) -> float:
    """The minute by which a gig should have its driver: 21:00 the evening before for a last pickup before 16:00,
    else 5 hours before it. With that evening already over, 3 hours before the last pickup."""
    evening = math.floor(last_pickup / DAY) * DAY - (DAY - SLEEP)
    if last_pickup % DAY >= 16 * HOUR:
        return last_pickup - 5 * HOUR
    return evening if awake(now, evening) >= HOUR else last_pickup - 3 * HOUR


def rng(seed: str) -> Callable[[], float]:
    """mulberry32 over a string hash, as fees.ts draws it: the same numbers for the same order id."""
    a = 0
    for i, char in enumerate(seed):
        a = i32(imul(a ^ ord(char), 2654435761) + i)
    state = [a]

    def draw() -> float:
        state[0] = i32(state[0] + 0x6D2B79F5)
        x = state[0]
        t = imul(i32(x ^ (u32(x) >> 15)), i32(1 | x))
        t = i32(i32(t + imul(i32(t ^ (u32(t) >> 7)), i32(61 | t))) ^ t)
        return u32(t ^ (u32(t) >> 14)) / 4294967296

    return draw


def fast(now: int, typical: float, opening: float, step: float, every: int, cap: float) -> list[dict]:
    """`opening` × typical at once, then `step` × typical more every `every` minutes up to `cap` × typical."""
    points: Points = []
    first = min(opening, cap)
    for i in range(40):
        ratio = min(cap, first + i * step)
        points.append((now + i * every, ratio))
        if ratio >= cap:
            break
    return schedule(points, typical)


def schedule(points: Points, typical: float) -> list[dict]:
    """Whole steps in time order whose fee never falls, 48 at most."""
    steps: list[dict] = []
    for minute, ratio in points:
        at = js_round(minute)
        fee = max(1, js_round(ratio * typical), steps[-1]["feeCents"] if steps else 0)
        last = steps[-1] if steps else None
        if last and at <= last["at"]:
            last["feeCents"] = fee
        elif not last or fee > last["feeCents"]:
            steps.append({"at": at, "feeCents": fee})
    return steps[:48]


def fee_at(steps: list[dict], now: float) -> int:
    """The fee that a schedule shows at `now`."""
    fee = steps[0]["feeCents"] if steps else 0
    for step in steps:
        if step["at"] <= now:
            fee = step["feeCents"]
    return fee
