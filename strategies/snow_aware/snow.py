"""Snow-aware fees and bundling, built on the headroom system's lane-fee planner and the base Bundler.

One `SnowState` collects the forecast windows. `SnowPlanner` opens a gig dearer when its pickup is in a place with
snow forecast on the pickup day. `SnowBundler` stretches only the chain legs that meet a forecast, gives an affected
chain a larger delivery buffer, and lets a snowy pickup skip the rest of a batch's wait. With no forecast both leave
every decision to the classes they extend. See README.md next to this file.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from spread.types import DeskEvent, DriverProfile, FeeStep, Order, PriceRequest, WorldMap

from strategies.bundling import Bundler, Unit
from strategies.bundling.bundling import (
    CHARGING_MINUTES,
    PLATES_MINUTES,
    RULE_MINUTES,
    Held,
    chain_minutes,
    next_open,
    saving,
)
from strategies.bundling.bundling import Params as BundlingParams
from strategies.dawn_fees import DawnParams, dawn_plan, last_dawn
from strategies.fees import Market
from strategies.lane_fee import LaneFee, LaneFeePlanner
from strategies.strategy import Minutes

DAY = 24 * 60


@dataclass(frozen=True)
class Params(DawnParams):
    """The dawn schedule's variables, plus the premium for a snowy pickup day."""

    snow_premium: float = 0.2  # added to `open` and `sprint_open`, as a multiple of the lane fee


@dataclass(frozen=True)
class BundlerParams(BundlingParams):
    """The base bundling thresholds, plus the slower drives and extra buffer in snow."""

    snow_slow: float = 1.35  # a snowy leg's drive over its road minutes, against the fair-weather 1.15
    snow_buffer: int = 60  # extra minutes before the window end at each delivery of an affected chain


class SnowState:
    """The forecast snow windows by place. Repeated observation is idempotent, so two strategies can share it."""

    def __init__(self) -> None:
        self.windows: dict[str, set[tuple[int, int]]] = {}

    def __bool__(self) -> bool:
        return any(self.windows.values())

    def observe(self, event: DeskEvent) -> None:
        if event["kind"] == "forecast":
            for place in event["placeIds"]:
                self.windows.setdefault(place, set()).add((event["from"], event["to"]))

    def overlaps(self, place: str, start: int, end: int) -> bool:
        """Whether snow is forecast at `place` in the half-open interval `[start, end)`."""
        return end > start and any(begin < end and start < ends for begin, ends in self.windows.get(place, ()))

    def pickup_day(self, place: str, starts_at: int) -> bool:
        """Whether the pickup place has any snow forecast on the day the gig starts."""
        day = starts_at // DAY * DAY
        return self.overlaps(place, day, day + DAY)

    def road(self, start_place: str, end_place: str, start: int, end: int) -> bool:
        """Whether either known place on a drive has snow forecast between departure and fair-weather arrival."""
        return self.overlaps(start_place, start, end) or self.overlaps(end_place, start, end)


class SnowPlanner(LaneFeePlanner):
    """The lane-fee dawn planner, with a higher capped opening on a snowy pickup day."""

    params: Params

    def __init__(
        self,
        roster: list[DriverProfile],
        world_map: WorldMap,
        level: int = 8,
        params: Params | None = None,
        lane: LaneFee | None = None,
        snow: SnowState | None = None,
    ) -> None:
        super().__init__(roster, world_map, level, params or Params(), lane)
        self.snow = snow if snow is not None else SnowState()

    def observe(self, event: DeskEvent) -> None:
        self.snow.observe(event)

    def schedule(self, order: Order, request: PriceRequest, cars: int, now: int) -> list[FeeStep]:
        gig = self.gig(order, request, cars, now)
        first = next((leg for leg, at in zip(order["legs"], order["deliveredAt"]) if at is None), order["legs"][0])
        if not self.snow.pickup_day(first["pickup"]["placeId"], gig.starts_at):
            return super().schedule(order, request, cars, now)
        self.counts["dawn" if last_dawn(now, gig.last_pickup_at, self.params) is not None else "urgent"] += 1
        p = self.params
        # The dawn and sprint plans keep their base top, worth and ceiling clamps; only the first rung moves here.
        opening = replace(
            p,
            open=min(p.top, p.open + p.snow_premium),
            sprint_open=min(p.top, p.sprint_open + p.snow_premium),
        )
        return dawn_plan(now, gig, self.level, opening)


