"""Special-delivery pricing: the urgency-ladder quote, raised by a premium for each special requirement.

It builds on the urgency pricing of strategies/delivery_urgency (#153), unchanged there: the same ladder, the same
schedule of option premiums, the same price war, outage and dealer trust. The one change is `multiplier`: a request
with special requirements is multiplied by `strategies/special_premium/specials.factor`, so an experienced car quotes
1.05 and an experienced manual car 1.1025 on top of the urgency ratio. Every dispatcher sets the admission's
`price_factor` from `multiplier()`, so the admission's margin check sees the same factor as the quote. No network.
"""

from __future__ import annotations

from spread.types import DriverProfile, WorldMap

from strategies.delivery_urgency.pricing import Params as UrgencyParams
from strategies.delivery_urgency.pricing import UrgencyPricing
from strategies.notes import NoteReader
from strategies.special_premium.specials import factor


class SpecialPricing(UrgencyPricing):
    """The urgency-ladder quote, multiplied by the special-requirement factor on top of the urgency premiums."""

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: UrgencyParams | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params)
        self.note_reader = NoteReader(roster, world_map, level)

    def multiplier(self, request: dict, now: int) -> float:
        """The ladder's factor times the special-requirement factor; up to level 3 quotes win anyway, so 1 stays 1."""
        m = super().multiplier(request, now)
        if self.level <= 3:
            return m
        return m * factor(request, self.note_reader)
