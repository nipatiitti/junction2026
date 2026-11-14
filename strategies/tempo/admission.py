"""Admission whose capacity follows how fast our gigs book: an area where drivers take our gigs within minutes has
drivers to spare, and one where gigs wait for hours has none, whatever the driver list says.

A strategy (strategies/strategy.py) built on the timed return leg of strategies/ceiling, unchanged there. The base
(strategies/admission) sizes each area's capacity from the drivers who live near it, and only tightens it after
deadline warnings, which come hours late. Level 8 multiplies each town's drivers by a factor of its own, and the
driver list does not show who works. The time from a post to its booking does, from the first hour of the week. Here
each pickup area's capacity is the base's times its tempo: the share of our gigs there that a driver took within
`quick` minutes, over the world's share, shrunk to the world while the area has few gigs. README.md next to this file
has the formula.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace

from spread.types import DeskEvent, DriverProfile, WorldMap

from strategies.admission import Held, Verdict
from strategies.ceiling.admission import ChainAdmission
from strategies.ceiling.admission import Params as ChainParams


@dataclass(frozen=True)
class Params(ChainParams):
    """The thresholds of the timed return leg, plus the tempo."""

    quick: int = 30  # a gig booked within this many minutes of its post is quick
    pool: int = 30  # gigs with a pickup within this drive of the place count for its tempo
    area_prior: float = 6.0  # an area's share counts this many gigs at the world's share
    world_prior: float = 10.0  # the world's share counts this many gigs at `world_start`
    world_start: float = 0.7  # the share of quick bookings before the week shows its own
    low: float = 0.6  # an area's capacity never falls below this many times the base's
    high: float = 1.5  # nor rises above this many times


class TempoAdmission(ChainAdmission):
    """The ceiling system's admission, with each area's capacity scaled by how fast our gigs book there."""

    params: Params

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())
        self.waiting: dict[str, tuple[str, int]] = {}  # gig id -> (pickup place, minute posted), until it is known
        self.results: list[tuple[str, bool]] = []  # (pickup place, booked within `quick`), one for each gig
        self.factors: list[float] = []  # the factor of each request assessed, for the summary

    def posted(self, gig_id: str, place: str, at: int) -> None:
        """The desk posted a gig whose first pickup is at `place`."""
        self.waiting[gig_id] = (place, at)

    def observe(self, event: DeskEvent) -> None:
        """The base's learning, plus each gig's tempo: quick when a driver takes it within `quick` minutes, slow
        when it has waited longer."""
        super().observe(event)
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

    def world_share(self) -> float:
        """The share of our gigs that booked quickly, shrunk to `world_start`."""
        p = self.params
        quick = sum(q for _, q in self.results)
        return (quick + p.world_prior * p.world_start) / (len(self.results) + p.world_prior)

    def tempo(self, place: str) -> float:
        """The area's capacity factor: its share of quick bookings, shrunk to the world's, over the world's."""
        p = self.params
        world = self.world_share()
        near = [q for town, q in self.results if self.minutes.get((town, place), 10**6) <= p.pool]
        share = (sum(near) + p.area_prior * world) / (len(near) + p.area_prior)
        return min(p.high, max(p.low, share / world))

    def assess(self, request: dict, held: Iterable[Held] = (), now: int | None = None) -> Verdict:
        """The base's verdict, with the area's capacity scaled by its tempo."""
        usual = self.params
        factor = self.tempo(request["legs"][0]["pickup"]["placeId"])
        self.factors.append(factor)
        self.params = replace(
            usual,
            capacity_per_driver=usual.capacity_per_driver * factor,
            min_capacity=usual.min_capacity * factor,
        )
        try:
            return super().assess(request, held, now)
        finally:
            self.params = usual

    def summary(self) -> str:
        """The chain admission line, plus the week's tempo."""
        line = super().summary()
        if not line:
            return ""
        wider = sum(f > 1.005 for f in self.factors)
        narrower = sum(f < 0.995 for f in self.factors)
        return (
            f"{line}; tempo: {len(self.results)} gigs timed, {self.world_share():.0%} booked within "
            f"{self.params.quick} min; {wider} requests with more room, {narrower} with less"
        ).replace("Chain admission:", "Tempo admission:", 1)
