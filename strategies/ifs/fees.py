"""The ifs fees: the fee schedule of a gig, with every number in values.json (rules.py).

The schedule is the dawn schedule of strategies/dawn_fees on the lane fee of strategies/lane_fee, both unchanged
there: a gig that has a morning before its last pickup opens low, holds that fee, and climbs from dawn on its last
morning, when the drivers plan their day; a gig with no morning to wait for climbs a short ladder. This file gives
that schedule its numbers from the values, and adds two rules to the opening fee. README.md next to this file has the
rules.
"""

from __future__ import annotations

from dataclasses import replace

from spread.types import DriverProfile, FeeStep, Order, PriceRequest, WorldMap

from strategies.dawn_fees import DawnParams, dawn_plan, last_dawn
from strategies.fees import FeePlanner
from strategies.ifs.rules import Params
from strategies.lane_fee import LaneFee, LaneFeePlanner

HOUR = 60


def dawn_params(v: Params) -> DawnParams:
    """The numbers of the dawn schedule, from the values. Hours become minutes."""
    return DawnParams(
        open=v.fee_open,
        hold=v.fee_hold,
        patience=round(v.fee_patience_hours * HOUR),
        quiet_from=round(v.fee_quiet_hour * HOUR),
        evening_at=round(v.fee_evening_hour * HOUR),
        tight=v.fee_tight,
        dawn_at=round(v.fee_dawn_hour * HOUR),
        dawn=v.fee_dawn,
        reach=round(v.fee_reach_hours * HOUR),
        step=max(1, round(v.fee_step_hours * HOUR)),
        top=v.fee_top,
        sprint=round(v.fee_sprint_hours * HOUR),
        sprint_open=v.fee_sprint_open,
        sprint_step=max(1, round(v.fee_sprint_step_minutes)),
    )


class IfFees(LaneFeePlanner):
    """The dawn fee planner on the lane fee, with its numbers from values.json."""

    def __init__(
        self,
        roster: list[DriverProfile],
        world_map: WorldMap,
        level: int = 8,
        params: Params | None = None,
        lane: LaneFee | None = None,
    ) -> None:
        self.values = params or Params()
        super().__init__(roster, world_map, level, dawn_params(self.values), lane)
        self.km = {(road["from"], road["to"]): road["km"] for road in world_map["roads"]}

    def typical(self, order: Order, request: PriceRequest) -> float:
        """The typical fee that every fee is a multiple of: the lane's, or the request's own (`lane_fee`)."""
        if not self.values.lane_fee:
            return FeePlanner.typical(self, order, request)
        return super().typical(order, request)

    def schedule(self, order: Order, request: PriceRequest, cars: int, now: int) -> list[FeeStep]:
        """The schedule for `cars` of the order's cars. A short trip and a car at a private address open at their
        own multiple of `fee_open`: the typical fee says least about what those cost a driver."""
        v = self.values
        opening = v.fee_open
        legs = order["legs"]
        if sum(self.km.get((leg["pickup"]["placeId"], leg["delivery"]["placeId"]), 0.0) for leg in legs) < v.short_km:
            opening *= v.fee_open_short
        if any(leg["pickup"]["privateAddress"] for leg in legs):
            opening *= v.fee_open_private
        gig = self.gig(order, request, cars, now)
        self.counts["dawn" if last_dawn(now, gig.last_pickup_at, self.params) is not None else "urgent"] += 1
        return dawn_plan(now, gig, self.level, replace(self.params, open=opening))
