"""The base class of every strategy: one idea of the dispatch system, in its own folder under strategies/.

Every strategy is built the same way, from what the desk loads once when it starts, and the desk feeds each one every
event of the week the same way. README.md in this folder lists the strategies and says how to write a new one.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from spread.types import DeskEvent, DriverProfile, WorldMap

Minutes = dict[tuple[str, str], int]  # (from place, to place) -> road minutes


@dataclass(frozen=True)
class NoParams:
    """The params of a strategy that has no thresholds of its own, or keeps them as module constants."""


class Strategy[P](ABC):
    """One strategy of the dispatch system.

    - It is built from the driver list, the world map and the level, which the desk loads once when it starts, and
      from its own `params`: a frozen dataclass whose defaults are the tuned thresholds. Every strategy's constructor
      takes `(roster, world_map, level=8, params=None)` and passes its own default `Params()` here when none is given.
    - `observe` learns from one event of the week. The desk feeds every event to every strategy, in order.
    - The strategy's own methods answer the desk's questions, such as `Admission.assess` or `PricingModel.price`.
    - `summary` is one line on the strategy's week, printed at the end of a practice week.
    """

    def __init__(self, roster: list[DriverProfile], world_map: WorldMap, level: int, params: P) -> None:
        self.roster, self.world_map, self.level, self.params = roster, world_map, level, params
        self.minutes: Minutes = {(road["from"], road["to"]): road["minutes"] for road in world_map["roads"]}

    @abstractmethod
    def observe(self, event: DeskEvent) -> None:
        """Learns from one event of the week. A strategy that learns nothing from events says so here."""

    def summary(self) -> str:
        """One line on the strategy's week, or an empty string when it keeps none."""
        return ""
