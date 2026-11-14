"""Outage admission: keep part of an area's capacity for requests that touch the flagged outage region.

A strategy (strategies/strategy.py) built on the headroom desk's lane-cost admission, unchanged there. Pricing's
existing detector supplies the region; this class does not detect an outage itself. While the region is active,
outside requests that share its pickup areas use only the unreserved capacity and must leave a wider margin.
README.md next to this file explains the reserve, its release and the risk of a false-positive flag.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace

from spread.types import DriverProfile, WorldMap

from strategies.admission import Held, Verdict
from strategies.headroom import HeadroomPricing
from strategies.lane_fee import LaneCostAdmission, LaneFee
from strategies.lead_cost import LeadCostParams
from strategies.pricing.model import DAY, in_hours


@dataclass(frozen=True)
class Params(LeadCostParams):
    """The headroom admission thresholds, plus the outage reserve and the margin outside it."""

    region_reserve: float = 0.5  # this share of a shared area's capacity is for requests touching the region
    outside_margin: float = 0.25  # outside requests sharing its drivers must leave this share of the price


class OutageAdmission(LaneCostAdmission):
    """The headroom admission with capacity reserved for the region flagged by its pricing model."""

    params: Params

    def __init__(
        self,
        roster: list[DriverProfile],
        world_map: WorldMap,
        level: int = 8,
        params: Params | None = None,
        lane: LaneFee | None = None,
        pricing: HeadroomPricing | None = None,
    ) -> None:
        super().__init__(roster, world_map, level, params or Params(), lane)
        self.pricing = pricing

    def region(self, now: int) -> frozenset[str] | None:
        """The region already flagged by pricing, only on its day and from 08:00 until 18:00."""
        if self.pricing is None or self.pricing.outage is None:
            return None
        day, region = self.pricing.outage
        return region if day == now // DAY and in_hours(now) else None

    def shares_drivers(self, pickup: str, region: frozenset[str]) -> bool:
        """Whether the pickup is in the admission area of a region place, in either road direction."""
        near = self.params.area_minutes
        return any(
            self.minutes.get((pickup, place), near + 1) <= near or self.minutes.get((place, pickup), near + 1) <= near
            for place in region
        )

    def assess(self, request: dict, held: Iterable[Held] = (), now: int | None = None) -> Verdict:
        """The headroom verdict, with the unreserved capacity and a wider margin for an outside request that
        would use the flagged region's drivers. Requests touching the region can use the reserve."""
        at = request["arrivedAt"] if now is None else now
        region = self.region(at)
        usual = self.params
        if region is not None:
            touches = any(leg[end]["placeId"] in region for leg in request["legs"] for end in ("pickup", "delivery"))
            pickup = request["legs"][0]["pickup"]["placeId"]
            if not touches and self.shares_drivers(pickup, region):
                available = 1 - usual.region_reserve
                self.params = replace(
                    usual,
                    capacity_per_driver=usual.capacity_per_driver * available,
                    min_capacity=usual.min_capacity * available,
                    min_margin=max(usual.min_margin, usual.outside_margin),
                )
        try:
            return super().assess(request, held, now)
        finally:
            self.params = usual
