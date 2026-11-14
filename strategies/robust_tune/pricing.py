"""Robust-tune pricing: headroom pricing with one world estimate and a slower response to individual outcomes.

A strategy (strategies/strategy.py) built on the headroom pricing of strategies/headroom, unchanged there. Place and
dealer offsets are off by default, so every request uses the world's learned multiplier under one moving maximum.
Dealer trust and the outage lift remain, because those premiums come from the rules rather than fitted lane effects.
README.md next to this file lists the defaults and the deliberately untested robustness hypothesis.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from spread.types import DriverProfile, WorldMap

from strategies.headroom.pricing import HeadroomPricing
from strategies.headroom.pricing import Params as HeadroomParams


@dataclass(frozen=True)
class Params(HeadroomParams):
    """Headroom's variables, plus whether to learn request offsets and how quickly old outcomes fade."""

    use_offsets: bool = False  # learn pickup, delivery and dealer offsets in addition to the world multiplier
    fade: float = 0.5  # share of headroom's usual world and maximum steps: half steps give old outcomes a longer fade


class RobustPricing(HeadroomPricing):
    """Headroom pricing whose learned price and maximum come from the world estimate alone by default."""

    params: Params

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())

    def learned(self, request: dict) -> tuple[float, bool]:
        """The world's learned multiplier, bounded by the usual floor and moving maximum. With offsets disabled no
        pickup, delivery or dealer can move a request's learned price, or make its effective maximum, away from it."""
        if self.params.use_offsets:
            return super().learned(request)
        log_m = self.log_m
        capped = log_m >= math.log(self.params.ceiling) - 1e-9
        return min(self.params.ceiling, max(self.params.floor, math.exp(log_m))), capped

    def apply(self, updates: list[tuple[str, float]], sign: float = 1.0) -> None:
        """Fades the world's updates and omits offset updates unless they are explicitly enabled."""
        scaled = [(key, delta * self.params.fade) for key, delta in updates if key == "" or self.params.use_offsets]
        super().apply(scaled, sign)

    def move_cap(self, won: bool) -> None:
        """Moves the one world maximum with the same rule and bounds as headroom, but with `fade` of its step."""
        p = self.params
        cap = math.log(1 + p.max_markup) + p.fade * p.cap_step * ((1.0 if won else 0.0) - p.cap_win)
        cap = min(math.log(1 + p.cap_high), max(math.log(1 + p.cap_low), cap))
        self.params = replace(p, max_markup=math.exp(cap) - 1)
        self.cap_moves["up" if won else "down"] += 1
