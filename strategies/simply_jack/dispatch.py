"""Simply Jack: a dispatch system that anyone can follow. See README.md next to this file.

Jack makes two decisions, each a few plain rules with their numbers at the top of this file.

1. The price of a request.
   a. Each dealer has its own price factor, a multiple of the list price. It starts at PRICE. A win raises it by
      LADDER_UP and a loss lowers it by LADDER_DOWN, between PRICE_MIN and PRICE_MAX. So Jack wins about a third.
   b. Earn trust first: in the first TRUST_DAYS of the week the two steps swap, so Jack wins most requests at a
      small margin. Each order on time lets its dealer accept 1% more from us later in the week.
   c. Each morning every dealer's factor falls by MORNING_STEP: overnight the competitor cuts its prices for the
      dealers we won most from.
   d. Too few drivers: each car that got the deadline warning in the last 24 hours adds WARN_STEP to every price.
   e. Friday: every price is FRIDAY_PRICE times lower. A car asked for on Friday has the weekend to wait, and the
      competitor's Friday prices were lower on every seed we played.
   f. The price war: when Jack wins at most one of his last WAR_WINDOW quotes, the competitor is 20% cheaper
      today. Until 18:00 Jack quotes WAR_PRICE times his price and the factors learn nothing. Once a week, and not
      on the day after the trust days, when his new prices lose a lot anyway; the window counts every quote.
   g. Quote every option at its list price times the factor, but leave out an option that gives a driver less
      than MIN_LEAD to reach the car (its deadline, less the drive, less the minute the dealer decides).
   h. Decline when no option is left, when a car goes from or to a private address, or when the typical driver
      fee is more than MAX_FEE_LIST times the list price.
2. The driver fee of a gig: FEE_OPEN times the typical fee, raised in FEE_STEPS even steps to FEE_TOP times it,
   reached TOP_BEFORE the car's last pickup. When that is on a later day, the fee holds until DAWN of that day,
   when drivers plan their day, and climbs from then. With an hour or less to go, the gig goes at the top at once.

Everything else (posting, notes, retries, bundling, direct offers, the final) is the root dispatch.py, unchanged.

Run it from the repository root: uv run strategies/simply_jack/dispatch.py --level 8 --seed spread-9
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import World
from spread.types import DeskEvent, FeeStep, Order, PriceRequest

import dispatch as root
from tools import record

POLICY = "simply-jack"  # its saved weeks form their own group in out/spread.sqlite
HOUR, DAY = 60, 24 * 60

# Jack's numbers. Change one, play a week, and keep it if the margin goes up.
PRICE = 1.50  # each dealer's price starts at the list price times this: the competitor asks 26% to 54% more
LADDER_UP = 0.02  # a won request raises its dealer's price by this share
LADDER_DOWN = 0.015  # a lost one lowers it by this share
TRUST_DAYS = 1  # Monday: a win adds LADDER_DOWN and a loss takes LADDER_UP, to win most requests
WAR_WINDOW, WAR_PRICE = 20, 0.85  # at most one win in this many quotes is the price war: quote this much less
WARN_STEP = 0.02  # each car warned in the last 24 hours (no driver 3 hours before its last pickup) adds this
FRIDAY_PRICE = 0.92  # Friday's quotes are this times the dealer's price
MORNING_STEP = 0.02  # each morning every dealer's price falls by this: overnight the competitor answers our wins
PRICE_MIN, PRICE_MAX = 1.25, 2.00  # a dealer's price stays between these times the list price
MIN_LEAD = 8 * HOUR  # leave out an option whose driver would have less than this to reach the car
MAX_FEE_LIST = 1.16  # decline when the typical fee is more than this times the list price: too dear a lane
FEE_OPEN = 1.0  # post a gig at the typical fee times this
FEE_TOP = 1.5  # and raise it to the typical fee times this
FEE_STEPS = 6  # in this many even steps, the opening fee included
TOP_BEFORE = 3 * HOUR  # the top fee is reached this long before the car's last pickup
DAWN = 6 * HOUR  # a gig with a morning to wait for holds its opening fee until this hour of its last morning

NUMBERS = {
    "PRICE": PRICE,
    "LADDER_UP": LADDER_UP,
    "LADDER_DOWN": LADDER_DOWN,
    "TRUST_DAYS": TRUST_DAYS,
    "WAR_WINDOW": WAR_WINDOW,
    "WAR_PRICE": WAR_PRICE,
    "WARN_STEP": WARN_STEP,
    "FRIDAY_PRICE": FRIDAY_PRICE,
    "MORNING_STEP": MORNING_STEP,
    "PRICE_MIN": PRICE_MIN,
    "PRICE_MAX": PRICE_MAX,
    "MIN_LEAD": MIN_LEAD,
    "MAX_FEE_LIST": MAX_FEE_LIST,
    "FEE_OPEN": FEE_OPEN,
    "FEE_TOP": FEE_TOP,
    "FEE_STEPS": FEE_STEPS,
    "TOP_BEFORE": TOP_BEFORE,
    "DAWN": DAWN,
}


def jack_prices(
    request: PriceRequest, factor: float, minutes: dict[tuple[str, str], int], discount: float = 1.0
) -> dict[str, int]:
    """Rule 1, the price: every option with time for a driver, at its list price times the dealer's `factor`, or
    nothing when no option is left, a car goes from or to a private address, or the driver costs too much.
    `minutes` are the road minutes between places."""
    drive = sum(minutes[leg["pickup"]["placeId"], leg["delivery"]["placeId"]] for leg in request["legs"])
    prices = {
        option["kind"]: round(option["listPriceCents"] * factor)
        for option in request["options"]
        if option["deadline"] - drive - request["respondBy"] >= MIN_LEAD
    }
    private = any(leg["pickup"]["privateAddress"] or leg["delivery"]["privateAddress"] for leg in request["legs"])
    dear = request["referenceFeeCents"] > MAX_FEE_LIST * min(option["listPriceCents"] for option in request["options"])
    if not prices or private or dear:
        return {}
    return {kind: round(cents * discount) for kind, cents in prices.items()}  # the war discount comes last


def jack_fees(typical: float, now: int, last_pickup_at: int) -> list[FeeStep]:
    """Rule 2, the driver fee: from FEE_OPEN to FEE_TOP times the typical fee, in even steps, reaching the top
    TOP_BEFORE minutes before the last pickup. Drivers plan their day in the morning, so a gig whose top is due on a
    later day holds its opening fee until DAWN of that day and climbs from there. With an hour or less to go, as
    after the deadline warning, it posts at the top at once."""
    top_at = last_pickup_at - TOP_BEFORE
    if top_at - now <= HOUR:
        return [{"at": now, "feeCents": max(1, round(typical * FEE_TOP))}]
    dawn = top_at // DAY * DAY + DAWN  # the last morning before the top, at least an hour before it
    if dawn > top_at - HOUR:
        dawn -= DAY
    start = max(now, dawn)  # the climb starts now, or at that morning when it is still to come
    steps: list[FeeStep] = []
    for k in range(FEE_STEPS):
        share = k / (FEE_STEPS - 1)  # 0 at the opening, 1 at the top
        at = now if k == 0 else start + round((top_at - start) * share)
        fee = typical * (FEE_OPEN + (FEE_TOP - FEE_OPEN) * share)
        steps.append({"at": at, "feeCents": max(1, round(fee))})
    return steps


class Recorder(record.Recorder):
    """Saves the week like the root system's, as the policy `simply-jack`, with Jack's numbers."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str, policy: str = POLICY):
        super().__init__(world, level, seed, kind, policy)

    def add_to_database(self, target: Path) -> None:
        meta = json.loads((target / "meta.json").read_text())
        record.write_json(target / "meta.json", {**meta, "settings": {"strategy": POLICY, "values": NUMBERS}})
        super().add_to_database(target)


