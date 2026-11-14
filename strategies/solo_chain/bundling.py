"""E2 — short cheap-solo window, then withdraw an unbooked solo and reconsider it as a chain.

If an order has long pickup slack, this pool gives its normal cheap solo fee a chance first. After
`Params.fallback_wait` minutes a still-unbooked order gets one more composition attempt with whatever partners are
available then. There is no wait for a compatible chain if one is already there immediately.
"""

from __future__ import annotations

from dataclasses import dataclass

from strategies.bundle_experiments.base import Fallback, FallbackBundler
from strategies.bundling import Params as BundlingParams


@dataclass(frozen=True)
class Params(BundlingParams):
    fallback_wait: int = 45  # minutes of slack-rich solo exposure before one later chain attempt


class SoloFirstBundler(FallbackBundler):
    params: Params

    def __init__(self, roster, world_map, level: int = 8, params: Params | None = None):
        super().__init__(roster, world_map, level, params or Params())

    def hold(self, order_id: str, batch: str | None, last_pickup_at: int, now: int) -> None:
        super().hold(order_id, batch, last_pickup_at, now)
        # Non-batch orders that can really use a later chain start here, not at post: adding the fallback wait to
        # the first deadline avoids losing a later night after a dusk win. Batch orders keep base hold/quiet logic.
        if batch is None and last_pickup_at - now >= self.params.safe:
            self.fallbacks[order_id] = Fallback(order_id, now + self.params.fallback_wait, batch, last_pickup_at)

    def fallbacks_due(self, now: int) -> list[Fallback]:
        expired = [f for f in self.fallbacks.values() if f.at <= now]
        for f in expired:
            self.fallbacks.pop(f.order_id, None)
        return [f for f in expired if f.attempts == 0]
