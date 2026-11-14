"""Direct offers to the drivers who looked at a gig and did not take it (`offers.ts`). Off by default (`offers` 0):
under 1% of the offers were accepted on the server and in the simulator. Each viewer who lives near the gig's first
pickup or last delivery gets the fee the app shows, × `offers`, as an offer: at most three open offers a gig and three
offers a driver a day."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from strategies.lean.js import js_round
from strategies.lean.ops import Roads

DAY = 24 * 60
NEAR = 90  # a viewer counts when they live within this many road minutes of the first pickup or the last delivery
PER_DRIVER = 3
PER_GIG = 3
OPEN_FOR = 10


class Offers:
    def __init__(self, roads: Roads, roster: list[dict]) -> None:
        self.roads = roads
        self.homes = {driver["id"]: driver["homePlaceId"] for driver in roster}
        self.viewers: dict[str, list[str]] = {}  # gig id -> the drivers who viewed it and wait for an offer
        self.offered: set[str] = set()
        self.days: dict[str, list[int]] = {}
        self.open: dict[str, list[int]] = {}
        self.sent = 0
        self.accepted = 0

    def viewed(self, gig_id: str, driver_id: str) -> None:
        if f"{gig_id} {driver_id}" in self.offered:
            return
        waiting = self.viewers.get(gig_id, [])
        if driver_id not in waiting:
            self.viewers[gig_id] = [*waiting, driver_id]

    def answered(self, accepted: bool) -> None:
        if accepted:
            self.accepted += 1

    def actions(self, books: Any, fee: Callable[[str], float]) -> list[dict]:
        """The offers to send now: for each open gig, its waiting viewers who live near it, at `fee(gig_id)` cents."""
        now = books.now
        day = now // DAY
        actions: list[dict] = []
        if now % DAY < 7 * 60 or now % DAY >= 22 * 60:
            return actions
        for gig_id, waiting in list(self.viewers.items()):
            del self.viewers[gig_id]
            post = books.posts.get(gig_id)
            first = post["stops"][0] if post else None
            last = post["stops"][-1] if post else None
            start = end = None
            if first and (order := books.orders.get(first["orderId"])):
                start = order["legs"][first["leg"]]["pickup"]["placeId"]
            if last and (order := books.orders.get(last["orderId"])):
                end = order["legs"][last["leg"]]["delivery"]["placeId"]
            if not post or not start or not end or gig_id in books.booked:
                continue
            if gig_id not in books.gigs_of(first["orderId"]):
                continue
            cents = js_round(fee(gig_id))
            live = [until for until in self.open.get(gig_id, []) if until > now]
            for driver_id in waiting:
                if len(live) >= PER_GIG or not cents > 0:
                    break
                home = self.homes.get(driver_id)
                today = [d for d in self.days.get(driver_id, []) if d == day]
                if not home or len(today) >= PER_DRIVER:
                    continue
                if self.roads.minutes(home, start) > NEAR and self.roads.minutes(end, home) > NEAR:
                    continue
                self.offered.add(f"{gig_id} {driver_id}")
                self.days[driver_id] = [*today, day]
                live.append(now + OPEN_FOR)
                self.sent += 1
                actions.append({"type": "offer", "gigId": gig_id, "driverId": driver_id, "feeCents": cents})
            self.open[gig_id] = live
        return actions
