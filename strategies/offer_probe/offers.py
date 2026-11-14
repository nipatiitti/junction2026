"""Offers as cost probes: ask only drivers with a sign of life, and learn which fee ratios they accept.

The audience and offer limits of strategies/offers are unchanged. This subclass adds a recent-activity filter and
learns accepted and declined answers by driver, pickup town and fee ratio. README.md next to this file has the rules.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from spread.types import DeskEvent, DriverProfile, WorldMap

from strategies.offers.offers import (
    DAY,
    HOUR,
    OFFER_MINUTES,
    PER_GIG_OPEN,
    Offers,
    quiet,
)
from strategies.offers.offers import Params as OfferParams


@dataclass(frozen=True)
class Params(OfferParams):
    """The base offer thresholds, plus recent activity and the acceptance probe's fee grid."""

    recent_hours: int = 3  # a driver who finished our last delivery this recently may be offered a gig
    target_accept: float = 0.25  # the observed accepted share an offer fee ratio must clear
    fee_grid: tuple[float, ...] = (0.65, 0.75, 0.85, 1.0)  # shares of the current app fee to probe


class ProbeOffers(Offers):
    """Direct offers to recently active drivers, with fees chosen from their and their town's answers."""

    params: Params

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())
        self.working: set[tuple[str, int]] = set()  # (driver, day): viewed, booked or started our gig
        self.finished: dict[str, int] = {}  # driver -> minute they finished the last delivery of our gig
        self.offer_ratios: dict[tuple[str, str], float] = {}  # (gig, driver) -> fee ratio sent
        self.driver_outcomes: dict[tuple[str, float], Counter[str]] = defaultdict(Counter)
        self.town_outcomes: dict[tuple[str, float], Counter[str]] = defaultdict(Counter)

    @staticmethod
    def acceptance(outcomes: Counter[str] | None) -> float | None:
        """The accepted share of offers read and answered, or None with no accepted/declined observations."""
        if outcomes is None:
            return None
        total = outcomes["accepted"] + outcomes["declined"]
        return outcomes["accepted"] / total if total else None

    def town_acceptance(self, pickup: str, ratio: float) -> float | None:
        """The learned acceptance rate at a pickup town and exact grid ratio; read-only, None without data."""
        return self.acceptance(self.town_outcomes.get((pickup, ratio)))

    def observe(self, event: DeskEvent) -> None:
        """Learns activity and price answers. An expired offer was not read, so it adds no price observation."""
        kind, at = event["kind"], event["at"]
        gig_id, driver = event.get("gigId"), event.get("driverId")
        if kind == "offer_answered" and gig_id and driver:
            answer = event["answer"]
            ratio = self.offer_ratios.pop((gig_id, driver), None)
            if ratio is not None and answer in ("accepted", "declined"):
                self.driver_outcomes[(driver, ratio)][answer] += 1
                info = self.gigs.get(gig_id)
                if info:
                    self.town_outcomes[(info.pickup, ratio)][answer] += 1
        super().observe(event)
        if kind in ("gig_viewed", "gig_booked", "gig_started") and driver:
            self.working.add((driver, at // DAY))
        elif kind == "delivered" and gig_id:
            driver = self.holder.get(gig_id)
            info = self.gigs.get(gig_id)
            if driver and info and event["placeId"] == info.end:
                self.finished[driver] = at

    def candidates(self, gig_id: str, now: int, rescue: bool) -> list[str]:
        """The base candidates who also viewed, booked or started today, or finished a gig recently."""
        recent_minutes = self.params.recent_hours * HOUR

        def active(driver: str) -> bool:
            finished = self.finished.get(driver)
            return (driver, now // DAY) in self.working or (finished is not None and now - finished <= recent_minutes)

        return [driver for driver in super().candidates(gig_id, now, rescue) if active(driver)]

    def fee_ratio(self, gig_id: str, driver: str, rescue: bool) -> float:
        """The lowest grid ratio whose observed acceptance clears the target, preferring the driver's own data.

        At each ratio the driver's accepted/declined answers take precedence over the pickup town's. With no data at
        any ratio, keep the base chain or rescue fee. With data but no qualifying ratio, probe the grid's top ratio.
        """
        p = self.params
        info = self.gigs[gig_id]
        observed = False
        grid = sorted(p.fee_grid)
        for ratio in grid:
            outcomes = self.driver_outcomes.get((driver, ratio))
            rate = self.acceptance(outcomes)
            if rate is None:
                rate = self.town_acceptance(info.pickup, ratio)
            if rate is not None:
                observed = True
                if rate >= p.target_accept:
                    return ratio
        if observed:
            return max(grid)
        return p.rescue_fee if rescue else p.chain_fee

    def offers(self, gig_id: str, now: int, rescue: bool = False) -> list[dict]:
        """The base offer loop, with a fee ratio chosen separately for each candidate driver."""
        if self.level < 3 or gig_id not in self.open or gig_id not in self.gigs or quiet(now):
            return []
        pending = self.pending[gig_id]
        for driver, sent_at in list(pending.items()):
            if now >= sent_at + OFFER_MINUTES + 1:
                del pending[driver]
        room = PER_GIG_OPEN - len(pending)
        if room <= 0:
            return []
        app_fee = self.app_fee(gig_id, now)
        actions = []
        for driver in self.candidates(gig_id, now, rescue)[:room]:
            ratio = self.fee_ratio(gig_id, driver, rescue)
            fee = max(1, int(app_fee * ratio + 0.5))
            pending[driver] = now
            self.sent[driver].append(now)
            self.answers["sent"] += 1
            self.asked.add((gig_id, driver))
            self.offer_ratios[(gig_id, driver)] = ratio
            actions.append({"type": "offer", "gigId": gig_id, "driverId": driver, "feeCents": fee})
        return actions
