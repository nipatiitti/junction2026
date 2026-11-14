"""Admission that prices a town's scarcity into the expected driver cost and carries the ceiling system's timed return
leg: the two changes of issue #176 in one `Strategy`.

Both changes live in the shared admission ([`../admission/`](../admission/README.md)) and neither folder changes it:

- [`../scarcity_cost/`](../scarcity_cost/README.md) (#148): the expected fee is multiplied by `1 + risk(pickup)`, where
  `risk` is the town's quotas per driver a day, projected from the week so far, times `safety` and capped at `cap`; and
  the hard capacity gate is gone, so a contested town has to be paid for rather than refused.
- [`../ceiling/`](../ceiling/README.md) (#64): a car counts as a return leg only when one of our transports ends near
  it, reaches it in time and finishes near where that transport started, and a transport carries one request's return
  leg at most.

The two changes sit in different methods of the base admission, so this class is those two strategies **combined**, not
another copy of either. It inherits from `ChainAdmission` and `ScarcityAdmission` at once; the method resolution order
gives the right mix:

- `assess` is the ceiling's (`ChainAdmission.assess`): it wraps the verdict below, then claims the return leg's
  transport when the request is taken;
- the verdict it wraps is the scarcity one (`ScarcityAdmission.assess`): the base's assessment with the capacity gate
  gone, and the scarcity-raised `expected_cost`;
- `pairs` is the ceiling's timed check, so it also feeds the base `expected_cost`'s 0.85 return-leg factor.

README.md next to this file has how the scarcity premium reaches the ceiling's floor, and the bench results.
"""

from __future__ import annotations

from dataclasses import dataclass

from spread.types import DriverProfile, WorldMap

from strategies.ceiling.admission import ChainAdmission
from strategies.ceiling.admission import Params as ChainParams
from strategies.scarcity_cost.admission import Params as ScarcityParams
from strategies.scarcity_cost.admission import ScarcityAdmission


@dataclass(frozen=True)
class Params(ChainParams, ScarcityParams):
    """The ceiling admission's return-leg thresholds and the scarcity admission's term, in one dataclass. The two
    sets of fields do not overlap, so this is their sum and every default is the one of its own folder."""


class ChainScarcityAdmission(ChainAdmission, ScarcityAdmission):
    """The scarcity-priced admission and the ceiling's timed return leg, in one strategy."""

    params: Params

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        # Both bases take `(roster, world_map, level, params)` and read `params or Params()` transitively, so the
        # combined Params is built here and passed on: everything above keeps its own defaults from it.
        super().__init__(roster, world_map, level, params or Params())

    def summary(self) -> str:
        """Both the week's contested towns (the scarcity line) and the chain verdicts, one per line."""
        return "\n".join(line for line in (ScarcityAdmission.summary(self), ChainAdmission.summary(self)) if line)
