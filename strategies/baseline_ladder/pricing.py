"""The baseline's quotes on a ladder: one shared multiple of the list price, lowered when we lose a quote and raised
when we win one, never above its ceiling. On top of it, a risk price: three times the list price for a request with no
driver left for it today in its pickup city or a neighbouring one, and a surcharge for a same-day delivery. No quote
falls to the request's typical fee.

No network: `price` takes a request and the option kinds that admission picked, as `BaselinePricing.price` does, and
`observe` takes the `price_request`, `order_won` and `order_lost` events. README.md next to this file has the rule.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from spread.types import DeskEvent, DriverProfile, PriceRequest, WorldMap

from strategies.notes import read_note
from strategies.strategy import Strategy

DAY = 24 * 60


@dataclass(frozen=True)
class Params:
    """The knobs of the quotes. The ladder's are in multiples of the list price: 0.01 is one point."""

    ceiling: float = 2  # the highest multiple of the list price the ladder quotes
    start: float = 1.5  # where the ladder starts the week
    floor: float = 1.0  # the lowest multiple the ladder falls to: never under the list price
    win_step: float = 0.075  # the multiple rises by this much after a win: 1.46 -> 1.47
    loss_step: float = 0.03  # and falls by this much after a loss: 1.49 -> 1.46
    over_fee_cents: int = 1  # the least quote is the request's typical fee plus this
    no_driver_multiple: float = 3.0  # the multiple for a request with no driver left for it, near or in its city
    neighbour_minutes: int = 90  # a city is a neighbour when its drivers reach the pickup in this many road minutes
    refill_daily: bool = True  # each city has all its drivers again at midnight; False counts over the whole week
    same_day: float = 0.2  # added to the multiple of a same-day delivery, on top of `ceiling`
    scarce: float = 0.5  # added to the multiple of a request with few drivers left for it, on top of `ceiling`
    scarce_drivers: int = 3  # few is this many drivers left in the city the request's driver comes from