class Desk(root.Desk):
    """The root desk, with Jack's price and Jack's driver fee."""

    def __init__(self, world: World, level: int, now: int):
        super().__init__(world, level, now)
        self.ladder = Ladder()
        self.strategies.append(self.ladder)  # the desk feeds it every event, and prints its line at the end

    def quote(self, request: PriceRequest) -> None:
        self.requests[request["id"]] = request
        if self.level <= 3:  # every quote wins up to level 3: no quote needed
            return
        discount = WAR_PRICE if self.ladder.at_war(self.now) else 1.0
        factor = self.ladder.factor(request["dealerId"]) * (1 + WARN_STEP * self.ladder.warned(self.now))
        if self.now // DAY == 4:  # Friday
            factor *= FRIDAY_PRICE
        prices = jack_prices(request, factor, self.pricing.minutes, discount)
        if prices:
            self.ladder.quoted[request["id"]] = request["dealerId"]
        else:  # a price far above the list price loses at no cost
            self.ladder.declined += 1
            prices = {option["kind"]: 10 * option["listPriceCents"] for option in request["options"][:1]}
        self.outbox.append({"type": "quote", "requestId": request["id"], "prices": prices})

    def fees_for(self, order: Order, cars: int) -> list[FeeStep]:
        typical = self.fees.typical(order, self.requests[order["id"]]) * cars / len(order["legs"])
        return jack_fees(typical, self.now, order["lastPickupAt"])


