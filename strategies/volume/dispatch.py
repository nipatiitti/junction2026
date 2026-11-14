"""The volume system: strategies/all_in with more orders where they leave margin. See README.md next to this file.

On the all-in desk (soft-top fees, lane-prior pricing, same-day quoting, the flu guard), it plays:

- the volume admission (admission.py): every option that pays its own driver cost goes on the quote (the option
  menu), and a remote pickup costs less than all_in assumes;
- the volume pricing (pricing.py): each option is priced over its own driver cost, and a quote with several options
  aims at 50% of its quotes, not 45%.

Run it from the repository root: uv run strategies/volume/dispatch.py --level 8 --seed spread-1
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
from strategies.all_in import dispatch as all_in
from strategies.strategy import Strategy
from strategies.volume.admission import Params as VolumeParams
from strategies.volume.admission import VolumeAdmission
from strategies.volume.pricing import Params as VolumePricingParams
from strategies.volume.pricing import VolumePricing
from tools import record

POLICY = "volume"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `volume`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(all_in.Desk):
    """The all-in desk with the volume admission and the volume pricing. A subclass can change the class attributes
    below to play other values of their variables."""

    admission_params = VolumeParams()
    pricing_params = VolumePricingParams()

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.admission.roster, self.admission.world_map  # loaded once by the root desk
        self.admission = VolumeAdmission(roster, world_map, level, self.admission_params, lane=self.lane)
        self.pricing = VolumePricing(roster, world_map, level, self.pricing_params)
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
        """The ceiling desk's quote (strategies/ceiling/dispatch.py), with every option that admission takes priced
        over its own driver cost. A request that admission declines, or whose driver cost and premium are above the
        maximum for every option, gets a price far above the list price, which loses at no cost."""
        self.requests[request["id"]] = request
        # Admission takes an option only when its driver cost plus the risk premium fits under the highest price we
        # would quote. Its Params are frozen, so it gets a copy with that price and margin.
        self.admission.params = replace(
            self.admission.params,
            price_factor=self.pricing.ceiling(request, self.now),
            min_margin=1 - 1 / (1 + self.pricing.params.risk_premium),
        )
        verdict = self.admission.assess(request, self.held(), self.now)
        costs = self.admission.costs.pop(request["id"], None)
        facts = self.facts_of(request["id"])
        # The note's deadline passes before the car can be collected (strategies/notes): decline.
        hopeless = facts.deadline is not None and facts.deadline <= (facts.earliest_pickup or request["arrivedAt"])
        prices: dict[str, int] = {}
        if verdict.accept and not hopeless:
            prices = self.pricing.price(request, self.now, verdict.expected_cost, verdict.options, costs)
        if not prices:
            self.admission.release(request["id"])  # a request we decline holds no transport and no place
            if self.level <= 3:
                return
            prices = {o["kind"]: 10 * o["listPriceCents"] for o in request["options"][:1]}
        self.outbox.append({"type": "quote", "requestId": request["id"], "prices": prices})


# The root loop (play_practice, play_final) plays with this desk, and main() saves its weeks as `volume`.
root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
