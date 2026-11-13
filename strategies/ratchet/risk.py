"""The probability that no driver books a gig at a pickup before its deadline warning, place by place: a prior
from where the world's drivers live, learned during the week from our own gigs there."""

from __future__ import annotations

from collections import Counter

from strategies.fees import Market

# The prior: RISK_BASE at a place with as many drivers within reach as the world's median place, rising to 1 at a
# place with none. It counts as RISK_PRIOR orders, so our own gigs take over after a few orders.
RISK_BASE = 0.15
RISK_PRIOR = 5


class Risk:
    def __init__(self, market: Market):
        self.market = market
        self.found: Counter[str] = Counter()  # place -> orders whose gig a driver booked before the warning
        self.missed: Counter[str] = Counter()  # place -> orders that reached their deadline warning with no driver
        self.counted: set[str] = set()  # each order counts once, at its first booking or its first warning

    def prior(self, place: str) -> float:
        return RISK_BASE + (1 - RISK_BASE) * self.market.scarcity(place)

    def of(self, place: str) -> float:
        """The share of our orders at the place that found no driver before the warning, with the prior."""
        seen = self.found[place] + self.missed[place]
        return (self.missed[place] + RISK_PRIOR * self.prior(place)) / (seen + RISK_PRIOR)

    def learn(self, order_id: str, place: str, found: bool) -> None:
        """An order's first booking (`found`) or its first deadline warning, whichever came first."""
        if order_id in self.counted:
            return
        self.counted.add(order_id)
        (self.found if found else self.missed)[place] += 1
