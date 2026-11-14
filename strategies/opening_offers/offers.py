"""Direct offers to drivers who live near a pickup, from the moment a gig goes into the app."""

from __future__ import annotations

from dataclasses import dataclass

from spread.types import DriverProfile, WorldMap

from strategies.offers import Offers
from strategies.offers.offers import Params as OffersParams


@dataclass(frozen=True)
class Params(OffersParams):
    """The usual offer thresholds; nearby homes are considered for every open gig in this system."""


class OpeningOffers(Offers):
    """Also asks drivers who live near a pickup, not only drivers finishing one of our gigs near it.

    `Offers.candidates` includes nearby homes for a rescue. This system uses the same ranking from the
    start, but `offers` still charges the chain fee (0.85 of the app fee) rather than the rescue fee.
    Home-near drivers who never see an app notification therefore get a direct offer at the lower fee.
    """

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())

    def candidates(self, gig_id: str, now: int, rescue: bool) -> list[str]:
        """The rescue's wider candidate list at every stage, with the fee still decided by `offers`."""
        return super().candidates(gig_id, now, rescue=True)
