"""The ifs fees: the fee schedule of a gig by plain rules, with every number in values.json (rules.py).

A schedule opens at `fee_open` times the typical fee, raises twice, and reaches its top fee `fee_top_hours` before the
order's last pickup, so a driver who books at the top can still reach the car. A car that can wait holds its early
fee, and a gig with little time left opens nearer the top. The helpers that keep a schedule inside the rules of the
game, and the fees after a drop, are those of strategies/fees, unchanged there. README.md next to this file has the
rules.
"""

from __future__ import annotations

from spread.types import DriverProfile, FeeStep, Order, PriceRequest, WorldMap

from strategies.fees import FeePlanner, Gig
from strategies.fees import plan as base_plan
from strategies.fees.schedule import DAY, HOUR, LATE_TOP, before_night, ceiling, valid, worth
from strategies.ifs.rules import Params


def plan(now: int, gig: Gig, level: int, v: Params, opening: float | None = None) -> list[FeeStep]:
    """The fee schedule of a gig from `now`. `opening` is the opening fee over the typical fee, `fee_open` when not
    given. Level 1 has one fee for each gig, which strategies/fees plans."""
    if level == 1:
        return base_plan(now, gig, level)
    top = max(1.0, min(gig.typical * v.fee_top, ceiling(gig)))
    top_at = before_night(gig.last_pickup_at - round(v.fee_top_hours * HOUR), now)
    span = top_at - now
    if span <= HOUR:  # the top fee is due within the hour: a driver needs all the time that is left
        steps = [(now, top)]
        if now >= gig.last_pickup_at:  # late already: step up once more a day after the last pickup
            later = max(now + HOUR, gig.last_pickup_at + DAY)
            steps.append((later, max(top, min(gig.typical * LATE_TOP, ceiling(gig, later)))))
        return valid(steps, level)
    # With less than `fee_urgent_hours` before the top fee is due, every fee moves towards the top.
    urgency = max(0.0, 1 - span / (v.fee_urgent_hours * HOUR))

    def fee(multiple: float) -> float:
        early = gig.typical * multiple
        return min(top, early + (top - early) * urgency)

    first = fee(v.fee_open if opening is None else opening)
    cap = max(first, min(top, worth(gig)))  # a fee before the top stays at or under the price
    # The raises come `fee_raise_1_hours` and `fee_raise_2_hours` after the post, sooner when little time is left:
    # at the latest a third and two thirds of the way to the top fee.
    first_at = now + min(round(v.fee_raise_1_hours * HOUR), span // 3)
    second_at = now + min(round(v.fee_raise_2_hours * HOUR), span * 2 // 3)
    if span >= v.fee_patient_hours * HOUR:
        # The car can wait: the second raise comes `fee_hold_hours` before the top, not soon after the post, so a
        # driver who plans the pickup day the evening before still sees the early fee.
        second_at = max(second_at, top_at - round(v.fee_hold_hours * HOUR))
    steps = [
        (now, first),
        (before_night(first_at, now), min(fee(v.fee_raise_1), cap)),
        (before_night(second_at, now), min(fee(v.fee_raise_2), cap)),
        (top_at, top),
    ]
    return valid(steps, level)


class IfFees(FeePlanner):
    """The fee planner of strategies/fees, whose schedule of one order's gig comes from the rules above."""

    params: Params

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level)
        self.params = params or Params()
        self.km = {(road["from"], road["to"]): road["km"] for road in world_map["roads"]}

    def schedule(self, order: Order, request: PriceRequest, cars: int, now: int) -> list[FeeStep]:
        """The schedule for `cars` of the order's cars. A short trip and a car at a private address open at their
        own multiple of `fee_open`: the typical fee says least about what those cost a driver."""
        v = self.params
        opening = v.fee_open
        legs = order["legs"]
        if sum(self.km.get((leg["pickup"]["placeId"], leg["delivery"]["placeId"]), 0.0) for leg in legs) < v.short_km:
            opening *= v.fee_open_short
        if any(leg["pickup"]["privateAddress"] for leg in legs):
            opening *= v.fee_open_private
        return plan(now, self.gig(order, request, cars, now), self.level, v, opening)
