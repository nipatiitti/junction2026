"""Ceiling pricing: the price of a quote, as high as we still win, never above our maximum and never below what
the driver will cost us.

It builds on the adaptive quoting of strategies/pricing (#13), unchanged there: the learned multiplier with its
place and dealer offsets, the price war, the outage and dealer trust. No network: `price` takes a request and its
driver cost and returns a price for the options we quote, and `observe` takes the `order_won`, `order_lost` and
`ledger` events. README.md next to this file explains the model.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from strategies.pricing.model import DAY, Outcome, Params, PricingModel, Quote, in_hours, request_keys


@dataclass
class CeilingParams(Params):
    """The variables of ceiling pricing, next to those of the adaptive quoting (`strategies/pricing`)."""

    # The maximum: we quote at most the list price x (1 + max_markup). At level 8 the competitor quotes about 40%
    # over the list price, so 0.39 stays just under it. Every price starts here.
    max_markup: float = 0.39
    # The premium on the driver cost for a driver who drops the gig, a failed visit, waiting and a late car. No quote
    # goes below the driver cost x (1 + risk_premium); when that is above the maximum, we decline the request.
    risk_premium: float = 0.10

    def __post_init__(self) -> None:
        self.ceiling = 1 + self.max_markup  # the learned multiplier never rises above the maximum


@dataclass
class CeilingQuote(Quote):
    """A quote, with what its outcome can teach."""

    capped: bool = False  # the learned price was at the maximum: a win cannot raise it
    floored: bool = False  # we quoted the driver cost floor, above the learned price: a loss says nothing of it


class CeilingPricing(PricingModel):
    """The adaptive quoting, started at our maximum and kept under it, over a floor of the driver cost."""

    def __init__(
        self, level: int, places: dict[str, tuple[float, float]] | None = None, params: CeilingParams | None = None
    ):
        self.cp = params or CeilingParams()
        super().__init__(level, places, self.cp)
        self.log_m = math.log(self.cp.ceiling)  # every price starts at the maximum

    # --- prices -------------------------------------------------------------------------------

    def learned(self, request: dict) -> tuple[float, bool]:
        """The learned multiplier on the list price for this request, between `floor` and the maximum, and
        whether the maximum cut it."""
        log_m = self.log_m + sum(self.offset.get(k, 0.0) for k in request_keys(request))
        capped = log_m >= math.log(self.cp.ceiling) - 1e-9  # the world's multiplier starts exactly at the top
        return min(self.cp.ceiling, max(self.cp.floor, math.exp(log_m))), capped

    def uplift(self, request: dict, now: int) -> float:
        """How much more than the competitor's price the dealer accepts from us: the outage boost in the outage
        region, where dealers turn to a dearer backup, and the dealer's trust at level 8. It lifts the price and
        the maximum alike."""
        lift = 1.0
        if self.in_outage(request, now):
            lift *= math.exp(self.outage_log)
        if self.level >= 8 and self.cp.trust:
            self.settle(now)
            lift *= 1 + self.trust.get(request["dealerId"], 0) / 100
        return lift

    def ceiling(self, request: dict, now: int) -> float:
        """The highest multiplier on the list price that we quote for this request now: the maximum, lifted."""
        if self.level <= 3:
            return 1.0
        return self.cp.ceiling * self.uplift(request, now)

    def price(self, request: dict, now: int, cost: float = 0, kinds: Iterable[str] | None = None) -> dict[str, int]:
        """A price in cents for each option in `kinds` (every option by default): the learned price, at least the
        driver cost `cost` (cents) x (1 + risk_premium), and at most the maximum. An option whose floor is above its
        maximum gets no price. Remembers the quote for its outcome."""
        if self.level <= 3:  # every quote wins the first option at its list price
            first = request["options"][0]
            return {first["kind"]: first["listPriceCents"]}
        wanted = None if kinds is None else set(kinds)
        options = [o for o in request["options"] if wanted is None or o["kind"] in wanted]
        self.end_war(now)
        learned, capped = self.learned(request)
        lift = self.uplift(request, now)
        least = cost * (1 + self.cp.risk_premium)
        prices: dict[str, int] = {}
        floored = True
        for option in options:
            listed = option["listPriceCents"]
            if self.in_war(now) and self.cp.war_decline:
                prices[option["kind"]] = listed * self.cp.decline_factor
                floored = False
                continue
            most = listed * self.cp.ceiling * lift
            if least > most:
                continue  # the driver and the premium cost more than we may ask
            floored = floored and listed * learned * lift < least
            prices[option["kind"]] = max(1, int(min(most, max(listed * learned * lift, least)) + 0.5))
        if prices:
            self.quotes[request["id"]] = CeilingQuote(
                at=request["arrivedAt"],
                keys=request_keys(request),
                pickup=request["legs"][0]["pickup"]["placeId"],
                outage=self.in_outage(request, now),
                capped=capped,
                floored=floored,
            )
        return prices

    # --- learning -----------------------------------------------------------------------------

    def outcome(self, request_id: str, won: bool) -> None:
        """A win pushes the multiplier up and a loss pushes it down, so it settles where `target_win` of the quotes
        win. A win at the maximum leaves it there, and a loss at the driver cost floor teaches nothing about it: our
        cost lost that request, not our price. The outcome still counts for the outage and war detectors."""
        quote = self.quotes.pop(request_id, None)
        if quote is None:
            return
        capped, floored = getattr(quote, "capped", False), getattr(quote, "floored", False)
        day, error = quote.at // DAY, (1.0 if won else 0.0) - self.cp.target_win
        if not won and floored:
            error = 0.0
        if quote.outage:  # the outage boost has its own cap and learns from every outcome but a loss at the floor
            self.outage_log = min(math.log(1.5), max(0.0, self.outage_log + 2 * self.cp.key_step * error))
            return
        if won and capped:
            error = 0.0
        if day == self.war_day and in_hours(quote.at):
            if not self.cp.war_decline and not self.war_over:  # follow the war, but leave the lanes alone
                self.apply([("", self.cp.step * error)])
            return
        if in_hours(quote.at):
            self.day_open.setdefault(day, self.log_m)
        updates = [("", self.cp.step * error)] + [(k, self.cp.key_step * error) for k in quote.keys]
        self.apply(updates)
        self.seen += 1
        if not in_hours(quote.at):
            return
        outcomes = self.today.setdefault(day, [])
        outcomes.append(Outcome(won, quote.pickup, updates))
        # One outage and one price war a week, never on the same day.
        if self.level >= 6 and self.outage is None and day != self.war_day:
            self.detect_outage(day, outcomes)
        if self.level >= 8 and day > 0 and self.war_day is None and (self.outage is None or self.outage[0] != day):
            self.detect_war(day, outcomes)
