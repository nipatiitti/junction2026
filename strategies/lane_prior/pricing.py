"""Lane-prior pricing: headroom pricing that starts each delivery place at the offset it has in every world.

A strategy (strategies/strategy.py) built on the headroom pricing of strategies/headroom, unchanged there. The
competitor's price on a lane has a part that is almost the same in every world: it is dearer where few drivers live
near the delivery place. `fit.py` measures that part on the saved weeks and writes it to priors.json; this class lifts
the price and the maximum of a request by the offset of its delivery place, as dealer trust and the outage lift them.
README.md next to this file explains the fit and why only the delivery place has a prior.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from spread.types import DriverProfile, WorldMap

from strategies.headroom.pricing import HeadroomPricing
from strategies.headroom.pricing import Params as HeadroomParams

PRIORS = Path(__file__).with_name("priors.json")


@dataclass(frozen=True)
class Params(HeadroomParams):
    """The variables of headroom pricing, plus how far the fitted offsets are trusted."""

    prior_weight: float = 0.7  # the share of a place's fitted offset that lifts its prices
    prior_limit: float = 0.15  # no place's lift is larger than this, in logs, up or down
    prior_down: float = 1.0  # the share of that for a place whose offset is negative: 0 only lifts, never lowers


class PriorPricing(HeadroomPricing):
    """Headroom pricing with the delivery place's offset from the saved weeks."""

    params: Params

    def __init__(
        self,
        roster: list[DriverProfile],
        world_map: WorldMap,
        level: int = 8,
        params: Params | None = None,
        priors: dict[str, float] | None = None,
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())
        fitted = json.loads(PRIORS.read_text())["delivery"] if priors is None else priors
        p = self.params
        self.prior = {
            place: max(
                -p.prior_limit, min(p.prior_limit, p.prior_weight * offset * (p.prior_down if offset < 0 else 1.0))
            )
            for place, offset in fitted.items()
        }
        self.lifted = {"up": 0, "down": 0}  # the week's quotes on a dearer and on a cheaper delivery place

    def lane(self, request: dict) -> float:
        """The lift of the request's delivery place: above 1 where the competitor is dear in every world."""
        if self.level < 4:
            return 1.0
        return math.exp(self.prior.get(request["legs"][-1]["delivery"]["placeId"], 0.0))

    def uplift(self, request: dict, now: int) -> float:
        """Ceiling pricing's lift (dealer trust, the outage) times the delivery place's. It lifts the price and the
        maximum alike, so admission sees the lane's price too."""
        return super().uplift(request, now) * self.lane(request)

    def price(self, request: dict, now: int, cost: float = 0, kinds=None) -> dict[str, int]:
        prices = super().price(request, now, cost, kinds)
        if prices and self.lane(request) != 1.0:
            self.lifted["up" if self.lane(request) > 1.0 else "down"] += 1
        return prices

    def summary(self) -> str:
        line = super().summary()
        if not line:
            return ""
        return f"{line}\nLane priors: {self.lifted['up']} quotes lifted for a dear delivery place, {self.lifted['down']} lowered for a cheap one"
