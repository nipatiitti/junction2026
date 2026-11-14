"""The eighty system: the strategies that each beat the headroom desk, in one desk. See README.md next to this file.

Everything not named here is the headroom system's (strategies/headroom). Three parts change, each to the class of a
system that beat headroom on its own (issue #200):

- fees: the soft-top planner (strategies/soft_top), the dawn schedule with a top of twice the lane fee;
- admission: the same-day admission (strategies/same_day), the fastest option that pays;
- pricing: the lane-prior pricing (strategies/lane_prior), lifted by the delivery place's fitted offset.

The variables of every part can be changed for one run with the environment variable `EIGHTY_PARAMS`: JSON with a
key per part (`admission`, `pricing`, `fees`, `lane`, `bundler`, `offers`) naming the fields of its `Params` to
change. `EIGHTY_TAG` names the variant: its weeks are saved with the policy `eighty-<tag>`. The defaults in
`PARAMS` below are the best values the bench found (README.md).

Run it from the repository root: uv run strategies/eighty/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import replace
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World

import dispatch as root
from strategies.headroom import dispatch as headroom
from strategies.lane_prior import PriorPricing
from strategies.same_day import SameDayAdmission
from strategies.soft_top import SoftTopPlanner
from strategies.strategy import Strategy
from tools import record

# The values this system plays with, by part, over the defaults of each part's class.
PARAMS: dict[str, dict[str, object]] = {}

TAG = os.environ.get("EIGHTY_TAG", "")
POLICY = f"eighty-{TAG}" if TAG else "eighty"  # its saved weeks form their own group in out/spread.sqlite


def params() -> dict[str, dict[str, object]]:
    """`PARAMS`, with the changes of `EIGHTY_PARAMS` on top."""
    merged = {part: dict(fields) for part, fields in PARAMS.items()}
    for part, fields in json.loads(os.environ.get("EIGHTY_PARAMS") or "{}").items():
        merged.setdefault(part, {}).update(fields)
    return merged


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `eighty` or `eighty-<tag>`."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)


class Desk(headroom.Desk):
    """The headroom desk with the soft-top fees, the same-day admission and the lane-prior pricing."""

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        roster, world_map = self.admission.roster, self.admission.world_map  # loaded once by the root desk
        self.admission = SameDayAdmission(roster, world_map, level, lane=self.lane)  # the fastest option that pays
        self.pricing = PriorPricing(roster, world_map, level)  # the price, lifted by the delivery place's offset
        self.fees = SoftTopPlanner(roster, world_map, level, lane=self.lane)  # the dawn schedule, with a lower top
        self.strategies: list[Strategy] = [
            self.notes,
            self.lane,
            self.admission,
            self.pricing,
            self.fees,
            self.offers,
            self.bundler,
        ]
        for part, fields in params().items():
            strategy = getattr(self, part)
            strategy.params = replace(strategy.params, **fields)


# The root loop (play_practice, play_final) plays with this desk, and main() saves its weeks as `eighty`.
root.Desk = Desk
root.Recorder = Recorder

class Tee:
    """Writes what the week prints to the terminal and to a log file too."""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, text: str) -> int:
        for stream in self.streams:
            stream.write(text)
            stream.flush()
        return len(text)

    def flush(self) -> None:
        for stream in self.streams:
            stream.flush()


if __name__ == "__main__":
    # EIGHTY_LOG names a folder: the week's output, the strategies' summaries included, goes to <tag>-<seed>.log too.
    if folder := os.environ.get("EIGHTY_LOG"):
        seed = sys.argv[sys.argv.index("--seed") + 1] if "--seed" in sys.argv else "random"
        Path(folder).mkdir(parents=True, exist_ok=True)
        sys.stdout = Tee(sys.stdout, (Path(folder) / f"{TAG or 'eighty'}-{seed}.log").open("w"))
    root.main()
