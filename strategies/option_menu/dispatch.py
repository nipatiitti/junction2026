"""The option-menu system: the ceiling system (strategies/ceiling) that quotes admission's option and every slower
one. See README.md next to this file.

Admission picks the earliest option with comfortable time for the drive. This desk quotes it and the request's slower
options too, each at ceiling pricing's price for it, so the dealer can take a cheaper, later delivery from us instead
of from the competitor. Everything else is the ceiling system's.

Run it from the repository root: uv run strategies/option_menu/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World
from spread.types import PriceRequest

import dispatch as root
from strategies.ceiling import dispatch as ceiling
from strategies.option_menu import OptionMenu
from tools import record

POLICY = "option-menu"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `option-menu`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(ceiling.Desk):
    """The ceiling desk, quoting a menu of options."""

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        self.menu = OptionMenu(self.admission.roster, self.admission.world_map, level)
        self.strategies = [self.notes, self.admission, self.pricing, self.fees, self.offers, self.bundler, self.menu]

    def quote(self, request: PriceRequest) -> None:
        """The ceiling desk's quote (strategies/ceiling/dispatch.py), with admission's option and the slower ones."""
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
            kinds = self.menu.kinds(request, verdict.options)
            prices = self.pricing.price(request, self.now, verdict.expected_cost, kinds)
            least = verdict.expected_cost * (1 + self.pricing.params.risk_premium)
            prices = self.menu.discount(request, verdict.options, prices, least)
        if not prices:
            self.admission.release(request["id"])
            if self.level <= 3:
                return
            prices = {o["kind"]: 10 * o["listPriceCents"] for o in request["options"][:1]}
        self.outbox.append({"type": "quote", "requestId": request["id"], "prices": prices})


root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
