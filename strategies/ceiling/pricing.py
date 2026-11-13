"""Ceiling pricing: the price of a quote, as high as we still win, never above our maximum and never below what
the driver will cost us. The maximum is lifted only where the rules let a dealer accept more from us than the
competitor's price: dealer trust at level 8, and the outage region.

It builds on the adaptive quoting of strategies/pricing (#13), unchanged there: the learned multiplier with its
place and dealer offsets, the price war, the outage and dealer trust. No network: `price` takes a request and its
driver cost and returns a price for the options we quote, and `observe` takes the `order_won`, `order_lost` and
`ledger` events. README.md next to this file explains the model.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from spread.types import DriverProfile, WorldMap

from strategies.pricing.model import DAY, Outcome, PricingModel, Quote, in_hours, request_keys
from strategies.pricing.model import Params as PricingParams


@dataclass(frozen=True)
class CeilingParams(PricingParams):
    """The variables of ceiling pricing, next to those of the adaptive quoting (`strategies/pricing`)."""

    # The maximum: we quote at most the list price x (1 + max_markup), lifted where the dealer accepts more from us
    # than the competitor's price (`CeilingPricing.uplift`). At level 8 the competitor quotes about 40% over the list
    # price, so 0.39 stays just under it. Every price starts here.
    max_markup: float = 0.39
    # The premium on the driver cost for a driver who drops the gig, a failed visit, waiting and a late car. No quote
    # goes below the driver cost x (1 + risk_premium); when that is above the maximum, we decline the request.
    risk_premium: float = 0.10

    def __post_init__(self) -> None:
        # The learned multiplier never rises above the maximum. The params are frozen, so it is set this way.
        object.__setattr__(self, "ceiling", 1 + self.max_markup)


@dataclass
class CeilingQuote(Quote):
    """A quote, with what its outcome can teach."""

    capped: bool = False  # the learned price was at the maximum: a win cannot raise it
    floored: bool = False  # we quoted the driver cost floor, above the learned price: a loss says nothing of it


class CeilingPricing(PricingModel):
    """The adaptive quoting, started at our maximum and kept under it, over a floor of the driver cost."""

    params: CeilingParams

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: CeilingParams | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or CeilingParams())
        self.log_m = math.log(self.params.ceiling)  # every price starts at the maximum

    # --- prices -------------------------------------------------------------------------------

    def learned(self, request: dict) -> tuple[float, bool]:
        """The learned multiplier on the list price for this request, between `floor` and the maximum, and
        whether the maximum cut it."""
        log_m = self.log_m + sum(self.offset.get(k, 0.0) for k in request_keys(request))
        capped = log_m >= math.log(self.params.ceiling) - 1e-9  # the world's multiplier starts exactly at the top
        return min(self.params.ceiling, max(self.params.floor, math.exp(log_m))), capped

    def uplift(self, request: dict, now: int) -> float:
        """How much more than the competitor's price the dealer accepts from us: the outage boost in the outage
        region, where dealers turn to a dearer backup (x1.2, learning up to x1.5), and the dealer's trust at level 8
        (1% for each order on time, up to x1.25). It lifts the price and the maximum alike."""
        lift = 1.0
        if self.in_outage(request, now):
            lift *= math.exp(self.outage_log)
        if self.level >= 8 and self.params.trust:
            self.settle(now)
            lift *= 1 + self.trust.get(request["dealerId"], 0) / 100
        return lift

    def ceiling(self, request: dict, now: int) -> float:
        """The highest multiplier on the list price that we quote for this request now: the maximum, lifted."""
        if self.level <= 3:
            return 1.0
        return self.params.ceiling * self.uplift(request, now)

    def price(self, request: dict, now: int, cost: float = 0, kinds: Iterable[str] | None = None) -> dict[str, int]:
        """A price in cents for each option in `kinds` (every option by default): the learned price, at least the
        driver cost `cost` (cents) x (1 + risk_premium), and at most the lifted maximum. An option whose floor is
        above its maximum gets no price. Remembers the quote for its outcome. Up to level 3 every quote wins the
        first option at its list price: it gets that price when it is in `kinds`, and nothing gets a price else."""
        wanted = None if kinds is None else set(kinds)
        if self.level <= 3:
            first = request["options"][0]
            if wanted is not None and first["kind"] not in wanted:
                return {}  # admission picked a later option, which a quote cannot win here
            return {first["kind"]: first["listPriceCents"]}
        options = [o for o in request["options"] if wanted is None or o["kind"] in wanted]
        self.end_war(now)
        learned, capped = self.learned(request)
        lift = self.uplift(request, now)
        least = cost * (1 + self.params.risk_premium)
        prices: dict[str, int] = {}
        floored = True
        for option in options:
            listed = option["listPriceCents"]
            if self.in_war(now) and self.params.war_decline:
                prices[option["kind"]] = listed * self.params.decline_factor
                floored = False
                continue
            most = listed * self.params.ceiling * lift
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
        cost lost that request, not our price. The outcome still counts for the outage and war detectors, with the
        change it made: the maximum can cut a step."""
        quote = self.quotes.pop(request_id, None)
        if quote is None:
            return
        capped, floored = getattr(quote, "capped", False), getattr(quote, "floored", False)
        day, error = quote.at // DAY, (1.0 if won else 0.0) - self.params.target_win
        if not won and floored:
            error = 0.0
        if quote.outage:  # the outage boost has its own cap and learns from every outcome but a loss at the floor
            self.outage_log = min(math.log(1.5), max(0.0, self.outage_log + 2 * self.params.key_step * error))
            return
        if won and capped:
            error = 0.0
        if day == self.war_day and in_hours(quote.at):
            if not self.params.war_decline and not self.war_over:  # follow the war, but leave the lanes alone
                self.apply([("", self.params.step * error)])
            return
        if in_hours(quote.at):
            self.day_open.setdefault(day, self.log_m)
        updates = [("", self.params.step * error)] + [(k, self.params.key_step * error) for k in quote.keys]
        before = {key: self.value(key) for key, _ in updates}
        self.apply(updates)
        moved = [(key, self.value(key) - was) for key, was in before.items()]
        self.seen += 1
        if not in_hours(quote.at):
            return
        outcomes = self.today.setdefault(day, [])
        outcomes.append(Outcome(won, quote.pickup, moved))
        # One outage and one price war a week, never on the same day.
        if self.level >= 6 and self.outage is None and day != self.war_day:
            self.detect_outage(day, outcomes)
        if self.level >= 8 and day > 0 and self.war_day is None and (self.outage is None or self.outage[0] != day):
            self.detect_war(day, outcomes)

    def value(self, key: str) -> float:
        """The estimate that an update moves: the world's log multiplier for "", else the offset of the key."""
        return self.log_m if key == "" else self.offset.get(key, 0.0)

    def detect_outage(self, day: int, outcomes: list[Outcome]) -> None:
        """The outage detector of strategies/pricing, whose undo takes back what the region's outcomes moved today
        in one step for each estimate. Undone one outcome at a time, the maximum would cut the undo of each loss
        while the world's multiplier is at the top, and every lane's price would end lower than without the
        region's outcomes."""
        saved = self.log_m, dict(self.offset)
        super().detect_outage(day, outcomes)
        if self.outage is None:
            return
        self.log_m, self.offset = saved
        net: dict[str, float] = {}
        for o in outcomes:
            if o.pickup in self.outage[1]:
                for key, moved in o.updates:
                    net[key] = net.get(key, 0.0) + moved
        self.apply(list(net.items()), -1.0)
