"""The ceiling system: the root dispatch.py with the ceiling pricing of issue #64. See README.md next to this file.

Quotes go as high as we still win: at most 39% over the list price, more only where the rules let a dealer accept more
from us (dealer trust at level 8, the outage), lower after a lost quote and higher again after a won one, and never
below the driver cost plus a risk premium. A car counts as a return leg only when one of our transports can bring its
driver there in time to take it back.

Its two strategies (strategies/strategy.py) take the place of the root desk's admission and pricing, and the desk
feeds them every event like the others. Everything else (the loop, posting, fees, bundling, notes, retries, direct
offers, the final) is the root dispatch.py, so its improvements reach this system too.

Run it from the repository root: uv run strategies/ceiling/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dataclasses import replace

from spread.client import World
from spread.types import DeskEvent, DeskSnapshot, PriceRequest

import dispatch as root
from strategies.admission import Held
from strategies.ceiling import CeilingPricing, ChainAdmission
from strategies.strategy import Strategy
from tools import record

POLICY = "ceiling"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `ceiling`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(root.Desk):
    """The root desk with ceiling pricing and the timed return leg."""

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.admission.roster, self.admission.world_map  # loaded once by the root desk
        self.admission = ChainAdmission(roster, world_map, level)  # which requests to take, with a timed return leg
        self.pricing = CeilingPricing(roster, world_map, level)  # the price: under the maximum, over the driver cost
        self.strategies: list[Strategy] = [
            self.notes,
            self.admission,
            self.pricing,
            self.fees,
            self.offers,
            self.bundler,
        ]

    def rejoin(self, snapshot: DeskSnapshot, history: list[DeskEvent]) -> None:
        """Rebuilds the books as the root desk does, then claims the return legs of the orders we hold again, which a
        new desk does not know, before it quotes the open requests."""
        super().rejoin({**snapshot, "openRequests": []}, history)
        self.admission.restore(self.requests.values(), self.held())
        for request in snapshot["openRequests"]:
            self.quote(request)

    def held(self) -> list[Held]:
        """The orders we hold, each with whether drivers hold all of its gigs now."""
        return [
            Held(o, bool(g := self.gigs_of(o["id"])) and all(x in self.booked for x in g)) for o in self.orders.values()
        ]

    def quote(self, request: PriceRequest) -> None:
        """Quotes the option that admission picks, at the ceiling price: as high as we still win, at most the
        maximum, and at least the driver cost plus its risk premium. A request that admission declines, or whose
        driver cost and premium are above the maximum, gets a price far above the list price, which loses at no
        cost; up to level 3 every quote wins, so no quote."""
        self.requests[request["id"]] = request
        # Admission takes the request only when the driver cost plus the risk premium fits under the highest price
        # we would quote. Its Params are frozen, so it gets a copy with that price and margin.
        self.admission.params = replace(
            self.admission.params,
            price_factor=self.pricing.ceiling(request, self.now),
            min_margin=1 - 1 / (1 + self.pricing.params.risk_premium),
        )
        verdict = self.admission.assess(request, self.held(), self.now)
        facts = self.facts_of(request["id"])
        # The note's deadline passes before the car can be collected (strategies/notes): decline.
        hopeless = facts.deadline is not None and facts.deadline <= (facts.earliest_pickup or request["arrivedAt"])
        prices: dict[str, int] = {}
        if verdict.accept and not hopeless:
            prices = self.pricing.price(request, self.now, verdict.expected_cost, verdict.options)
        if not prices:
            self.admission.release(request["id"])  # a request we decline holds no transport and no place
            if self.level <= 3:
                return
            prices = {o["kind"]: 10 * o["listPriceCents"] for o in request["options"][:1]}
        self.outbox.append({"type": "quote", "requestId": request["id"], "prices": prices})


# The root loop (play_practice, play_final) plays with this desk, and main() saves its weeks as `ceiling`.
root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
