"""Contextual pricing: headroom pricing everywhere, except a lower maximum where our gigs book slowly.

A strategy (strategies/strategy.py) that delegates each request to one of two shared pricing objects, chosen by its
first pickup town. The desk tells it when each gig is posted; as in strategies/tempo, bookings and the time since the
post teach the town's booking rate. Every event reaches both pricing objects, so switching towns never loses their
learned state. README.md next to this file explains the selection rule.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace

from spread.types import DeskEvent, DriverProfile, WorldMap

from strategies.ceiling.pricing import CeilingPricing
from strategies.headroom.pricing import HeadroomPricing
from strategies.headroom.pricing import Params as HeadroomParams
from strategies.strategy import Strategy


@dataclass(frozen=True)
class Params(HeadroomParams):
    """The base pricing's variables, plus the slow-town estimate and its pricing cap."""

    quick: int = 30  # a gig booked within this many minutes of its post is quick
    slow_share: float = 0.5  # a town with observations is slow below this share of quick bookings
    slow_markup: float = 0.29  # the slow policy starts with this maximum markup, below the base's 0.39


class ContextualPricing(Strategy[Params]):
    """Chooses one shared pricing policy per request from its pickup town's observed booking rate."""

    def __init__(
        self,
        roster: list[DriverProfile],
        world_map: WorldMap,
        level: int = 8,
        params: Params | None = None,
        slow_policy: CeilingPricing | None = None,
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())
        self.base_policy = HeadroomPricing(roster, world_map, level, self.params)
        self.slow_policy = slow_policy or HeadroomPricing(
            roster, world_map, level, replace(self.params, max_markup=self.params.slow_markup)
        )
        self.policies = (self.base_policy, self.slow_policy)
        self.waiting: dict[str, tuple[str, int]] = {}  # gig id -> (pickup place, minute posted), until it is timed
        self.results: list[tuple[str, bool]] = []  # (pickup place, booked within `quick`), one for each timed gig

    def posted(self, gig_id: str, place: str, at: int) -> None:
        """The desk posted a gig whose first pickup is at `place`."""
        self.waiting[gig_id] = (place, at)

    def observe(self, event: DeskEvent) -> None:
        """Both policies learn every event; a booking, expiry or wait past `quick` also times one of our gigs."""
        for policy in self.policies:
            policy.observe(event)
        kind, at = event["kind"], event["at"]
        accepted = kind == "offer_answered" and event.get("answer") == "accepted"
        if (kind == "gig_booked" or accepted) and event["gigId"] in self.waiting:
            place, posted = self.waiting.pop(event["gigId"])
            self.results.append((place, at - posted <= self.params.quick))
        elif kind == "gig_expired" and event["gigId"] in self.waiting:
            self.results.append((self.waiting.pop(event["gigId"])[0], False))
        for gig_id, (place, posted) in list(self.waiting.items()):
            if at - posted > self.params.quick:
                del self.waiting[gig_id]
                self.results.append((place, False))

    def quick_share(self, place: str) -> float | None:
        """The share of the town's timed gigs that booked quickly, or None while the town has no observations."""
        observed = [quick for town, quick in self.results if town == place]
        return sum(observed) / len(observed) if observed else None

    def policy(self, request: dict) -> CeilingPricing:
        """The slow policy below `slow_share`, and the base policy otherwise and without observations."""
        place = request["legs"][0]["pickup"]["placeId"]
        share = self.quick_share(place)
        return self.slow_policy if share is not None and share < self.params.slow_share else self.base_policy

    def ceiling(self, request: dict, now: int) -> float:
        """The selected policy's maximum, which admission uses before pricing the same request."""
        return self.policy(request).ceiling(request, now)

    def price(self, request: dict, now: int, cost: float = 0, kinds: Iterable[str] | None = None) -> dict[str, int]:
        """Delegates the quote to the selected policy, leaving its learned state in that shared instance."""
        return self.policy(request).price(request, now, cost, kinds)
