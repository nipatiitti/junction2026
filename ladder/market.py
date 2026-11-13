"""The map and the driver list, read once at the start: road minutes between places, straight-line distances, and how
many drivers live within reach of a place. The ladder measures how easy a ride is with them."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from spread.types import DriverProfile, WorldMap

REACH = 45  # road minutes at which a driver's home counts e^-1 (37%) towards a place's supply
NOTIFY_KM = 30  # the app notifies a driver of a gig whose first pickup is this close to their home, in a straight line


def experienced(driver: DriverProfile) -> bool:
    """May drive a premium car: rating at least 4.8 and at least 50 completed gigs."""
    return driver["rating"] >= 4.8 and driver["completedGigs"] >= 50


@dataclass(frozen=True)
class Nearby:
    """A driver who lives within reach of a place."""

    driver: DriverProfile
    minutes: int  # road minutes from their home to the place
    km: float  # straight-line km from their home to the place


class Market:
    """Road minutes and km between places, and where the drivers live."""

    def __init__(self, world_map: WorldMap, roster: list[DriverProfile]):
        self.places = {place["id"]: place for place in world_map["places"]}
        self.minutes = {(road["from"], road["to"]): road["minutes"] for road in world_map["roads"]}
        self.km = {(road["from"], road["to"]): road["km"] for road in world_map["roads"]}
        self.drivers = {driver["id"]: driver for driver in roster}
        self.homes: Counter[str] = Counter(driver["homePlaceId"] for driver in roster)
        self.experienced_homes: Counter[str] = Counter(d["homePlaceId"] for d in roster if experienced(d))
        self._supply: dict[tuple[str, str], float] = {}

    def drive(self, a: str, b: str) -> int:
        """Road minutes from a to b; the map has every pair."""
        return self.minutes.get((a, b), 0 if a == b else 24 * 60)

    def road_km(self, a: str, b: str) -> float:
        return self.km.get((a, b), 0.0 if a == b else 1000.0)

    def straight_km(self, a: str, b: str) -> float:
        """The straight-line distance in km, as the app measures its 30 km notification radius."""
        p, q = self.places.get(a), self.places.get(b)
        if p is None or q is None:
            return 1000.0
        lat1, lat2 = math.radians(p["lat"]), math.radians(q["lat"])
        dlat, dlon = lat2 - lat1, math.radians(q["lon"] - p["lon"])
        h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        return 2 * 6371 * math.asin(math.sqrt(h))

    def supply(self, place: str, who: str = "all") -> float:
        """How many drivers live within reach of the place: each driver counts e^(-road minutes from home / REACH).
        `who` is "all" or "experienced"."""
        key = (place, who)
        if key not in self._supply:
            homes = self.experienced_homes if who == "experienced" else self.homes
            self._supply[key] = sum(n * math.exp(-self.drive(home, place) / REACH) for home, n in homes.items())
        return self._supply[key]

    def nearby(self, place: str, within: int) -> list[Nearby]:
        """The drivers who live within `within` road minutes of the place, nearest first."""
        found = [
            Nearby(driver, self.drive(driver["homePlaceId"], place), self.straight_km(driver["homePlaceId"], place))
            for driver in self.drivers.values()
            if self.drive(driver["homePlaceId"], place) <= within
        ]
        return sorted(found, key=lambda n: (n.minutes, n.driver["drops"] / (1 + n.driver["completedGigs"])))
