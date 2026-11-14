"""The drivers' side, learned while the week runs (`supply.ts`): what a booking costs over its typical fee, as a sum of
effects (the world, the pickup place, the delivery place, whether the car must be collected today). A driver who lives
where a gig ends takes it cheaply, and a town without drivers needs every raise, so the places differ more than the
orders do. Each booking moves every effect of its cars by its share of what the sum got wrong."""

from __future__ import annotations


class Supply:
    def __init__(self, base: float) -> None:
        self.base = base  # what a booking costs × typical before the week's bookings say
        self.effects: dict[str, list[float]] = {}  # key -> [mean, count]

    @staticmethod
    def keys(start: str | None, end: str | None, today: bool) -> list[str]:
        return ["world", f"from:{start}", f"to:{end}", *(["today"] if today else [])]

    def ratio(self, keys: list[str]) -> float:
        """What a booking with these effects costs × typical."""
        total = self.base
        for key in keys:
            effect = self.effects.get(key)
            total += effect[0] if effect else 0
        return min(2, max(0.5, total))

    def learn(self, keys: list[str], ratio: float) -> None:
        """A car booked at `ratio` × its typical fee. An effect with few bookings moves little: it starts as if it
        had seen 10 bookings at the mean (3 for the world)."""
        miss = ratio - self.ratio(keys)
        for key in keys:
            effect = self.effects.setdefault(key, [0.0, 3 if key == "world" else 10])
            effect[1] = min(effect[1] + 1, 40)  # the week moves: old bookings fade
            effect[0] += miss / effect[1] / len(keys)
