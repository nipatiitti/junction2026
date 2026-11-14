"""Slack-budget admission: spend unused on-time room on positive-margin requests, and protect the reserve.

A strategy (strategies/strategy.py) built on the headroom desk's lane-cost admission, unchanged there. Its live slack
is `counted // 10 - (late + undelivered)`, the same formula as `week_facts.late_slack`, with cancelled orders left
out. Above the reserve it retries only a cost decline with a bounded cost discount and a strictly positive margin.
At or below the reserve it declines requests with known delivery risks that the base admission would take. Positive
slack permits that risk; it does not forecast on-time delivery. README.md next to this file defines the states.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, replace

from spread.types import DeskEvent, DriverProfile, WorldMap

from strategies.admission import Held, Verdict
from strategies.admission.admission import HOUR
from strategies.lane_fee import LaneCostAdmission, LaneFee
from strategies.lead_cost import LeadCostParams
from strategies.notes import NoteReader


@dataclass(frozen=True)
class Params(LeadCostParams):
    """The lead-cost variables, plus the on-time reserve, its cost easing and the known-risk thresholds."""

    reserve: int = 2  # this many late orders of slack stay unused; easing needs strictly more
    risk_discount: float = 0.10  # the most a cost-declined request's expected driver cost is eased, as a share
    long_drive: int = 6 * HOUR  # a drive at least this long is risky with fewer than `few_drivers` near the pickup
    few_drivers: float = 2.0  # the base admission's distance- and reliability-weighted driver supply
    slow_booking: int = 6 * HOUR  # a post that waits longer than this for a booking is slow; an expired one is too
    slow_evidence: int = 2  # a town needs this many booked or expired gigs before its booking speed counts
    slow_share: float = 0.5  # at least this share of those gigs must be slow for the town to be a risk


@dataclass
class _SlackOrder:
    """What the live on-time account needs of one order that has not been cancelled."""

    deadline: int
    delivered: list[int | None]


class SlackBudgetAdmission(LaneCostAdmission):
    """The headroom admission, eased only above an on-time reserve and tightened at or below it."""

    params: Params

    def __init__(
        self,
        roster: list[DriverProfile],
        world_map: WorldMap,
        level: int = 8,
        params: Params | None = None,
        lane: LaneFee | None = None,
        notes: NoteReader | None = None,
    ) -> None:
        super().__init__(roster, world_map, level, params or Params(), lane)
        self.notes = notes or NoteReader(roster, world_map, level)
        self.counted: set[str] = set()  # every order won, less cancellations; open orders included
        self.late_orders: set[str] = set()  # delivered after a deadline, or named by a late refund
        self.undelivered: set[str] = set()  # past the deadline without every car delivered, or penalised as such
        self.slack_orders: dict[str, _SlackOrder] = {}
        self.late_refunds: set[str] = set()  # the ledger knows note deadlines that the order's deadline does not
        self.undelivered_penalties: set[str] = set()
        self.posted_gigs: dict[str, tuple[str, int]] = {}  # gig id -> (first pickup, minute posted), until resolved
        self.booking_results: dict[str, list[bool]] = defaultdict(list)  # pickup -> each gig booked within the limit
        self.easing = False  # true only inside the retry of a cost decline
        self.eased = 0
        self.guarded = 0

    @property
    def slack(self) -> int:
        """The live equivalent of `week_facts.late_slack`: room above 90% on time, not a delivery forecast."""
        return len(self.counted) // 10 - (len(self.late_orders) + len(self.undelivered))

    def posted(self, gig_id: str, place: str, at: int) -> None:
        """The desk posted a gig whose first pickup is at `place`; its booking speed can identify a slow town."""
        self.posted_gigs[gig_id] = (place, at)

    def observe(self, event: DeskEvent) -> None:
        """The base's learning, the live on-time account, and how quickly each pickup town's gigs book."""
        super().observe(event)
        kind, at = event["kind"], event["at"]
        if kind == "order_won":
            order = event["order"]
            order_id = order["id"]
            self.counted.add(order_id)
            self.slack_orders[order_id] = _SlackOrder(order["deadline"], list(order["deliveredAt"]))
            self._classify(order_id, at)
        elif kind == "order_changed":
            order = event["order"]
            order_id = order["id"]
            if order_id in self.slack_orders:
                self.slack_orders[order_id] = _SlackOrder(order["deadline"], list(order["deliveredAt"]))
                self._classify(order_id, at)
        elif kind == "order_cancelled":
            order_id = event["orderId"]
            self.counted.discard(order_id)
            self.late_orders.discard(order_id)
            self.undelivered.discard(order_id)
            self.late_refunds.discard(order_id)
            self.undelivered_penalties.discard(order_id)
            self.slack_orders.pop(order_id, None)
            for gig in event["gigs"]:
                self.posted_gigs.pop(gig["gigId"], None)
        elif kind == "delivered":
            order_id = event["orderId"]
            tracked = self.slack_orders.get(order_id)
            if tracked is not None:
                tracked.delivered[event["leg"]] = at
                self._classify(order_id, at)
        elif kind == "ledger":
            line = event["line"]
            order_id = line.get("orderId")
            if order_id in self.counted:
                if line["kind"] == "late_refund":
                    self.late_refunds.add(order_id)
                elif line["kind"] == "undelivered_penalty":
                    self.undelivered_penalties.add(order_id)
                self._classify(order_id, at)
        accepted = kind == "offer_answered" and event.get("answer") == "accepted"
        if kind == "gig_booked" or accepted:
            posted = self.posted_gigs.pop(event["gigId"], None)
            if posted is not None:
                place, posted_at = posted
                self.booking_results[place].append(at - posted_at <= self.params.slow_booking)
        elif kind == "gig_expired":
            posted = self.posted_gigs.pop(event["gigId"], None)
            if posted is not None:
                self.booking_results[posted[0]].append(False)
        self._expire_slack(at)

    def _classify(self, order_id: str, now: int) -> None:
        """Moves one order between the open, late and undelivered states without counting it twice."""
        tracked = self.slack_orders[order_id]
        complete = all(at is not None for at in tracked.delivered)
        if order_id in self.undelivered_penalties:
            late, undelivered = False, True
        elif order_id in self.late_refunds:
            late, undelivered = True, False
        else:
            late = complete and any(at is not None and at > tracked.deadline for at in tracked.delivered)
            undelivered = not complete and now > tracked.deadline
        if late:
            self.late_orders.add(order_id)
        else:
            self.late_orders.discard(order_id)
        if undelivered:
            self.undelivered.add(order_id)
        else:
            self.undelivered.discard(order_id)

    def _expire_slack(self, now: int) -> None:
        """An open order becomes undelivered for the live account once its deadline has passed."""
        for order_id, tracked in self.slack_orders.items():
            if now > tracked.deadline and any(at is None for at in tracked.delivered):
                self._classify(order_id, now)

    def slow_town(self, place: str) -> bool:
        """Whether enough of this town's own resolved gigs booked slowly; another town's bookings do not count."""
        results = self.booking_results.get(place, [])
        p = self.params
        return len(results) >= p.slow_evidence and results.count(False) / len(results) >= p.slow_share

    def risk_factors(self, request: dict) -> list[str]:
        """The known delivery risks that the reserve regime declines, even when the base admission accepts."""
        p = self.params
        legs = request["legs"]
        pickup = legs[0]["pickup"]
        factors = []
        if self.drive_minutes(legs) >= p.long_drive and self.supply(pickup["placeId"]) < p.few_drivers:
            factors.append("long drive with few drivers")
        if any(leg["pickup"]["privateAddress"] for leg in legs):
            factors.append("private pickup")
        facts = self.notes.read(request)
        if facts.deadline is not None and facts.deadline < min(o["deadline"] for o in request["options"]):
            factors.append("note with a tighter deadline")
        if self.slow_town(pickup["placeId"]):
            factors.append("town with slow bookings")
        return factors

    def verdict(self, request: dict, held: list[Held], now: int) -> Verdict:
        """The base's verdict, except that a request with a known risk cannot spend the on-time reserve."""
        verdict = super().verdict(request, held, now)
        if not verdict.accept or self.slack > self.params.reserve:
            return verdict
        factors = self.risk_factors(request)
        if not factors:
            return verdict
        self.guarded += 1
        self.pending.pop(request["id"], None)  # the base accepted before the reserve check; hold no place on a decline
        reason = f"slack {self.slack} at reserve {self.params.reserve}: {', '.join(factors)}"
        return Verdict(False, [], verdict.expected_cost, -1.0, reason)

    def assess(self, request: dict, held: Iterable[Held] = (), now: int | None = None) -> Verdict:
        """The headroom verdict. Only its cost declines may be retried, only above the reserve, and only with a
        strictly positive margin after at most `risk_discount` of expected cost easing."""
        held = list(held)
        at = request["arrivedAt"] if now is None else now
        self._expire_slack(at)
        usual = self.params
        verdict = super().assess(request, held, at)
        if verdict.accept or self.slack <= usual.reserve or not verdict.reason.startswith("cost"):
            return verdict
        self.counts["declined"] -= 1  # the retry replaces the first verdict rather than adding another request
        self.counts["cost"] -= 1
        self.params = replace(usual, min_margin=1e-9)  # strictly positive, instead of the usual risk premium
        self.easing = True
        try:
            eased = super().assess(request, held, at)
        finally:
            self.params, self.easing = usual, False
        self.eased += eased.accept
        return eased

    def lead_cost(self, request: dict, option: dict, held: Iterable[Held], now: int) -> int:
        """The usual lane cost, discounted only during the bounded retry of a cost decline."""
        cost = super().lead_cost(request, option, held, now)
        return int(cost * (1 - self.params.risk_discount) + 0.5) if self.easing else cost

    def summary(self) -> str:
        """The base's verdicts, plus the final live slack and how often each regime changed admission."""
        line = super().summary()
        account = (
            f"Slack budget: {len(self.counted)} counted, {len(self.late_orders)} late, "
            f"{len(self.undelivered)} undelivered; slack {self.slack}; {self.eased} cost-eased, "
            f"{self.guarded} declined for known risk"
        )
        return f"{line}\n{account}" if line else account
