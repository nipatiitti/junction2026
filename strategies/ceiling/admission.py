"""Admission with a timed return leg: a car counts as a return leg only when one of our transports ends near it, its
driver gets there in time to collect it, and the car goes back towards where that transport started.

It builds on the admission control of strategies/admission (#14), unchanged there. The base asks `pairs` for a
return leg: the car then takes half a place in the area's capacity and costs 0.85 of the usual driver cost. This
class answers `pairs` with the timed check, and lets each transport carry the return leg of one request only.
README.md next to this file explains it.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from strategies.admission import Admission, Held, Verdict

HOUR = 60
FAR = 10**6  # road minutes between two places the map does not join


@dataclass(frozen=True)
class ReturnLeg:
    """When a request's car is a return leg of one of our transports."""

    near: int = 30  # the car waits within this drive of where the transport ends
    wait: int = 2 * HOUR  # the transport's driver gets there at most this long before the car is ready
    back: int = 60  # the request's last delivery is within this drive of where the transport started
    spare: int = HOUR  # the driver delivers the request's cars this long before its earliest deadline


@dataclass
class ChainAdmission(Admission):
    """Admission control whose return leg is timed, one request for each transport."""

    leg: ReturnLeg = field(default_factory=ReturnLeg)

    def __post_init__(self) -> None:
        super().__post_init__()
        # order id -> (request id, its respondBy): the request whose return leg rides on that order's transport
        self.claims: dict[str, tuple[str, int]] = {}
        self.now = 0  # the minute of the request being assessed

    def assess(self, request: dict, held: Iterable[Held] = (), now: int | None = None) -> Verdict:
        """The base's verdict, with the timed return leg. An accepted return leg claims its transport."""
        held = list(held)
        self.now = request["arrivedAt"] if now is None else now
        verdict = super().assess(request, held, now)
        transport = self.chain(request, held, self.now)
        if verdict.accept and transport is not None:
            self.claims[transport] = (request["id"], request["respondBy"])
        return verdict

    def pairs(self, request: dict, held: Iterable[Held]) -> bool:
        """What the base asks for the capacity and the expected cost: is the car a return leg?"""
        return self.chain(request, held, self.now) is not None

    def chain(self, request: dict, held: Iterable[Held], now: int) -> str | None:
        """The order whose transport can take the request's car back, or None. Its last delivery is near where the
        car waits, its driver gets there (from its pickup window, or now, plus its drive) in time to collect the car
        and deliver the request's cars by the request's earliest deadline, and the request's last delivery is near
        where the transport started, close to its driver's home. A transport that a driver already holds comes
        first. Only a premium transport, whose driver is experienced, takes a premium car."""
        p = self.leg
        first = request["legs"][0]["pickup"]
        window = first["window"]
        end = request["legs"][-1]["delivery"]["placeId"]  # where the driver finishes with the request's cars
        due = min(option["deadline"] for option in request["options"]) - p.spare
        drive = self.drive_minutes(request["legs"])
        premium = any(leg["car"]["premium"] for leg in request["legs"])
        for h in sorted(held, key=lambda h: not h.booked):
            order = h.order
            if order["deliveredAt"][-1] is not None or self.claimed(order["id"], now):
                continue
            if premium and not any(leg["car"]["premium"] for leg in order["legs"]):
                continue
            start = order["legs"][0]["pickup"]  # where the transport's driver set out
            stop = order["legs"][-1]["delivery"]["placeId"]  # where they will be free
            reach = self.minutes.get((stop, first["placeId"]), FAR)
            if reach > p.near or self.minutes.get((end, start["placeId"]), FAR) > p.back:
                continue
            there = max(now, start["window"]["from"]) + self.drive_minutes(order["legs"]) + reach
            collect = max(there, window["from"])
            if collect - there <= p.wait and collect <= window["to"] and collect + drive <= due:
                return order["id"]
        return None

    def claimed(self, order_id: str, now: int) -> bool:
        """The order's transport already carries the return leg of a request we wait to hear on, or of an order we
        won and have not delivered."""
        claim = self.claims.get(order_id)
        return claim is not None and (claim[1] >= now or claim[0] in self.orders)
