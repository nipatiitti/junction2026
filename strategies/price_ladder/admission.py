"""Admission control with a shadow price for driver capacity: the admission of strategies/admission (#14),
unchanged there, with one addition.

The base's expected driver fee is what a driver will likely take for the cars. This class adds a second, notional
cost on top of it: the shadow price of the area capacity the order's driver hours use, from how full the area day
already is. It is what makes admission decline the marginal order once an area is filling, rather than only when
the base's hard capacity gate slams shut. The shadow is never paid to a driver: it does not reach strategies/fees,
and no posted fee includes it. README.md next to this file has the formula.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import NamedTuple

from spread.types import DriverProfile, WorldMap

from strategies.admission import Admission, Held
from strategies.admission.admission import Params as AdmissionParams

HOUR, DAY = 60, 24 * 60


@dataclass(frozen=True)
class Params(AdmissionParams):
    """The admission thresholds, plus the knobs of the shadow price."""

    kappa: float = 2000.0  # cents per driver hour, once the area is past `start` full
    start: float = 0.5  # the area load, as a share of its capacity, below which capacity is free
    eps: float = 0.05  # keeps the shadow finite as the area fills


class Cost(NamedTuple):
    """What one request's cars cost us, in three parts: the fee and hours are real, the shadow is notional."""

    fee: int  # cents: the driver fee we expect to pay, the base's expected cost
    hours: float  # the driver hours the cars take, the drive at least
    shadow: int  # cents: the shadow cost of the area capacity those hours use, never paid to a driver

    @property
    def total(self) -> int:
        """The cost the profit check compares the quote against."""
        return self.fee + self.shadow


class Verdict(NamedTuple):
    """The answer for one request, with the driver cost split into its fee and its shadow."""

    accept: bool
    options: list[str]
    cost: Cost
    score: float  # the expected margin over the price, after the shadow cost
    reason: str

    @property
    def expected_cost(self) -> int:
        """The driver fee we expect to pay, without the shadow cost."""
        return self.cost.fee


class ShadowAdmission(Admission):
    """Admission whose expected cost carries a shadow price for the area's driver capacity."""

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())

    def shadow_cost(self, hours: float, used: float) -> int:
        """The notional shadow cost of the area capacity that `hours` of driving uses, where `used` is the area
        day's load as a share of its capacity (1 when full). It is zero below `start` and grows without bound as
        the area fills: the opportunity cost of the orders the committed driver time crowds out."""
        p = self.params
        over = used - p.start
        if over <= 0:
            return 0
        return int(p.kappa * over / max(p.eps, 1 - used) * hours + 0.5)

    def assess(self, request: dict, held: Iterable[Held] = (), now: int | None = None) -> Verdict:
        """The base's assessment, with the shadow price of the capacity the request would use charged on top of
        the expected driver fee for the profit check."""
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
        price = option["listPriceCents"] * p.price_factor
        margin = (price - cost.total) / price
        if margin < p.min_margin:
            return Verdict(False, [], cost, margin, f"cost {cost.total / 100:.0f} over price {price / 100:.0f}")
        self.pending[request["id"]] = (request["respondBy"], pickup, day, weight)
        return Verdict(True, [option["kind"]], cost, margin, "ok")
