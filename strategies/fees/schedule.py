"""Fee schedules planned back from the last pickup. Pure functions: no network, no world.

A schedule opens at a fee set by the place and the hour, raises a few times in large steps, and
reaches its top fee a travel margin before `lastPickupAt`, so a driver who books at the top still
has time to get to the car. No fee goes above the ceiling that the order's price sets.
"""

from __future__ import annotations

from dataclasses import dataclass

from spread.types import FeeStep

HOUR, DAY = 60, 24 * 60

# The opening fee, as a multiple of the typical fee: OPEN_BASE, plus a premium for each thing that makes
# the work dearer for a driver than the typical fee assumes. With admission control, two thirds of the gigs
# book at their opening fee, and the premiums bought no more of them: they are off (see README.md).
# Opening under the typical fee costs less, and the first raise reaches the typical fee within the hour.
OPEN_BASE = 0.9
OPEN_SCARCE = 0.0  # at a pickup with no drivers within reach, against the world's median place
OPEN_EVENING = 0.0  # the drive ends after 18:00, when the trip home is dear
OPEN_SATURDAY = 0.0  # Saturday work
OPEN_LONG = 0.0  # a drive of 3 hours or more: a long trip home from the delivery town
LONG_DRIVE = 3 * HOUR
# The least opening fee, as a multiple of the typical fee, whatever the premiums add up to.
OPEN_FLOOR = 0.9
# The top fee, as a multiple of the typical fee, before the ceiling cuts it: the top of the starter's steep fees.
TOP = 2.5
# What a late car costs, as a share of its price: the whole price, the refund for a car late by more than two
# business days. The ceiling of the top fee is the price plus this, so an on-time car never costs more than a
# late one.
LATE_SHARE = 1.0
# What a car never delivered costs, as a share of its price: no price, and a penalty of twice the price.
# No fee on time goes above the price plus this: past it, leaving the car costs less than delivering it.
PENALTY = 2.0
# The typical fee of a trip from its road minutes, for a car the dealer sends to another place: the
# request's typical fee is for the trip it asked for. Fitted on the saved level-8 weeks (12 seeds): a
# single car's typical fee is about this, and a trade-in's about that of its first car's trip.
TRIP_BASE = 1603  # cents
TRIP_PER_MINUTE = 38.65  # cents a road minute, €23.19 an hour
# A car that is late already: a day after its last pickup it steps up to this multiple of the typical
# fee, as the starter's steep fees did, under a ceiling of twice its price: a car late by more than two
# business days costs its whole price, and a car never delivered twice its price on top.
LATE_TOP = 2.5
# With less than this left before the top fee is due, the schedule opens closer to its top.
URGENT_SPAN = 8 * HOUR
# Raises after the opening fee, the last one at the top fee. Few, so drivers do not learn to wait for the next.
RAISES = 3
# The raises before the top come early, this long after the post at the latest: drivers who know they
# work the next day book a day ahead when the fee is right, before their day fills up. The fee then
# holds until the top fee is due.
EARLY_RAISES = (HOUR, 3 * HOUR)
# How far each raise before the top goes, as a share of the way from the opening fee to the top fee: small,
# about as far as the starter's hourly raises (1.06 and 1.38 times the typical fee), so few gigs book dear.
RAISE_SHARES = (0.1, 0.3)
# The travel margin before `lastPickupAt`: an hour to see the gig, plus the trip from the drivers'
# homes by public transport, which is slower than the road minutes. Never less than 6 hours, never more
# than 8: most late cars had drivers who wanted them at the top fee but could no longer reach the pickup
# in its window, so the top comes early in the pickup day, while their day still has room.
SEE = HOUR
TRANSIT = 1.5
MARGIN_MIN, MARGIN_MAX = 6 * HOUR, 8 * HOUR
# Drivers rarely look at the app at night: a raise due then comes at 22:00 the evening before.
NIGHT_FROM, NIGHT_TO, EVENING = 23 * HOUR, 7 * HOUR, 22 * HOUR
# After a drop: the driver who gave the gig back books again only for more. With less than this left
# before the top fee, the gig reprices at least this much above the fee that was dropped.
DROP_SPAN = 6 * HOUR
DROP_STEP = 0.15
MAX_STEPS = 48


@dataclass(frozen=True)
class Gig:
    """What a schedule is planned from, for the cars of one gig."""

    typical: float  # the typical fee for the gig's cars, for the trip they make now, in cents
    price: float  # the order's price for the gig's cars, in cents
    last_pickup_at: int  # the order's `lastPickupAt`
    starts_at: int  # the earliest pickup: the later of now and the car's ready time
    drive_minutes: int  # road minutes from the pickup to the delivery
    scarcity: float  # 0 where drivers are as near as at the world's median place or nearer, 1 where none are
    travel_minutes: int  # road minutes from the nearest drivers' homes to the pickup


def margin(gig: Gig) -> int:
    """Minutes before `lastPickupAt` at which the top fee is due."""
    return round(min(MARGIN_MAX, max(MARGIN_MIN, SEE + TRANSIT * gig.travel_minutes)))


