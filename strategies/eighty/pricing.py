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
from strategies.pricing.model import DAY, in_hours, request_keys


@dataclass(frozen=True)
class Params(PriorParams):
    """The variables of lane-prior pricing, plus the cost-aware move."""

    cost_slope: float = 0.0  # the price moves by this share of log(cost / price) away from the week's mean
    cost_limit: float = 0.2  # the move stays within this, in logs, up or down
    cost_mean: float = -0.37  # the mean of log(cost / price) before the week has quotes (saved weeks: -0.37)
    cost_prior: int = 20  # that starting mean counts as this many quotes
    shade: float = 0.0  # every price is lowered by this, in logs, after the move
    # The maximum's own offsets for each pickup place, delivery place and dealer (README.md): a quote at the maximum
    # moves them by this step, up after a win and down after a loss, so each settles where `cap_win` of its quotes at
    # the maximum win. 0 turns them off.
    key_cap_step: float = 0.0
    key_cap_limit: float = 0.15  # each offset stays within this, in logs, up or down


class CostPricing(PriorPricing):
    """Lane-prior pricing whose price leans with the driver cost of the request."""

    params: Params

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())
        self.cost_sum, self.cost_n = 0.0, 0  # the week's log(cost / price) of the quotes so far
        self.moved = {"up": 0, "down": 0}
        self.cap_offset: dict[str, float] = {}  # key -> the maximum's offset for it, in logs
        self.cap_moved = {"up": 0, "down": 0}

    def cap_lift(self, request: dict) -> float:
        """The maximum's own lift for the request: its pickup place's, delivery place's and dealer's offsets."""
        if self.level <= 3 or self.params.key_cap_step <= 0:
            return 1.0
        return math.exp(sum(self.cap_offset.get(key, 0.0) for key in request_keys(request)))

    def ceiling(self, request: dict, now: int) -> float:
        """The highest multiplier we quote for this request now, with the maximum's own lift: admission sees it too."""
        return super().ceiling(request, now) * self.cap_lift(request)

    def outcome(self, request_id: str, won: bool) -> None:
        """Moves the maximum's offsets of a quote at the maximum, then learns as lane-prior pricing does. The outage,
        the price war and a quote at the driver cost floor have their own rules and teach the offsets nothing."""
        p = self.params
        quote = self.quotes.get(request_id)
        if p.key_cap_step > 0 and quote is not None and getattr(quote, "capped", False):
            war = quote.at // DAY == self.war_day and in_hours(quote.at)
            if not getattr(quote, "floored", False) and not quote.outage and not war:
                step = p.key_cap_step * ((1.0 if won else 0.0) - p.cap_win)
                for key in quote.keys:
                    value = self.cap_offset.get(key, 0.0) + step
                    self.cap_offset[key] = max(-p.key_cap_limit, min(p.key_cap_limit, value))
        super().outcome(request_id, won)

    def mean(self) -> float:
        p = self.params
        return (p.cost_mean * p.cost_prior + self.cost_sum) / (p.cost_prior + self.cost_n)

    def price(self, request: dict, now: int, cost: float = 0, kinds: Iterable[str] | None = None) -> dict[str, int]:
        prices = super().price(request, now, cost, kinds)
        p = self.params
        if self.level <= 3 or not prices:
            return prices
        least = cost * (1 + p.risk_premium)
        listed = {o["kind"]: o["listPriceCents"] for o in request["options"]}
        quote = self.quotes.get(request["id"])
        lift = self.cap_lift(request)
        if quote is not None and getattr(quote, "capped", False) and lift != 1.0:
            # A quote at the maximum is at the maximum with its own lift.
            self.cap_moved["up" if lift > 1 else "down"] += 1
            prices = {
                kind: cents
                if cents >= p.decline_factor * listed.get(kind, cents)
                else max(1, int(max(least, cents * lift) + 0.5))
                for kind, cents in prices.items()
            }
        if cost <= 0 or p.cost_slope == 0 and p.shade == 0:
            return prices
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
        if self.params.key_cap_step > 0:
            line += (
                f"\nKey maximum: {self.cap_moved['up']} quotes at the maximum lifted, {self.cap_moved['down']} lowered; "
                f"{sum(1 for v in self.cap_offset.values() if v > 0)} keys up, "
                f"{sum(1 for v in self.cap_offset.values() if v < 0)} down"
            )
        return (
            f"{line}\nCost-aware: {self.moved['up']} prices raised for a dear car, {self.moved['down']} lowered, "
            f"mean log(cost / price) {self.mean():.3f}"
        )
