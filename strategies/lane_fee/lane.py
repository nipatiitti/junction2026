"""Lane fee: the typical fee of a request without its noise, for admission and for the fee schedule.

Three strategies (strategies/strategy.py). `LaneFee` answers what a lane's work is usually paid: the mean typical fee
of the lane's requests in the saved weeks (lanes.json, fitted by fit.py), a line over the road minutes, and the
request's own typical fee, each weighted by how much it knows. `LaneCostAdmission` is the lead-cost admission of
strategies/lead_cost with its driver cost on that fee, and `LaneFeePlanner` the town fee planner of
strategies/town_open with its schedules on it; neither changes those folders. README.md next to this file explains why.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from spread.types import DeskEvent, DriverProfile, Order, PriceRequest, WorldMap

from strategies.dawn_fees import DawnParams
from strategies.fees.fees import trip
from strategies.lead_cost import LeadCostAdmission, LeadCostParams
from strategies.strategy import Strategy
from strategies.town_open import TownFeePlanner, TownOpening

LANES = Path(__file__).with_name("lanes.json")


@dataclass(frozen=True)
class Params:
    """How much each source of a lane's fee counts, in requests of the lane."""

    own: float = 1.0  # the request's own typical fee: one request of its lane
    line: float = 1.5  # the line over the road minutes: lanes differ from it about as much as 1.5 requests' noise


class LaneFee(Strategy[Params]):
    """The typical fee of a lane, from the saved weeks."""

    def __init__(
        self,
        roster: list[DriverProfile],
        world_map: WorldMap,
        level: int = 8,
        params: Params | None = None,
        fitted: dict | None = None,
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())
        fitted = json.loads(LANES.read_text()) if fitted is None else fitted
        self.base, self.per_minute = fitted["base"], fitted["per_minute"]
        self.lanes: dict[str, tuple[float, int]] = {lane: (mean, n) for lane, (mean, n) in fitted["lanes"].items()}

    def observe(self, event: DeskEvent) -> None:
        """Learns nothing from the week: the lanes are those of the saved weeks."""

    def typical(self, pickup: str, delivery: str, own: float | None = None) -> float:
        """The typical fee of the lane, in cents: the weighted mean, in logs, of the lane's saved requests, the line
        over its road minutes and, when it is for this trip, the request's own typical fee `own`."""
        p = self.params
        drive = self.minutes.get((pickup, delivery), 0)
        total, weight = p.line * math.log(max(1.0, self.base + self.per_minute * drive)), p.line
        if f"{pickup}>{delivery}" in self.lanes:
            mean, n = self.lanes[f"{pickup}>{delivery}"]
            total, weight = total + n * mean, weight + n
        if own is not None and own > 0:
            total, weight = total + p.own * math.log(own), weight + p.own
        return math.exp(total / weight)

    def of_request(self, request: PriceRequest) -> float:
        """The lane fee of a request: the lane of its first car, as its typical fee is (a trade-in's too)."""
        first = request["legs"][0]
        return self.typical(first["pickup"]["placeId"], first["delivery"]["placeId"], request["referenceFeeCents"])


class LaneCostAdmission(LeadCostAdmission):
    """The lead-cost admission, with its driver cost on the lane fee."""

    def __init__(
        self,
        roster: list[DriverProfile],
        world_map: WorldMap,
        level: int = 8,
        params: LeadCostParams | None = None,
        lane: LaneFee | None = None,
    ) -> None:
        super().__init__(roster, world_map, level, params)
        self.lane = lane or LaneFee(roster, world_map, level)

    def typical(self, request: dict) -> float:
        return self.lane.of_request(request)


class LaneFeePlanner(TownFeePlanner):
    """The town fee planner, with every schedule on the lane fee."""

    def __init__(
        self,
        roster: list[DriverProfile],
        world_map: WorldMap,
        level: int = 8,
        params: DawnParams | None = None,
        opening: TownOpening | None = None,
        lane: LaneFee | None = None,
    ) -> None:
        super().__init__(roster, world_map, level, params, opening)
        self.lane = lane or LaneFee(roster, world_map, level)

    def typical(self, order: Order, request: PriceRequest) -> float:
        """The lane fee of the trip the order's first car makes now. The request's own typical fee counts only while
        the car still goes where the request said: after a change of plan it is the fee of another trip."""
        first = order["legs"][0]
        same = all(trip(asked) == trip(now) for asked, now in zip(request["legs"], order["legs"]))
        own = request["referenceFeeCents"] if same else None
        return self.lane.typical(first["pickup"]["placeId"], first["delivery"]["placeId"], own)
