"""Direct offers: send a gig to drivers we know are near its pickup, to fill it cheaply or to rescue it.

The logic needs no network: it reads the driver list, the map, the gigs we post and the events of the week.
See README.md next to this file for when an offer goes out, to whom and at what fee.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import NamedTuple

from spread.types import DeskEvent, DriverProfile, WorldMap

from strategies.strategy import Strategy

HOUR, DAY = 60, 24 * 60
OFFER_MINUTES = 10  # an offer is open this long; the answer comes inside it (yes) or after it (no, unread)
PER_DRIVER_PER_DAY = 3
PER_GIG_OPEN = 3
QUIET_FROM, QUIET_TO = 23 * HOUR, 7 * HOUR  # no driver reads an offer then


@dataclass(frozen=True)
class Params:
    """The thresholds. The defaults are tuned on seeds spread-1 to spread-5 at level 8 (README.md)."""

    near_minutes: int = 60  # a driver who finishes within this drive of a pickup is near it
    home_minutes: int = 45  # a driver who lives within this drive of a pickup is near it
    fresh_minutes: int = 3 * HOUR  # a driver free this long ago may have gone home: no longer near
    chain_fee: float = 0.85  # a driver finishing nearby gets this share of the app fee
    rescue_fee: float = 1.0  # a gig past its deadline warning goes at the app fee, to drivers it never notified
    spare_minutes: int = 30  # a driver must reach the pickup this long before the pickup window ends


class GigInfo(NamedTuple):
    """What we know of a gig we posted."""

    pickup: str  # the first pickup place
    pickup_until: int  # the last minute a driver can collect the first car
    end: str  # the last delivery place
    drive: int  # road minutes from the first pickup to the last delivery
    manual: bool  # only a driver with a manual licence may take it
    experienced: bool  # only an experienced driver may take it (premium car)


class Position(NamedTuple):
    """Where one of our drivers is, or will be, free: a place and the minute."""

    place: str
    at: int


class Offers(Strategy[Params]):
    """Chooses direct offers. Feed it the gigs we post with `register` and every event with `observe`."""

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())
        self.drivers = {d["id"]: d for d in self.roster}
        self.gigs: dict[str, GigInfo] = {}
        self.open: set[str] = set()  # gigs that no driver holds now
        self.holder: dict[str, str] = {}  # gig id -> the driver who holds it
        self.free: dict[str, Position] = {}  # driver id -> where and when they finish our gig, or finished it
        self.schedules: dict[str, list[dict]] = {}  # gig id -> its fee schedule
        self.sent: dict[str, list[int]] = defaultdict(list)  # driver -> minutes we sent them offers
        self.skip: set[tuple[str, int]] = set()  # (driver, day): declined or did not read: not again that day
        self.pending: dict[str, dict[str, int]] = defaultdict(dict)  # gig id -> driver -> minute the offer went
        self.asked: set[tuple[str, str]] = set()  # (gig, driver): offered once already
        self.active: set[tuple[str, int]] = set()  # (driver, day): viewed, booked or answered us: works today
        self.rescuing: set[str] = set()  # gigs past their deadline warning, rescued until a driver books them
        self.answers: dict[str, int] = defaultdict(int)  # sent, accepted, declined, expired, refused
        self.refusals: list[str] = []

    # --- what we know ----------------------------------------------------------------------------------

    def register(self, gig_id: str, info: GigInfo, schedule: list[dict]) -> None:
        """A gig the world accepted, with its fee schedule. It is open until a driver books it."""
        self.gigs[gig_id] = info
        self.schedules[gig_id] = schedule
        self.open.add(gig_id)

    def reschedule(self, gig_id: str, schedule: list[dict]) -> None:
        self.schedules[gig_id] = schedule

    def app_fee(self, gig_id: str, now: int) -> int:
        """The fee the app shows now: the latest step that has started, else the first."""
        schedule = self.schedules[gig_id]
        return max((s["feeCents"] for s in schedule if s["at"] <= now), default=schedule[0]["feeCents"])

    def sent_today(self, driver: str, now: int) -> int:
        """Offers sent to the driver in the last 24 hours: within the limit of three a day, however the day
        is counted."""
        return sum(1 for at in self.sent[driver] if at > now - DAY)

    def forget(self, gig_id: str) -> None:
        """A gig that left the app: withdrawn, expired or done."""
        self.open.discard(gig_id)
        self.rescuing.discard(gig_id)
        self.pending.pop(gig_id, None)

    def rescue(self, gig_id: str) -> None:
        """A gig past its deadline warning: from now on, also ask drivers who live near its pickup."""
        self.rescuing.add(gig_id)

    def observe(self, event: DeskEvent) -> None:
        """Learns from one event of the week: who booked, dropped or delivered our gigs, and the offers' answers."""
        kind, at = event["kind"], event["at"]
        gig_id = event.get("gigId")
        seen = kind in ("gig_viewed", "gig_booked", "offer_answered") and event.get("answer") != "expired"
        if seen and "driverId" in event:  # an unread offer says nothing; anything else says they work today
            self.active.add((event["driverId"], at // DAY))
        if kind == "gig_booked":
            self.open.discard(gig_id)
            self.rescuing.discard(gig_id)
            self.pending.pop(gig_id, None)
            self.holder[gig_id] = event["driverId"]
            info = self.gigs.get(gig_id)
            if info:
                # They finish at the last delivery, about the drive after they can first collect the car.
                self.free[event["driverId"]] = Position(info.end, max(at, info.pickup_until - 4 * HOUR) + info.drive)
        elif kind in ("gig_dropped", "no_show"):
            if gig_id in self.gigs:
                self.open.add(gig_id)
            self.holder.pop(gig_id, None)
            self.free.pop(event["driverId"], None)
            if kind == "gig_dropped":
                self.skip.add((event["driverId"], at // DAY))
        elif kind == "delivered":
            driver = self.holder.get(gig_id)
            info = self.gigs.get(gig_id)
            if driver and info and event["placeId"] == info.end:
                self.free[driver] = Position(info.end, at)
        elif kind == "gig_expired":
            self.forget(gig_id)
        elif kind == "order_cancelled":
            for gig in event["gigs"]:
                self.forget(gig["gigId"])
        elif kind == "offer_answered":
            driver, answer = event["driverId"], event["answer"]
            self.answers[answer] += 1
            self.pending.get(gig_id, {}).pop(driver, None)
            if answer == "accepted":
                self.observe({"kind": "gig_booked", "at": at, "gigId": gig_id, "driverId": driver})
            else:
                self.skip.add((driver, at // DAY))

    # --- whom to ask -----------------------------------------------------------------------------------

    def may_drive(self, driver: dict, info: GigInfo) -> bool:
        manual_ok = not info.manual or driver["licence"] == "manual"
        experienced = driver["rating"] >= 4.8 and driver["completedGigs"] >= 50
        return manual_ok and (not info.experienced or experienced)

    def candidates(self, gig_id: str, now: int, rescue: bool) -> list[str]:
        """Drivers who can reach the gig's pickup in time, best placed first: those who finish one of our
        gigs near it, then, to rescue a gig, those who live near it."""
        info = self.gigs[gig_id]
        p, day = self.params, now // DAY
        latest = info.pickup_until - p.spare_minutes
        ranked: list[tuple[float, str]] = []
        for driver_id, pos in self.free.items():
            if pos.at < now - p.fresh_minutes or self.holder.get(gig_id) == driver_id:
                continue
            reach = self.minutes.get((pos.place, self.gigs[gig_id].pickup), 10**6)
            if reach <= p.near_minutes and max(pos.at, now) + reach <= latest:
                ranked.append((reach, driver_id))
        if rescue:
            chained = {d for _, d in ranked}
            for driver_id, driver in self.drivers.items():
                if driver_id in chained:
                    continue
                reach = self.minutes.get((driver["homePlaceId"], info.pickup), 10**6)
                if reach <= p.home_minutes and now + reach <= latest:
                    # A driver seen working today first, then a reliable one: few drops for the gigs they did.
                    idle = 0 if (driver_id, day) in self.active else 200
                    ranked.append(
                        (100 + idle + reach + 60 * driver["drops"] / (driver["completedGigs"] + 5), driver_id)
                    )
        ranked.sort()
        return [
            d
            for _, d in ranked
            if self.may_drive(self.drivers[d], info)
            and (d, day) not in self.skip
            and self.sent_today(d, now) < PER_DRIVER_PER_DAY
            and (gig_id, d) not in self.asked
        ]

    def offers(self, gig_id: str, now: int, rescue: bool = False) -> list[dict]:
        """The offers to send for one open gig now, within the limits: none at night, at most three open
        per gig, three per driver per day. A rescue asks drivers who live near too, at the app fee."""
        if self.level < 3 or gig_id not in self.open or gig_id not in self.gigs or quiet(now):
            return []
        pending = self.pending[gig_id]
        for driver, sent_at in list(pending.items()):  # an answer comes after the 10 minutes at the latest
            if now >= sent_at + OFFER_MINUTES + 1:
                del pending[driver]
        room = PER_GIG_OPEN - len(pending)
        if room <= 0:
            return []
        fee = max(
            1, int(self.app_fee(gig_id, now) * (self.params.rescue_fee if rescue else self.params.chain_fee) + 0.5)
        )
        actions = []
        for driver in self.candidates(gig_id, now, rescue)[:room]:
            pending[driver] = now
            self.sent[driver].append(now)
            self.answers["sent"] += 1
            self.asked.add((gig_id, driver))
            actions.append({"type": "offer", "gigId": gig_id, "driverId": driver, "feeCents": fee})
        return actions

    def due(self, now: int) -> list[dict]:
        """The offers to send now, once the step's events are all read, so no gig a driver has just booked
        gets one: for every open gig, to our drivers who finish near its pickup, and for a rescued gig also
        to drivers who live near it."""
        actions = []
        for gig_id in sorted(self.open):
            actions += self.offers(gig_id, now, rescue=gig_id in self.rescuing)
        return actions

    def refused(self, reason: str) -> None:
        """An offer the world refused: counted for the bench, which must see none for a limit."""
        self.answers["refused"] += 1
        self.refusals.append(reason)

    def summary(self) -> str:
        a = self.answers
        return (
            f"Offers: {a['sent']} sent, {a['accepted']} accepted, {a['declined']} declined, "
            f"{a['expired']} expired, {a['refused']} refused"
            + "".join(
                f"\n  refused {n}x: {reason}"
                for reason, n in Counter(re.sub(r"\S*\d\S*", "#", r) for r in self.refusals).most_common(5)
            )
        )


def quiet(now: int) -> bool:
    """From 23:00 to 07:00 no driver reads an offer."""
    minute = now % DAY
    return minute >= QUIET_FROM or minute < QUIET_TO
