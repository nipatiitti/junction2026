"""Radar pricing: lane-prior pricing with a surge, like a ride-hailing broker's, from the live balance of our open work
and our drivers near the pickup.

A strategy (strategies/strategy.py) built on the lane-prior pricing of strategies/lane_prior, unchanged there. The
radar is the desk's direct offers (strategies/offers), which already track where each of our drivers will finish our
gig and when, as a flight tracker shows where each plane will land, and which of our gigs no driver holds yet. This
class reads them and does not change them. README.md next to this file explains the rule.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import NamedTuple

from spread.types import DriverProfile, WorldMap

from strategies.lane_prior.pricing import Params as PriorParams
from strategies.lane_prior.pricing import PriorPricing
from strategies.offers import Offers

HOUR = 60


@dataclass(frozen=True)
class Params(PriorParams):
    """The variables of lane-prior pricing, plus the surge."""

    radar_minutes: int = 60  # work and drivers within this drive of the pickup count for its area
    fresh_minutes: int = 3 * HOUR  # a driver free this long ago may have gone home: no longer on the radar
    horizon: int = 18 * HOUR  # an open gig counts as demand when its last pickup minute is this close
    surge_power: float = 0.06  # the surge is the area's (demand + 1) / (supply + 1), to this power ...
    surge_up: float = 0.08  # ... and lifts a price at most this much, in logs (+8.3%) ...
    surge_down: float = 0.05  # ... and lowers it at most this much (-4.9%)
    center_weight: float = 0.02  # the weight of each quote in the week's mean balance, which the surge is measured from


class Radar(NamedTuple):
    """The area of one request's pickup now: our gigs there that no driver holds, and our drivers who will be free
    there in time to collect the car."""

    demand: int
    supply: int

    def balance(self) -> float:
        """The log of (demand + 1) / (supply + 1): above 0 where work waits for drivers, below 0 where drivers wait."""
        return math.log((self.demand + 1) / (self.supply + 1))


class RadarPricing(PriorPricing):
    """Lane-prior pricing whose lift has a surge for the balance of work and drivers near the pickup."""

    params: Params

    def __init__(
        self,
        roster: list[DriverProfile],
        world_map: WorldMap,
        level: int = 8,
        params: Params | None = None,
        radar: Offers | None = None,
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())
        self.radar = radar  # the desk's offers: where our drivers finish, and which gigs wait for one
        self.center = 0.0  # the week's mean balance so far: the surge lifts against it, so its mean stays near 1
        self.surged: Counter[str] = Counter()  # the week's quotes surged up and down, for the summary

    def scan(self, request: dict, now: int) -> Radar:
        """The radar of the request's first pickup: our open gigs within `radar_minutes` of it whose last pickup minute
        is within `horizon`, and our drivers who finish within `radar_minutes` of it and can reach it before its
        window ends."""
        if self.radar is None:
            return Radar(0, 0)
        p = self.params
        pickup = request["legs"][0]["pickup"]
        place, until = pickup["placeId"], pickup["window"]["to"]
        demand = 0
        for gig_id in self.radar.open:
            info = self.radar.gigs.get(gig_id)
            if info is None or not now <= info.pickup_until <= now + p.horizon:
                continue
            if self.minutes.get((info.pickup, place), 10**6) <= p.radar_minutes:
                demand += 1
        supply = 0
        for pos in self.radar.free.values():
            if pos.at < now - p.fresh_minutes:
                continue
            reach = self.minutes.get((pos.place, place), 10**6)
            if reach <= p.radar_minutes and max(pos.at, now) + reach <= until:
                supply += 1
        return Radar(demand, supply)

    def surge(self, request: dict, now: int) -> float:
        """The surge on the request's price: above 1 where more of our work waits near its pickup than the week's mean,
        below 1 where more of our drivers will be free there. Within `surge_down` and `surge_up`, in logs."""
        if self.level < 4 or self.radar is None:
            return 1.0
        p = self.params
        log = p.surge_power * (self.scan(request, now).balance() - self.center)
        return math.exp(min(p.surge_up, max(-p.surge_down, log)))

    def uplift(self, request: dict, now: int) -> float:
        """Lane-prior pricing's lift (dealer trust, the outage, the delivery place) times the surge. It lifts the price
        and the maximum alike. Admission weighs a request at `multiplier`, which has no surge: whether a car pays is
        its own question, and the surge only sets what we ask for it."""
        return super().uplift(request, now) * self.surge(request, now)

    def price(self, request: dict, now: int, cost: float = 0, kinds=None) -> dict[str, int]:
        prices = super().price(request, now, cost, kinds)
        if prices and self.level >= 4 and self.radar is not None:
            surge = self.surge(request, now)
            if surge != 1.0:
                self.surged["up" if surge > 1.0 else "down"] += 1
            # The mean moves after the quote, so admission and the price above saw the same surge.
            w = self.params.center_weight
            self.center = (1 - w) * self.center + w * self.scan(request, now).balance()
        return prices

    def summary(self) -> str:
        line = super().summary()
        if not line:
            return ""
        return (
            f"{line}\nRadar: {self.surged['up']} quotes surged where work waited for drivers, "
            f"{self.surged['down']} lowered where our drivers would be free; mean balance {self.center:+.2f}"
        )
