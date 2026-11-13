"""A bundler whose orders all wait for a chain: the bundling of strategies/bundling, unchanged there, with the wait
and the thresholds opened up so far more cars share a gig.

The base holds only the orders of a batch, and the bundling README says "without the wait, a week has only 2 to 5
[bundles]". Every order waits here, a car joins a chain for a smaller saving, and a chain may carry one more car.
The 12-hour rule, the window, buffer and lead checks and the audience match are the base's, so the on-time risk stays
contained. README.md next to this file has the numbers.
"""

from __future__ import annotations

from dataclasses import dataclass

from spread.types import DriverProfile, WorldMap

from strategies.bundling import Bundler
from strategies.bundling.bundling import Held
from strategies.bundling.bundling import Params as BundlingParams


@dataclass(frozen=True)
class Params(BundlingParams):
    """The base's thresholds, opened up: more orders wait, they join for less and a chain carries one more car."""

    max_cars: int = 4  # cars in one gig, against the base's 3
    min_saving: float = 5.0  # driver-minutes a car must save to join, against the base's 10
    hold: int = 60  # any order waits this long for a chain, never later than `safe` before its last pickup


class WaitingBundler(Bundler):
    """A Bundler whose every order waits for a chain, not only the orders of a batch."""

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())

    def hold(self, order_id: str, batch: str | None, last_pickup_at: int, now: int) -> None:
        """Puts a new order in the pool for `hold`, whether or not it belongs to a batch."""
        until = max(now, min(now + self.params.hold, last_pickup_at - self.params.safe))
        self.pool[order_id] = Held(order_id, batch, now, until)

    def ready(self, held: Held, now: int) -> bool:
        """An order of a batch goes when its batch has gone quiet, as the base has it; any other order waits out
        its `hold`, so that chains can form around it."""
        if not held.batch:
            return now >= held.until
        return super().ready(held, now)
