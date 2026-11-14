"""Bulk-yard admission: a large batch gets one yard-capacity budget, not 35 independent area checks.

A strategy (strategies/strategy.py) built on the headroom desk's lane-cost admission. Once a batch has `bulk_min`
requests, a small roster-only schedule estimates which of them drivers living near the yard could finish by their
deadlines. Those requests still pass headroom's option and profit checks, at a discounted price; the rest are declined.
Smaller batches are exactly the headroom admission. README.md next to this file has the estimate and its limits.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace

from spread.types import DeskEvent, DriverProfile, PriceRequest, WorldMap

from strategies.admission import Held, Verdict
from strategies.lane_fee import LaneCostAdmission, LaneFee
from strategies.lead_cost import LeadCostParams

FAR = 10**6


@dataclass(frozen=True)
class Params(LeadCostParams):
    """The headroom admission's thresholds, plus the yard-capacity estimate and its quote discount."""

    bulk_min: int = 10  # requests with one batch id before the batch is planned as a unit
    bulk_near: int = 90  # only drivers whose home is within this many road minutes of the yard count
    bulk_discount: float = 0.05  # the normal quote is multiplied by 1 - this, never below the driver-cost floor
    bulk_slow: float = 1.15  # the capacity schedule stretches road minutes by this factor
    bulk_buffer: int = 60  # planned delivery is at least this many minutes before the earliest option's deadline


class BulkYardAdmission(LaneCostAdmission):
    """The headroom admission with one capacity schedule for each large batch."""

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
        self.batches: dict[str, dict[str, PriceRequest]] = {}
        self.bulk_counts: dict[str, int] = {"batches": 0, "admitted": 0, "declined": 0}

    def observe(self, event: DeskEvent) -> None:
        """Learns the requests of each batch, then lets headroom track orders, drivers and delivery outcomes."""
        if event["kind"] == "price_request":
            request = event["request"]
            batch = request.get("batchId")
            if batch:
                known = self.batches.setdefault(batch, {})
                was_bulk = len(known) >= self.params.bulk_min
                known[request["id"]] = request
                self.bulk_counts["batches"] += not was_bulk and len(known) == self.params.bulk_min
        super().observe(event)

    def batch_requests(self, batch: str) -> list[PriceRequest]:
        """The requests seen so far in one batch, in arrival order."""
        return sorted(self.batches.get(batch, {}).values(), key=lambda request: (request["arrivedAt"], request["id"]))

    def is_bulk(self, request: PriceRequest) -> bool:
        batch = request.get("batchId")
        return bool(batch and len(self.batches.get(batch, {})) >= self.params.bulk_min)

    def accepted(self, requests: list[PriceRequest], now: int) -> set[str]:
        """A greedy schedule of the batch on drivers living within `bulk_near` of its yard.

        Requests go in earliest-deadline order. Each goes to the nearby, eligible driver who can finish it first,
        after the drive home-to-yard or back from that driver's previous delivery. A driver then returns to the yard
        for the next car. This is only a capacity estimate: it reserves no driver and posts no gig.
        """
        if not requests:
            return set()
        yard = requests[0]["legs"][0]["pickup"]["placeId"]
        drivers = []
        for driver in self.roster:
            home = driver["homePlaceId"]
            reach = self.minutes.get((home, yard), FAR)
            if reach <= self.params.bulk_near:
                drivers.append((driver, now + round(reach * self.params.bulk_slow)))
        free = {driver["id"]: at for driver, at in drivers}
        admitted: set[str] = set()
        ordered = sorted(
            requests,
            key=lambda request: (
                min(option["deadline"] for option in request["options"]),
                request["arrivedAt"],
                request["id"],
            ),
        )
        for request in ordered:
            premium = any(leg["car"]["premium"] for leg in request["legs"])
            first = request["legs"][0]["pickup"]
            ready = max(leg["pickup"]["window"]["from"] for leg in request["legs"])
            drive = round(self.drive_minutes(request["legs"]) * self.params.bulk_slow)
            due = min(option["deadline"] for option in request["options"]) - self.params.bulk_buffer
            candidates = []
            for driver, _ in drivers:
                if premium and not (driver["rating"] >= 4.8 and driver["completedGigs"] >= 50):
                    continue
                start = max(free[driver["id"]], ready)
                finish = start + drive
                if finish <= due:
                    candidates.append((finish, driver["id"], driver))
            if not candidates:
                continue
            finish, _, driver = min(candidates)
            admitted.add(request["id"])
            last = request["legs"][-1]["delivery"]["placeId"]
            back = self.minutes.get((last, first["placeId"]), FAR)
            free[driver["id"]] = finish + round(back * self.params.bulk_slow)
        return admitted

    def assess(self, request: dict, held: Iterable[Held] = (), now: int | None = None) -> Verdict:
        """Headroom's verdict below `bulk_min`; above it, one share of the batch's capacity and the bulk discount.

        The batch schedule replaces the ordinary per-request area gate, which would otherwise stop the batch after a
        few cars. The option, slack, lead-cost and profit checks are unchanged. The discount is included in the price
        that the profit check must cover, so a discounted quote cannot go below the usual driver-cost floor.
        """
        held = list(held)
        now = request["arrivedAt"] if now is None else now
        if not self.is_bulk(request):
            return super().assess(request, held, now)
        batch = request.get("batchId") or ""
        requests = self.batch_requests(batch)
        if request["id"] not in self.accepted(requests, now):
            self.counts["declined"] += 1
            self.bulk_counts["declined"] += 1
            return Verdict(False, [], 0, -1.0, f"bulk yard capacity: {len(self.accepted(requests, now))} estimates")
        original = self.params
        pickup = request["legs"][0]["pickup"]
        load = self.load(pickup["placeId"], pickup["window"]["from"] // (24 * 60), held)
        try:
            self.params = replace(
                original,
                price_factor=original.price_factor * (1 - original.bulk_discount),
                min_capacity=load + len(requests) + 1,
            )
            verdict = super().assess(request, held, now)
        finally:
            self.params = original
        self.bulk_counts["admitted" if verdict.accept else "declined"] += 1
        return verdict

    def summary(self) -> str:
        line = super().summary()
        counts = self.bulk_counts
        if not counts["batches"]:
            return line
        extra = (
            f"Bulk yard: {counts['batches']} batches, {counts['admitted']} accepted and "
            f"{counts['declined']} declined after the yard estimate"
        )
        return f"{line}\n{extra}" if line else extra
