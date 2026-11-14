"""The dealers' side, learned while the week runs (`demand.ts`): for one option of one request, the highest multiple
of the list price that wins. Its log is a sum of effects (the world, the day, the dealer, the pickup place, the
delivery place, the option), each a mean and a variance, updated from every quote that wins or loses. The priors are
the measured level 8 facts: half of the quotes win at 1.40 × list, worlds differ by 7%, days by 15%, same-day takes
13% more, and 20 to 25% of noise stays in every request."""

from __future__ import annotations

import math
from dataclasses import dataclass

from strategies.lean.js import exp

DAY = 24 * 60
MAX_STEP = 0.12  # the most that one outcome moves an estimate, in log price


def middle(level: int) -> float:
    """Half of the quotes win at this multiple of the list price, by level."""
    return 1.4 if level >= 8 else 1.25 if level == 7 else 1


# Each kind of effect: its prior mean and variance in log price, and the variance it gains back each morning.
PRIOR = {
    "world": (0, 0.006, 0.0005),
    "day": (0, 0.0225, 0),
    "dealer": (0, 0.008, 0.001),
    "from": (0, 0.008, 0.001),
    "to": (0, 0.008, 0.001),
    "same_day": (0.12, 0.002, 0),
    "next_day": (0, 0.002, 0),
    "within_3_days": (0, 0.002, 0),
}


class Effect:
    __slots__ = ("mean", "variance")

    def __init__(self, mean: float, variance: float) -> None:
        self.mean, self.variance = mean, variance


@dataclass(frozen=True)
class Belief:
    """An option's threshold: its log multiple of the list price, and the logistic scale of our doubt about it."""

    mu: float
    scale: float
    variance: float


class Demand:
    def __init__(self, level: int, noise: float) -> None:
        self.effects: dict[str, Effect] = {}
        self.noise = noise
        self.base = math.log(middle(level))
        self.day = -1

    @staticmethod
    def keys(request: dict, kind: str) -> list[str]:
        leg = request["legs"][0] if request["legs"] else None
        return [
            "world",
            f"day:{request['arrivedAt'] // DAY}",
            f"dealer:{request['dealerId']}",
            f"from:{leg['pickup']['placeId'] if leg else None}",
            f"to:{leg['delivery']['placeId'] if leg else None}",
            kind,
        ]

    def belief(self, keys: list[str], offset: float = 0) -> Belief:
        mu = self.base + offset
        variance = 0.0
        for key in keys:
            effect = self.effect(key)
            mu += effect.mean
            variance += effect.variance
        scale = self.noise * math.sqrt(1 + (math.pi * variance) / (8 * self.noise * self.noise))
        return Belief(mu, scale, variance)

    @staticmethod
    def chance(belief: Belief, multiple: float) -> float:
        """The chance that a price of `multiple` × list wins."""
        return 1 / (1 + exp((math.log(multiple) - belief.mu) / belief.scale))

    def learn(self, keys: list[str], offset: float, multiple: float, won: bool) -> None:
        """Learns from one quote: `multiple` × list won or lost. Each effect moves by its share of the doubt."""
        if not (multiple > 0) or not math.isfinite(multiple):
            return
        belief = self.belief(keys, offset)
        p = Demand.chance(belief, multiple)
        gradient = ((1 if won else 0) - p) / belief.scale
        curve = (p * (1 - p)) / (belief.scale * belief.scale)
        gain = 1 / (1 + belief.variance * curve)
        step = abs(belief.variance * gradient * gain)
        damp = MAX_STEP / step if step > MAX_STEP else 1
        for key in keys:
            effect = self.effect(key)
            effect.mean += effect.variance * gradient * gain * damp
            effect.variance = max(1e-5, effect.variance - effect.variance * effect.variance * curve * gain)

    def dawn(self, day: int) -> None:
        """A new day: the effects that the competitor moves get some doubt back."""
        if day <= self.day:
            return
        self.day = day
        for key, effect in self.effects.items():
            _, variance, drift = PRIOR[key.split(":")[0]]
            effect.variance = min(variance, effect.variance + drift)

    def effect(self, key: str) -> Effect:
        effect = self.effects.get(key)
        if effect is None:
            mean, variance, _ = PRIOR[key.split(":")[0]]
            effect = self.effects[key] = Effect(mean, variance)
        return effect


def best_price(belief: Belief, list_cents: int, cost_cents: float) -> float | None:
    """The price in cents that earns the most: the chance to win times what the win leaves over `cost_cents`. None
    when no price leaves anything. The grid is walked by adding 0.01, as demand.ts does, so the floats agree."""
    best = 0.0
    price = None
    multiple = 0.9
    while multiple <= 3.001:
        value = Demand.chance(belief, multiple) * (multiple * list_cents - cost_cents)
        if value > best:
            best = value
            price = multiple * list_cents
        multiple += 0.01
    return price
