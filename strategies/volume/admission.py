"""Volume admission: the all-in admission of strategies/all_in, with two changes that take more orders where they
leave margin. Issue #304.

A strategy (strategies/strategy.py) built on `AllInAdmission`, unchanged there:

- the option menu: an accepted request gets every option that leaves time for the drive and pays its own driver
  cost, not only the one admission picks. The dealer takes the option with the most headroom, so each option is one
  more chance to win at the same price;
- a remote pickup's driver cost rises half as much as all_in assumes (`scarce_pickup` 0.4, not 0.8): the saved weeks
  paid 0.68 of the expected cost there, and the cost was flat across driver supply at 0.4.

README.md next to this file has the numbers behind both.
"""

from __future__ import annotations

from dataclasses import dataclass

from spread.types import DeskEvent, DriverProfile, WorldMap

from strategies.admission import Held, Verdict
from strategies.all_in import AllInAdmission, AllInParams
from strategies.lane_fee import LaneFee


@dataclass(frozen=True)
class Params(AllInParams):
    """The variables of the all-in admission, with a lower remote-pickup cost and the option menu."""

    # A remote pickup's cost rises by this share where no driver lives near it; all_in has 0.8 (strategies/lead_cost).
    scarce_pickup: float = 0.4
    menu: bool = True  # quote every option that pays its own driver cost, not only admission's pick


class VolumeAdmission(AllInAdmission):
    """The all-in admission with the option menu and a lower remote-pickup cost."""

    params: Params

    def __init__(
        self,
        roster: list[DriverProfile],
        world_map: WorldMap,
        level: int = 8,
        params: Params | None = None,
        lane: LaneFee | None = None,
    ) -> None:
        super().__init__(roster, world_map, level, params or Params(), lane)
        self.costs: dict[str, dict[str, int]] = {}  # request id -> the expected driver cost of each option taken
        self.picks: dict[str, str] = {}  # request id -> admission's own pick, while the dealer decides
        self.menu_counts = {"quotes": 0, "added options": 0, "won": 0, "won an added option": 0}

    def verdict(self, request: dict, held: list[Held], now: int) -> Verdict:
        """The all-in verdict. An accepted request then gets the menu: every other option with the slack that
        admission asks for, and the margin that it asks for at that option's own driver cost."""
        verdict = super().verdict(request, held, now)
        if not verdict.accept:
            return verdict
        costs = {verdict.options[0]: int(verdict.expected_cost)}
        if self.params.menu and self.level >= 4 and len(request["options"]) > 1:
            costs.update(self.menu(request, held, now, set(costs)))
        self.costs[request["id"]] = costs
        self.picks[request["id"]] = verdict.options[0]
        if len(costs) > 1:
            self.menu_counts["quotes"] += 1
            self.menu_counts["added options"] += len(costs) - 1
        return verdict._replace(options=list(costs))

    def menu(self, request: dict, held: list[Held], now: int, taken: set[str]) -> dict[str, int]:
        """The other options that pass admission's own tests, each with its own driver cost: the slack of
        strategies/admission (with the flu guard's), and the minimum margin at the highest price we would quote."""
        p = self.params
        squeeze = self.tightening(self.on_time_share(held, now))
        min_slack = p.min_slack / max(squeeze, 0.5)
        guarded = self.guarded_quotes  # the base verdict has counted the options that the flu guard keeps off
        added: dict[str, int] = {}
        for option in request["options"]:
            if option["kind"] in taken or self.option_slack(request, option, now) < min_slack:
                continue
            cost = self.lead_cost(request, option, held, now)
            price = option["listPriceCents"] * p.price_factor
            if price > 0 and (price - cost) / price >= p.min_margin:
                added[option["kind"]] = cost
        self.guarded_quotes = guarded
        return added

    def observe(self, event: DeskEvent) -> None:
        """The base's learning, plus which option the dealer took when the quote had the menu."""
        super().observe(event)
        kind = event["kind"]
        if kind == "order_won":
            order = event["order"]
            pick = self.picks.pop(order["id"], None)
            if pick is not None:
                self.menu_counts["won"] += 1
                self.menu_counts["won an added option"] += order["option"] != pick
        elif kind == "order_lost":
            self.picks.pop(event["requestId"], None)

    def release(self, request_id: str) -> None:
        super().release(request_id)
        self.costs.pop(request_id, None)
        self.picks.pop(request_id, None)

    def summary(self) -> str:
        c = self.menu_counts
        return (
            f"{super().summary()}\nOption menu: {c['quotes']} quotes with {c['added options']} added options; "
            f"of {c['won']} orders won, {c['won an added option']} took an added option"
        )
