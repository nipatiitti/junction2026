"""Route-optimised bundling: cheapest insertion into a chain, on the base bundler's cost model and constraints.

The base bundler always appends the next order. This bundler also tries every earlier route position, while keeping
each order's stops together. Waiting, fees, break-up handling and the desk are unchanged. See README.md next to this
file.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from spread.types import DriverProfile, WorldMap

from strategies.bundling import Bundler, Unit
from strategies.bundling.bundling import Params as BundlingParams
from strategies.bundling.bundling import chains, feasible, saving
from strategies.fees import Market
from strategies.strategy import Minutes


@dataclass(frozen=True)
class Params(BundlingParams):
    """The base bundler's thresholds, unchanged: route optimisation adds no threshold of its own."""


def route_chains(
    starts: list[Unit], extra: list[Unit], now: int, market: Market, minutes: Minutes, params: Params
) -> list[list[Unit]]:
    """Builds each chain by cheapest insertion, keeping every unit's stops together.

    Every unused, audience-compatible unit is tried at every position, including the append position used by the base.
    The feasible candidate with the largest marginal saving wins; for one added unit this is also the route with the
    lowest driver cost. If no selected insertion changes that append-only order, the base planner gives the groups.
    """
    used: set[str] = set()
    groups: list[list[Unit]] = []
    pool = starts + extra
    rerouted = False
    for head in sorted(starts, key=lambda unit: unit.windows[0]["from"]):
        if head.order_id in used:
            continue
        group = [head]
        used.add(head.order_id)
        while True:
            best_group: list[Unit] | None = None
            best_unit: Unit | None = None
            best_at = 0
            best_saving = params.min_saving
            before = saving(group, market, minutes, params)
            for unit in pool:
                if unit.order_id in used or unit.audience != head.audience:
                    continue
                for at in range(len(group) + 1):
                    candidate = group[:at] + [unit] + group[at:]
                    gain = saving(candidate, market, minutes, params) - before
                    if gain > best_saving and feasible(candidate, now, minutes, params):
                        best_group, best_unit, best_at, best_saving = candidate, unit, at, gain
            if best_group is None or best_unit is None:
                break
            rerouted = rerouted or best_at < len(group)
            group = best_group
            used.add(best_unit.order_id)
        groups.append(group)
    if not rerouted:
        return chains(starts, extra, now, market, minutes, params)
    return groups


class RouteBundler(Bundler):
    """The base bundler with cheapest-insertion routes instead of append-only chain growth."""

    params: Params

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())

    def due(self, now: int, unit_of: Callable[[str], Unit | None]) -> list[list[Unit]]:
        """Releases the same ready orders as the base, but gives their groups to the route planner."""
        ready = {held.order_id for held in self.pool.values() if self.ready(held, now)}
        if not ready:
            return []
        starts: list[Unit] = []
        extra: list[Unit] = []
        for order_id in list(self.pool):
            unit = unit_of(order_id)
            if unit is None or order_id in ready:
                self.pool.pop(order_id)
            if unit is not None:
                (starts if order_id in ready else extra).append(unit)
        groups = route_chains(starts, extra, now, self.market, self.minutes, self.params)
        for group in groups:
            for unit in group[1:]:
                self.pool.pop(unit.order_id, None)
            self.counts["orders"] += len(group)
            if len(group) > 1:
                self.counts["bundles"] += 1
                self.counts["bundled orders"] += len(group)
                self.counts["bundled cars"] += sum(unit.cars for unit in group)
        return groups
