"""The baseline's quotes: the starter quotes the list price of each option it quotes, re-homed as a strategy.

It is the organisers' code from `spread/starter.py`, unchanged: every quote is the option's list price, and the
request's first option is the one admission picks. README.md next to this file says so.
"""

from __future__ import annotations

from spread.types import DeskEvent, DriverProfile, PriceRequest, WorldMap

from strategies.strategy import NoParams, Strategy


class BaselinePricing(Strategy[NoParams]):
    """The starter's price: the list price of each option that admission picked."""

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: NoParams | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or NoParams())

    def observe(self, event: DeskEvent) -> None:
        """Learns nothing from the week: the price is always the list price."""

    def price(self, request: PriceRequest, kinds: list[str]) -> dict[str, int]:
        """The list price of each option kind that admission picked."""
        options = {option["kind"]: option for option in request["options"]}
        return {kind: options[kind]["listPriceCents"] for kind in kinds}
