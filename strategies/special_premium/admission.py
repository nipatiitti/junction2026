"""Special-priced admission: the urgency admission of strategies/delivery_urgency, budgeting for the higher driver fee
its special requirements buy.

`SpecialPricing` raises the quote for a special request, but this class raises the expected driver cost by the same
factor (`specials.factor`), so the profit check compares the bigger quote against the bigger cost: the relative margin
is as before, and only the euro margin per order grows. Without this the admission would think the extra driver fee
were pure margin. README.md next to this file has the rule.
"""

from __future__ import annotations

from collections.abc import Iterable

from spread.types import DriverProfile, WorldMap

from strategies.admission import Held
from strategies.delivery_urgency.admission import Params as UrgencyAdmissionParams
from strategies.delivery_urgency.admission import UrgencyAdmission
from strategies.notes import NoteReader
from strategies.special_premium.specials import factor


class SpecialAdmission(UrgencyAdmission):
    """Urgency admission whose expected driver cost is multiplied by the special-requirement factor."""

    def __init__(
        self,
        roster: list[DriverProfile],
        world_map: WorldMap,
        level: int = 8,
        params: UrgencyAdmissionParams | None = None,
    ) -> None:
        super().__init__(roster, world_map, level, params)
        self.note_reader = NoteReader(roster, world_map, level)

    def expected_cost(self, request: dict, held: Iterable[Held] = ()) -> int:
        """The base's expected driver cost, times `1 + SPECIAL_SHARE` per special requirement, so admission budgets
        for the higher fee that `SpecialFeePlanner` posts."""
        return int(super().expected_cost(request, held) * factor(request, self.note_reader) + 0.5)
