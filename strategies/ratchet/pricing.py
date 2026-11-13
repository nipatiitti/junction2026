"""Quote prices: a ratchet per dealer under a maximum markup.

A dealer's price starts at the maximum, falls only after we lose a quote to that dealer, and climbs back towards
the maximum after each win. It builds on the adaptive quoting of strategies/pricing, unchanged there: the same dealer
trust, but a different rule for the multiplier, and no price war or outage logic. No network: `price` takes a
request and returns a price for each option we quote, and `observe` takes the `order_won`, `order_lost` and `ledger`
events. README.md next to this file explains the model.
"""

from __future__ import annotations

from dataclasses import dataclass

from spread.types import DriverProfile, WorldMap

from strategies.pricing.model import DAY, PricingModel
from strategies.pricing.model import Params as PricingParams


@dataclass(frozen=True)
class Params(PricingParams):
    """The ratchet's knobs. Of the fields of `strategies/pricing`, only `floor` and `trust` are used."""

    # The highest multiplier on the list price is 1 + max_markup, before dealer trust: a dealer's price starts
    # there, and every win moves it back towards it.
    max_markup: float = 0.39
    cut: float = 0.04  # a lost quote lowers its dealer's multiplier by this share
    recover: float = 0.3  # a won quote moves its dealer's multiplier this share of the way back to the maximum
    # Each new day moves every multiplier this share of the way back to the maximum: the competitor's day factor
    # is new every day, and a price that the price war cut comes back. 0 turns it off.
    daily_recover: float = 0.3


@dataclass
class Sent:
    """A quote waiting for its outcome."""

    dealer: str
    # Every quoted price was raised to the cost floor, above the ratchet's price: losing it says nothing about
    # the ratchet's price, so the loss does not lower it.
    floored: bool


class RatchetPricing(PricingModel):
    """One world's quote prices: a multiplier on the list price for each dealer, which falls only after a lost
    quote and climbs back towards the maximum after each win, with dealer trust on top at level 8."""

    params: Params

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())
        self.top = 1 + self.params.max_markup  # the highest multiplier, before trust
        # The multiplier of a dealer that we have not quoted yet: it learns from every dealer's outcomes alike.
        self.world = self.top
        self.dealer: dict[str, float] = {}  # dealer id -> its multiplier on the list price, before trust
        self.day = 0  # the day of the last daily recovery
        self.sent: dict[str, Sent] = {}  # request id -> the quote waiting for its outcome

    def multiplier(self, request: dict, now: int) -> float:
        """The multiplier on the list price for this request now, dealer trust included."""
        if self.level <= 3:
            return 1.0
        self.new_day(now)
        m = self.dealer.get(request["dealerId"], self.world)
        if self.level >= 8 and self.params.trust:
            m *= 1 + self.trust_of(request["dealerId"], now) / 100
        return m

    def price(self, request: dict, now: int, kinds: list[str] | None = None, floor: int = 0) -> dict[str, int]:
        """A price in cents for each option of `kinds` (all by default): the list price times the multiplier,
        but never under `floor` cents, the least price at which the request is worth taking. Remembers the
        quote for its outcome."""
        if self.level <= 3:  # every quote wins the first option at its list price
            first = request["options"][0]
            return {first["kind"]: first["listPriceCents"]}
        m = self.multiplier(request, now)
        options = [o for o in request["options"] if kinds is None or o["kind"] in kinds]
        prices = {o["kind"]: max(1, int(o["listPriceCents"] * m + 0.5)) for o in options}
        self.sent[request["id"]] = Sent(request["dealerId"], bool(prices) and all(c < floor for c in prices.values()))
        return {kind: max(cents, floor) for kind, cents in prices.items()}

    def outcome(self, request_id: str, won: bool) -> None:
        """A win moves the dealer's multiplier back towards the maximum, a loss lowers it. Nothing else lowers it,
        so the price stays just under what the dealer accepts. The world's multiplier learns the same way."""
        sent = self.sent.pop(request_id, None)
        if sent is None or not won and sent.floored:
            return
        self.dealer[sent.dealer] = self.ratchet(self.dealer.get(sent.dealer, self.world), won)
        self.world = self.ratchet(self.world, won)

    def ratchet(self, m: float, won: bool) -> float:
        if won:
            return m + self.params.recover * (self.top - m)
        return max(min(self.params.floor, self.top), m * (1 - self.params.cut))

    def new_day(self, now: int) -> None:
        """On each new day, every multiplier moves `daily_recover` of the way back to the maximum."""
        day = now // DAY
        if day <= self.day:
            return
        keep = (1 - self.params.daily_recover) ** (day - self.day)
        self.world = self.top - (self.top - self.world) * keep
        self.dealer = {dealer: self.top - (self.top - m) * keep for dealer, m in self.dealer.items()}
        self.day = day

    def trust_of(self, dealer: str, now: int) -> int:
        """The orders that the dealer counts as on time now, up to 25: each adds 1% to the prices it accepts."""
        self.settle(now)
        return self.trust.get(dealer, 0)

    def summary(self) -> str:
        """The dealers' multipliers at the end of the week."""
        if self.level <= 3 or not self.dealer:
            return ""
        values = sorted(self.dealer.values())
        return (
            f"Ratchet: {len(values)} dealers, multipliers {values[0]:.2f} to {values[-1]:.2f}, "
            f"median {values[len(values) // 2]:.2f}, world {self.world:.2f}"
        )
