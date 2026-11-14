"""E3 — statistical informed hold before trying the same cheap-solo-then-chain fallback.

An order at a dense follow-on destination can have a little longer to find a follow-on car; an order at a quiet
one doesn't. The expected number of new cars in this city's current day/hour is read from priors.json, fitted
from the saved weeks with one week per seed. Time windows, driver audience and the safe posting deadline win
before demand statistics. Everything else about solo-first trials is strategies/solo_chain/bundling.py's.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from spread.types import PriceRequest

from strategies.bundle_experiments.base import Fallback
from strategies.solo_chain.bundling import Params, SoloFirstBundler


@dataclass(frozen=True)
class PriorParams(Params):
    likely_cars: float = 0.5  # expected cars to earn one 60-minute hold
    some_cars: float = 0.25  # ... and one shorter 45-minute hold; less than this means no extra wait
    long_wait: int = 60
    short_wait: int = 45


class InformedBundler(SoloFirstBundler):
    params: PriorParams

    def __init__(self, roster, world_map, level: int = 8, params: PriorParams | None = None):
        super().__init__(roster, world_map, level, params or PriorParams())
        self.destination: dict[str, str] = {}
        self.priors = json.loads(Path(__file__).with_name("priors.json").read_text())["rates"]

    def request(self, request: PriceRequest) -> None:
        super().request(request)
        self.destination[request["id"]] = request["legs"][0]["delivery"]["placeId"]

    def prior(self, city: str, now: int) -> float:
        day, hour = now // 1440 % 7, now % 1440 // 60
        return self.priors.get(city, {}).get(str(day), {}).get(str(hour), 0.0)

    def hold(self, order_id: str, batch: str | None, last_pickup_at: int, now: int) -> None:
        super().hold(order_id, batch, last_pickup_at, now)
        if batch is None and last_pickup_at - now >= self.params.safe:
            likely = self.prior(self.destination.get(order_id, ""), now)
            if likely >= self.params.likely_cars * self.params.long_wait / 60:
                wait = self.params.long_wait
            elif likely >= self.params.some_cars * self.params.short_wait / 60:
                wait = self.params.short_wait
            else:
                return
            self.fallbacks[order_id] = Fallback(order_id, now + wait, batch, last_pickup_at)
