"""Admission that counts dealer trust as an asset: at level 8 an order delivered on time makes its dealer accept 1%
more from us on every later order, up to 25 orders. So an order is worth its margin plus 1% of what that dealer will
still pay us this week, and a busy dealer's car is worth taking at a thinner margin early in the week.

A strategy (strategies/strategy.py) built on the timed return leg of strategies/ceiling, unchanged there. The value
of one more order on time is read from the week so far: the dealer's requests per open hour, the open hours left
after the car arrives, the share of our quotes that dealer takes, and the prices it asks for. Admission subtracts that
value from the driver cost, so the margin check and the price floor of ceiling pricing both see the net cost.
README.md next to this file has the formula.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from spread.types import DeskEvent, DriverProfile, WorldMap

from strategies.admission import Held, Verdict
from strategies.ceiling.admission import ChainAdmission
from strategies.ceiling.admission import Params as ChainParams

HOUR, DAY = 60, 24 * 60
OPEN_FROM, OPEN_TO = 8 * HOUR, 18 * HOUR  # price requests come Monday to Friday, almost all in these hours
WEEK_OPEN = 5 * (OPEN_TO - OPEN_FROM)
TRUST_CAP = 25  # a dealer counts at most 25 orders on time


@dataclass(frozen=True)
class Params(ChainParams):
    """The thresholds of the timed return leg, plus the value of trust."""

    trust_step: float = 0.01  # each order on time raises what the dealer accepts by 1%
    on_time: float = 0.97  # the chance that a car we take arrives on time, from the bench
    arrival: int = 12 * HOUR  # the trust counts from about when the car arrives: the value starts this long from now
    observed: int = 4 * HOUR  # the dealer's request rate is read over at least this many open minutes
    win_prior: float = 4.0  # the dealer's share of our quotes counts this many quotes at the world's share
    markup: float = 1.35  # the dealer's later prices: its list prices times this
    value_cap: float = 0.3  # the value never takes more than this share off the driver cost


def open_minutes(at: int) -> int:
    """The request minutes of the week, 08:00 to 18:00 Monday to Friday, before minute `at`."""
    return sum(min(max(at - day * DAY - OPEN_FROM, 0), OPEN_TO - OPEN_FROM) for day in range(5))


class TrustValueAdmission(ChainAdmission):
    """The ceiling system's admission, with the trust that an order buys taken off its driver cost."""

    params: Params

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())
        self.trust_of: Callable[[str], int] = lambda dealer: 0  # the desk points this at ceiling pricing's count
        self.requests: Counter[str] = Counter()  # dealer -> its price requests so far
        self.listed: Counter[str] = Counter()  # dealer -> the sum of its requests' first list prices
        self.dealer_of: dict[str, str] = {}  # request id -> dealer
        self.taken: set[str] = set()  # requests we priced, so their outcome says what the dealer takes
        self.won_by: Counter[str] = Counter()
        self.lost_by: Counter[str] = Counter()
        self.values: list[float] = []  # the value of each request taken, in cents, for the summary

    def observe(self, event: DeskEvent) -> None:
        """The base's learning, plus each dealer's requests and what it did with our prices."""
        super().observe(event)
        kind = event["kind"]
        if kind == "price_request":
            request = event["request"]
            self.requests[request["dealerId"]] += 1
            self.listed[request["dealerId"]] += request["options"][0]["listPriceCents"]
            self.dealer_of[request["id"]] = request["dealerId"]
        elif kind == "order_won" and event["order"]["id"] in self.taken:
            self.won_by[event["order"]["dealerId"]] += 1
        elif kind == "order_lost" and event["requestId"] in self.taken:
            self.lost_by[self.dealer_of.get(event["requestId"], "")] += 1

    def value(self, request: dict, now: int) -> float:
        """The trust that one more order on time with this dealer buys, in cents: 1% of what the dealer will still
        pay us this week, from about when the car arrives, times the chance that it arrives on time."""
        p = self.params
        dealer = request["dealerId"]
        if self.level < 8 or self.trust_of(dealer) >= TRUST_CAP or not self.requests[dealer]:
            return 0.0
        seen = max(open_minutes(now), p.observed)
        left = WEEK_OPEN - open_minutes(now + p.arrival)
        if left <= 0:
            return 0.0
        later = self.requests[dealer] / seen * left  # the dealer's requests still to come after the car arrives
        world = (sum(self.won_by.values()) + 1) / (sum(self.won_by.values()) + sum(self.lost_by.values()) + 2)
        share = (self.won_by[dealer] + p.win_prior * world) / (self.won_by[dealer] + self.lost_by[dealer] + p.win_prior)
        price = self.listed[dealer] / self.requests[dealer] * p.markup
        return p.trust_step * later * share * price * p.on_time

    def expected_cost(self, request: dict, held: Iterable[Held] = ()) -> int:
        """The driver cost less the trust the order buys, at most `value_cap` of the cost off."""
        cost = super().expected_cost(request, held)
        off = min(self.value(request, self.now), self.params.value_cap * cost)
        return int(cost - off + 0.5)

    def assess(self, request: dict, held: Iterable[Held] = (), now: int | None = None) -> Verdict:
        """The base's verdict on the net cost. A request taken is remembered, so its outcome teaches the dealer's
        share."""
        verdict = super().assess(request, held, now)
        if verdict.accept:
            self.taken.add(request["id"])
            self.values.append(self.value(request, self.now))
        return verdict

    def release(self, request_id: str) -> None:
        """The desk declined a request that admission took: its outcome says nothing of the dealer."""
        super().release(request_id)
        self.taken.discard(request_id)

    def summary(self) -> str:
        """The chain admission line, plus the trust value of the requests taken."""
        line = super().summary()
        if not line:
            return ""
        valued = [v for v in self.values if v > 0]
        mean = sum(valued) / len(valued) / 100 if valued else 0.0
        return f"{line}; trust value: {len(valued)} requests valued, €{mean:.2f} on average".replace(
            "Chain admission:", "Trust-value admission:", 1
        )
