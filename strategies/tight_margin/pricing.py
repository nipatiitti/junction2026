"""Tight-margin pricing: ceiling's prices while the week's drivers keep up, max-margin's once they fall behind.

A strategy (strategies/strategy.py) built on the max-margin pricing of strategies/max_margin, unchanged there. On the
three seeds where max margin was played, it beat ceiling only on `spread-2`, and not for a dearer competitor: ceiling
sold there at 1.34 x the list price against 1.46 on `spread-1`, where max margin lost. On `spread-2`, ceiling's drivers
fell behind. Its cars paid €65.62 to their drivers against €53 to €62 on the other seeds, and its late refunds were the
highest; max margin, winning fewer cars at higher prices, paid €57.47 a car and refunded €26 instead of €205. By
Tuesday night ceiling's and slack fees' weeks had 6 or 7 deadline warnings and expired gigs on `spread-2` and 10 on
`spread-4`, against 0 or 1 on `spread-1`, `spread-3` and `spread-5`.

So this pricing starts as ceiling's: a maximum of 1.39 x the list price, the lane and dealer offsets of ceiling, and a
floor of the driver cost x 1.10. It counts the week's `deadline_close` and `gig_expired` events; at `tight_after` of
them before Tuesday 24:00 (`tight_by`), the drivers are behind, and it turns into max-margin pricing for the rest of
the week: up to 2.0 x the list price, the option and lane-length offsets, and a floor of the driver cost x 1.25.
README.md next to this file has the numbers.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from spread.types import DeskEvent, DriverProfile, WorldMap

from strategies.max_margin import MaxPricing
from strategies.max_margin import Params as MaxParams
from strategies.pricing.model import DAY

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
BEHIND = ("deadline_close", "gig_expired")  # the events that show the drivers falling behind


@dataclass(frozen=True)
class Params(MaxParams):
    """Max-margin pricing's variables for a tight week, the calm week's beside them, and when to switch."""

    tight_after: int = 4  # deadline warnings and expired gigs before the week counts as tight
    # Only those before Tuesday 24:00 count: later in the week a busy day brings a few in every world.
    tight_by: int = 2 * DAY
    calm_markup: float = 0.39  # ceiling's maximum, 1.39 x the list price
    calm_key_step: float = 0.015  # ceiling's offset step
    calm_key_limit: float = 0.25  # ceiling's offset limit
    calm_risk_premium: float = 0.10  # ceiling's floor over the driver cost


class TightPricing(MaxPricing):
    """Ceiling's prices until the drivers fall behind, then max-margin's."""

    params: Params

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        tight = params or Params()
        super().__init__(roster, world_map, level, tight)
        self.tight_params = tight
        self.params = replace(
            tight,
            max_markup=tight.calm_markup,
            key_step=tight.calm_key_step,
            key_limit=tight.calm_key_limit,
            risk_premium=tight.calm_risk_premium,
        )
        self.tight = False
        self.behind = 0
        self.tight_at: int | None = None

    def observe(self, event: DeskEvent) -> None:
        """Max-margin pricing's learning, and the count of deadline warnings and expired gigs that switches it, until
        `tight_by`."""
        super().observe(event)
        if self.tight or event["kind"] not in BEHIND:
            return
        at = event.get("at")
        if isinstance(at, int) and at >= self.params.tight_by:
            return
        self.behind += 1
        if self.behind >= self.params.tight_after:
            self.tight, self.tight_at, self.params = True, event.get("at"), self.tight_params

    def segment(self, request: dict) -> tuple[str, ...]:
        """The option and lane-length offsets, once the week is tight; none before, as in ceiling."""
        return super().segment(request) if self.tight else ()

    def ceiling(self, request: dict, now: int) -> float:
        """Admission's highest price: ceiling's lifted maximum while calm, max margin's learned price with headroom
        once tight."""
        if self.tight:
            return super().ceiling(request, now)
        return super(MaxPricing, self).ceiling(request, now)

    def summary(self) -> str:
        """Max-margin's line, plus when the week turned tight."""
        line = super().summary()
        if not line:
            return line
        if not self.tight:
            return f"{line}; calm all week ({self.behind} deadline warnings and expired gigs)"
        at = self.tight_at or 0
        return f"{line}; tight from {WEEKDAYS[at // DAY % 7]} {at % DAY // 60:02d}:{at % 60:02d}"
