"""Admission for the ratchet system: the admission control of `strategies/admission` (capacity, time, the option
to quote), with a cost floor instead of its profit check, and small losses that buy dealer trust at level 8."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field, replace

from strategies.admission import Admission, Held, Params, Verdict


@dataclass(frozen=True)
class TrustParams(Params):
    """The trust allowance, next to the thresholds of `strategies/admission`. `min_margin` is the margin that the
    floor asks of a request otherwise."""

    # Level 8: each order delivered on time raises the prices its dealer accepts from us by 1%, up to
    # `trust_cap` orders. While a dealer counts fewer, its floor allows a loss of up to `trust_loss` of the price,
    # once it has sent us `trust_requests` requests: a dealer that sends few has little later business to repay it.
    trust_loss: float = 0.10
    trust_requests: int = 5
    trust_cap: int = 25


@dataclass
class TrustAdmission(Admission):
    """Decides which requests to take and the least price worth quoting for each."""

    params: TrustParams = field(default_factory=TrustParams)

    def __post_init__(self) -> None:
        super().__post_init__()
        self.requests_of: dict[str, set[str]] = defaultdict(set)  # dealer -> the requests it has sent us

    def assess(
        self, request: dict, held: Iterable[Held] = (), now: int | None = None, price_factor: float = 1.0
    ) -> Verdict:
        """The verdict of `strategies/admission` on capacity, time and the option to quote, at our price, but
        without its profit check: a request whose price is under its floor is quoted at the floor instead."""
        self.requests_of[request["dealerId"]].add(request["id"])
        params = self.params
        self.params = replace(params, price_factor=price_factor, min_margin=-math.inf)
        try:
            return super().assess(request, held, now)
        finally:
            self.params = params

    def min_margin(self, request: dict, trust: int) -> float:
        """The least margin a request must leave: `min_margin`, or at level 8 a loss of up to `trust_loss` of the
        price while the dealer's trust can still grow and it sends enough requests to repay it."""
        p = self.params
        dealer_requests = len(self.requests_of[request["dealerId"]])
        if self.level >= 8 and trust < p.trust_cap and dealer_requests >= p.trust_requests:
            return min(p.min_margin, -p.trust_loss)
        return p.min_margin

    def floor(self, request: dict, verdict: Verdict, trust: int, fee: float) -> int:
        """The least price, in cents, at which the request's cars are worth moving: the expected driver cost,
        never under the opening fee that we would post for them (`fee`), over 1 − the margin we ask of it.
        Below it we would lose more than we accept, but the floor may still win where the competitor is dearer,
        and a quote that loses costs nothing."""
        cost = max(verdict.expected_cost, fee)
        return int(cost / (1 - min(0.9, self.min_margin(request, trust))) + 0.5)
