"""The baseline's admission: the starter takes every request and quotes its first option, re-homed as a strategy.

It is the organisers' code from `spread/starter.py`, unchanged: the starter never declines, and it always quotes the
request's first option. README.md next to this file says so.
"""

from __future__ import annotations

from spread.types import DeskEvent, DriverProfile, PriceRequest, WorldMap

from strategies.strategy import NoParams, Strategy


class BaselineAdmission(Strategy[NoParams]):
    """The starter's admission: every request is taken, and its first option is the one quoted."""

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: NoParams | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or NoParams())

    def observe(self, event: DeskEvent) -> None:
        """Learns nothing from the week: every request is taken."""

    def options(self, request: PriceRequest) -> list[str]:
        """The option kinds to quote: the request's first option."""
        return [request["options"][0]["kind"]]
