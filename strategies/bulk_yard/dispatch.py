"""The bulk-yard system: headroom with batch-wide admission and yard-first chains. See README.md beside this file.

Run it from the repository root: uv run strategies/bulk_yard/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dataclasses import replace

from spread.client import World
from spread.types import PriceRequest

import dispatch as root
from strategies.bulk_yard import BulkYardAdmission, BulkYardBundler
from strategies.headroom import dispatch as headroom
from strategies.strategy import Strategy
from tools import record

POLICY = "bulk-yard"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `bulk-yard`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(headroom.Desk):
    """The headroom desk with batch-wide admission and a separate bulk-batch bundling pool."""

    admission: BulkYardAdmission

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.admission.roster, self.admission.world_map  # loaded once by the root desk
        self.admission = BulkYardAdmission(roster, world_map, level, lane=self.lane)
        self.bundler = BulkYardBundler(roster, world_map, level)
        self.deferred: dict[str, dict[str, PriceRequest]] = {}
        self.strategies: list[Strategy] = [
            self.notes,
            self.lane,
            self.admission,
            self.pricing,
            self.fees,
            self.offers,
            self.bundler,
        ]

    def quote(self, request: PriceRequest) -> None:
        """Defers a batch to the end of the step so its requests can be quoted as one unit.

        An unbatched request goes straight through headroom. A small batch uses that same quote at the same world
        minute once the step has been read. When a batch reaches `bulk_min`, every still-open request is requoted from
        the joint capacity plan, replacing the earlier small-batch quotes before the dealers respond.
        """
        self.requests[request["id"]] = request
        batch = request.get("batchId")
        if not batch:
            super().quote(request)
            return
        self.deferred.setdefault(batch, {})[request["id"]] = request

    def post_due(self) -> None:
        """Quotes deferred batches once, then releases won orders to the yard-aware bundler."""
        for batch, arrived in self.deferred.items():
            requests = list(arrived.values())
            if not any(self.admission.is_bulk(request) for request in requests):
                for request in requests:
                    super().quote(request)
                continue
            for request in self.admission.batch_requests(batch):
                if request["id"] not in self.orders and request["respondBy"] >= self.now:
                    self.admission.release(request["id"])
                    self.pricing.quotes.pop(request["id"], None)
                    self.bulk_quote(request)
        self.deferred.clear()
        super().post_due()

    def bulk_quote(self, request: PriceRequest) -> None:
        """The ceiling quote, with the batch's price factor and list prices reduced by `bulk_discount`.

        Pricing still applies its learned price, maximum and driver-cost floor to the discounted list prices. Thus a
        discount shrinks at that floor; an option whose floor does not fit is not quoted.
        """
        self.requests[request["id"]] = request
        self.admission.params = replace(
            self.admission.params,
            price_factor=self.pricing.ceiling(request, self.now),
            min_margin=1 - 1 / (1 + self.pricing.params.risk_premium),
        )
        verdict = self.admission.assess(request, self.held(), self.now)
        facts = self.facts_of(request["id"])
        hopeless = facts.deadline is not None and facts.deadline <= (facts.earliest_pickup or request["arrivedAt"])
        prices: dict[str, int] = {}
        if verdict.accept and not hopeless:
            discount = 1 - self.admission.params.bulk_discount
            discounted = {
                **request,
                "options": [
                    {**option, "listPriceCents": max(1, int(option["listPriceCents"] * discount + 0.5))}
                    for option in request["options"]
                ],
            }
            prices = self.pricing.price(discounted, self.now, verdict.expected_cost, verdict.options)
        if not prices:
            self.admission.release(request["id"])
            if self.level <= 3:
                return
            prices = {option["kind"]: 10 * option["listPriceCents"] for option in request["options"][:1]}
        self.outbox.append({"type": "quote", "requestId": request["id"], "prices": prices})


# The root loop plays with this desk, and main() saves its weeks as `bulk-yard`.
root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
