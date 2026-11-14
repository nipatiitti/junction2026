"""Adaptive chain waiting: each order waits according to how fast gigs book in its pickup town.

A strategy (strategies/strategy.py) built on strategies/bundling, unchanged there. Every order waits, as in
strategies/bundling_more, but the wait is short where drivers book quickly and longer where they book slowly or not
at all. The estimates come from our own gigs and fade towards the base's 45-minute wait. README.md next to this file
has the learning rule.
"""

from __future__ import annotations

from dataclasses import dataclass

from spread.types import DeskEvent, DriverProfile, Order, WorldMap

from strategies.bundling import Bundler
from strategies.bundling.bundling import Held
from strategies.bundling.bundling import Params as BundlingParams

HOUR = 60


@dataclass(frozen=True)
class Params(BundlingParams):
    """The base bundling thresholds, plus the bounds and memory of the adaptive wait."""

    min_hold: int = 15  # a town whose gigs book at `fast` minutes waits at least this long
    max_hold: int = 2 * HOUR  # a town whose gigs book at `slow` minutes, or mostly expire, waits at most this long
    fast: int = 30  # minutes per booked gig at or below which the hold is `min_hold`
    slow: int = 3 * HOUR  # minutes per booked gig at or above which the hold is `max_hold`
    memory: float = 4.0  # effective terminal gigs in each estimate; also caps the weight of a new one
    half_life: int = 12 * HOUR  # old observations lose half their weight in this many minutes


@dataclass
class Posted:
    """A gig with no terminal booking event yet."""

    place: str
    at: int
    views: int = 0


@dataclass
class Town:
    """The faded running estimates of one pickup town."""

    minutes: float = 0.0  # minutes from a post to its booking or expiry
    booked: float = 0.0  # share of terminal gigs that booked rather than expired
    weight: float = 0.0  # effective observations left after fading; zero means cold start
    at: int = 0  # when the weight was last faded
    views: int = 0  # views of the town's open gigs, for the summary


class AdaptiveHoldBundler(Bundler):
    """A Bundler whose every order waits for a chain for a time learned at its pickup town."""

    params: Params

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())
        self.order_places: dict[str, str] = {}
        self.open: dict[str, Posted] = {}  # gig id -> its first pickup and post minute
        self.towns: dict[str, Town] = {}

    def posted(self, gig_id: str, place: str, at: int) -> None:
        """The desk accepted a gig: time it from its first pickup town."""
        self.open[gig_id] = Posted(place, at)

    def town(self, place: str, at: int) -> Town:
        """Returns a town after fading its observations to `at`."""
        stats = self.towns.setdefault(place, Town(at=at))
        elapsed = max(0, at - stats.at)
        stats.weight *= 0.5 ** (elapsed / self.params.half_life)
        stats.at = at
        return stats

    def learn(self, gig: Posted, at: int, booked: bool) -> None:
        """Adds one terminal gig with a weight set by the faded history, so recent gigs count most."""
        stats = self.town(gig.place, at)
        step = 1.0 / (stats.weight + 1.0)
        stats.minutes += (max(0, at - gig.at) - stats.minutes) * step
        stats.booked += ((1.0 if booked else 0.0) - stats.booked) * step
        stats.weight = min(self.params.memory, stats.weight + 1.0)

    def observe(self, event: DeskEvent) -> None:
        """Keeps the base's batches and cancellations, and learns the booking tempo of each pickup town."""
        super().observe(event)
        kind, at = event["kind"], event["at"]
        accepted = kind == "offer_answered" and event.get("answer") == "accepted"
        if kind == "gig_booked" or accepted:
            if gig := self.open.pop(event["gigId"], None):
                self.learn(gig, at, booked=True)
        elif kind == "gig_expired":
            if gig := self.open.pop(event["gigId"], None):
                self.learn(gig, at, booked=False)
        elif kind == "gig_viewed":
            if gig := self.open.get(event["gigId"]):
                gig.views += 1
                # A view is interest, not a booked or expired outcome. It only ages the old terminal observations.
                self.town(gig.place, at).views += 1
        elif kind == "order_won":
            self.order_places[event["order"]["id"]] = pickup_place(event["order"])
        elif kind == "order_cancelled":
            self.order_places.pop(event["orderId"], None)
            for gig in event["gigs"]:
                self.open.pop(gig["gigId"], None)

    def wait(self, place: str | None, now: int) -> int:
        """Minutes to wait: the base `hold` while cold, then longer for slower bookings and more expiries.

        A town's minutes per booked gig is its running minutes to a terminal outcome, divided by its booked share.
        It maps linearly from `fast` to `slow` onto `min_hold` to `max_hold`. Faded observations blend that answer
        back towards the base `hold` as their weight falls.
        """
        if place is None or place not in self.towns:
            return self.params.hold
        stats = self.town(place, now)
        if stats.weight <= 0.0:
            return self.params.hold
        p = self.params
        pace = stats.minutes / max(stats.booked, 0.05)
        fraction = min(1.0, max(0.0, (pace - p.fast) / (p.slow - p.fast)))
        learned = p.min_hold + fraction * (p.max_hold - p.min_hold)
        confidence = min(1.0, stats.weight)
        return round(p.hold + confidence * (learned - p.hold))

    def hold(self, order_id: str, batch: str | None, last_pickup_at: int, now: int) -> None:
        """Puts every new order in the pool for its town's learned wait, never beyond the base `safe` limit."""
        wait = self.wait(self.order_places.get(order_id), now)
        until = max(now, min(now + wait, last_pickup_at - self.params.safe))
        self.pool[order_id] = Held(order_id, batch, now, until)

    def ready(self, held: Held, now: int) -> bool:
        """A batch can still go when quiet; any other order waits out its learned hold."""
        if not held.batch:
            return now >= held.until
        return super().ready(held, now)

    def summary(self) -> str:
        """The base's bundling line, plus how much booking evidence the waits learned from."""
        learned = sum(stats.weight > 0.0 for stats in self.towns.values())
        views = sum(stats.views for stats in self.towns.values())
        return f"{super().summary()}; learned hold in {learned} towns after {views:,} views"


def pickup_place(order: Order) -> str:
    """Where the order's first undelivered car waits."""
    first = next((leg for leg, at in zip(order["legs"], order["deliveredAt"]) if at is None), order["legs"][0])
    return first["pickup"]["placeId"]
