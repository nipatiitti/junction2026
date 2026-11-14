"""Admission for the two days that level 8 does not announce: the price war and the outage.

A strategy (strategies/strategy.py) built on the timed return leg of strategies/ceiling, unchanged there. Ceiling
pricing already flags both days (strategies/pricing): on the war day its price follows the competitor down, and in
the outage region it lifts the price. Admission does not know either, so in the outage it keeps the usual capacity,
and on the war day it takes a request whenever the driver cost fits under the usual maximum.

- **The outage.** For one working day dealers in one region turn to a backup about 30% dearer than the competitor.
  Here each area in the region holds `outage_capacity` times its usual cars, so more of those requests are taken.
- **The war.** For one working day the competitor quotes 20% under its usual prices. With `war_margin` set,
  admission checks the margin at the price we will really quote then, and asks that share of it, so the war day's
  drivers are left for the requests that pay. It is off: on the saved ceiling weeks the war day's orders earned
  about as much as the other days' (the driver cost floor of ceiling pricing holds there too), and every margin
  tried lost money in the offline replay. README.md next to this file has the numbers.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace

from spread.types import DriverProfile, WorldMap

from strategies.admission import Held, Verdict
from strategies.ceiling.admission import ChainAdmission
from strategies.ceiling.admission import Params as ChainParams


@dataclass(frozen=True)
class Params(ChainParams):
    """The thresholds of the timed return leg, plus the war's margin and the outage's capacity."""

    # On the war day, take a request only with this share of the war price left; None takes it as on other days.
    war_margin: float | None = None
    outage_capacity: float = 1.5  # in the outage region, an area holds this many times its usual cars


class WarGuardAdmission(ChainAdmission):
    """The ceiling system's admission, with room in the outage and, when asked, a wide margin on the war day."""

    params: Params

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())
        # The desk sets these before each assess, from ceiling pricing.
        self.war_price: float | None = None  # the multiplier we will quote on the war day, None on other days
        self.outage = False  # the request's pickup is in the outage region, during the outage

    def assess(self, request: dict, held: Iterable[Held] = (), now: int | None = None) -> Verdict:
        """The base's verdict, with more room in the outage region during the outage, and on the war day at the
        war price with the war margin when `war_margin` is set."""
        usual = self.params
        p = usual
        if self.war_price is not None and p.war_margin is not None:
            p = replace(p, price_factor=self.war_price, min_margin=max(p.min_margin, p.war_margin))
        if self.outage:
            p = replace(
                p,
                capacity_per_driver=p.capacity_per_driver * p.outage_capacity,
                min_capacity=p.min_capacity * p.outage_capacity,
            )
        self.params = p
        try:
            verdict = super().assess(request, held, now)
        finally:
            self.params = usual
        if self.war_price is not None:
            self.counts["war " + ("taken" if verdict.accept else "declined")] += 1
        if self.outage:
            self.counts["outage " + ("taken" if verdict.accept else "declined")] += 1
        return verdict

    def summary(self) -> str:
        """The chain admission line, plus the war day's and the outage's verdicts."""
        line = super().summary()
        if not line:
            return ""
        c = self.counts
        return (
            f"{line}; war day: {c['war taken']} taken, {c['war declined']} declined; outage: {c['outage taken']} "
            f"taken, {c['outage declined']} declined"
        ).replace("Chain admission:", "War-guard admission:", 1)
