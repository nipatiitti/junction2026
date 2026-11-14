"""The menu of delivery options to quote: the one admission picks, and every slower one the request offers.

A strategy (strategies/strategy.py) of its own, with no learning. Admission (strategies/admission) quotes one option:
the earliest that leaves comfortable time for the drive, which is the dearest. A dealer who would rather wait than pay
for speed then has nothing cheaper from us, and takes the competitor's price. Here the slower options go on the quote
too, each at its own list price, which is lower for a later deadline (`within_3_days` about 0.93 x `next_day`, and
`next_day` about 0.93 x `same_day` on the saved weeks), times the learned multiplier, and `slow_discount` less for each
step slower. A slower option leaves more time, so it is never harder to deliver on time than the option admission
picked. README.md next to this file has the numbers.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from spread.types import DeskEvent, DriverProfile, WorldMap

from strategies.strategy import Strategy

KINDS = ("same_day", "next_day", "within_3_days")  # from the fastest to the slowest


@dataclass(frozen=True)
class Params:
    """How the slower options are priced."""

    slow_discount: float = 0.0  # each option slower than admission's pick costs this share less, after its list price
    most: int = 3  # quote at most this many options


class OptionMenu(Strategy[Params]):
    """Picks the options to quote, and counts which ones the dealers took."""

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())
        self.offered: dict[str, str] = {}  # request id -> the option admission picked
        self.counts: Counter[str] = Counter()

    def observe(self, event: DeskEvent) -> None:
        """Counts whether a won order took admission's pick or a slower option."""
        if event["kind"] == "order_lost":
            self.offered.pop(event["requestId"], None)
        if event["kind"] != "order_won":
            return
        picked = self.offered.pop(event["order"]["id"], None)
        if picked is not None:
            self.counts["won at the pick" if event["order"]["option"] == picked else "won slower"] += 1

    def kinds(self, request: dict, picked: list[str]) -> list[str]:
        """The pick and every option of the request with a later deadline, at most `most` of them. Up to level 3
        every quote wins the first option, so only the pick."""
        if self.level <= 3 or not picked:
            return picked
        deadline = {o["kind"]: o["deadline"] for o in request["options"]}
        first = min(deadline[k] for k in picked)
        slower = [o["kind"] for o in request["options"] if o["deadline"] > first and o["kind"] not in picked]
        menu = (list(picked) + sorted(slower, key=lambda k: deadline[k]))[: self.params.most]
        self.offered[request["id"]] = picked[0]
        self.counts["quoted"] += 1
        self.counts["with slower options"] += len(menu) > len(picked)
        return menu

    def discount(self, request: dict, picked: list[str], prices: dict[str, int], least: float) -> dict[str, int]:
        """The slower options' prices, `slow_discount` less for each step slower than the pick, never under `least`."""
        if not self.params.slow_discount or not picked:
            return prices
        order = sorted(prices, key=lambda k: KINDS.index(k) if k in KINDS else len(KINDS))
        base = order.index(picked[0]) if picked[0] in order else 0
        out = dict(prices)
        for rank, kind in enumerate(order):
            if rank > base:
                cut = prices[kind] * (1 - self.params.slow_discount) ** (rank - base)
                out[kind] = max(int(least + 0.5), int(cut + 0.5))
        return out

    def summary(self) -> str:
        """How often a quote carried slower options, and which option the won orders took."""
        c = self.counts
        if not c["quoted"]:
            return ""
        return (
            f"Option menu: {c['quoted']} quotes, {c['with slower options']} with slower options; won "
            f"{c['won at the pick']} at admission's pick and {c['won slower']} at a slower option"
        )
