"""Max-margin pricing: the war-guard pricing of strategies/war_guard, free to charge each kind of request as much as
it accepts.

A strategy (strategies/strategy.py) built on WarGuardPricing, unchanged there. Ceiling pricing (strategies/ceiling)
never quotes above 1.39 x the list price, lifted only for dealer trust and the outage. Its world multiplier starts
there and its lane and dealer offsets add on top of it, so once the multiplier is at the top, a request that would
pay more never gets a higher price. Here the price may climb to `max_markup` over the list price, and two offsets join
the lane and dealer ones: the delivery option quoted, and the lane's length by its list price. On our first
max-margin weeks, quotes above 1.45 x the list price won 42% of `same_day` requests against 22% of `next_day` ones,
and 42% of lanes under 60 km against 20% of those over 300 km, while a dealer's early wins hardly told its later ones.
A `same_day` quote aims to win `target_fast` of the time, the others `target_win`; no quote goes under the driver
cost x (1 + `risk_premium`). README.md next to this file has the numbers.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, replace

from spread.types import DriverProfile, WorldMap

from strategies.pricing.model import request_keys
from strategies.war_guard import WarGuardPricing, WarPricingParams

OLD_TOP = 1.39  # ceiling pricing's maximum over the list price, for the summary
# A lane's length by the cheapest option's list price, in cents: on the saved weeks, a next_day list price of €35 or
# less is a lane under 60 km, €58 under 150 km and €96 under 300 km.
BANDS = ((3500, "short"), (5800, "mid"), (9600, "long"))
FAST = "same_day"


@dataclass(frozen=True)
class Params(WarPricingParams):
    """War-guard pricing's variables, with a far higher maximum, an offset for the option and the lane's length, and
    a lower share to win for same-day quotes."""

    max_markup: float = 1.0  # at most 2.0 x the list price, before the trust and outage lift
    start: float = 1.39  # the world multiplier's first value: ceiling's maximum
    target_win: float = 0.5  # the share of next_day and within_3_days quotes the price aims to win, as in ceiling
    target_fast: float = 0.4  # the share of same_day quotes it aims to win: dealers pay more for speed
    key_step: float = 0.02  # each offset moves 2% in logs per outcome (ceiling: 1.5%)
    key_limit: float = 0.5  # an offset stays within ±50% (ceiling: ±25%)
    risk_premium: float = 0.25  # no quote under the driver cost x 1.25 (ceiling: x 1.10)
    headroom: float = 0.2  # admission's highest price: the learned price x 1.2, never above the maximum


def band(request: dict) -> str:
    """The lane's length, by the cheapest option's list price."""
    cheapest = min(o["listPriceCents"] for o in request["options"])
    return next((name for top, name in BANDS if cheapest <= top), "far")


class MaxPricing(WarGuardPricing):
    """War-guard pricing up to `max_markup`, with offsets for the option and the lane's length."""

    params: Params

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())
        self.log_m = math.log(self.params.start)
        self.kinds: list[str] | None = None  # the options being priced, while `price` runs

    def segment(self, request: dict) -> tuple[str, ...]:
        """The offsets beyond the lane and the dealer: the lane's length, and the option when one is priced."""
        keys = [f"band:{band(request)}"]
        if self.kinds is not None and len(self.kinds) == 1:
            keys.append(f"kind:{self.kinds[0]}")
        return tuple(keys)

    def learned(self, request: dict) -> tuple[float, bool]:
        """Ceiling's learned multiplier, with the option's and the lane length's offsets added."""
        log_m = self.log_m + sum(self.offset.get(k, 0.0) for k in request_keys(request) + self.segment(request))
        capped = log_m >= math.log(self.params.ceiling) - 1e-9
        return min(self.params.ceiling, max(self.params.floor, math.exp(log_m))), capped

    def ceiling(self, request: dict, now: int) -> float:
        """The highest multiplier on the list price that admission counts on for this request: the learned price with
        `headroom`, never above the maximum, lifted for trust and the outage. With the far higher maximum, admission
        would otherwise take every car whose driver costs less than twice its list price."""
        if self.level <= 3:
            return 1.0
        learned, _ = self.learned(request)
        return min(self.params.ceiling, learned * (1 + self.params.headroom)) * self.uplift(request, now)

    def price(self, request: dict, now: int, cost: float = 0, kinds: Iterable[str] | None = None) -> dict[str, int]:
        """War-guard pricing's price with the option's and the lane length's offsets; the quote learns them too, and
        a same_day quote remembers that it aims at `target_fast`."""
        self.kinds = None if kinds is None else list(kinds)
        try:
            prices = super().price(request, now, cost, self.kinds)
            quote = self.quotes.get(request["id"]) if prices else None
            if quote is not None and self.level >= 4:
                quote.keys = quote.keys + self.segment(request)
                quote.fast = list(prices) == [FAST]
                self.counts["same_day quotes"] += quote.fast
                lift = self.uplift(request, now)
                listed = {o["kind"]: o["listPriceCents"] for o in request["options"]}
                if not self.in_war(now) and any(p > listed[k] * OLD_TOP * lift for k, p in prices.items()):
                    self.counts["above the old maximum"] += 1
        finally:
            self.kinds = None
        return prices

    def outcome(self, request_id: str, won: bool) -> None:
        """War-guard pricing's outcome, aiming at `target_fast` for a same_day quote."""
        quote = self.quotes.get(request_id)
        if quote is None or not getattr(quote, "fast", False):
            super().outcome(request_id, won)
            return
        saved = self.params
        self.params = replace(saved, target_win=saved.target_fast)
        try:
            super().outcome(request_id, won)
        finally:
            self.params = saved

    def summary(self) -> str:
        """The war-guard line, renamed, plus the same_day quotes, the quotes above ceiling's old maximum, and the
        learned offsets of the option and the lane's length."""
        line = super().summary()
        if not line:
            return line
        learned = ", ".join(
            f"{k.split(':')[1]} {math.exp(v):.2f}"
            for k, v in sorted(self.offset.items())
            if k.startswith(("band:", "kind:"))
        )
        c = self.counts
        return (
            f"Max-margin {line[0].lower()}{line[1:]}; {c['same_day quotes']} same_day quotes, "
            f"{c['above the old maximum']} above x{OLD_TOP}; offsets {learned}"
        )
