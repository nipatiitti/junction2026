"""The price of a quote: the list price times a multiplier that we learn from our own wins and losses, times what
the dealer's trust in us adds at level 8.

The competitor's price is the list price times factors for the world, the lane, the day and the request (HANDBOOK.md,
"Dealers compare prices"). We cannot see it, but each quote that wins or loses tells us on which side of it we were.
The multiplier rises a step after a win and falls a step after a loss, so it settles where about half of our quotes
win: just under the competitor. Each dealer has its own offset on top, learned the same way, more slowly.
"""

from __future__ import annotations

import math
from collections import Counter

from spread.types import DeskEvent, PriceRequest

# The world multiplier at the start, by level: the middle of the competitor's range over the list price.
START = {1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0, 5: 1.0, 6: 1.0, 7: 1.24, 8: 1.38}
STEP = 0.025  # the world multiplier moves this much (in log) after each win or loss
DEALER_STEP = 0.02  # a dealer's offset moves this much after each of its outcomes
DEALER_CAP = 0.15  # a dealer's offset stays within this (in log)
LOWEST, HIGHEST = 0.9, 2.2  # the world multiplier stays within these
# Never quote below this times the typical fee, by rung: under it a car does not pay its driver. Harder rungs pay
# more to their drivers.
FLOOR = {1: 1.25, 2: 1.25, 3: 1.4, 4: 1.35, 5: 1.6, 6: 1.4}
TRUST_CAP = 25  # level 8: each dealer counts up to 25 orders delivered on time, each worth 1% more


class Pricing:
    """Learns the multiplier on the list price that wins about half of our quotes."""

    def __init__(self, level: int):
        self.level = level
        self.world = math.log(START.get(level, 1.0))
        self.dealer: Counter[str] = Counter()  # dealer id -> log offset
        self.trust: Counter[str] = Counter()  # dealer id -> orders delivered on time, as the dealer counts them
        self.quoted: dict[str, str] = {}  # request id -> dealer id, for the quotes that wait for an answer

    def multiplier(self, dealer: str) -> float:
        trust = 1 + min(self.trust[dealer], TRUST_CAP) / 100 if self.level >= 8 else 1.0
        return math.exp(self.world + self.dealer[dealer]) * trust

    def prices(self, request: PriceRequest, kinds: list[str], rung: int) -> dict[str, int]:
        """The price of each option kind that we quote. Up to level 3 every quote wins at the list price."""
        options = {option["kind"]: option for option in request["options"]}
        if self.level <= 3:
            return {kind: options[kind]["listPriceCents"] for kind in kinds}
        m = self.multiplier(request["dealerId"])
        floor = int(FLOOR.get(rung, 1.25) * request["referenceFeeCents"] + 0.5)  # the fee is for all its cars
        return {kind: max(int(options[kind]["listPriceCents"] * m + 0.5), floor) for kind in kinds}

    def sent(self, request: PriceRequest) -> None:
        """A real quote went out: its answer teaches the multiplier."""
        self.quoted[request["id"]] = request["dealerId"]

    def observe(self, event: DeskEvent) -> None:
        if event["kind"] == "order_won":
            self.learn(event["order"]["id"], won=True)
        elif event["kind"] == "order_lost":
            self.learn(event["requestId"], won=False)

    def learn(self, request_id: str, won: bool) -> None:
        dealer = self.quoted.pop(request_id, None)
        if dealer is None or self.level <= 3:  # a decline, or a level where every quote wins
            return
        sign = 1 if won else -1
        self.world = min(math.log(HIGHEST), max(math.log(LOWEST), self.world + sign * STEP))
        self.dealer[dealer] = min(DEALER_CAP, max(-DEALER_CAP, self.dealer[dealer] + sign * DEALER_STEP))

    def delivered(self, dealer: str, on_time: bool) -> None:
        """Level 8: an order delivered on time adds one to the dealer's count; a late one halves it."""
        self.trust[dealer] = min(TRUST_CAP, self.trust[dealer] + 1) if on_time else self.trust[dealer] // 2

    def summary(self) -> str:
        trusted = sum(1 for count in self.trust.values() if count > 0)
        return f"Pricing: world multiplier {math.exp(self.world):.3f}, {trusted} dealers trust us"