def trip_fee(minutes: int) -> float:
    """The typical fee of a trip of these road minutes, in cents."""
    return TRIP_BASE + TRIP_PER_MINUTE * minutes


def ceiling(gig: Gig, at: int | None = None) -> float:
    """The highest fee of a step due `at`: what the car is worth before the top, plus what being late
    would cost, but never more than leaving the car would cost. From a day after the last pickup, being
    later costs the whole price, so the ceiling is twice the price, unless the fee is above it already."""
    if at is not None and at >= gig.last_pickup_at + DAY:
        return gig.price * PENALTY
    return min(worth(gig) + gig.price * LATE_SHARE, gig.price * (1 + PENALTY))


def worth(gig: Gig) -> float:
    """The highest fee of a step before the top: the price, at which the order still breaks even. A car
    whose trip costs more than its price, after the dealer sent it farther, may reach the trip's typical
    fee instead: a late car costs that much too, and leaving it costs more."""
    return min(max(gig.price, gig.typical), gig.price * (1 + PENALTY))


def opening_multiple(gig: Gig) -> float:
    """The opening fee over the typical fee, by place and hour."""
    multiple = OPEN_BASE + OPEN_SCARCE * min(1.0, max(0.0, gig.scarcity))
    ends = gig.starts_at + gig.drive_minutes
    if ends % DAY >= 18 * HOUR or ends // DAY > gig.starts_at // DAY:
        multiple += OPEN_EVENING
    if gig.starts_at // DAY % 7 == 5:
        multiple += OPEN_SATURDAY
    if gig.drive_minutes >= LONG_DRIVE:
        multiple += OPEN_LONG
    return max(OPEN_FLOOR, multiple)


def plan(now: int, gig: Gig, level: int, floor: float = 0) -> list[FeeStep]:
    """The fee schedule from `now`. `floor` is the least opening fee, after a drop."""
    # The floor after a drop may lift the top, but never above the ceiling.
    top = max(1.0, min(max(gig.typical * TOP, floor), ceiling(gig)))
    top_at = before_night(gig.last_pickup_at - margin(gig), now)
    span = top_at - now
    if span <= HOUR:  # the top fee is due within the hour: a driver needs all the time that is left
        steps = [(now, top)]
        if now >= gig.last_pickup_at:  # late already: step up once more a day after the last pickup
            later = max(now + HOUR, gig.last_pickup_at + DAY)
            steps.append((later, max(top, min(gig.typical * LATE_TOP, ceiling(gig, later)))))
        return valid(steps, level)
    # Little time left: open closer to the top.
    urgency = max(0.0, 1 - span / URGENT_SPAN)
    opening = gig.typical * opening_multiple(gig)
    opening = min(max(opening + (top - opening) * urgency, floor), top)
    if level == 1 or opening >= top:
        return valid([(now, opening)], level)
    # Each step before the top stays at or under the price, unless the opening fee is above it already.
    cap = max(opening, min(top, worth(gig)))
    steps = [(now, opening)]
    for k in range(1, RAISES + 1):
        at = now + span * k // RAISES if k == RAISES else min(now + span * k // RAISES, now + EARLY_RAISES[k - 1])
        fee = opening + (top - opening) * (1 if k == RAISES else RAISE_SHARES[k - 1])
        steps.append((before_night(at, now), top if k == RAISES else min(fee, cap)))
    return valid(steps, level)


def after_drop(now: int, gig: Gig, level: int, dropped_fee: int) -> list[FeeStep] | None:
    """The new schedule after a driver gave the gig back at `dropped_fee`, or None to keep the one in
    the app. A fee that only just paid that driver is likely to drop again, so when the schedule has
    little time left to find another driver, it steps up from the dropped fee at once."""
    top_at = before_night(gig.last_pickup_at - margin(gig), now)
    if top_at - now >= DROP_SPAN:
        return None
    return plan(now, gig, level, floor=min(ceiling(gig), dropped_fee * (1 + DROP_STEP)))


def before_night(at: int, now: int) -> int:
    """A step due at night comes at 22:00 the evening before, but not before now."""
    minute = at % DAY
    if minute >= NIGHT_FROM:
        return max(now, at - minute + EVENING)
    if minute < NIGHT_TO:
        return max(now, at - minute - DAY + EVENING)
    return at


def valid(steps: list[tuple[float, float]], level: int) -> list[FeeStep]:
    """Whole minutes and whole cents, times in order, fees never falling, 1 to 48 steps, one at level 1."""
    schedule: list[FeeStep] = []
    for at, fee in sorted(steps, key=lambda step: step[0]):
        # int(x + 0.5) rounds halves up, as the starter does.
        step: FeeStep = {"at": int(at), "feeCents": max(1, int(fee + 0.5))}
        if schedule and step["feeCents"] < schedule[-1]["feeCents"]:
            step["feeCents"] = schedule[-1]["feeCents"]
        if schedule and step["at"] <= schedule[-1]["at"]:
            schedule[-1]["feeCents"] = step["feeCents"]
        elif schedule and step["feeCents"] == schedule[-1]["feeCents"]:
            continue  # no raise: the step changes nothing in the app
        else:
            schedule.append(step)
    return schedule[:1] if level == 1 else schedule[:MAX_STEPS]
