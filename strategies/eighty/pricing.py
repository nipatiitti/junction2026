"""Cost-aware pricing: the lane-prior price, moved up for a car that is dear to move and down for a cheap one.

A strategy (strategies/strategy.py) built on the lane-prior pricing of strategies/lane_prior, unchanged there. That
pricing quotes every request at one learned multiplier on the list price, whatever the car costs us. The competitor
does not: one part of its price follows how hard the lane is for drivers (HANDBOOK.md), so where our driver cost is a
large share of our price, its price tends to be high too, and where the cost is small, its price tends to be low.
README.md next to this file has what the saved weeks show.

The move is about zero on average over the week's quotes, so the learned multiplier still settles where it wins its
target share: `cost_slope` x (log(cost / price) - the week's mean of it), within `cost_limit` either way. An optional
`shade` takes a further share off every price.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from spread.types import DriverProfile, WorldMap

from strategies.lane_prior import PriorPricing
from strategies.lane_prior.pricing import Params as PriorParams


@dataclass(frozen=True)
class Params(PriorParams):
    """The variables of lane-prior pricing, plus the cost-aware move."""

    cost_slope: float = 0.3  # the price moves by this share of log(cost / price) away from the week's mean
    cost_limit: float = 0.2  # the move stays within this, in logs, up or down
    cost_mean: float = -0.37  # the mean of log(cost / price) before the week has quotes (saved weeks: -0.37)
    cost_prior: int = 20  # that starting mean counts as this many quotes
    shade: float = 0.0  # every price is lowered by this, in logs, after the move


class CostPricing(PriorPricing):
    """Lane-prior pricing whose price leans with the driver cost of the request."""

    params: Params

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())
        self.cost_sum, self.cost_n = 0.0, 0  # the week's log(cost / price) of the quotes so far
        self.moved = {"up": 0, "down": 0}

    def mean(self) -> float:
        p = self.params
        return (p.cost_mean * p.cost_prior + self.cost_sum) / (p.cost_prior + self.cost_n)

    def price(self, request: dict, now: int, cost: float = 0, kinds: Iterable[str] | None = None) -> dict[str, int]:
        prices = super().price(request, now, cost, kinds)
        p = self.params
        if self.level <= 3 or cost <= 0 or not prices:
            return prices
        least = cost * (1 + p.risk_premium)
        listed = {o["kind"]: o["listPriceCents"] for o in request["options"]}
        out: dict[str, int] = {}
        mean = self.mean()
        for kind, cents in prices.items():
            if cents >= p.decline_factor * listed.get(kind, cents):  # the war's decline: leave it
                out[kind] = cents
                continue
            ratio = math.log(cost / cents)
            self.cost_sum += ratio
            self.cost_n += 1
            move = max(-p.cost_limit, min(p.cost_limit, p.cost_slope * (ratio - mean))) - p.shade
            self.moved["up" if move > 0 else "down"] += 1
            out[kind] = max(1, int(max(least, cents * math.exp(move)) + 0.5))
        return out

    def summary(self) -> str:
        line = super().summary()
        if not line:
            return ""
        return (
            f"{line}\nCost-aware: {self.moved['up']} prices raised for a dear car, {self.moved['down']} lowered, "
            f"mean log(cost / price) {self.mean():.3f}"
        )
