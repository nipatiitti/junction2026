"""The notes strategy: reads each request's note once, and keeps the snowfalls forecast at each place, which the
stop windows of a car on summer tyres wait for. See README.md next to this file."""

from __future__ import annotations

from spread.types import DeskEvent, DriverProfile, PriceRequest, WorldMap

from strategies.notes.plan import Snow
from strategies.notes.reader import NoteFacts, read_note
from strategies.strategy import NoParams, Strategy


class NoteReader(Strategy[NoParams]):
    """What each request's note says, and the snow forecasts. Feed it every event with `observe`, ask `read` for a
    request's facts, and give `snow` or `snow_at` to `pickup_window`. Its thresholds are the constants of reader.py
    and plan.py, so its `params` are empty."""

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: NoParams | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or NoParams())
        self.facts: dict[str, NoteFacts] = {}  # request id -> what its note says
        self.snow: dict[str, list[Snow]] = {}  # place id -> the snowfalls forecast there

    def observe(self, event: DeskEvent) -> None:
        """Learns from one event of the week: the snowfalls that a `forecast` announces."""
        if event["kind"] == "forecast":
            for place in event["placeIds"]:
                self.snow.setdefault(place, []).append((event["from"], event["to"]))

    def read(self, request: PriceRequest) -> NoteFacts:
        """What the request's note says, read once. The note speaks of the first car: in a trade-in, the new car."""
        if request["id"] not in self.facts:
            self.facts[request["id"]] = read_note(request["note"] and request["note"]["text"], request["arrivedAt"])
        return self.facts[request["id"]]

    def snow_at(self, *places: str) -> list[Snow]:
        """The snowfalls forecast at the places, place by place."""
        return [snowfall for place in places for snowfall in self.snow.get(place, [])]
