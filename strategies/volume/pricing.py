"""Volume pricing: the lane-prior pricing of strategies/lane_prior, priced per option for the option menu. Issue #304.

A strategy (strategies/strategy.py) built on `PriorPricing`, unchanged there. That pricing (from strategies/headroom)
learns one price that wins 45% of the quotes. With the option menu of admission.py a quote can carry several
options, so here:

- each option is priced over its own driver cost, which admission passes in, not over the cost of admission's pick;
- a faster option is never cheaper than a slower one;
- a quote with more than one option aims at 50% of its quotes, not 45%: the dealer has more ways to say yes at the
  same price, and aiming at 45% would take all of that back as price.

README.md next to this file has the numbers.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace

from strategies.ceiling.pricing import CeilingQuote
from strategies.lane_prior import PriorParams, PriorPricing
from strategies.pricing.model import request_keys


@dataclass(frozen=True)
class Params(PriorParams):
    """The variables of lane-prior pricing, plus the win share of a quote with several options."""

    menu_target_win: float = 0.50  # the share of the quotes with more than one option that the learned price aims at


@dataclass
class MenuQuote(CeilingQuote):
    """A quote, with the win share that its outcome is measured against."""

    target: float = 0.45


class VolumePricing(PriorPricing):
    """Lane-prior pricing with each option over its own driver cost, and its own win share for the option menu."""

    params: Params

    def price(
        self,
        request: dict,
        now: int,
        cost: float = 0,
        kinds: Iterable[str] | None = None,
        costs: Mapping[str, float] | None = None,
    ) -> dict[str, int]:
        """Ceiling pricing's price for each option in `kinds`, each over its own driver cost floor (`costs`, in cents by
        option; `cost` for an option without one), then no faster option under a slower one's price. Remembers the
        quote with the win share it aims at."""
        if self.level <= 3:
            return super().price(request, now, cost, kinds)
        p = self.params
        wanted = None if kinds is None else set(kinds)
        options = [o for o in request["options"] if wanted is None or o["kind"] in wanted]
        self.end_war(now)
        learned, capped = self.learned(request)
        lift = self.uplift(request, now)
        prices: dict[str, int] = {}
        floored = True
        for option in options:
            kind, listed = option["kind"], option["listPriceCents"]
            if self.in_war(now) and p.war_decline:
                prices[kind] = listed * p.decline_factor
                floored = False
                continue
            least = (costs or {}).get(kind, cost) * (1 + p.risk_premium)
            most = listed * p.ceiling * lift
            if least > most:
                continue  # the driver and the premium cost more than we may ask
            floored = floored and listed * learned * lift < least
            prices[kind] = max(1, int(min(most, max(listed * learned * lift, least)) + 0.5))
        prices = no_faster_cheaper(prices, request)
        if prices:
            real = sum(
                1 for o in options if o["kind"] in prices and prices[o["kind"]] < p.decline_factor * o["listPriceCents"]
            )
            self.counts["quoted"] += 1
            self.counts["at the maximum"] += capped
            self.counts["at the floor"] += floored
            self.counts["several options"] += real > 1
            self.quotes[request["id"]] = MenuQuote(
                at=request["arrivedAt"],
                keys=request_keys(request),
                pickup=request["legs"][0]["pickup"]["placeId"],
                outage=self.in_outage(request, now),
                capped=capped,
                floored=floored,
                target=p.menu_target_win if real > 1 else p.target_win,
            )
            if self.lane(request) != 1.0:  # lane-prior pricing's count of lifted quotes
                self.lifted["up" if self.lane(request) > 1.0 else "down"] += 1
        return prices

    def outcome(self, request_id: str, won: bool) -> None:
        """Headroom pricing's learning, measured against the quote's own win share."""
        quote = self.quotes.get(request_id)
        target = getattr(quote, "target", None)
        if target is None or target == self.params.target_win:
            super().outcome(request_id, won)
            return
        usual = self.params.target_win
        self.params = replace(self.params, target_win=target)
        try:
            super().outcome(request_id, won)
        finally:
            self.params = replace(self.params, target_win=usual)

    def summary(self) -> str:
        line = super().summary()
        if not line:
            return ""
        return f"{line}\nVolume pricing: {self.counts['several options']} quotes with several options"


def no_faster_cheaper(prices: dict[str, int], request: dict) -> dict[str, int]:
    """Raises a faster option's price to a slower one's where it is lower, so a dealer is never paid to wait less."""
    out = dict(prices)
    floor = 0
    for option in sorted((o for o in request["options"] if o["kind"] in prices), key=lambda o: -o["deadline"]):
        out[option["kind"]] = max(out[option["kind"]], floor)  # slowest first
        floor = out[option["kind"]]
    return out
