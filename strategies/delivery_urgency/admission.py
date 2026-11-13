"""Urgency-priced admission: the shadow admission of strategies/price_ladder, checking the kind-adjusted quote.

The base admission weighs a request's expected driver cost and the shadow price of its capacity against the price we
would quote. That price is the option's own list price times the ladder's multiple, which no longer matches what
`UrgencyPricing` sends: a faster option is quoted higher. This class overrides `assess` to compare the cost with the
kind-adjusted price of the option it picks, so a request is taken only when its real quote covers the cost.
README.md next to this file has the schedule.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from spread.types import DriverProfile, WorldMap

from strategies.admission import Held
from strategies.delivery_urgency.pricing import Schedule, quote_price
from strategies.price_ladder.admission import Cost, ShadowAdmission, Verdict
from strategies.price_ladder.admission import Params as BaseShadowParams

HOUR, DAY = 60, 24 * 60


@dataclass(frozen=True)
class Params(BaseShadowParams):
    """The shadow admission's thresholds, plus the schedule of the delivery options."""

    schedule: Schedule = field(default_factory=Schedule)


class UrgencyAdmission(ShadowAdmission):
    """Shadow admission whose profit check uses the kind-adjusted quote for the option it picks."""

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())

    def assess(self, request: dict, held: Iterable[Held] = (), now: int | None = None) -> Verdict:
        """The base's assessment, with the profit check on the kind-adjusted quote: a faster option is quoted higher,
        so it must clear the cost at that higher price. The rest of the choice of option is the base's."""
        held = list(held)
        p = self.params
        now = request["arrivedAt"] if now is None else now
        self._expire(now)
        leg = request["legs"][0]
        pickup, day = leg["pickup"]["placeId"], leg["pickup"]["window"]["from"] // DAY
        premium = any(leg["car"]["premium"] for leg in request["legs"])
        supply = self.supply(pickup, "experienced" if premium else "all") / self.stress(pickup)
        squeeze = self.tightening(self.on_time_share(held, now))
        paired = self.pairs(request, held)

        per_driver = p.capacity_per_driver_posting if self.level == 1 else p.capacity_per_driver
        capacity = max(p.min_capacity, per_driver * supply) * squeeze
        load = self.load(pickup, day, held)
        weight = 0.5 if paired else 1.0
        if load + weight > capacity:
            return Verdict(False, [], Cost(0, 0.0, 0), -1.0, f"area full: {load:.1f} waiting of {capacity:.1f}")

        # The capacity this request would use, as a share of the area day's: the shadow cost of it is charged
        # against the price, but is never paid to a driver.
        hours = self.drive_minutes(request["legs"]) / HOUR
        cost = Cost(self.expected_cost(request, held), hours, self.shadow_cost(hours, (load + weight) / capacity))
        min_slack = p.min_slack / max(squeeze, 0.5)
        usable = [o for o in request["options"] if self.option_slack(request, o, now) >= min_slack]
        if self.level == 1:  # every quote wins the request's first option, whichever option it prices
            usable = [o for o in usable[:1] if o is request["options"][0]]
        if not usable:
            return Verdict(False, [], cost, -1.0, "no option leaves time for the drive")
        comfortable = [o for o in usable if self.option_slack(request, o, now) >= p.comfortable_slack / squeeze]
        option = comfortable[0] if comfortable else usable[-1]
        price = quote_price(request, option["kind"], p.price_factor, p.schedule)
        margin = (price - cost.total) / price
        if margin < p.min_margin:
            return Verdict(False, [], cost, margin, f"cost {cost.total / 100:.0f} over price {price / 100:.0f}")
        self.pending[request["id"]] = (request["respondBy"], pickup, day, weight)
        return Verdict(True, [option["kind"]], cost, margin, "ok")
