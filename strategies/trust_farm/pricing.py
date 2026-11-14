"""Trust-farm pricing: discount selected dealers' easy orders until their trust reaches a target, then harvest it.

Headroom pricing (strategies/headroom), unchanged there, already counts dealer trust from our own ledger and applies
its uplift. This class also counts each dealer's requests. While one of the busiest dealers is below the target, the
usual price and maximum are lowered by `farm_markup`; at the target, or after farming ends, headroom gets the full
uplift. README.md next to this file explains the two phases and the late-order guard.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from spread.types import DeskEvent, DriverProfile, WorldMap

from strategies.headroom.pricing import HeadroomPricing
from strategies.headroom.pricing import Params as HeadroomParams
from strategies.pricing.model import DAY, TRUST_CAP


@dataclass(frozen=True)
class Params(HeadroomParams):
    """Headroom's variables, plus which dealers to farm, how far, and when to stop."""

    farm_dealers: int = 3  # farm this many dealers with the most requests so far; ties go to the lower dealer id
    farm_target: int = 10  # stop discounting when the dealer counts this many orders on time, at most the game's 25
    farm_markup: float = 0.10  # take this markup off the normal maximum before trust and outage lifts: 1.39 -> 1.29
    farm_until_day: int = 2  # farm through this zero-based day (Wednesday); a late order cannot reopen it later


class TrustFarmPricing(HeadroomPricing):
    """Headroom pricing with an explicit farm phase below `farm_target` and a harvest phase from it onwards."""

    params: Params

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())
        self.requests: Counter[str] = Counter()  # dealer -> requests so far this week, including the current one

    def observe(self, event: DeskEvent) -> None:
        """Headroom's ledger learning, plus the request counts that choose the farm set."""
        if event["kind"] == "price_request":
            self.requests[event["request"]["dealerId"]] += 1
        super().observe(event)

    def farming(self, request: dict, now: int) -> bool:
        """Whether this request is in the farm phase now. Reaching the target harvests; passing Wednesday stays in
        harvest even when a late refund halves the count. Before then, a halved count below the target farms again.
        """
        if self.level < 8 or now // DAY > self.params.farm_until_day:
            return False
        self.settle(now)  # a revenue line from an earlier minute with no late refund is now known on time
        dealer = request["dealerId"]
        if self.trust.get(dealer, 0) >= min(self.params.farm_target, TRUST_CAP):
            return False
        busiest = sorted(self.requests, key=lambda d: (-self.requests[d], d))
        return dealer in busiest[: self.params.farm_dealers]

    def uplift(self, request: dict, now: int) -> float:
        """Headroom's trust and outage lift, scaled in the farm phase so the maximum loses `farm_markup` before the
        lift. The driver-cost floor in ceiling pricing stays unchanged. Harvest calls only the parent's rule.
        """
        lift = super().uplift(request, now)
        if self.farming(request, now):
            lift *= max(0.01, 1 - self.params.farm_markup / self.params.ceiling)
        return lift

    def price(self, request: dict, now: int, cost: float = 0, kinds=None) -> dict[str, int]:
        """The headroom price, discounted while farming. A deliberate farm cap gives no evidence about headroom's
        normal moving maximum, so its outcome does not move that maximum; it still teaches the learned price.
        """
        farmed = self.farming(request, now)
        prices = super().price(request, now, cost, kinds)
        if farmed and prices:
            self.counts["farmed"] += 1
            quote = self.quotes.get(request["id"])
            if quote is not None and getattr(quote, "capped", False):
                quote.capped = False
                self.counts["at the maximum"] -= 1
        return prices

    def summary(self) -> str:
        line = super().summary()
        if not line:
            return ""
        return f"{line}\nTrust farm: {self.counts['farmed']} discounted quotes"
