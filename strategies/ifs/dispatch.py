"""The ifs system: the root dispatch.py, deciding by plain `if` rules whose numbers are all in values.json. See
README.md next to this file.

Its rules (rules.py) take the place of the root desk's admission and pricing: they pick the option to quote, set its
price and decline what does not pay or does not fit. Its fees (fees.py) plan each gig's fee schedule. Everything else
(the loop, posting, notes, retries, bundling, direct offers, the final) is the root dispatch.py, so its improvements
reach this system too.

Run it from the repository root, with the options of the root dispatch.py and one more: `--values <file>` plays with
the values of that file in place of those in values.json.

    uv run strategies/ifs/dispatch.py --level 8 --seed spread-1
    uv run strategies/ifs/dispatch.py --level 8 --seed spread-1 --values out/ifs/best.json
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import argparse
import json
from types import MappingProxyType

from spread.client import World
from spread.types import FeeStep, PriceRequest

import dispatch as root
from strategies.admission import Held
from strategies.fees import Gig
from strategies.ifs.fees import IfFees, plan
from strategies.ifs.rules import IfRules, Params, load_values
from strategies.strategy import Strategy
from tools import record

POLICY = "ifs"  # its saved weeks form their own group in out/spread.sqlite
PARAMS = Params()  # the values this run plays with: those of values.json, or of the file named with --values


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `ifs`, with the values it was played with."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)

    def add_to_database(self, target: Path) -> None:
        """The values go into the week's meta.json before the database reads it, so both hold them."""
        meta = json.loads((target / "meta.json").read_text())
        record.write_json(
            target / "meta.json", {**meta, "settings": {"strategy": POLICY, "values": dict(PARAMS.values)}}
        )
        super().add_to_database(target)


class Desk(root.Desk):
    """The root desk, quoting by the ifs rules and paying by the ifs fees."""

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.admission.roster, self.admission.world_map  # loaded once by the root desk
        self.rules = IfRules(roster, world_map, level, PARAMS)  # which requests to take, and at what price
        self.fees = IfFees(roster, world_map, level, PARAMS)  # the fee schedule of each gig
        self.strategies: list[Strategy] = [self.notes, self.rules, self.fees, self.offers, self.bundler]

    def held(self) -> list[Held]:
        """The orders we hold, each with whether drivers hold all of its gigs now."""
        return [
            Held(o, bool(g := self.gigs_of(o["id"])) and all(x in self.booked for x in g)) for o in self.orders.values()
        ]

    def quote(self, request: PriceRequest) -> None:
        """Quotes the option and the price that the rules give. A request they decline gets a price far above the
        list price, which loses at no cost; up to level 3 every quote wins, so no quote."""
        self.requests[request["id"]] = request
        facts = self.facts_of(request["id"])
        # The note's deadline passes before the car can be collected (strategies/notes): decline.
        hopeless = facts.deadline is not None and facts.deadline <= (facts.earliest_pickup or request["arrivedAt"])
        prices = {} if hopeless else self.rules.quote(request, self.held(), self.now)
        if not prices:
            if self.level <= 3:
                return
            prices = {o["kind"]: 10 * o["listPriceCents"] for o in request["options"][:1]}
        self.outbox.append({"type": "quote", "requestId": request["id"], "prices": prices})


def bundle_plan(now: int, gig: Gig, level: int) -> list[FeeStep]:
    """The fee schedule of a gig with several orders' cars, by the same rules as a gig of one order."""
    return plan(now, gig, level, PARAMS)


def main() -> None:
    """Reads --values, then plays as the root dispatch.py does, with its options."""
    global PARAMS
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--values", type=Path)
    own, rest = parser.parse_known_args()
    if "-h" in rest or "--help" in rest:
        print("This system adds one option: --values <file> plays with the values of that file in place of those in")
        print("strategies/ifs/values.json. The file names some or all of the values. The other options:\n")
    if own.values is not None:
        try:
            PARAMS = Params(MappingProxyType(load_values(own.values)))
        except (OSError, ValueError) as error:
            sys.exit(f"ifs: {error}")
    sys.argv[1:] = rest
    root.main()


# The root loop (play_practice, play_final) plays with this desk, plans the fees of a bundle by these rules, and
# main() saves its weeks as `ifs`.
root.Desk = Desk
root.Recorder = Recorder
root.fees_plan = bundle_plan

if __name__ == "__main__":
    main()
