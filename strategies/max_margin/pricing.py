"""Max-margin pricing: the war-guard pricing of strategies/war_guard, free to charge each world, lane and dealer as
much as it accepts.

A strategy (strategies/strategy.py) built on WarGuardPricing, unchanged there. Ceiling pricing (strategies/ceiling)
never quotes above 1.39 x the list price, lifted only for dealer trust and the outage. Its world multiplier starts
there and its lane and dealer offsets add on top of it, so once the multiplier is at the top, a dealer who would pay
more never gets a higher price, and a world whose competitor sits at 1.54 x the list price, as level 8 allows, is
quoted as one at 1.39. Here the multiplier starts at `start`, just above the old top, and may climb to `max_markup`
over the list price; it aims to win `target_win` of the quotes, not half; the offsets may move further and faster;
and no quote goes under the driver cost x (1 + `risk_premium`). README.md next to this file has the numbers.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from spread.types import DriverProfile, WorldMap

from strategies.war_guard import WarGuardPricing, WarPricingParams

OLD_TOP = 1.39  # ceiling pricing's maximum over the list price, for the summary


@dataclass(frozen=True)
class Params(WarPricingParams):
    """War-guard pricing's variables, with a far higher maximum and a lower share of quotes to win."""

    max_markup: float = 1.0  # at most 2.0 x the list price, before the trust and outage lift
    start: float = 1.42  # the world multiplier's first value, just above ceiling's maximum
    target_win: float = 0.40  # the share of quotes the price aims to win: fewer cars, each at a higher margin
    key_step: float = 0.02  # each pickup, delivery and dealer offset moves 2% in logs per outcome (ceiling: 1.5%)
    key_limit: float = 0.5  # an offset stays within ±50% (ceiling: ±25%)
    risk_premium: float = 0.25  # no quote under the driver cost x 1.25 (ceiling: x 1.10)
    headroom: float = 0.2  # admission's highest price: the learned price x 1.2, never above the maximum


class MaxPricing(WarGuardPricing):
    """War-guard pricing that starts at `start`, climbs to `max_markup` and aims at `target_win`."""

    params: Params

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())
        self.log_m = math.log(self.params.start)

    def ceiling(self, request: dict, now: int) -> float:
        """The highest multiplier on the list price that admission counts on for this request: the learned price with
        `headroom`, never above the maximum, lifted for trust and the outage. With the far higher maximum, admission
        would otherwise take every car whose driver costs less than twice its list price."""
        if self.level <= 3:
            return 1.0
        learned, _ = self.learned(request)
        return min(self.params.ceiling, learned * (1 + self.params.headroom)) * self.uplift(request, now)

    def price(self, request: dict, now: int, cost: float = 0, kinds: Iterable[str] | None = None) -> dict[str, int]:
        """War-guard pricing's price, counting the quotes above ceiling's old maximum."""
        prices = super().price(request, now, cost, kinds)
        if self.level >= 4 and prices and not self.in_war(now):
            lift = self.uplift(request, now)
            listed = {o["kind"]: o["listPriceCents"] for o in request["options"]}
            if any(p > listed[k] * OLD_TOP * lift for k, p in prices.items()):
                self.counts["above the old maximum"] += 1
        return prices

    def summary(self) -> str:
        """The war-guard line, renamed, plus the quotes above ceiling's old maximum."""
        line = super().summary()
        if not line:
            return line
        return f"Max-margin {line[0].lower()}{line[1:]}; {self.counts['above the old maximum']} above x{OLD_TOP}"
