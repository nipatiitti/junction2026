"""Admission with a timed return leg: a car counts as a return leg only when one of our transports ends near it, its
driver gets there in time to collect it, and the car's last stop is near where that transport started.

It builds on the admission control of strategies/admission (#14), unchanged there. The base asks `pairs` for a
return leg: the car then takes half a place in the area's capacity and costs 0.85 of the usual driver cost. This
class answers `pairs` with the timed check, and lets each transport carry the return leg of one request only.
README.md next to this file explains it.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from spread.types import DriverProfile, WorldMap

from strategies.admission import Admission, Held, Verdict
from strategies.admission.admission import Params as AdmissionParams

HOUR = 60
FAR = 10**6  # road minutes between two places the map does not join


@dataclass(frozen=True)
class ChainParams(AdmissionParams):
    """The admission thresholds, plus when a request's car is a return leg of one of our transports."""

    near: int = 30  # the car waits within this drive of where the transport ends
    wait: int = 2 * HOUR  # the transport's driver gets there at most this long before the car is ready
    back: int = 60  # the request's last delivery is within this drive of where the transport started
    spare: int = HOUR  # the driver delivers the request's cars this long before its earliest deadline


class ChainAdmission(Admission):
    """Admission control whose return leg is timed, one request for each transport."""

    params: ChainParams

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: ChainParams | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or ChainParams())
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

    def release(self, request_id: str) -> None:
        """The desk declines a request that admission took: its transport and its place in the area are free."""
        self.pending.pop(request_id, None)
        self.claims = {order: claim for order, claim in self.claims.items() if claim[0] != request_id}

    def restore(self, requests: Iterable[dict], held: Iterable[Held]) -> None:
        """Claims the transports again after a restart: a new desk rebuilds its orders from the history, but not the
        claims. Each request we won and still hold is assessed again, in the order they came, at the minute it came,
        against the orders won before it, as far as they were delivered then. The orders and whether a driver holds
        them are today's, so it comes close, not exact."""
        requests, held = list(requests), list(held)
        won_at = {r["id"]: r["respondBy"] for r in requests}  # the dealer decides at the request's respondBy
        for request in sorted((r for r in requests if r["id"] in self.orders), key=lambda r: r["arrivedAt"]):
            at = request["arrivedAt"]
            then = [Held(as_of(h.order, at), h.booked) for h in held if won_at.get(h.order["id"], at + 1) <= at]
            transport = self.chain(request, then, at)
            if transport is not None:
                self.claims[transport] = (request["id"], request["respondBy"])

    def pairs(self, request: dict, held: Iterable[Held]) -> bool:
        """What the base asks for the capacity and the expected cost: is the car a return leg?"""
        return self.chain(request, held, self.now) is not None

    def chain(self, request: dict, held: Iterable[Held], now: int) -> str | None:
        """The order whose transport can take the request's car back, or None. Its last delivery is near where the
        car waits, its driver gets there (from its pickup window, or now, plus its drive) in time to collect the car
        and deliver the request's cars by the request's earliest deadline, and the request's last delivery is near
        where the transport started, close to its driver's home. It checks how near the car ends, not which way it
        goes. A transport that a driver already holds comes first. Only a premium transport, whose driver is
        experienced, takes a premium car."""
        p = self.params
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


def as_of(order: dict, at: int) -> dict:
    """The order as it was at minute `at`: its cars delivered after then are not delivered yet."""
    return {**order, "deliveredAt": [t if t is not None and t <= at else None for t in order["deliveredAt"]]}
