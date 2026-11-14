"""Special-delivery fees: the shared fee schedule, with the typical fee raised for the requirements that make a car
harder to place.

`SpecialPricing` charges the dealer `1.05 ** n` for `n` special requirements; this class pays drivers the same share,
by multiplying the gig's typical fee by `specials.factor`. Scaling the typical fee scales the whole opening/raise/top
schedule, so drivers actually get the compensation, not just the admission's estimate. Since the driver fee is a
fraction of the order's price, the same 5% is a bigger number on the quote than on the fee, and the euro margin grows.
The existing price-plus-penalty ceiling still caps it.
"""

from __future__ import annotations

from spread.types import DriverProfile, Order, PriceRequest, WorldMap

from strategies.fees import FeePlanner
from strategies.notes import NoteReader
from strategies.special_premium.specials import factor


class SpecialFeePlanner(FeePlanner):
    """The shared fee planner whose typical fee is multiplied by the special-requirement factor."""

    def __init__(self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: None = None) -> None:
        super().__init__(roster, world_map, level, params)
        self.note_reader = NoteReader(roster, world_map, level)

    def typical(self, order: Order, request: PriceRequest) -> float:
        """The typical fee of the order's cars, times the special-requirement factor; the scale carries through
        the schedule and the bundle's units."""
        return super().typical(order, request) * factor(request, self.note_reader)
