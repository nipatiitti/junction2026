"""The joint-bid system: the headroom system whose quote and fee schedule share one driver-cost estimate.

Before quoting, the desk previews the fee schedule for the option admission picked. JointPricing uses the schedule's
expected paid fee as its cost floor instead of admission's generic estimate. Posting, admission and everything else
remain the headroom system's. See README.md next to this file.

Run it from the repository root: uv run strategies/joint_bid/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dataclasses import replace

from spread.client import World
from spread.types import FeeStep, PriceRequest

import dispatch as root
from strategies.headroom import dispatch as headroom
from strategies.joint_bid import JointFeePlanner, JointPricing
from strategies.strategy import Strategy
from tools import record

POLICY = "joint-bid"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `joint-bid`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(headroom.Desk):
    """The headroom desk, pricing against the fee schedule it previews before each quote."""

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.admission.roster, self.admission.world_map  # loaded once by the root desk
        self.fees = JointFeePlanner(roster, world_map, level, lane=self.lane)  # the schedule and its pure preview
        self.pricing = JointPricing(roster, world_map, level)  # headroom pricing over the schedule's expected fee
        self.strategies: list[Strategy] = [
            self.notes,
            self.lane,
            self.admission,
            self.pricing,
            self.fees,
            self.offers,
            self.bundler,
        ]

    def fee_schedule(self, request: PriceRequest, kinds: list[str]) -> list[FeeStep] | None:
        """The schedule the fee planner would use for the one option admission picked. No unique option means no
        estimate, and pricing falls back to admission's cost. The would-be order is valued at the current lifted
        maximum, since its actual quote is not known yet."""
        options = [option for option in request["options"] if option["kind"] in kinds]
        if len(options) != 1:
            return None
        option = options[0]
        price = max(1, int(option["listPriceCents"] * self.pricing.ceiling(request, self.now) + 0.5))
        return self.fees.preview(request, option, price, self.admission.last_pickup(request, option), self.now)

    def quote(self, request: PriceRequest) -> None:
        """Quotes as the ceiling desk does, replacing the driver cost with the expected fee of the schedule previewed
        for admission's option. Admission, the note check and the deliberately losing decline quote are unchanged."""
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
            schedule = self.fee_schedule(request, verdict.options)
            prices = self.pricing.price(request, self.now, verdict.expected_cost, verdict.options, schedule)
        if not prices:
            self.admission.release(request["id"])
            if self.level <= 3:
                return
            prices = {o["kind"]: 10 * o["listPriceCents"] for o in request["options"][:1]}
        self.outbox.append({"type": "quote", "requestId": request["id"], "prices": prices})


# The root loop (play_practice, play_final) plays with this desk, and main() saves its weeks as `joint-bid`.
root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
