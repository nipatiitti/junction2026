"""Where the drivers live, from the world's driver list and map: how scarce they are near a pickup,
and how far the nearest of them travel to it."""

from __future__ import annotations

import math
import statistics
from collections import Counter

from spread.types import DriverProfile, WorldMap

# Drivers count towards a place by the road minutes from their home: a driver an hour away counts
# about a third as much as one who lives there.
REACH_MINUTES = 60
# The travel time to a pickup is the road time from the homes of its nearest drivers, this many.
NEAREST = 10
UNKNOWN_TRAVEL = 60


class Market:
    def __init__(self, world_map: WorldMap, roster: list[DriverProfile]):
        self.road = {(r["from"], r["to"]): r["minutes"] for r in world_map["roads"]}
        self.homes = Counter(driver["homePlaceId"] for driver in roster)
        places = [place["id"] for place in world_map["places"]]
        self.access = {place: self._access(place) for place in places}
        self.median_access = statistics.median(self.access.values()) if self.access else 0.0
        self.travel = {place: self._travel(place) for place in places}

    def minutes(self, origin: str, destination: str) -> int:
        return self.road.get((origin, destination), 0)

    def scarcity(self, place: str) -> float:
        """0 where drivers are as near as at the world's median place or nearer, up to 1 where none are."""
        if place not in self.access or self.median_access <= 0:
            return 0.0
        return max(0.0, 1 - self.access[place] / self.median_access)

    def travel_minutes(self, place: str) -> int:
        return self.travel.get(place, UNKNOWN_TRAVEL)

    def _access(self, place: str) -> float:
        return sum(
            count * math.exp(-self.road.get((home, place), math.inf) / REACH_MINUTES)
            for home, count in self.homes.items()
        )

    def _travel(self, place: str) -> int:
        seen = 0
        for home in sorted(self.homes, key=lambda home: self.road.get((home, place), math.inf)):
            seen += self.homes[home]
            if seen >= NEAREST:
                return self.road.get((home, place), UNKNOWN_TRAVEL)
        return UNKNOWN_TRAVEL