def timeline(group: list[Unit], now: int, minutes: Minutes, params: BundlerParams, snow: SnowState) -> list[int] | None:
    """The base chain timeline, with only legs meeting a forecast stretched by `snow_slow`.

    A positive-length leg meets a forecast when either end's place has snow between departure and the arrival the
    base's `slow` stretch would give. One such leg adds `snow_buffer` to the delivery buffer of the whole chain.
    """
    times: list[int] = []
    deliveries: list[tuple[int, int]] = []
    here, at = None, now + params.lead
    snowy = False
    for unit in group:
        for stop, place, window, hours in zip(unit.stops, unit.places, unit.windows, unit.hours):
            if here is None:
                arrive = at
            else:
                road = minutes.get((here, place), 0)
                fair_arrival = at + round(road * params.slow)
                on_snow = road > 0 and snow.road(here, place, at, fair_arrival)
                snowy = snowy or on_snow
                arrive = at + round(road * (params.snow_slow if on_snow else params.slow))
            ready = next_open(max(arrive, window["from"]), hours)
            if ready is None:
                return None
            if here is not None and stop["kind"] == "pickup" and ready - arrive > params.max_wait:
                return None
            if stop["kind"] == "delivery":
                deliveries.append((ready, window["to"]))
            elif ready > window["to"]:
                return None
            times.append(ready)
            at = ready
            if stop["kind"] == "pickup":
                at += PLATES_MINUTES if stop.get("withPlates") else 0
                at += CHARGING_MINUTES if stop.get("withCharging") else 0
            here = place
    buffer = params.buffer + (params.snow_buffer if snowy else 0)
    if any(ready > end - buffer for ready, end in deliveries):
        return None
    return times


def feasible(group: list[Unit], now: int, minutes: Minutes, params: BundlerParams, snow: SnowState) -> bool:
    """The base multi-car and driving checks, followed by the snow-aware timeline."""
    if sum(unit.cars for unit in group) > params.max_cars:
        return False
    if chain_minutes(group, minutes) > min(RULE_MINUTES, params.max_drive):
        return False
    return timeline(group, now, minutes, params, snow) is not None


def chains(
    starts: list[Unit],
    extra: list[Unit],
    now: int,
    market: Market,
    minutes: Minutes,
    params: BundlerParams,
    snow: SnowState,
) -> list[list[Unit]]:
    """The base chain-growth rule, with each candidate checked by the snow-aware timeline."""
    used: set[str] = set()
    groups: list[list[Unit]] = []
    pool = starts + extra
    for head in sorted(starts, key=lambda unit: unit.windows[0]["from"]):
        if head.order_id in used:
            continue
        group = [head]
        used.add(head.order_id)
        while True:
            best, best_saving = None, params.min_saving
            for unit in pool:
                if unit.order_id in used or unit.audience != head.audience:
                    continue
                candidate = group + [unit]
                gain = saving(candidate, market, minutes, params) - saving(group, market, minutes, params)
                if gain > best_saving and feasible(candidate, now, minutes, params, snow):
                    best, best_saving = unit, gain
            if best is None:
                break
            group.append(best)
            used.add(best.order_id)
        groups.append(group)
    return groups


class SnowBundler(Bundler):
    """The base Bundler with snow-local timing and no remaining batch wait for a snowy pickup."""

    params: BundlerParams

    def __init__(
        self,
        roster: list[DriverProfile],
        world_map: WorldMap,
        level: int = 8,
        params: BundlerParams | None = None,
        snow: SnowState | None = None,
    ) -> None:
        super().__init__(roster, world_map, level, params or BundlerParams())
        self.snow = snow if snow is not None else SnowState()
        self.pickups: dict[str, tuple[str, int]] = {}  # order id -> (first pickup place, stated window start)

    def observe(self, event: DeskEvent) -> None:
        self.snow.observe(event)
        super().observe(event)
        if event["kind"] in ("order_won", "order_changed"):
            order = event["order"]
            first = next((leg for leg, at in zip(order["legs"], order["deliveredAt"]) if at is None), order["legs"][0])
            self.pickups[order["id"]] = (first["pickup"]["placeId"], first["pickup"]["window"]["from"])

    def forget(self, order_id: str) -> None:
        super().forget(order_id)
        self.pickups.pop(order_id, None)

    def ready(self, held: Held, now: int) -> bool:
        """A snowy pickup goes at the desk's next `post_due`; every other order keeps the base wait."""
        pickup = self.pickups.get(held.order_id)
        if pickup is not None:
            place, starts_at = pickup
            if self.snow.pickup_day(place, max(now, starts_at)):
                return True
        return super().ready(held, now)

    def due(self, now: int, unit_of: Callable[[str], Unit | None]) -> list[list[Unit]]:
        """Exactly the base's `due` before any forecast; afterwards the same pool rule with snow-aware chains."""
        if not self.snow:
            return super().due(now, unit_of)
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
        groups = chains(starts, extra, now, self.market, self.minutes, self.params, self.snow)
        for group in groups:
            for unit in group[1:]:
                self.pool.pop(unit.order_id, None)
            self.counts["orders"] += len(group)
            if len(group) > 1:
                self.counts["bundles"] += 1
                self.counts["bundled orders"] += len(group)
                self.counts["bundled cars"] += sum(unit.cars for unit in group)
        return groups
