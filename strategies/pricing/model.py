"""Adaptive quoting: the price of a quote that we want to send, learned from our own wins and losses.

No network: `price` takes a request and returns a price for each option, and `observe` takes the
`order_won`, `order_lost` and `ledger` events. README.md next to this file explains the model.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

HOUR, DAY = 60, 24 * 60
WORK_FROM, WORK_TO = 8 * HOUR, 18 * HOUR  # the price war and the outage last from 08:00 to 18:00
REGION_KM = 80  # an outage region is a town and the places within 80 km of it
TRUST_CAP = 25  # a dealer counts at most 25 orders on time, each worth 1% at level 8

# The multiplier on the list price that a world starts from, by level: about the middle of the
# competitor's range. Up to level 3 every quote wins at the list price, so the price stays there.
START = {4: 1.0, 5: 1.0, 6: 1.0, 7: 1.25, 8: 1.35}


@dataclass
class Params:
    """The knobs of the model. The defaults are the ones that did best on the bench (README.md)."""

    target_win: float = 0.5  # the share of quotes the multiplier aims to win
    step: float = 0.03  # log step of the world's multiplier per outcome
    key_step: float = 0.015  # log step of each pickup, delivery and dealer offset per outcome
    key_limit: float = 0.25  # an offset stays within ±25%
    floor: float = 0.9  # the multiplier never falls below 0.9 times the list price
    ceiling: float = 2.0
    # The price war: the world's multiplier falls `war_drop` (in logs) below its level at the day's
    # first outcome, with losses on at least `war_places` pickup places. Until 18:00 the multiplier
    # follows the war down, or we decline with `war_decline`; then it returns to the day's level.
    war_drop: float = 0.15
    war_places: int = 6
    war_decline: bool = False
    # The outage: a region whose win share today is above the rest of the day's, by `outage_gap` and
    # by `outage_z` in a two-proportion test, with at least `outage_min` outcomes on each side. Its
    # requests then start at `outage_boost` times the price, and that boost learns until 18:00.
    outage_min: int = 12
    outage_z: float = 2.5
    outage_gap: float = 0.15
    outage_boost: float = 1.2
    trust: bool = True  # level 8: add 1% per order the dealer counts
    decline_factor: int = 10  # a declined option is quoted at ten times its list price


@dataclass
class Quote:
    """What we sent for one request, kept until its outcome arrives."""

    at: int  # when the request arrived
    keys: tuple[str, ...]
    pickup: str
    outage: bool  # priced with the outage boost


@dataclass
class Outcome:
    won: bool
    pickup: str
    updates: list[tuple[str, float]] = field(default_factory=list)  # what the outcome added to the estimate


class PricingModel:
    """One world's estimate of the price that wins, with the price war, the outage and dealer trust."""

    def __init__(self, level: int, places: dict[str, tuple[float, float]] | None = None, params: Params | None = None):
        self.level, self.p = level, params or Params()
        self.log_m = math.log(START.get(level, 1.0))  # the world's multiplier on the list price, in logs
        self.offset: dict[str, float] = {}  # "pickup:<place>", "delivery:<place>", "dealer:<id>" -> log offset
        self.quotes: dict[str, Quote] = {}  # request id -> the quote waiting for its outcome
        self.today: dict[int, list[Outcome]] = {}  # day -> the outcomes of usual quotes in 08:00-18:00
        self.day_open: dict[int, float] = {}  # day -> the world's multiplier at the day's first outcome
        self.war_day: int | None = None
        self.war_over = False  # the multiplier is back at the war day's opening level
        self.outage: tuple[int, frozenset[str]] | None = None  # (day, the pickup places of the region)
        self.outage_log = 0.0  # the outage boost, in logs, learned from the boosted quotes
        self.near = neighbours(places or {})
        # Dealer trust, counted from the ledger.
        self.trust: dict[str, int] = {}
        self.dealer_of: dict[str, str] = {}  # order id -> dealer
        self.unsettled: dict[str, int] = {}  # order id -> minute of its revenue line, not yet known on time
        self.settled: set[str] = set()

    # --- prices -------------------------------------------------------------------------------

    def multiplier(self, request: dict, now: int) -> float:
        """The multiplier on the list price for this request now."""
        if self.level <= 3:
            return 1.0
        self.end_war(now)
        keys = request_keys(request)
        log_m = self.log_m + sum(self.offset.get(k, 0.0) for k in keys)
        m = min(self.p.ceiling, max(self.p.floor, math.exp(log_m)))
        if self.in_outage(request, now):
            m *= math.exp(self.outage_log)
        if self.level >= 8 and self.p.trust:
            self.settle(now)
            m *= 1 + self.trust.get(request["dealerId"], 0) / 100
        return m

    def price(self, request: dict, now: int) -> dict[str, int]:
        """A price in cents for each of the request's options, and remembers the quote for its outcome."""
        if self.level <= 3:  # every quote wins the first option at its list price
            first = request["options"][0]
            return {first["kind"]: first["listPriceCents"]}
        m = self.multiplier(request, now)
        factor = self.p.decline_factor if self.in_war(now) and self.p.war_decline else m
        self.quotes[request["id"]] = Quote(
            at=request["arrivedAt"],
            keys=request_keys(request),
            pickup=request["legs"][0]["pickup"]["placeId"],
            outage=self.in_outage(request, now),
        )
        return {o["kind"]: max(1, int(o["listPriceCents"] * factor + 0.5)) for o in request["options"]}

    def in_war(self, now: int) -> bool:
        return self.war_day == now // DAY and in_hours(now)

    def in_outage(self, request: dict, now: int) -> bool:
        if self.outage is None or self.outage[0] != now // DAY or not in_hours(now):
            return False
        return request["legs"][0]["pickup"]["placeId"] in self.outage[1]

    def end_war(self, now: int) -> None:
        """At 18:00 on the war day the competitor's prices are back, and so is our multiplier."""
        if self.war_day is not None and not self.war_over and now >= self.war_day * DAY + WORK_TO:
            self.log_m, self.war_over = self.day_open[self.war_day], True

    # --- learning -----------------------------------------------------------------------------

    def observe(self, event: dict) -> None:
        """Feeds the model an event: `order_won`, `order_lost` and `ledger` matter, the rest is ignored."""
        kind = event["kind"]
        if kind == "order_won":
            self.dealer_of[event["order"]["id"]] = event["order"]["dealerId"]
            self.outcome(event["order"]["id"], True)
        elif kind == "order_lost":
            self.outcome(event["requestId"], False)
        elif kind == "ledger":
            self.ledger(event["line"])

    def outcome(self, request_id: str, won: bool) -> None:
        """Tracks a quantile of the winning price: a win pushes the multiplier up and a loss down, so it
        settles where `target_win` of the quotes win. Each step fades the older results."""
        quote = self.quotes.pop(request_id, None)
        if quote is None:
            return
        day, error = quote.at // DAY, (1.0 if won else 0.0) - self.p.target_win
        if quote.outage:
            self.outage_log = min(math.log(1.5), max(0.0, self.outage_log + 2 * self.p.key_step * error))
            return
        if day == self.war_day and in_hours(quote.at):
            if not self.p.war_decline and not self.war_over:  # follow the war, but leave the lanes alone
                self.apply([("", self.p.step * error)])
            return
        if in_hours(quote.at):
            self.day_open.setdefault(day, self.log_m)
        updates = [("", self.p.step * error)] + [(k, self.p.key_step * error) for k in quote.keys]
        self.apply(updates)
        if not in_hours(quote.at):
            return
        outcomes = self.today.setdefault(day, [])
        outcomes.append(Outcome(won, quote.pickup, updates))
        if self.level >= 8 and day > 0 and self.war_day is None:
            self.detect_war(day, outcomes)
        if self.level >= 6 and day != self.war_day and (self.outage is None or self.outage[0] != day):
            self.detect_outage(day, outcomes)

    def apply(self, updates: list[tuple[str, float]], sign: float = 1.0) -> None:
        for key, delta in updates:
            if key == "":
                lo, hi = math.log(self.p.floor), math.log(self.p.ceiling)
                self.log_m = min(hi, max(lo, self.log_m + sign * delta))
            else:
                lim = self.p.key_limit
                self.offset[key] = min(lim, max(-lim, self.offset.get(key, 0.0) + sign * delta))

    def detect_war(self, day: int, outcomes: list[Outcome]) -> None:
        """The world's multiplier falling far below the day's opening, on many lanes, is the price war.
        Monday has no usual level to fall from, so a war on Monday is only followed, not flagged."""
        if self.log_m > self.day_open[day] - self.p.war_drop:
            return
        if len({o.pickup for o in outcomes if not o.won}) >= self.p.war_places:
            self.war_day = day

    def detect_outage(self, day: int, outcomes: list[Outcome]) -> None:
        """A region that wins far more often than the rest of the day is the outage there. What its
        wins taught the world and its lanes today is undone, and the region gets its own boost."""
        best: tuple[float, frozenset[str]] | None = None
        for region in self.near.values():
            inside = [o for o in outcomes if o.pickup in region]
            n_in, n_out = len(inside), len(outcomes) - len(inside)
            if n_in < self.p.outage_min or n_out < self.p.outage_min:
                continue
            w_in = sum(o.won for o in inside)
            p_in, p_out = w_in / n_in, (sum(o.won for o in outcomes) - w_in) / n_out
            pooled = (w_in + p_out * n_out) / (n_in + n_out)
            spread = math.sqrt(pooled * (1 - pooled) * (1 / n_in + 1 / n_out)) or 1.0
            z = (p_in - p_out) / spread
            if p_in - p_out >= self.p.outage_gap and z >= self.p.outage_z and (best is None or z > best[0]):
                best = (z, region)
        if best is None:
            return
        self.outage, self.outage_log = (day, best[1]), math.log(self.p.outage_boost)
        for o in outcomes:
            if o.pickup in best[1]:
                self.apply(o.updates, -1.0)

    # --- dealer trust -------------------------------------------------------------------------

    def ledger(self, line: dict) -> None:
        """Counts dealer trust: a revenue line without a late refund is an order on time."""
        order_id = line.get("orderId")
        if not order_id:
            return
        self.settle(line["at"])
        if line["kind"] == "revenue":
            self.unsettled[order_id] = line["at"]
        elif line["kind"] in ("late_refund", "undelivered_penalty") and order_id not in self.settled:
            self.unsettled.pop(order_id, None)
            self.settled.add(order_id)
            dealer = self.dealer_of.get(order_id)
            if dealer is not None:
                self.trust[dealer] = self.trust.get(dealer, 0) // 2

    def settle(self, now: int) -> None:
        """A revenue line from an earlier minute that got no late refund is an order on time."""
        for order_id, at in list(self.unsettled.items()):
            if at < now:
                del self.unsettled[order_id]
                self.settled.add(order_id)
                dealer = self.dealer_of.get(order_id)
                if dealer is not None:
                    self.trust[dealer] = min(TRUST_CAP, self.trust.get(dealer, 0) + 1)


def in_hours(at: int) -> bool:
    return WORK_FROM <= at % DAY < WORK_TO


def request_keys(request: dict) -> tuple[str, ...]:
    leg = request["legs"][0]
    return (
        f"pickup:{leg['pickup']['placeId']}",
        f"delivery:{leg['delivery']['placeId']}",
        f"dealer:{request['dealerId']}",
    )


def km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Straight-line distance in km between two (lat, lon) points."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def neighbours(places: dict[str, tuple[float, float]]) -> dict[str, frozenset[str]]:
    """Each town's outage region: the town and the places within 80 km of it."""
    return {
        town: frozenset(p for p, pos in places.items() if km(here, pos) <= REGION_KM) for town, here in places.items()
    }


def places_from_map(world_map: dict) -> dict[str, tuple[float, float]]:
    """The (lat, lon) of each place in the world map, as `PricingModel` takes them."""
    return {p["id"]: (p["lat"], p["lon"]) for p in world_map["places"]}
