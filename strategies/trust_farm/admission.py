"""Trust-farm admission: while pricing farms a dealer, take only easy orders that can grow trust without lateness.

The headroom desk's lane-cost admission (strategies/lane_fee), unchanged outside the farm phase. Here an easy order
has a short drive, no note a driver can miss, and a pickup town whose own gigs have booked quickly. The desk tells
admission where each new gig starts, as strategies/tempo does; the booking times decide whether the town stays easy.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from spread.types import DeskEvent, DriverProfile, WorldMap

from strategies.admission import Held, Verdict
from strategies.admission.admission import HOUR, risky_note
from strategies.lane_fee import LaneCostAdmission, LaneFee
from strategies.lead_cost import LeadCostParams


@dataclass(frozen=True)
class Params(LeadCostParams):
    """Headroom admission's variables, plus the easy-order filter used only while farming."""

    easy_drive: int = 2 * HOUR  # farm orders drive at most this many road minutes, including a trade-in's two legs
    quick: int = 30  # a gig booked within this many minutes of its post is quick
    fast_share: float = 0.5  # at least this share of the pickup town's gigs must book quickly
    fast_prior: float = 2.0  # a town starts with this many observations' weight, half quick and half slow


class TrustFarmAdmission(LaneCostAdmission):
    """Lane-cost admission with a short-drive, fast-booking, safe-note filter in the farm phase only."""

    params: Params

    def __init__(
        self,
        roster: list[DriverProfile],
        world_map: WorldMap,
        level: int = 8,
        params: Params | None = None,
        lane: LaneFee | None = None,
    ) -> None:
        super().__init__(roster, world_map, level, params or Params(), lane)
        self.is_farming: Callable[[dict, int], bool] = lambda request, now: False  # the desk connects pricing here
        self.waiting: dict[str, tuple[str, int]] = {}  # gig id -> (first pickup town, minute posted)
        self.results: list[tuple[str, bool]] = []  # (pickup town, booked within `quick`), one for each timed gig

    def posted(self, gig_id: str, place: str, at: int) -> None:
        """The desk posted a new gig whose first pickup is at `place`; time it until a driver takes it."""
        self.waiting[gig_id] = (place, at)

    def observe(self, event: DeskEvent) -> None:
        """Headroom admission's learning, plus quick and slow bookings by pickup town."""
        super().observe(event)
        kind, at = event["kind"], event["at"]
        accepted = kind == "offer_answered" and event.get("answer") == "accepted"
        if (kind == "gig_booked" or accepted) and event["gigId"] in self.waiting:
            place, posted = self.waiting.pop(event["gigId"])
            self.results.append((place, at - posted <= self.params.quick))
        elif kind == "gig_expired" and event["gigId"] in self.waiting:
            self.results.append((self.waiting.pop(event["gigId"])[0], False))
        elif kind == "order_cancelled":
            for gig in event["gigs"]:
                self.waiting.pop(gig["gigId"], None)
        for gig_id, (place, posted) in list(self.waiting.items()):
            if at - posted > self.params.quick:
                del self.waiting[gig_id]
                self.results.append((place, False))

    def fast(self, place: str) -> bool:
        """Whether the pickup town's quick-booking share, with a neutral two-observation prior, reaches `fast_share`.
        An unseen town is eligible, so the filter does not prevent the first farm order from producing evidence.
        """
        seen = [quick for town, quick in self.results if town == place]
        share = (sum(seen) + 0.5 * self.params.fast_prior) / (len(seen) + self.params.fast_prior)
        return share >= self.params.fast_share

    def easy(self, request: dict) -> bool:
        """The farm filter: at most `easy_drive` on the road, a fast pickup town, and no risky note."""
        return (
            self.drive_minutes(request["legs"]) <= self.params.easy_drive
            and self.fast(request["legs"][0]["pickup"]["placeId"])
            and not risky_note(request.get("note"))
        )

    def assess(self, request: dict, held: Iterable[Held] = (), now: int | None = None) -> Verdict:
        """Headroom's verdict for every request except a farmed dealer's non-easy ones, which lose at no cost. Easy
        farm requests still face the usual capacity, slack and margin checks at pricing's discounted maximum.
        """
        at = request["arrivedAt"] if now is None else now
        if self.is_farming(request, at) and not self.easy(request):
            self.counts["declined"] += 1
            self.counts["farm not easy"] += 1
            return Verdict(False, [], 0, -1.0, "farm order is not easy")
        verdict = super().assess(request, held, at)
        if self.is_farming(request, at) and verdict.accept:
            self.counts["farm easy"] += 1
        return verdict

    def summary(self) -> str:
        line = super().summary()
        if not line:
            return ""
        return (
            f"{line}\nTrust farm admission: {self.counts['farm easy']} easy requests taken; "
            f"{self.counts['farm not easy']} farm requests declined as not easy"
        )
