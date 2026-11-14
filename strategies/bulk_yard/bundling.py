"""Bulk-yard bundling: keep a large batch in its own pool and build its chains from the yard.

The base Bundler supplies the batch hold/quiet rules, the maximum cars and drive, every window and audience check,
the driver-minute saving and the fee scaling. This subclass only stops a large batch from joining unrelated chains,
then calls the same chain planner for that batch. Smaller batches use the base's mixed pool unchanged.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from spread.types import DriverProfile, PriceRequest, WorldMap

from strategies.bundling import Bundler, Unit
from strategies.bundling.bundling import Params as BundlingParams
from strategies.bundling.bundling import chains


@dataclass(frozen=True)
class Params(BundlingParams):
    """The base chain constraints and fees, plus when a batch gets its own planning pool."""

    bulk_min: int = 10  # requests with one batch id before the batch is bundled separately


class BulkYardBundler(Bundler):
    """The base bundler with a separate yard-first chain plan for each large batch."""

    params: Params

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())
        self.batch_sizes: dict[str, int] = {}
        self.yards: dict[str, str] = {}

    def request(self, request: PriceRequest) -> None:
        """Uses the base's request timing, and remembers which batches are bulk and which yard they leave."""
        super().request(request)
        batch = request.get("batchId")
        if batch:
            self.batch_sizes[batch] = self.batch_sizes.get(batch, 0) + 1
            self.yards.setdefault(batch, request["legs"][0]["pickup"]["placeId"])

    def is_bulk(self, batch: str | None) -> bool:
        return bool(batch and self.batch_sizes.get(batch, 0) >= self.params.bulk_min)

    def due(self, now: int, unit_of: Callable[[str], Unit | None]) -> list[list[Unit]]:
        """Posts due orders as the base does, except that bulk batches wait for their own quiet/hold release.

        A waiting bulk order cannot be borrowed by an unrelated chain. Once any of its batch is ready, all won orders
        of that batch are candidates in one call to the base's `chains`; their first pickup is the common yard.
        """
        ready = {held.order_id for held in self.pool.values() if self.ready(held, now)}
        if not ready:
            return []
        bulk_ready = {held.batch for held in self.pool.values() if held.order_id in ready and self.is_bulk(held.batch)}
        starts: list[Unit] = []
        extra: list[Unit] = []
        bulk_starts: dict[str, list[Unit]] = {}
        bulk_extra: dict[str, list[Unit]] = {}
        for order_id in list(self.pool):
            held = self.pool[order_id]
            unit = unit_of(order_id)
            if unit is None or order_id in ready:
                self.pool.pop(order_id)
            if unit is None:
                continue
            if self.is_bulk(held.batch):
                if held.batch not in bulk_ready:
                    continue  # not due yet, and not available to an unrelated chain
                batch = held.batch or ""
                (bulk_starts if order_id in ready else bulk_extra).setdefault(batch, []).append(unit)
            else:
                (starts if order_id in ready else extra).append(unit)

        planned = [(chains(starts, extra, now, self.market, self.minutes, self.params), False)]
        for batch in sorted(bulk_ready):
            groups = chains(
                bulk_starts.get(batch, []),
                bulk_extra.get(batch, []),
                now,
                self.market,
                self.minutes,
                self.params,
            )
            planned.append((groups, True))

        groups: list[list[Unit]] = []
        for batch_groups, bulk in planned:
            for group in batch_groups:
                for unit in group[1:]:
                    self.pool.pop(unit.order_id, None)
                self.counts["orders"] += len(group)
                if len(group) > 1:
                    self.counts["bundles"] += 1
                    self.counts["bulk bundles"] += bulk
                    self.counts["bundled orders"] += len(group)
                    self.counts["bundled cars"] += sum(unit.cars for unit in group)
                groups.append(group)
        return groups
