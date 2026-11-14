"""Town opening: the opening fee of each pickup town, learned from how fast its gigs book.

Two strategies (strategies/strategy.py). `TownOpening` keeps one opening fee, as a multiple of the typical fee, for
the world and an offset for each pickup town: a gig that a driver books at its opening fee within minutes lowers it,
and a gig that needed a raise lifts it. `TownFeePlanner` is the lane fee planner of strategies/lane_fee, unchanged
there, opening each gig at its town's multiple. README.md next to this file explains the rule.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace

from spread.types import DeskEvent, DriverProfile, FeeStep, Order, PriceRequest, WorldMap

from strategies.dawn_fees import DawnParams, dawn_plan, last_dawn
from strategies.lane_fee import LaneFee, LaneFeePlanner
from strategies.strategy import Strategy


@dataclass(frozen=True)
class Params:
    """The variables of the opening fee. Each fee is a multiple of the gig's typical fee."""

    start: float = 0.9  # every town opens here on Monday: the opening fee of strategies/fees
    low: float = 0.8  # no town opens below this ...
    high: float = 1.0  # ... or above this
    quick: int = 20  # a booking at the opening fee within this many minutes of the post is a quick one
    quick_share: float = 0.7  # the opening settles where this share of a town's gigs book quickly
    step: float = 0.015  # the world's step per gig: -0.45% after a quick booking, +1.05% after a raise
    town_step: float = 0.03  # the same for the town's own offset: -0.9% and +2.1%
    town_limit: float = 0.12  # a town's offset stays within this of the world's opening
    same: float = (
        0.05  # a gig that opened within this of its town's fee teaches; one with little time left opens higher
    )


@dataclass
class Posted:
    """A gig that opened at its town's fee and has no driver yet."""

    place: str
    at: int
    fee: int


class TownOpening(Strategy[Params]):
    """Learns the opening fee of each pickup town. The desk tells it each gig it posts, with `posted`."""

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())
        self.world = self.params.start
        self.offset: dict[str, float] = {}  # pickup place -> what its opening differs from the world's by
        self.open: dict[str, Posted] = {}  # gig id -> the gig, while no driver has booked it
        self.counts: Counter[str] = Counter()

    def multiple(self, place: str) -> float:
        """The opening fee of a gig that starts at `place`, over its typical fee."""
        p = self.params
        if self.level < 2:  # level 1 has its own ladder (strategies/fees)
            return p.start
        return min(p.high, max(p.low, self.world + self.offset.get(place, 0.0)))

    def posted(self, gig_id: str, place: str, at: int, fee: int, multiple: float) -> None:
        """A gig of one order that the world accepted. It teaches only when it opened at about its town's fee: a gig
        with little time left opens far higher (strategies/fees), and says nothing of the town."""
        if multiple <= self.multiple(place) + self.params.same:
            self.open[gig_id] = Posted(place, at, fee)

    def observe(self, event: DeskEvent) -> None:
        """Learns from the first booking of each gig, and from a gig that expired without one."""
        kind = event["kind"]
        if kind == "gig_booked" or kind == "offer_answered" and event.get("answer") == "accepted":
            gig = self.open.pop(event["gigId"], None)
            if gig is None or "feeCents" not in event:  # an accepted offer does not say its fee
                return
            if event["feeCents"] > gig.fee:
                self.learn(gig.place, raised=True)
            elif event["at"] - gig.at <= self.params.quick:
                self.learn(gig.place, raised=False)
            else:
                self.counts["slow at the opening fee"] += 1
        elif kind == "gig_expired":
            gig = self.open.pop(event["gigId"], None)
            if gig is not None:
                self.learn(gig.place, raised=True)
        elif kind == "order_cancelled":
            for gig in event["gigs"]:
                self.open.pop(gig["gigId"], None)

    def learn(self, place: str, raised: bool) -> None:
        """One step for the world and for the town: down after a quick booking at the opening fee, up after a gig
        that needed a raise, so both settle where `quick_share` of the gigs book quickly."""
        p = self.params
        error = (1.0 if raised else 0.0) - (1 - p.quick_share)
        self.world = min(p.high, max(p.low, self.world + p.step * error))
        offset = self.offset.get(place, 0.0) + p.town_step * error
        self.offset[place] = min(p.town_limit, max(-p.town_limit, offset))
        self.counts["raised" if raised else "quick"] += 1

    def summary(self) -> str:
        c = self.counts
        if not c:
            return ""
        towns = sorted(self.offset, key=lambda place: self.multiple(place))
        ends = ", ".join(f"{place} {self.multiple(place):.2f}" for place in towns[:3] + towns[-3:])
        return (
            f"Town opening: {c['quick']} gigs booked quickly at the opening fee, {c['raised']} needed a raise, "
            f"{c['slow at the opening fee']} booked slowly at it; world x{self.world:.2f}; {ends}"
        )


class TownFeePlanner(LaneFeePlanner):
    """The lane fee planner, opening each gig at the fee of its pickup town."""

    def __init__(
        self,
        roster: list[DriverProfile],
        world_map: WorldMap,
        level: int = 8,
        params: DawnParams | None = None,
        lane: LaneFee | None = None,
        opening: TownOpening | None = None,
    ) -> None:
        super().__init__(roster, world_map, level, params, lane)
        self.opening = opening or TownOpening(roster, world_map, level)

    def schedule(self, order: Order, request: PriceRequest, cars: int, now: int) -> list[FeeStep]:
        gig = self.gig(order, request, cars, now)
        self.counts["dawn" if last_dawn(now, gig.last_pickup_at, self.params) is not None else "urgent"] += 1
        return dawn_plan(now, gig, self.level, replace(self.params, open=self.opening.multiple(pickup_place(order))))


def pickup_place(order: Order) -> str:
    """Where the order's first undelivered car waits: the place a gig for it starts at."""
    first = next((leg for leg, at in zip(order["legs"], order["deliveredAt"]) if at is None), order["legs"][0])
    return first["pickup"]["placeId"]