class BaselineLadderPricing(Strategy[Params]):
    """The list price of each option that admission picked, times the ladder's multiple, with the risk price.

    The multiple is shared by every request of the week. It starts at `start`, falls by `loss_step` after each
    quote we lost, never under `floor`, and rises by `win_step` after each one we won, up to `ceiling`.

    Each city has an audience: the drivers who live there. Every request takes one driver off for the day, whether
    we win the quote or not: from its pickup city, or, when that has none left, from the nearest neighbouring city
    that has. A request that finds no driver left in any of them is quoted at `no_driver_multiple` instead, and its
    outcome leaves the ladder where it is.
    """

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())
        self.multiple = min(self.params.ceiling, max(self.params.floor, self.params.start))
        self.won = 0  # the ladder's quotes we won
        self.lost = 0  # and lost
        self.drivers = Counter(d["homePlaceId"] for d in roster)  # city -> the drivers who live there
        # (experienced, manual licence) -> city -> the drivers who live there and fit both
        self.audience: dict[tuple[bool, bool], Counter[str]] = {
            (experienced, manual): Counter(
                d["homePlaceId"]
                for d in roster
                if (not experienced or (d["rating"] >= 4.8 and d["completedGigs"] >= 50))
                and (not manual or d["licence"] == "manual")
            )
            for experienced in (False, True)
            for manual in (False, True)
        }
        self.names = {place["id"]: place["name"] for place in world_map.get("places", [])}
        # day -> (experienced, manual licence) -> the drivers left in each city who fit both
        self.left: dict[int, dict[tuple[bool, bool], Counter[str]]] = {}
        self.near: dict[str, list[str]] = {}  # pickup city -> itself and its neighbours, nearest first
        self.off_ladder: set[str] = set()  # the requests quoted at `no_driver_multiple`
        self.won_off_ladder = 0  # and those of them we won
        self.scarce: set[str] = set()  # the requests that left `scarce_drivers` or fewer drivers in their city

    def observe(self, event: DeskEvent) -> None:
        """Counts each request against its pickup city, and moves the ladder: up after `order_won`, down after
        `order_lost`. The baseline quotes every request, so every outcome is one of our quotes; a rejoined desk
        rebuilds the counts and the multiple from the week's history."""
        if event["kind"] == "price_request":
            request = event["request"]
            left = self.take(request)  # the request takes a driver off, won or not
            if left is None:
                self.off_ladder.add(request["id"])
            elif left <= self.params.scarce_drivers:
                self.scarce.add(request["id"])
        elif event["kind"] == "order_won" and event["order"]["id"] in self.off_ladder:
            self.won_off_ladder += 1
            order = event["order"]
            city = order["legs"][0]["pickup"]["placeId"]
            print(
                f"Won at {self.params.no_driver_multiple:g} x list: order {order['id']} from "
                f"{self.names.get(city, city)}, EUR {order['priceCents'] / 100:,.2f}",
                flush=True,
            )
        elif event["kind"] == "order_won":
            self.won += 1
            self.multiple = round(min(self.params.ceiling, self.multiple + self.params.win_step), 6)
        elif event["kind"] == "order_lost" and event["requestId"] not in self.off_ladder:
            self.lost += 1
            self.multiple = round(max(self.params.floor, self.multiple - self.params.loss_step), 6)

    def cities(self, pickup: str) -> list[str]:
        """The pickup city, then its neighbours, nearest first: the cities with drivers who reach the pickup in
        `neighbour_minutes` by road."""
        if pickup not in self.near:
            reach = [(self.minutes.get((city, pickup), 10**6), city) for city in self.drivers if city != pickup]
            self.near[pickup] = [pickup] + [city for far, city in sorted(reach) if far <= self.params.neighbour_minutes]
        return self.near[pickup]

    def take(self, request: PriceRequest) -> int | None:
        """Takes a driver for the request off the day's audience: from its pickup city, or from the nearest
        neighbour that has one left, and returns how many drivers who may take the gig that city has left. None
        when no city has one. Who may take the gig is as the baseline posts it: an experienced driver (rating at
        least 4.8 and at least 50 completed gigs) for a premium car, one with a manual licence when the dealer's
        note says the car is manual, and anyone otherwise. The driver taken off counts against every group they
        belong to, so the city's groups never hold more drivers than it has."""
        day = request["arrivedAt"] // DAY if self.params.refill_daily else 0
        if day not in self.left:
            self.left[day] = {group: Counter(count) for group, count in self.audience.items()}
        left = self.left[day]
        premium = any(leg["car"]["premium"] for leg in request["legs"])
        note = request["note"]
        manual = read_note(note and note["text"], request["arrivedAt"]).manual
        needed = (premium, manual)
        for city in self.cities(request["legs"][0]["pickup"]["placeId"]):
            fit = left[needed][city]
            if fit > 0:
                # the driver taken is in a group when every driver who fits the request is: when the group's
                # members among those who fit are as many as those who fit. A looser group always is.
                taken = [
                    group for group in left if left[(group[0] or needed[0], group[1] or needed[1])][city] >= fit
                ]
                for group in taken:
                    left[group][city] -= 1
                return left[needed][city]
        return None

    def price(self, request: PriceRequest, kinds: list[str]) -> dict[str, int]:
        """The price in cents of each option kind that admission picked: the ladder's multiple of the list price,
        plus `scarce` when `observe` found few drivers left for it and `same_day` for a same-day delivery, which
        pass `ceiling`; or `no_driver_multiple` when no driver was left at all. At least the typical fee plus
        `over_fee_cents`. The surcharges are this quote's only: the ladder stays where it is. The price is rounded
        down, so that the ladder alone never passes `ceiling` times the list price."""
        options = {option["kind"]: option for option in request["options"]}
        least = request["referenceFeeCents"] + self.params.over_fee_cents
        prices = {}
        for kind in kinds:
            if request["id"] in self.off_ladder:
                factor = self.params.no_driver_multiple
            else:
                factor = self.multiple
                if request["id"] in self.scarce:
                    factor += self.params.scarce
                if kind == "same_day":
                    factor += self.params.same_day
            prices[kind] = max(least, int(options[kind]["listPriceCents"] * factor + 1e-6))
        return prices

    def summary(self) -> str:
        """One line about the ladder at the end of the week."""
        return (
            f"Ladder: {self.multiple:.2f} x list at the end, {self.won} quotes won, {self.lost} lost, "
            f"{len(self.off_ladder)} requests with no driver left quoted at {self.params.no_driver_multiple:g} x, "
            f"{self.won_off_ladder} of them won"
        )
