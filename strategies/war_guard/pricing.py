"""Ceiling pricing that forgets what the price war taught its lanes, and starts the outage at the backup's markup.

A strategy (strategies/strategy.py) built on the ceiling pricing of strategies/ceiling, unchanged there. Ceiling
pricing (through strategies/pricing) flags the price war only once the world's multiplier has fallen `war_drop`
below the day's opening, with losses on several pickups. Until then each war loss also lowers the offset of its
pickup, its delivery and its dealer, by 0.75% in logs each. At 18:00 the world's multiplier goes back to the day's
opening, but those offsets stay down, so the next days quote those lanes and dealers lower, for a war that is over.
Here, when the war is flagged, the day's outcomes give back what they moved on the offsets, as the outage detector
already does for its region. The outage's boost starts at `outage_boost`, 1.3 by default: dealers there turn to a
backup about 30% dearer than the competitor. README.md next to this file has the numbers.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from spread.types import DriverProfile, WorldMap

from strategies.ceiling.pricing import CeilingPricing
from strategies.ceiling.pricing import Params as CeilingParams
from strategies.pricing.model import Outcome

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


@dataclass(frozen=True)
class Params(CeilingParams):
    """Ceiling pricing's variables, with the outage's boost starting at the backup's markup."""

    outage_boost: float = 1.3


class WarGuardPricing(CeilingPricing):
    """Ceiling pricing that undoes the war day's lessons for its lanes and dealers once it flags the war."""

    params: Params

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())
        self.undone: Counter[str] = Counter()

    def detect_war(self, day: int, outcomes: list[Outcome]) -> None:
        """The base's detector. When it flags the war, the day's outcomes so far give back their moves on the pickup,
        delivery and dealer offsets; the world's multiplier keeps following the war, and goes back at 18:00."""
        was = self.war_day
        super().detect_war(day, outcomes)
        if was is not None or self.war_day != day:
            return
        for outcome in outcomes:
            keys = [(key, moved) for key, moved in outcome.updates if key != ""]
            self.apply(keys, -1.0)
            self.undone["outcomes"] += 1
            self.undone["offsets"] += len(keys)

    def summary(self) -> str:
        """The ceiling line, plus the war's lessons that were undone."""
        line = super().summary()
        if not line or self.war_day is None:
            return line
        return (
            f"{line}; war flagged on {WEEKDAYS[self.war_day % 7]}, {self.undone['outcomes']} of its outcomes taken back "
            f"from the lane and dealer offsets"
        )
