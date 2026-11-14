"""The baseline with its quotes on a ladder: the desk and the play loop of strategies/baseline/baseline.py, unchanged,
with `BaselineLadderPricing` in the place of `BaselinePricing` and `RampFees` in the place of `BaselineFees`.
Admission, the note reader and the retry are the baseline's. See README.md next to this file.

Run it with `uv run python strategies/baseline_ladder/baseline_ladder.py --level 8 --seed spread-1`, or bench it
against the baseline with
`uv run python -m strategies.bench strategies/baseline_ladder/baseline_ladder.py strategies/baseline/baseline.py`.
"""

from __future__ import annotations

import sys
from functools import partial
from pathlib import Path
from typing import ClassVar

# Run as a file, Python looks for modules next to it; record.py, spread_proxy.py and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World

import record
from strategies.baseline import baseline
from strategies.baseline_ladder.fees import RampFees
from strategies.baseline_ladder.pricing import BaselineLadderPricing

POLICY = "baseline-ladder"  # the policy of the weeks this system saves, so they form their own group in the data

baseline_play_practice = baseline.play_practice  # the baseline's loop, before `main` puts this file's in its place


class Desk(baseline.Desk):
    """The baseline's desk, quoting with the ladder and paying on the ramp. Everything else is the baseline's."""

    last: ClassVar[Desk | None] = None  # the desk built last, for the ladder's line at the end of the week

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.pricing.roster, self.pricing.world_map  # as the baseline's desk loaded them
        swaps = {
            id(self.pricing): BaselineLadderPricing(roster, world_map, level),
            id(self.fees): RampFees(roster, world_map, level),
        }
        self.strategies = [swaps.get(id(strategy), strategy) for strategy in self.strategies]
        self.pricing, self.fees = swaps[id(self.pricing)], swaps[id(self.fees)]  # type: ignore[assignment]
        Desk.last = self


def play_practice(world: World, level: int) -> None:
    """The baseline's practice week, then a line on where the ladder ended."""
    baseline_play_practice(world, level)
    if Desk.last is not None:
        print(Desk.last.pricing.summary(), flush=True)


def main() -> None:
    """The baseline's runner, with this file's desk in the place of the baseline's, and the weeks saved under this
    system's policy. The baseline's loops and runner find the desk, the loop and the recorder by name."""
    baseline.Desk = Desk  # type: ignore[misc]
    baseline.play_practice = play_practice
    record.Recorder = partial(record.Recorder, policy=POLICY)  # type: ignore[assignment,misc]
    baseline.main()


if __name__ == "__main__":
    main()
