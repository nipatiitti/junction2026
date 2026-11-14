"""Outage pricing: headroom pricing with a configurable opening markup in the flagged outage region.

A strategy (strategies/strategy.py) built on strategies/headroom, unchanged there. The existing detector,
uplift and learning all stay in the base classes: only the starting outage boost is derived from `outage_markup`.
"""

from __future__ import annotations

from dataclasses import dataclass

from spread.types import DriverProfile, WorldMap

from strategies.headroom import HeadroomParams, HeadroomPricing


@dataclass(frozen=True)
class Params(HeadroomParams):
    """The headroom pricing variables, with the opening backup markup over the usual lifted price."""

    outage_markup: float = 0.3

    def __post_init__(self) -> None:
        super().__post_init__()
        object.__setattr__(self, "outage_boost", 1 + self.outage_markup)


class OutagePricing(HeadroomPricing):
    """Headroom pricing whose base outage uplift starts at `1 + outage_markup` and keeps learning."""

    params: Params

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())