class Ladder:
    """Each dealer's price factor, moved by the answers to the quotes we meant: a decline teaches nothing."""

    def __init__(self) -> None:
        self.factors: dict[str, float] = {}  # dealer id -> price factor; a dealer not here is at PRICE
        self.day = 0  # the day of the last event, for the morning step
        self.quoted: dict[str, str] = {}  # request id -> its dealer, for the requests we quoted to win
        self.declined = self.won = self.lost = self.war_quotes = 0
        self.recent: list[bool] = []  # the last WAR_WINDOW answers: won or lost
        self.war_day = -1  # the day the price war was seen, until 18:00
        self.warnings: dict[str, int] = {}  # order id -> the minute of its last deadline warning

    def factor(self, dealer: str) -> float:
        return self.factors.get(dealer, PRICE)

    def warned(self, now: int) -> int:
        """The cars that got the deadline warning in the last 24 hours."""
        return sum(1 for at in self.warnings.values() if now - at < DAY)

    def at_war(self, now: int) -> bool:
        """True from a run of WAR_WINDOW quotes with at most one win, after the day the trust days end, until 18:00."""
        war = self.war_day == now // DAY and now % DAY < 18 * HOUR
        self.war_quotes += war
        return war

    def observe(self, event: DeskEvent) -> None:
        if event["at"] // DAY > self.day:  # a new morning: the competitor has answered our wins overnight
            self.day = event["at"] // DAY
            self.factors = {d: max(PRICE_MIN, f * (1 - MORNING_STEP)) for d, f in self.factors.items()}
        if event["kind"] == "deadline_close":
            self.warnings[event["orderId"]] = event["at"]
        elif event["kind"] == "order_won":
            self.learn(event["order"]["id"], won=True, at=event["at"])
        elif event["kind"] == "order_lost":
            self.learn(event["requestId"], won=False, at=event["at"])

    def learn(self, request_id: str, won: bool, at: int) -> None:
        dealer = self.quoted.pop(request_id, None)
        if dealer is None:
            return
        self.won, self.lost = self.won + won, self.lost + (not won)
        self.recent = [*self.recent, won][-WAR_WINDOW:]
        war = len(self.recent) == WAR_WINDOW and sum(self.recent) <= 1
        # One price war a week; not the day after the trust days, when Jack's new prices lose a lot anyway.
        if war and at >= (TRUST_DAYS + 1) * DAY and self.war_day < 0:
            self.war_day = at // DAY
        if self.war_day == at // DAY and at % DAY < 18 * HOUR:
            return  # the price war teaches nothing about our dealers
        up, down = (LADDER_DOWN, LADDER_UP) if at < TRUST_DAYS * DAY else (LADDER_UP, LADDER_DOWN)
        factor = self.factor(dealer) * (1 + up if won else 1 - down)
        self.factors[dealer] = min(PRICE_MAX, max(PRICE_MIN, factor))

    def summary(self) -> str:
        factors = sorted(self.factors.values())
        spread = f"x{factors[0]:.2f} to x{factors[-1]:.2f}" if factors else "none"
        return (
            f"Simply Jack: {self.won} won, {self.lost} lost, {self.declined} declined; dealer prices {spread}; "
            f"price war on day {self.war_day}, {self.war_quotes} war quotes. "
            f"Numbers: {NUMBERS}"
        )


# The root loop (play_practice, play_final) plays with this desk, and main() saves its weeks as `simply-jack`.
root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
