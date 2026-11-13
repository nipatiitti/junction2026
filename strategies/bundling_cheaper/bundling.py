"""A bundler whose bundles keep a smaller share of what their cars would cost alone: the bundling of
strategies/bundling, unchanged there, with the fee rule pushed harder.

A bundle's fee is the sum of its cars' typical fees times the chain's cost over the sum of the solo costs, clamped to
`[fee_floor, fee_cap]`. The base caps it at 0.95, so a bundle may pay 95% of what its cars would cost posted alone;
here it caps at 0.8. The floor stays the base's 0.6, which is what keeps a bundle worth a driver's while: a two-car
bundle pays `2 x share` of a single car's fee, so a floor much under 0.5 would pay the driver less than the one car
they could take instead, and no one would take the bundle. README.md next to this file has the numbers.
"""

from __future__ import annotations

from dataclasses import dataclass

from spread.types import DriverProfile, WorldMap

from strategies.bundling import Bundler
from strategies.bundling.bundling import Params as BundlingParams


@dataclass(frozen=True)
class Params(BundlingParams):
    """The base's thresholds, with the share of the solo bill a bundle keeps capped lower."""

    fee_cap: float = 0.8  # a bundle pays at most this share of the sum of its single fees (the base's 0.95)


class CheapBundler(Bundler):
    """A Bundler whose bundles pay less per car and more in total than any single car of the chain."""

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())
