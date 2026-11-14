"""Ladder pricing per city: the price of a quote as a multiple of the list price, with one ladder position for each
pickup city instead of one shared position for the whole week.

It builds on the ladder of strategies/price_ladder (#126), unchanged there: the same clamped range, the same unequal
steps, the same price war, outage and dealer trust. The one change is the state. `log_ms` holds a position per pickup
place and each outcome moves only its own city's ladder; a parallel world ladder (the parent's `log_m`) still moves on
every outcome, so the war and outage detectors stay the parent's. No network: `price` takes a request and returns a
price for each option, and `observe` takes the `order_won`, `order_lost` and `ledger` events. README.md next to this
file has the model and how to run it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from spread.types import DriverProfile, WorldMap

from strategies.price_ladder.pricing import LadderPricing
from strategies.price_ladder.pricing import Params as LadderParams
from strategies.pricing.model import DAY, Outcome, PricingModel, Quote, in_hours


@dataclass(frozen=True)
class Params(LadderParams):
    """The price ladder's knobs, unchanged: the ladder is per city, not one shared position."""


@dataclass
class CityQuote(Quote):
    """A quote, with the pickup city whose ladder it moved."""

    key: str = ""  # the pickup place id: the city's own ladder


class CityLadderPricing(LadderPricing):
    """The price ladder with one position per pickup city.

    Each city has its own position on the list price, inside [`floor`, `ceiling`] and starting at the top of its range.
    A win in a city raises that city's position and a loss lowers it, by the parent's steps; the other cities are not
    moved. A city we have not quoted yet starts at `start`. The price war, the outage and dealer trust are the
    parent's: the war is detected on the parallel world ladder (`log_m`, moved on every outcome, exactly as the shared
    price ladder moves it), and the outage boost and the dealer trust multiply a city's price as before. The war's
    18:00 restore applies to the world ladder only, so the cities keep the day's net move and climb back with wins.
    """

    params: Params

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: Params | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())
        self.log_ms: dict[str, float] = {}  # pickup city -> the city's ladder position, in logs

    def key(self, request: dict) -> str:
        """The city whose ladder a request moves: its first pickup place."""
        return request["legs"][0]["pickup"]["placeId"]

    def position(self, key: str) -> float:
        """A city's ladder position in logs, `start` before its first outcome."""
        return self.log_ms.get(key, math.log(self.params.start))

    def multiplier(self, request: dict, now: int) -> float:
        """The multiplier on the list price for this request now, from its city's ladder, the outage and the trust."""
        if self.level <= 3:
            return 1.0
        self.end_war(now)
        m = min(self.params.ceiling, max(self.params.floor, math.exp(self.position(self.key(request)))))
        if self.in_outage(request, now):
            m *= math.exp(self.outage_log)
        if self.level >= 8 and self.params.trust:
            self.settle(now)
            m *= 1 + self.trust.get(request["dealerId"], 0) / 100
        return m

    def price(self, request: dict, now: int) -> dict[str, int]:
        """A price in cents for each option, and a count of the quotes at either end of the city's range."""
        prices = PricingModel.price(self, request, now)
        if self.level > 3:
            self.quoted += 1
            m = math.exp(self.position(self.key(request)))
            if m <= self.params.floor * 1.001:
                self.at_floor += 1
            elif m >= self.params.ceiling * 0.999:
                self.at_ceiling += 1
            quote = self.quotes.get(request["id"])
            if quote is not None:  # remember the city, so its outcome moves the right ladder
                self.quotes[request["id"]] = CityQuote(
                    quote.at, quote.keys, quote.pickup, quote.outage, self.key(request)
                )
        return prices

    def apply(self, updates: list[tuple[str, float]], sign: float = 1.0) -> None:
        """Moves each named estimate: the world ladder for `""` (the war's sensor), a city's ladder otherwise."""
        lo, hi = math.log(self.params.floor), math.log(self.params.ceiling)
        for key, delta in updates:
            if key == "":
                self.log_m = min(hi, max(lo, self.log_m + sign * delta))
            else:
                self.log_ms[key] = min(hi, max(lo, self.position(key) + sign * delta))

    def outcome(self, request_id: str, won: bool) -> None:
        """The city's ladder step after an outcome: down on a loss, up on a win, in logs so that the price moves by a
        share of itself. The world ladder moves too, so the war and outage detectors stay the parent's; only the city's
        ladder prices. No offsets: one position per city, shared across the week."""
        quote = self.quotes.pop(request_id, None)
        if quote is None:
            return
        if won:
            self.won += 1
        step = math.log(1 + self.params.win_step) if won else math.log(1 - self.params.loss_step)
        key = quote.key
        day = quote.at // DAY
        if quote.outage:  # the outage boost keeps learning from the error, as in the adaptive model
            error = (1.0 if won else 0.0) - self.params.target_win
            self.outage_log = min(math.log(1.5), max(0.0, self.outage_log + 2 * self.params.key_step * error))
            return
        if day == self.war_day and in_hours(quote.at):
            if not self.params.war_decline and not self.war_over:  # follow the war, in the city and the world
                self.apply([("", step), (key, step)])
            return
        if in_hours(quote.at):
            self.day_open.setdefault(day, self.log_m)
        updates = [("", step), (key, step)]
        self.apply(updates)
        self.seen += 1
        if not in_hours(quote.at):
            return
        outcomes = self.today.setdefault(day, [])
        outcomes.append(Outcome(won, quote.pickup, updates))
        # One outage and one price war a week, never on the same day.
        if self.level >= 6 and self.outage is None and day != self.war_day:
            self.detect_outage(day, outcomes)
        if self.level >= 8 and day > 0 and self.war_day is None and (self.outage is None or self.outage[0] != day):
            self.detect_war(day, outcomes)

    def summary(self) -> str:
        """One line about the cities' ladders at the end of the week."""
        won = f"{self.won / self.quoted:.0%}" if self.quoted else "-"
        if not self.log_ms:
            return f"City ladder: {self.quoted} quotes, {won} won, no city moved"
        values = [math.exp(v) for v in self.log_ms.values()]
        floor = sum(1 for v in values if v <= self.params.floor * 1.001)
        ceiling = sum(1 for v in values if v >= self.params.ceiling * 0.999)
        return (
            f"City ladder: {len(values)} cities, {self.quoted} quotes, {won} won, "
            f"{min(values):.2f} to {max(values):.2f} x list, {floor} at the floor, {ceiling} at the top"
        )
