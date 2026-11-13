"""Admission with the town's driver scarcity priced into the cost, and no hard capacity gate.

It builds on the admission control of strategies/admission (#14), unchanged there, and replaces two of its parts:

- the flat shortage premium (`cost_base`, 1.15 at levels 7 and 8) with a scarcity term that rises with the town's
  quotas per driver;
- the hard capacity gate, which declines a request when an area's waiting cars reach `0.10 × supply`.

Scarcity then becomes a price, not a cliff: a contested town has to be paid for, and a town we win little of is still
contested, which our own load cannot see. The fee a driver is offered may go past this estimate (strategies/fees, up
to the quote's ceiling) and we take the loss on that order rather than leave the car. README.md next to this file has
the formula and the constants.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from spread.types import DeskEvent, DriverProfile, WorldMap

from strategies.admission import Admission, Held, Verdict
from strategies.admission.admission import Params as AdmissionParams

HOUR, DAY = 60, 24 * 60


@dataclass(frozen=True)
class Params(AdmissionParams):
    """The admission thresholds, plus the town's scarcity term on top of the base's expected fee."""

    safety: float = 0.05  # the risk for each quota a driver in the town sees in a day
    cap: float = 0.5  # the scarcity term never rises above this


class ScarcityAdmission(Admission):
    """Admission whose expected cost rises with a town's quotas per driver, and which never refuses a full area."""

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
        per_driver_day = self.quotas[place] / days / drivers
        return min(self.params.cap, self.params.safety * per_driver_day)

    def expected_cost(self, request: dict, held: Iterable[Held] = ()) -> int:
        """The base's expected fee, times `1 + risk(pickup)`: what the town's scarcity adds on top of the typical
        fee scaled by the supply, the hour, the note and a return leg. With `safety = 0` it is the base's."""
        place = request["legs"][0]["pickup"]["placeId"]
        return int(super().expected_cost(request, held) * (1 + self.risk(place, request["arrivedAt"])) + 0.5)

    def assess(self, request: dict, held: Iterable[Held] = (), now: int | None = None) -> Verdict:
        """The base's assessment without the capacity gate: the area's load is no longer a reason to decline, only
        the price is. The rest of the choice of option is the base's."""
        held = list(held)
        p = self.params
        now = request["arrivedAt"] if now is None else now
        self._expire(now)
        leg = request["legs"][0]
        pickup, day = leg["pickup"]["placeId"], leg["pickup"]["window"]["from"] // DAY
        squeeze = self.tightening(self.on_time_share(held, now))
        paired = self.pairs(request, held)

        cost = self.expected_cost(request, held)
        min_slack = p.min_slack / max(squeeze, 0.5)
        usable = [o for o in request["options"] if self.option_slack(request, o, now) >= min_slack]
        if self.level == 1:  # every quote wins the request's first option, whichever option it prices
            usable = [o for o in usable[:1] if o is request["options"][0]]
        if not usable:
            return Verdict(False, [], cost, -1.0, "no option leaves time for the drive")
        comfortable = [o for o in usable if self.option_slack(request, o, now) >= p.comfortable_slack / squeeze]
        option = comfortable[0] if comfortable else usable[-1]
        price = option["listPriceCents"] * p.price_factor
        margin = (price - cost) / price
        if margin < p.min_margin:
            return Verdict(False, [], cost, margin, f"cost {cost / 100:.0f} over price {price / 100:.0f}")
        self.pending[request["id"]] = (request["respondBy"], pickup, day, 0.5 if paired else 1.0)
        return Verdict(True, [option["kind"]], cost, margin, "ok")

    def summary(self) -> str:
        """One line on the week's most contested towns."""
        if not self.quotas:
            return ""
        worst = sorted(self.quotas, key=lambda p: -self.risk(p, 5 * DAY))[:3]
        return "Scarcity: " + ", ".join(f"{place} x{1 + self.risk(place, 5 * DAY):.2f}" for place in worst)
