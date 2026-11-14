"""The quotes of the baseline with fee tiers: a fixed multiple of the list price.

No network: `price` takes a request and the option kinds that admission picked, as `BaselinePricing.price` does.
README.md next to this file has the rule.
"""

from __future__ import annotations

from dataclasses import dataclass

from spread.types import DeskEvent, DriverProfile, PriceRequest, WorldMap

from strategies.strategy import Strategy


@dataclass(frozen=True)
class Params:
    """The knob of the quotes."""

    multiple: float = 2  # every quote is this multiple of the option's list price


class FixedMultiplePricing(Strategy[Params]):
    """The list price of each option that admission picked, times `multiple`. Up to level 3 the dealer ignores the
    price: every quote wins at the list price."""

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())

    def observe(self, event: DeskEvent) -> None:
        """Learns nothing from the week: the multiple is fixed."""

    def price(self, request: PriceRequest, kinds: list[str]) -> dict[str, int]:
        """`multiple` times the list price of each option kind that admission picked, rounded down to the cent."""
        options = {option["kind"]: option for option in request["options"]}
        return {kind: int(options[kind]["listPriceCents"] * self.params.multiple + 1e-6) for kind in kinds}
