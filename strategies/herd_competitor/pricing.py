"""Competitor herding: headroom pricing that sometimes loses a dealer's low-margin requests on purpose.

A strategy (strategies/strategy.py) built on strategies/headroom, unchanged there. The competitor cuts its prices for
a dealer whose recent requests we mostly won. While our rolling win share is too high, this class turns an admitted
request with little expected margin into the ceiling desk's usual costless decline. Wins and losses still feed the
rolling share, but a deliberate loss teaches nothing to headroom pricing. README.md next to this file explains the
window, the two thresholds and the margin guard.
"""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass

from spread.types import DeskEvent, DriverProfile, WorldMap

from strategies.headroom.pricing import HeadroomPricing
from strategies.headroom.pricing import Params as HeadroomParams


@dataclass(frozen=True)
class Params(HeadroomParams):
    """The variables of headroom pricing, plus the dealer win-share rule. These starting values are not tuned."""

    herd_window: int = 20  # the decided requests whose wins and losses make a dealer's rolling win share
    herd_ceiling: float = 0.70  # above this win share, start losing that dealer's low-margin requests on purpose
    herd_floor: float = 0.50  # once herding, stop when the rolling win share falls under this
    herd_keep: float = 50.0  # euros: never deliberately lose a request whose expected margin is above this


class HerdPricing(HeadroomPricing):
    """Headroom pricing with a rolling dealer win share and deliberate low-margin losses."""

    params: Params

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())
        self.request_dealer: dict[str, str] = {}
        self.recent: defaultdict[str, deque[bool]] = defaultdict(deque)
        self.herd: set[str] = set()  # dealers whose low-margin requests we are losing on purpose
        self.herd_counts: Counter[str] = Counter()

    def register(self, request: dict) -> None:
        """Remembers the dealer of every request the desk quotes, including one admission declines."""
        self.request_dealer[request["id"]] = request["dealerId"]

    def observe(self, event: DeskEvent) -> None:
        """Adds every decided request to its dealer's window, then lets headroom pricing learn from it as usual."""
        if event["kind"] == "order_won":
            order = event["order"]
            self.record(order["dealerId"], True)
        elif event["kind"] == "order_lost":
            dealer = self.request_dealer.get(event["requestId"])
            if dealer is not None:
                self.record(dealer, False)
        super().observe(event)

    def record(self, dealer: str, won: bool) -> None:
        """Keeps at most the last `herd_window` outcomes of this dealer."""
        recent = self.recent[dealer]
        recent.append(won)
        if len(recent) > self.params.herd_window:
            recent.popleft()

    def herding(self, dealer: str) -> bool:
        """Starts above the ceiling and stops below the floor, leaving a band that avoids switching on every result."""
        recent = self.recent.get(dealer)
        if not recent:
            return False
        share = sum(recent) / len(recent)
        if dealer in self.herd:
            if share < self.params.herd_floor:
                self.herd.remove(dealer)
                return False
            return True
        if share > self.params.herd_ceiling:
            self.herd.add(dealer)
            return True
        return False

    def price(self, request: dict, now: int, cost: float = 0, kinds=None) -> dict[str, int]:
        """Returns headroom's normal price, or no price to make the ceiling desk send its costless decline.

        The normal price gives the request's expected euro margin over admission's driver cost. While herding, a
        margin of at most `herd_keep` is sacrificed; above it the request is always kept. The pending learning quote
        is removed with the normal price, so the deliberate loss moves neither the learned price nor its maximum.
        """
        prices = super().price(request, now, cost, kinds)
        if self.level <= 3 or not prices or not self.herding(request["dealerId"]):
            return prices
        margin = max(prices[o["kind"]] - cost for o in request["options"] if o["kind"] in prices) / 100
        if margin > self.params.herd_keep:
            self.herd_counts["kept"] += 1
            return prices
        quote = self.quotes.pop(request["id"], None)
        if quote is not None:
            self.counts["quoted"] -= 1
            self.counts["at the maximum"] -= getattr(quote, "capped", False)
            self.counts["at the floor"] -= getattr(quote, "floored", False)
        self.herd_counts["declined"] += 1
        return {}

    def summary(self) -> str:
        line = super().summary()
        if not self.herd_counts:
            return line
        herd = f"Herd: {self.herd_counts['declined']} low-margin declines, {self.herd_counts['kept']} kept by the guard"
        return f"{line}\n{herd}" if line else herd
