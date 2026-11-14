"""The herd-competitor system: headroom with deliberate low-margin losses where we win too much.

Admission, fees and everything else are the headroom system's (strategies/headroom). The one strategy change is this
folder's pricing. The desk registers every request with it, so the rolling dealer win share includes both ordinary
quotes and requests that admission declined. See README.md next to this file.

Run it from the repository root: uv run strategies/herd_competitor/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World
from spread.types import PriceRequest

import dispatch as root
from strategies.headroom import dispatch as headroom
from strategies.herd_competitor import HerdPricing
from strategies.strategy import Strategy
from tools import record

POLICY = "herd-competitor"  # its saved weeks form their own group in out/spread.sqlite


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `herd-competitor`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(headroom.Desk):
    """The headroom desk with competitor-herding pricing."""

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.admission.roster, self.admission.world_map  # loaded once by the root desk
        self.pricing = HerdPricing(roster, world_map, level)
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
        """Registers the request for its outcome, then uses the ceiling desk's quote and costless-decline path."""
        self.pricing.register(request)
        super().quote(request)


# The root loop (play_practice, play_final) plays with this desk, and main() saves its weeks as `herd-competitor`.
root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
