"""Admission for the ratchet system: the admission control of strategies/admission, unchanged there (capacity, time
and the option to quote), with a cost floor instead of its profit check, and small losses that buy dealer trust at
level 8. README.md next to this file explains it."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, replace

from spread.types import DeskEvent, DriverProfile, WorldMap

from strategies.admission import Admission, Held, Verdict
from strategies.admission.admission import Params as AdmissionParams


@dataclass(frozen=True)
class Params(AdmissionParams):
    """The admission thresholds, plus the trust allowance. `min_margin` is the margin that the floor asks of a
    request otherwise."""

    # Level 8: each order delivered on time raises the prices its dealer accepts from us by 1%, up to `trust_cap`
    # orders. While a dealer counts fewer, its floor allows a loss of up to `trust_loss` of the price, once it has
    # sent us `trust_requests` requests: a dealer that sends few has little later business to repay it.
    trust_loss: float = 0.10
    trust_requests: int = 5
    trust_cap: int = 25


class TrustAdmission(Admission):
    """Decides which requests to take, and the least price worth quoting for each."""

    params: Params

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())
        self.requests_of: dict[str, set[str]] = defaultdict(set)  # dealer -> the requests it has sent us

    def observe(self, event: DeskEvent) -> None:
        """The base's learning, plus each dealer's requests, which the trust allowance counts."""
        super().observe(event)
        if event["kind"] == "price_request":
            self.requests_of[event["request"]["dealerId"]].add(event["request"]["id"])

    def assess(
        self, request: dict, held: Iterable[Held] = (), now: int | None = None, price_factor: float = 1.0
    ) -> Verdict:
        """The base's verdict on capacity, time and the option to quote, at our price (`price_factor` times the
        list price), but without its profit check: a request whose price is under its floor is quoted at the
        floor instead."""
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
