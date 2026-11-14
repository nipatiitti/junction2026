"""Shared wiring for the three chain experiments. See strategies/return_legs, solo_chain and informed_chain."""

from __future__ import annotations

from dataclasses import dataclass

from strategies.all_in import dispatch as all_in
from strategies.bundling import Bundler


@dataclass
class Fallback:
    """One earlier chance at a compatible chain before the order goes out solo again, if it still needs one."""

    order_id: str
    at: int
    batch: str | None
    last_pickup_at: int
    attempts: int = 0


class FallbackBundler(Bundler):
    """A bundler that can also offer an already-solo order one later chance at a chain.

    Subclasses implement `fallbacks_due`: when one of their fallback timers has arrived. If the solo gig's driver
    is still available, `SoloChainDesk` then asks the base desk to withdraw that gig and puts the order in the bundle
    pool again. This never withdraws a gig a driver already accepted.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fallbacks: dict[str, Fallback] = {}

    def forget(self, order_id: str) -> None:
        super().forget(order_id)
        self.fallbacks.pop(order_id, None)

    def fallbacks_due(self, now: int) -> list[Fallback]:
        raise NotImplementedError


class ExperimentDesk(all_in.Desk):
    """AllInDesk unchanged except its bundler, and one small hook for a later chain opportunity."""

    def retry_chains(self, now: int) -> None:
        """Return early-solo orders to the pool once a bundler says a partner may now be worth trying for.

        Call this immediately before posting due bundles, as dispatch does. Desks with only a Bundler that has no
        fallback pool override this with a no-op."""
        raise NotImplementedError

    def post_due(self) -> None:
        self.retry_chains(self.now)
        super().post_due()


class SoloChainDesk(ExperimentDesk):
    """A deadline-aware fallback for an order whose first solo attempt found no driver."""

    def retry_chains(self, now: int) -> None:
        assert isinstance(self.bundler, FallbackBundler)
        for fallback in self.bundler.fallbacks_due(now):
            order_id = fallback.order_id
            order = self.orders.get(order_id)
            # A booked or fully-delivered car must not be taken away. An undeliverable/ended order must not re-pool.
            if order is None or self.unit(order_id) is None or any(g in self.booked for g in self.gigs_of(order_id)):
                continue
            if not self.withdraw(order_id):  # the base returns False only if a driver already has the gig
                continue
            self.bundler.counts["solo fallbacks"] += 1
            self.bundler.hold(order_id, fallback.batch, fallback.last_pickup_at, now)
            fresh = self.bundler.fallbacks.get(order_id)
            if fresh is not None:
                fresh.attempts += 1


class InstantChainDesk(ExperimentDesk):
    """Only immediate chains: there are no low-solo fallback timers to roll over to later gig composition."""

    def retry_chains(self, now: int) -> None:
        pass
