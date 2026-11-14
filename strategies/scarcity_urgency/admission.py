"""Admission that prices a town's scarcity into the urgency-checked profit check, with the capacity gate optional.

It builds on the admission of strategies/delivery_urgency (#153), unchanged there, and adds the change of
strategies/scarcity_cost (#148):

- the expected fee is multiplied by `1 + risk(pickup)`, where `risk` is the town's quotas per driver a day, projected
  from the week so far, times `safety`, capped at `cap`. That is how contested the town is over the whole market,
  which our own waiting cars cannot see;
- the hard capacity gate is gone, so a contested town has to be paid for rather than refused.

`Params(gate=True)` puts the gate back and `Params(safety=0)` removes the scarcity term, so either change can be
benched on its own. The quote stays `UrgencyPricing`. README.md next to this file has the numbers.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from spread.types import DeskEvent, DriverProfile, WorldMap

from strategies.admission import Held
from strategies.delivery_urgency.admission import Params as UrgencyParams
from strategies.delivery_urgency.admission import UrgencyAdmission
from strategies.delivery_urgency.pricing import quote_price
from strategies.price_ladder.admission import Cost, Verdict

HOUR, DAY = 60, 24 * 60


@dataclass(frozen=True)
class Params(UrgencyParams):
    """The urgency admission's thresholds, plus the town's scarcity term and the capacity gate."""

    safety: float = 0.05  # the risk for each quota a driver in the town sees in a day
    cap: float = 0.5  # the scarcity term never rises above this
    gate: bool = False  # False: a full area is priced, not refused


class ScarcityUrgencyAdmission(UrgencyAdmission):
    """Urgency admission whose expected fee rises with the town's quotas per driver, and whose gate is optional."""

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())
        self.quotas: Counter[str] = Counter()  # pickup place -> the price requests we have seen for it
        self.first_at: int | None = None  # the minute of the week's first event

    def observe(self, event: DeskEvent) -> None:
        """The base's learning, plus the week's quotas: one for each request, at its pickup place."""
        super().observe(event)
        if self.first_at is None or event["at"] < self.first_at:
            self.first_at = event["at"]
        if event["kind"] == "price_request":
            self.quotas[event["request"]["legs"][0]["pickup"]["placeId"]] += 1

    def risk(self, place: str, now: int) -> float:
        """How contested the town is: the quotas its drivers see in a day, projected from the week so far, times
        `safety`, capped at `cap`. Zero where the place has no drivers or no quotas yet."""
        drivers = self.homes["all"].get(place, 0)
        if drivers <= 0:
            return 0.0
        days = max(1.0, (now - (self.first_at if self.first_at is not None else now)) / DAY)
        return min(self.params.cap, self.params.safety * self.quotas[place] / days / drivers)

    def expected_cost(self, request: dict, held: Iterable[Held] = ()) -> int:
        """The base's expected fee times `1 + risk(pickup)`: what the town's scarcity adds on top of the typical fee
        scaled by the supply, the hour, the note and a return leg. With `safety = 0` it is the base's."""
        place = request["legs"][0]["pickup"]["placeId"]
        return int(super().expected_cost(request, held) * (1 + self.risk(place, request["arrivedAt"])) + 0.5)

    def assess(self, request: dict, held: Iterable[Held] = (), now: int | None = None) -> Verdict:
        """The base's assessment with the capacity gate made optional: with `gate` off, only the price declines a
        request. Everything else, including the kind-adjusted quote the profit check uses, is the base's."""
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
        if p.gate and load + weight > capacity:
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
