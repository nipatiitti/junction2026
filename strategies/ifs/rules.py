"""The ifs rules: what to do with a price request, as plain `if` rules over the request's inputs.

Every number that a rule compares with or multiplies by has a name, and its value is in values.json next to this
file, so a rule changes without a code edit: change the number, or give another file of values. `cost` and `price`
hold the rules, one `if` for each input. The search (search.py) looks for better values by playing weeks.

A strategy (strategies/strategy.py): no network. `quote` takes a request and the orders we hold and returns a price
for the one option we want, or nothing to decline; `observe` takes every event of the week. README.md next to this
file explains each rule.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

from spread.types import DeliveryOption, DeskEvent, DriverProfile, LedgerLine, Leg, PriceRequest, WorldMap

from strategies.admission import Held
from strategies.admission.admission import risky_note
from strategies.lane_fee import LaneFee
from strategies.lead_cost.admission import open_hours
from strategies.strategy import Strategy

HOUR, DAY = 60, 24 * 60
MONDAY, FRIDAY, SATURDAY = 0, 4, 5
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
WORK_FROM, WORK_TO = 8 * HOUR, 18 * HOUR  # the price war and the outage last from 08:00 to 18:00
TRUST_CAP = 25  # a dealer counts at most 25 orders on time, each worth 1% at level 8
OWN_LIMIT = 1.25  # the own factor of a dealer or a place stays within 25% of the usual price
OUTAGE_LOSSES = 2  # this many lost quotes in a row at the outage's price end the outage at that place
VALUES = Path(__file__).with_name("values.json")


def read_values(path: Path) -> dict[str, dict]:
    """The entries of a values file, by name. An entry is a number, or `{"value": ...}` with the range and step that
    the search uses."""
    entries = json.loads(path.read_text())
    return {name: entry if isinstance(entry, dict) else {"value": entry} for name, entry in entries.items()}


def load_values(path: Path | None = None) -> dict[str, float]:
    """The value of every name in values.json, with the values of the file at `path` in their place. That file may
    hold some of the names or all of them, but none that values.json does not have."""
    values = {name: entry["value"] for name, entry in read_values(VALUES).items()}
    if path is not None:
        for name, entry in read_values(path).items():
            if name not in values:
                raise ValueError(f"{path} names {name}, which {VALUES.name} does not have")
            values[name] = entry["value"]
    return values


@dataclass(frozen=True)
class Params:
    """The values of the rules, by name: `params.fee_open` is the number named `fee_open`. Without `values` they are
    those of values.json."""

    values: Mapping[str, float] = field(default_factory=lambda: MappingProxyType(load_values()))

    def __getattr__(self, name: str) -> float:
        if name == "values" or name.startswith("__"):
            raise AttributeError(name)
        try:
            return self.values[name]
        except KeyError:
            raise AttributeError(f"{VALUES.name} has no value named {name}") from None


@dataclass(frozen=True)
class Inputs:
    """Every input of a price request that a rule reads, as a plain number or flag."""

    dealer: str
    day: int  # the day the request came: 0 is Monday, 4 is Friday
    pickup: str  # the place where its first car waits
    delivery: str  # the place where its last car goes
    km: float  # road km that its cars travel
    drive: int  # road minutes to move its cars one after the other
    decided: int  # the minute the dealer decides: we post the gig then
    ready: int  # the minute its last car is ready to collect
    wait: float  # hours from the dealer's decision until its first car is ready; under 0 when it is ready already
    typical: float  # the typical fee for its cars, in cents: its lane's, or its own (`lane_fee`)
    trade_in: bool  # two cars: the new one out and the old one back
    premium: bool  # a premium car, which needs an experienced driver
    low_charge: bool  # an electric car under 30%: the driver stops to charge it
    private_pickup: bool  # a car waits at a private address
    private_delivery: bool  # a car goes to a private address
    batch: bool  # one of several cars that a dealer sends at once
    note: bool  # its note asks for something a driver can miss
    drivers_pickup: float  # drivers who live near the first pickup, the nearer ones counting more
    drivers_delivery: float  # the same near the last delivery
    drivers_able: float  # the drivers near the pickup who may take the car: the experienced ones for a premium car
    trust: int  # level 8: the orders we delivered to this dealer on time, up to 25
    waiting: float  # our cars near the pickup that still need a driver that day, and our quotes not yet answered
    on_time: float  # our share of orders on time so far


@dataclass
class Quoted:
    """What we sent for one request, kept until its outcome arrives."""

    at: int  # when the request arrived
    dealer: str
    pickup: str
    delivery: str
    floored: bool  # the driver cost set the price, above the usual price
    capped: bool  # the usual price was the most we ask
    outage: bool  # priced with the outage's lift


class IfRules(Strategy[Params]):
    """Quotes price requests by plain rules, and learns the usual price from the week's wins and losses."""

    def __init__(
        self,
        roster: list[DriverProfile],
        world_map: WorldMap,
        level: int = 8,
        params: Params | None = None,
        lane: LaneFee | None = None,
    ) -> None:
        super().__init__(roster, world_map, level, params or Params())
        self.lane = lane or LaneFee(roster, world_map, level)  # what a lane's work is usually paid
        self.km = {(road["from"], road["to"]): road["km"] for road in world_map["roads"]}
        # Where the drivers live: all of them, and those who may take a premium car.
        self.homes: dict[str, Counter[str]] = {"all": Counter(), "experienced": Counter()}
        for driver in roster:
            self.homes["all"][driver["homePlaceId"]] += 1
            if driver["rating"] >= 4.8 and driver["completedGigs"] >= 50:
                self.homes["experienced"][driver["homePlaceId"]] += 1
        self.nearby: dict[tuple[str, str], float] = {}  # (place, audience) -> the drivers near it
        # The usual price is `price_base` times the ladder, which a win raises and a loss lowers. The most we ask is
        # `price_base` times the cap, which the outcomes of the quotes at it move.
        self.ladder = 1.0
        self.cap = 1.0
        self.dealer: dict[str, float] = {}  # dealer -> its own factor on the usual price
        self.place: dict[str, float] = {}  # "from <pickup place>" or "to <delivery place>" -> its own factor
        self.quotes: dict[str, Quoted] = {}  # request id -> the quote waiting for its outcome
        # Runs of outcomes in the working hours of one day: losses in a row are the price war, wins in a row at one
        # pickup place are the outage there.
        self.run_day = -1
        self.losses = 0
        # The prices before a run of losses began: the ladder, the dealers' factors and the places'.
        self.before_losses: tuple[float, dict[str, float], dict[str, float]] = (self.ladder, {}, {})
        self.war_day: int | None = None
        self.wins: dict[str, int] = {}  # pickup place -> its wins in a row today
        self.gain: dict[str, float] = {}  # pickup place -> how much those wins raised the ladder
        self.outage: dict[str, int] = {}  # pickup place -> the day of the outage we flagged there
        self.outage_losses: dict[str, int] = {}  # pickup place -> lost quotes in a row at the outage's price
        # Dealer trust, counted from the account: a revenue line without a late refund is an order on time.
        self.trust: dict[str, int] = {}
        self.dealer_of: dict[str, str] = {}  # order id -> dealer
        self.unsettled: dict[str, int] = {}  # order id -> minute of its revenue line, not yet known on time
        self.settled: set[str] = set()
        # Our own week: the orders on the road, and how many arrived on time.
        self.open: dict[str, tuple[int, list[int | None]]] = {}  # order id -> (deadline, when each car arrived)
        self.on_time = 0
        self.late = 0
        self.pending: dict[str, tuple[int, str, int]] = {}  # request id -> (respondBy, pickup, pickup day)
        self.counts: Counter[str] = Counter()  # the week's quotes, for the summary

    # --- the rules ----------------------------------------------------------------------------------------------

    def quote(self, request: PriceRequest, held: Iterable[Held], now: int) -> dict[str, int]:
        """A price in cents for the one option we want, or nothing: the desk then declines the request. We decline
        when no option leaves time for the drive, when the area has no room for one more car, and when the driver
        cost with our margin is above the most we ask. Of the options that pay, we quote the one that leaves the
        most money after its driver."""
        v = self.params
        self.counts["requests"] += 1
        i = self.inputs(request, held, now)
        offered = request["options"][:1] if self.level <= 3 else request["options"]  # up to level 3 the first wins
        options = [option for option in offered if self.slack(i, option, now) >= v.slack_hours_least]
        if not options:
            return self.decline("time")
        room = max(v.room_least, v.room_per_driver * i.drivers_able)
        if i.on_time < v.on_time_guard:
            room *= v.room_when_late  # too many of our cars are late: take fewer
        if i.waiting + 1 > room:
            return self.decline("room")
        best: tuple[float, DeliveryOption, float, bool, bool] | None = None
        for option in options:
            listed = option["listPriceCents"]
            usual, most = self.price(i, option, now)
            cost = self.cost(i, option, self.lead(request, i, option))
            least = cost * (1 + v.min_margin)
            if least > listed * most:
                continue  # its driver would cost more than the most we ask
            cents = max(listed * usual, least)
            if best is None or cents - cost > best[0]:
                best = (cents - cost, option, cents, listed * usual < least, usual >= most)
        if best is None:
            return self.decline("cost")
        _, option, cents, floored, capped = best
        self.quotes[request["id"]] = Quoted(
            request["arrivedAt"], i.dealer, i.pickup, i.delivery, floored, capped, self.in_outage(i.pickup, now)
        )
        self.pending[request["id"]] = (
            request["respondBy"],
            i.pickup,
            request["legs"][0]["pickup"]["window"]["from"] // DAY,
        )
        self.counts["quoted"] += 1
        self.counts[f"quoted {option['kind']}"] += 1
        self.counts["at the cost floor"] += floored
        return {option["kind"]: max(1, int(cents + 0.5))}

    def slack(self, i: Inputs, option: DeliveryOption, now: int) -> float:
        """Hours that an option leaves beyond the drive, from when a driver can collect the car."""
        start = max(i.ready, now + HOUR)  # a driver needs an hour to see the gig and reach the car
        return (option["deadline"] - start - i.drive) / HOUR

    def lead(self, request: PriceRequest, i: Inputs, option: DeliveryOption) -> float:
        """Hours from the dealer's decision to the last minute the first car can be collected and still arrive by
        the option's deadline: the deadline less the drive, inside the pickup site's stated hours or a private
        seller's slot. About the order's `lastPickupAt`, as strategies/lead_cost counts it."""
        first = request["legs"][0]["pickup"]
        latest = option["deadline"] - i.drive
        if first["privateAddress"] or not first.get("hours"):
            latest = min(latest, first["window"]["to"])
        else:
            for day in range(latest // DAY, latest // DAY - 7, -1):
                span = open_hours(first["hours"], day)
                if span is not None and latest >= day * DAY + span[0]:
                    latest = min(latest, day * DAY + span[1])
                    break
        return (latest - i.decided) / HOUR

    def cost(self, i: Inputs, option: DeliveryOption, lead: float) -> float:
        """What we expect to pay drivers for the request's cars when the dealer takes `option`, in cents: the
        typical fee, times one factor for each thing that makes the work dearer or cheaper for a driver. `lead` is
        the hours we have to find one."""
        v = self.params
        cost = i.typical * (v.cost_base if self.level >= 7 else 0.8 if self.level == 1 else 1.0)
        if self.level >= 7:  # in a shortage, how long the car can wait for its driver decides most of its cost
            if lead < v.lead_tight_hours:
                cost *= v.cost_lead_tight  # to collect within hours: the fee climbs to its top before a driver comes
            elif lead < v.lead_short_hours:
                cost *= v.cost_lead_short
            elif i.wait >= v.ready_later_hours:
                cost *= v.cost_ready_later  # ready tomorrow or later: drivers plan that day ahead, at the early fee
            elif i.wait >= v.ready_soon_hours:
                cost *= v.cost_ready_soon
            elif lead < v.lead_day_hours:
                cost *= v.cost_lead_day  # ready now, and to collect within a day
        # Few drivers near the car: a long trip to it. Few near the end: an expensive trip home.
        cost *= 1 + v.cost_far_pickup * math.exp(-i.drivers_pickup / v.drivers_scale)
        cost *= 1 + v.cost_far_delivery * math.exp(-i.drivers_delivery / v.drivers_scale)
        if option["kind"] == "same_day":
            cost *= v.cost_same_day
        if i.km < v.short_km:
            cost *= v.cost_short
        if i.km > v.long_km:
            cost *= v.cost_long
        if i.private_pickup:
            cost *= v.cost_private_pickup
        if i.private_delivery:
            cost *= v.cost_private_delivery
        if i.trade_in:
            cost *= v.cost_trade_in
        if i.premium:
            cost *= v.cost_premium
        if i.low_charge:
            cost *= v.cost_charging
        if i.batch:
            cost *= v.cost_batch
        if i.note:
            cost *= v.cost_note
        if i.ready % DAY >= v.evening_hour * HOUR:
            cost *= v.cost_evening
        if i.ready // DAY % 7 >= SATURDAY:
            cost *= v.cost_weekend
        if i.day % 7 == FRIDAY:
            cost *= v.cost_friday
        return cost

    def price(self, i: Inputs, option: DeliveryOption, now: int) -> tuple[float, float]:
        """The price over the list price that we want for the option, and the most that we ask for it. The usual
        price is `price_base` times the ladder and the own factors of the dealer, the pickup place and the delivery
        place, lower in the price war; the most is `price_base` times the cap. Each rule that fits then lifts both
        by its factor."""
        v = self.params
        if self.level <= 3:
            return 1.0, 1.0  # every quote wins at the list price
        most = v.price_base * self.cap
        own = self.dealer.get(i.dealer, 1.0) * self.place.get(f"from {i.pickup}", 1.0)
        usual = min(most, v.price_base * self.ladder * own * self.place.get(f"to {i.delivery}", 1.0))
        if self.in_war(now):
            usual *= v.price_war
        lift = 1.0
        if option["kind"] == "same_day":
            lift *= v.price_same_day
        if option["kind"] == "within_3_days":
            lift *= v.price_three_days
        if i.km < v.short_km:
            lift *= v.price_short
        if i.km > v.long_km:
            lift *= v.price_long
        if i.day % 7 == MONDAY:
            lift *= v.price_monday
        if i.batch:
            lift *= v.price_batch
        if i.trust > 0:
            lift *= 1 + v.trust_use * i.trust / 100  # a dealer accepts 1% more for each order on time
        if self.in_outage(i.pickup, now):
            lift *= v.price_outage  # the competitor is down there: dealers turn to a dearer backup
        return usual * lift, most * lift

    def decline(self, why: str) -> dict[str, int]:
        self.counts[f"declined for {why}"] += 1
        return {}

    def in_war(self, now: int) -> bool:
        return self.war_day == now // DAY and WORK_FROM <= now % DAY < WORK_TO

    def in_outage(self, pickup: str, now: int) -> bool:
        return self.outage.get(pickup) == now // DAY and WORK_FROM <= now % DAY < WORK_TO

    # --- the inputs ---------------------------------------------------------------------------------------------

    def inputs(self, request: PriceRequest, held: Iterable[Held], now: int) -> Inputs:
        """The request's inputs, with what we know of its dealer, its area and our week."""
        legs = request["legs"]
        first = legs[0]["pickup"]
        pickup, delivery = first["placeId"], legs[-1]["delivery"]["placeId"]
        premium = any(leg["car"]["premium"] for leg in legs)
        decided = max(now, request["respondBy"])
        self.settle(now)
        return Inputs(
            dealer=request["dealerId"],
            day=request["arrivedAt"] // DAY,
            pickup=pickup,
            delivery=delivery,
            km=sum(self.km.get((leg["pickup"]["placeId"], leg["delivery"]["placeId"]), 0.0) for leg in legs),
            drive=self.drive(legs),
            decided=decided,
            ready=max(leg["pickup"]["window"]["from"] for leg in legs),
            wait=(first["window"]["from"] - decided) / HOUR,
            typical=self.lane.of_request(request) if self.params.lane_fee else request["referenceFeeCents"],
            trade_in=len(legs) > 1,
            premium=premium,
            low_charge=any(low_charge(leg) for leg in legs),
            private_pickup=any(leg["pickup"]["privateAddress"] for leg in legs),
            private_delivery=any(leg["delivery"]["privateAddress"] for leg in legs),
            batch=request.get("batchId") is not None,
            note=risky_note(request.get("note")),
            drivers_pickup=self.near(pickup),
            drivers_delivery=self.near(delivery),
            drivers_able=self.near(pickup, "experienced" if premium else "all"),
            trust=self.trust.get(request["dealerId"], 0) if self.level >= 8 else 0,
            waiting=self.waiting(pickup, first["window"]["from"] // DAY, held, now),
            on_time=(self.on_time + 9.5) / (self.on_time + self.late + 10),  # 95% before the first order arrives
        )

    def drive(self, legs: list[Leg]) -> int:
        """Road minutes to move the cars one after the other, as one driver would."""
        total, here = 0, None
        for leg in legs:
            a, b = leg["pickup"]["placeId"], leg["delivery"]["placeId"]
            if here is not None and here != a:
                total += self.minutes.get((here, a), 0)
            total += self.minutes.get((a, b), 0)
            here = b
        return total

    def near(self, place: str, audience: str = "all") -> float:
        """Drivers who live near `place`: each counts e^(-road minutes from home / `reach_minutes`), so 1 at the
        place itself and about a third at `reach_minutes` from it. `audience` is `all` or `experienced`."""
        key = (place, audience)
        if key not in self.nearby:
            reach = self.params.reach_minutes
            self.nearby[key] = sum(
                count * math.exp(-self.minutes.get((town, place), 10**6) / reach)
                for town, count in self.homes[audience].items()
            )
        return self.nearby[key]

    def waiting(self, pickup: str, day: int, held: Iterable[Held], now: int) -> float:
        """Our cars that still need a driver from the area around `pickup` on `day`: the orders we hold that no
        driver holds, and the requests we have quoted and not heard on. The area is `area_minutes` of road."""
        area = self.params.area_minutes
        for request_id in [r for r, (respond_by, _, _) in self.pending.items() if respond_by < now]:
            del self.pending[request_id]
        count = 0.0
        for h in held:
            first = h.order["legs"][0]["pickup"]
            near = self.minutes.get((first["placeId"], pickup), area + 1) <= area
            if h.waiting and near and first["window"]["from"] // DAY == day:
                count += 1
        for _, place, pending_day in self.pending.values():
            if pending_day == day and self.minutes.get((place, pickup), area + 1) <= area:
                count += 1
        return count

    # --- learning -----------------------------------------------------------------------------------------------

    def observe(self, event: DeskEvent) -> None:
        """Learns from one event of the week: wins and losses move the usual price, account lines count dealer
        trust, and deliveries count our orders on time."""
        kind, at = event["kind"], event["at"]
        if kind == "order_won":
            order = event["order"]
            self.pending.pop(order["id"], None)
            self.dealer_of[order["id"]] = order["dealerId"]
            self.open[order["id"]] = (order["deadline"], list(order["deliveredAt"]))
            self.outcome(order["id"], True)
        elif kind == "order_lost":
            self.pending.pop(event["requestId"], None)
            self.outcome(event["requestId"], False)
        elif kind == "order_changed":
            order = event["order"]
            if order["id"] in self.open:
                self.open[order["id"]] = (order["deadline"], self.open[order["id"]][1])
        elif kind == "order_cancelled":
            self.open.pop(event["orderId"], None)
        elif kind == "delivered":
            tracked = self.open.get(event["orderId"])
            if tracked is not None:
                tracked[1][event["leg"]] = at
                if all(t is not None for t in tracked[1]):
                    self.arrived(event["orderId"], at <= tracked[0])
        elif kind == "ledger":
            self.ledger(event["line"])
        # An order still on the road after its deadline is late, whenever it arrives.
        for order_id in [o for o, (deadline, _) in self.open.items() if at > deadline]:
            self.arrived(order_id, False)

    def arrived(self, order_id: str, on_time: bool) -> None:
        self.open.pop(order_id, None)
        if on_time:
            self.on_time += 1
        else:
            self.late += 1

    def outcome(self, request_id: str, won: bool) -> None:
        """A won quote raises the usual price by `ladder_up` and a lost one lowers it by `ladder_down`, between
        `ladder_min` and the cap. The same way, the dealer's own factor moves by `dealer_step`, and those of the
        pickup place and the delivery place by `place_step`. The cap, the most we ask, moves by `cap_step` with the
        outcome of each quote at it, between `cap_min` and `cap_max`. A quote that the driver cost priced and lost
        says nothing: our cost lost it, not our price. Then two runs are counted, in the working hours of one day:
        `war_losses` losses in a row are the price war, and `outage_wins` wins in a row at one pickup place are the
        outage there."""
        quote = self.quotes.pop(request_id, None)
        if quote is None:
            return  # a request we declined
        v = self.params
        self.counts["won" if won else "lost"] += 1
        day, working = quote.at // DAY, WORK_FROM <= quote.at % DAY < WORK_TO
        if day == self.war_day and working:
            return  # the war's prices say nothing about the usual price
        if quote.outage:
            self.outage_losses[quote.pickup] = 0 if won else self.outage_losses.get(quote.pickup, 0) + 1
            if self.outage_losses[quote.pickup] >= OUTAGE_LOSSES:
                self.outage.pop(quote.pickup, None)  # dealers there do not pay the outage's price: it is over
            return
        if not won and quote.floored:
            return
        if quote.capped:  # dealers took the most we ask, or refused it: ask a little more, or less
            self.cap = min(v.cap_max, max(v.cap_min, self.cap * (1 + (v.cap_step if won else -v.cap_step))))
        if working and day != self.run_day:  # a run of wins or losses does not go on overnight
            self.run_day, self.losses, self.wins, self.gain = day, 0, {}, {}
        if not won and self.losses == 0:
            self.before_losses = (self.ladder, dict(self.dealer), dict(self.place))
        before = self.ladder
        self.ladder = min(self.cap, max(v.ladder_min, before * (1 + (v.ladder_up if won else -v.ladder_down))))
        own = self.dealer.get(quote.dealer, 1.0) * (1 + (v.dealer_step if won else -v.dealer_step))
        self.dealer[quote.dealer] = min(OWN_LIMIT, max(1 / OWN_LIMIT, own))
        for place in (f"from {quote.pickup}", f"to {quote.delivery}"):
            own = self.place.get(place, 1.0) * (1 + (v.place_step if won else -v.place_step))
            self.place[place] = min(OWN_LIMIT, max(1 / OWN_LIMIT, own))
        if not working:
            return
        place = quote.pickup
        if not won:
            self.wins[place], self.gain[place] = 0, 1.0
            self.losses += 1
            # Monday has no usual price to fall from, so a war on Monday is followed down, not flagged.
            if self.level >= 8 and self.war_day is None and day > 0 and self.losses >= v.war_losses:
                self.war_day = day
                self.ladder, self.dealer, self.place = (
                    self.before_losses[0],
                    dict(self.before_losses[1]),
                    dict(self.before_losses[2]),
                )
            return
        self.losses = 0
        if quote.capped:
            return  # where we already ask the most, wins are what we expect: they are no sign of an outage
        self.wins[place] = self.wins.get(place, 0) + 1
        self.gain[place] = self.gain.get(place, 1.0) * self.ladder / before
        if self.level >= 6 and self.wins[place] >= v.outage_wins and self.outage.get(place) != day:
            self.outage[place], self.outage_losses[place] = day, 0
            self.counts["outages"] += 1
            # What the run's wins added to the usual price belongs to this place alone: take it back.
            self.ladder = max(v.ladder_min, self.ladder / self.gain[place])
            self.wins[place], self.gain[place] = 0, 1.0

    def ledger(self, line: LedgerLine) -> None:
        """Counts dealer trust: an order on time adds one, up to 25, and a late order halves the count."""
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

    def summary(self) -> str:
        """The week's quotes: how many requests we quoted and won, at which options, why we declined the others,
        and where the usual price and the most we ask ended."""
        c = self.counts
        if not c["requests"]:
            return ""
        kinds = ", ".join(f"{c[key]} {key[7:].replace('_', ' ')}" for key in sorted(c) if key.startswith("quoted "))
        base = self.params.price_base
        line = (
            f"Ifs: {c['quoted']} of {c['requests']} requests quoted ({kinds}), {c['won']} won; declined "
            f"{c['declined for time']} for time, {c['declined for room']} for room, {c['declined for cost']} for cost; "
            f"{c['at the cost floor']} quotes at the cost floor; usual price x{base * self.ladder:.2f}, "
            f"the most we ask x{base * self.cap:.2f}"
        )
        if self.war_day is not None:
            line += f"; price war on {WEEKDAYS[self.war_day % 7]}"
        if c["outages"]:
            line += f"; outage flagged at {c['outages']} place{'s' if c['outages'] != 1 else ''}"
        return line


def low_charge(leg: Leg) -> bool:
    """An electric car under 30%: the gig gets a charging stop."""
    car = leg["car"]
    return bool(car["electric"]) and car["chargePercent"] is not None and car["chargePercent"] < 30
