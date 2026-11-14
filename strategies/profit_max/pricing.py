"""Expected-profit pricing: each quote goes to the price where (price - driver cost) x the chance that the dealer takes
it is highest, not to one learned price for every request.

A strategy (strategies/strategy.py) built on the ceiling pricing of strategies/ceiling, unchanged there: the same
learned multiplier, offsets, maximum, lift, price war and outage. The base learns where half of our quotes win; this
class reads that price as the middle of a logistic win curve and picks, between the driver cost floor and the lifted
maximum, the price that earns most on average. A cheap car is quoted under the middle to win it more often, a dear one
over it. README.md next to this file explains the curve and its variables.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, replace

from spread.types import DriverProfile, WorldMap

from strategies.ceiling.pricing import CeilingPricing, CeilingQuote
from strategies.ceiling.pricing import Params as CeilingParams
from strategies.pricing.model import request_keys


@dataclass(frozen=True)
class Params(CeilingParams):
    """The variables of ceiling pricing, plus the win curve."""

    # The width of the win curve, in logs of the price: at the middle price half of the quotes win, at 8% above it
    # 27% do, at 8% below it 73%. The handbook says the chance falls quickly above the competitor's price.
    spread: float = 0.08
    grid: int = 41  # prices tried between the floor and the maximum, evenly in logs
    # A quote at the maximum cannot show where the middle is: we win more than half of them. The middle is then read
    # from the share of them that win, smoothed with this many pseudo-quotes at one half.
    capped_prior: float = 10.0


@dataclass
class ProfitQuote(CeilingQuote):
    """A ceiling quote, with the chance of a win that the curve gave the price we sent."""

    chance: float = 0.5


class ProfitPricing(CeilingPricing):
    """Ceiling pricing that picks each price for the most expected margin on the learned win curve."""

    params: Params

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())
        self.capped_seen = 0  # usual quotes whose learned price was at the maximum, with an outcome
        self.capped_won = 0
        self.moves: Counter[str] = Counter()  # the week's quotes, by where the curve put them against the middle

    def middle(self, learned: float, capped: bool) -> float:
        """The multiplier on the list price at which half of the quotes win. At the maximum, the share of the
        capped quotes that won says how far above it the middle lies."""
        if not capped:
            return learned
        prior = self.params.capped_prior
        share = (self.capped_won + prior / 2) / (self.capped_seen + prior)
        share = min(0.95, max(0.05, share))
        return learned * math.exp(self.params.spread * math.log(share / (1 - share)))

    def chance(self, price: float, middle: float) -> float:
        """The chance that the dealer takes `price` when half of the quotes at `middle` win."""
        x = (math.log(price) - math.log(middle)) / self.params.spread
        return 1 / (1 + math.exp(min(50.0, max(-50.0, x))))

    def best(self, low: float, high: float, middle: float, cost: float) -> float:
        """The price between `low` and `high` with the most expected margin, (price - cost) x chance."""
        if high <= low:
            return high
        n = max(2, self.params.grid)
        step = (math.log(high) - math.log(low)) / (n - 1)
        prices = [low * math.exp(step * k) for k in range(n)]
        return max(prices, key=lambda p: (p - cost) * self.chance(p, middle))

    def price(self, request: dict, now: int, cost: float = 0, kinds: Iterable[str] | None = None) -> dict[str, int]:
        """A price in cents for each option in `kinds`: the most expected margin on the win curve, at least the
        driver cost x (1 + risk_premium) and at most the lifted maximum. Up to level 3, during a declined price war,
        and without a cost, it prices as ceiling pricing does."""
        if self.level <= 3 or cost <= 0 or (self.in_war(now) and self.params.war_decline):
            return super().price(request, now, cost, kinds)
        wanted = None if kinds is None else set(kinds)
        options = [o for o in request["options"] if wanted is None or o["kind"] in wanted]
        self.end_war(now)
        learned, capped = self.learned(request)
        lift = self.uplift(request, now)
        middle = self.middle(learned, capped)
        least = cost * (1 + self.params.risk_premium)
        prices: dict[str, int] = {}
        floored, chances, sides = True, [], []
        for option in options:
            listed = option["listPriceCents"]
            most = listed * self.params.ceiling * lift
            if least > most:
                continue  # the driver and the premium cost more than we may ask
            low = max(least, listed * self.params.floor * lift)
            centre = listed * middle * lift
            chosen = self.best(min(low, most), most, centre, least)
            floored = floored and listed * learned * lift < least
            prices[option["kind"]] = max(1, int(chosen + 0.5))
            chances.append(self.chance(chosen, centre))
            sides.append(chosen / (listed * learned * lift))
        if not prices:
            return {}
        self.counts["quoted"] += 1
        self.counts["at the maximum"] += capped
        self.counts["at the floor"] += floored
        ratio = sum(sides) / len(sides)
        self.moves["under"] += ratio < 0.995
        self.moves["over"] += ratio > 1.005
        self.quotes[request["id"]] = ProfitQuote(
            at=request["arrivedAt"],
            keys=request_keys(request),
            pickup=request["legs"][0]["pickup"]["placeId"],
            outage=self.in_outage(request, now),
            capped=capped,
            floored=floored,
            chance=sum(chances) / len(chances),
        )
        return prices

    def outcome(self, request_id: str, won: bool) -> None:
        """Learns the middle of the curve from each outcome against the chance it gave the price we sent: a win at
        a price the curve called likely moves it little. A quote sent at the middle moves it as ceiling pricing
        does. A capped quote also counts towards the share of capped quotes that win."""
        quote = self.quotes.get(request_id)
        if quote is None:
            return
        if getattr(quote, "capped", False) and not quote.outage:
            self.capped_seen += 1
            self.capped_won += won
        target = self.params.target_win
        self.params = replace(self.params, target_win=getattr(quote, "chance", target))
        try:
            super().outcome(request_id, won)
        finally:
            self.params = replace(self.params, target_win=target)

    def summary(self) -> str:
        """The ceiling line, plus how often the curve quoted under and over the middle."""
        line = super().summary()
        if not line:
            return ""
        m = self.moves
        return f"{line}; profit curve: {m['under']} under the learned price, {m['over']} over it".replace(
            "Ceiling:", "Profit pricing:", 1
        )
