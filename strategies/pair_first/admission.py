"""Pair-first admission: prefer a request whose cars can continue on a transport we already hold.

A strategy (strategies/strategy.py) built on the headroom desk's lane-cost admission, unchanged there. The ceiling
system's timed return-leg check finds the partner and its claims keep one request per transport. Here the request
need not return to the partner's first pickup, its expected driver cost gets a configurable discount, and it takes a
configurable share of an area's capacity. README.md next to this file states the saving's assumption.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from spread.types import DriverProfile, WorldMap

from strategies.admission import Held, Verdict
from strategies.admission.admission import DAY
from strategies.ceiling.admission import FAR
from strategies.lane_fee import LaneCostAdmission, LaneFee
from strategies.lead_cost import LeadCostParams


@dataclass(frozen=True)
class Params(LeadCostParams):
    """The headroom admission thresholds, plus the pair discount and its area-capacity weight."""

    # A pair continues the partner's trip; unlike a return leg, it need not end near the partner's first pickup.
    back: int = FAR
    chain_discount: float = 0.15  # take this fraction off the usual expected driver cost when a partner exists
    pair_weight: float = 0.5  # the share of one area-capacity place that a paired request takes


class PairFirstAdmission(LaneCostAdmission):
    """The headroom admission with a chain saving priced into requests that pair with a held order."""

    params: Params

    def __init__(
        self,
        roster: list[DriverProfile],
        world_map: WorldMap,
        level: int = 8,
        params: Params | None = None,
        lane: LaneFee | None = None,
    ) -> None:
        super().__init__(roster, world_map, level, params or Params(), lane)

    def verdict(self, request: dict, held: list[Held], now: int) -> Verdict:
        """The headroom verdict, with a pair taking `pair_weight` of a place instead of a whole one."""
        p = self.params
        self._expire(now)
        leg = request["legs"][0]
        pickup, day = leg["pickup"]["placeId"], leg["pickup"]["window"]["from"] // DAY
        premium = any(leg["car"]["premium"] for leg in request["legs"])
        supply = self.supply(pickup, "experienced" if premium else "all") / self.stress(pickup)
        squeeze = self.tightening(self.on_time_share(held, now))
        per_driver = p.capacity_per_driver_posting if self.level == 1 else p.capacity_per_driver
        capacity = max(p.min_capacity, per_driver * supply) * squeeze
        load = self.load(pickup, day, held)
        weight = p.pair_weight if self.pairs(request, held) else 1.0
        if load + weight > capacity:
            return Verdict(False, [], 0, -1.0, f"area full: {load:.1f} waiting of {capacity:.1f}")
        min_slack = p.min_slack / max(squeeze, 0.5)
        usable = [o for o in request["options"] if self.option_slack(request, o, now) >= min_slack]
        if self.level == 1:  # every quote wins the request's first option, whichever option it prices
            usable = [o for o in usable[:1] if o is request["options"][0]]
        if not usable:
            return Verdict(False, [], self.expected_cost(request, held), -1.0, "no option leaves time for the drive")
        costs = {o["kind"]: self.lead_cost(request, o, held, now) for o in usable}
        fastest = min(o["deadline"] for o in request["options"])

        def worth(o: dict) -> float:
            """The option's margin, counted less when the dealer could have a faster one: it then wins less often."""
            margin = o["listPriceCents"] * p.price_factor - costs[o["kind"]]
            return margin * (p.slower_win if o["deadline"] > fastest and margin > 0 else 1.0)

        option = max(usable, key=worth)
        price, cost = option["listPriceCents"] * p.price_factor, costs[option["kind"]]
        margin = (price - cost) / price
        if margin < p.min_margin:
            return Verdict(False, [], cost, margin, f"cost {cost / 100:.0f} over price {price / 100:.0f}")
        self.pending[request["id"]] = (request["respondBy"], pickup, day, weight)
        return Verdict(True, [option["kind"]], cost, margin, "ok")

    def lead_cost(self, request: dict, option: dict, held: Iterable[Held], now: int) -> int:
        """The headroom driver cost, less `chain_discount` when the timed partner check succeeds.

        The base call sees no held orders so that its return-leg discount does not stack with this pair discount.
        """
        cost = super().lead_cost(request, option, (), now)
        if self.pairs(request, held):
            return int(cost * (1 - self.params.chain_discount) + 0.5)
        return cost
