"""A read-only preview of the lane fee planner's schedule for a request that has not been won yet."""

from __future__ import annotations

from typing import cast

from spread.types import FeeStep, Order, PriceRequest

from strategies.dawn_fees import dawn_plan
from strategies.lane_fee import LaneFeePlanner


class JointFeePlanner(LaneFeePlanner):
    """The headroom fee planner, able to preview a schedule without posting it or counting it as posted."""

    def preview(
        self, request: PriceRequest, option: dict, price: int, last_pickup_at: int, now: int
    ) -> list[FeeStep] | None:
        """The full schedule for one solo order of every car in `request`, or None when there are no cars. `price`
        is the would-be order's price and `last_pickup_at` its last pickup, both estimated by the desk. This calls
        the same pure schedule function as `schedule`, but changes none of the planner's booking statistics."""
        if not request["legs"]:
            return None
        order = cast(
            Order,
            {
                **request,
                "priceCents": price,
                "lastPickupAt": last_pickup_at,
                "deliveredAt": [None] * len(request["legs"]),
            },
        )
        gig = self.gig(order, request, len(request["legs"]), now)
        return dawn_plan(now, gig, self.level, self.params) or None
