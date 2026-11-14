"""Scaled-cost admission: the same-day admission with its driver cost estimate scaled by one factor.

A strategy (strategies/strategy.py) built on the same-day admission of strategies/same_day, unchanged there. That
admission declines a request when its expected driver cost, plus the risk premium, does not fit under the highest
price we would quote. In the cheap worlds this is the most common reason to decline (README.md next to this file), so
`cost_scale` lets the bench measure whether the estimate is too high or too low. The scaled cost is also the floor
of the price and what the cost-aware pricing leans on.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from strategies.admission import Held
from strategies.same_day import SameDayAdmission
from strategies.same_day.admission import Params as SameDayParams


@dataclass(frozen=True)
class Params(SameDayParams):
    """The variables of the same-day admission, plus one factor on its driver cost."""

    cost_scale: float = 1.0  # every lead cost is multiplied by this


class ScaledAdmission(SameDayAdmission):
    """The same-day admission whose driver cost is scaled by `cost_scale`."""

    params: Params

    def __init__(self, roster, world_map, level: int = 8, params: Params | None = None, lane=None) -> None:
        super().__init__(roster, world_map, level, params or Params(), lane=lane)

    def lead_cost(self, request: dict, option: dict, held: Iterable[Held], now: int) -> int:
        return int(super().lead_cost(request, option, held, now) * self.params.cost_scale + 0.5)
