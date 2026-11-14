"""Simply Jack: a dispatch system that anyone can follow. See README.md next to this file.

Jack makes two decisions, and each is a few plain rules with its numbers at the top of this file:

1. The price. Each dealer has its own price factor. It starts at PRICE, rises by LADDER_UP after each request of
   that dealer we win and falls by LADDER_DOWN after each we lose, between PRICE_MIN and PRICE_MAX. Quote every
   option of a request at its list price times the dealer's factor. Leave out an option that gives a driver less
   than MIN_LEAD to reach the car: its deadline, less the drive, less the minute the dealer decides. Decline a
   request with no option left, or whose typical driver fee is more than MAX_FEE_SHARE of our price.
2. The driver fee. Post each gig at FEE_OPEN times the typical fee, then raise it in FEE_STEPS even steps to
   FEE_TOP times the typical fee, which it reaches TOP_BEFORE minutes before the car's last pickup. When that is on
   a later day, the gig holds its opening fee until DAWN of that day, and only then climbs. A gig with an hour or
   less to go, as after the deadline warning, goes at once at the top fee.

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
PRICE = 1.55  # each dealer's price starts at the list price times this: the competitor asks 26% to 54% more
LADDER_UP = 0.02  # a won request raises its dealer's price by this share
LADDER_DOWN = 0.01  # a lost one lowers it by this share
PRICE_MIN, PRICE_MAX = 1.40, 2.00  # a dealer's price stays between these times the list price
MIN_LEAD = 6 * HOUR  # leave out an option whose driver would have less than this to reach the car
MAX_FEE_SHARE = 0.75  # decline when the typical fee is more than this share of our price
FEE_OPEN = 0.8  # post a gig at the typical fee times this
FEE_TOP = 1.6  # and raise it to the typical fee times this
FEE_STEPS = 6  # in this many even steps, the opening fee included
TOP_BEFORE = 3 * HOUR  # the top fee is reached this long before the car's last pickup
DAWN = 6 * HOUR  # a gig with a morning to wait for holds its opening fee until this hour of its last morning

NUMBERS = {
    "PRICE": PRICE,
    "LADDER_UP": LADDER_UP,
    "LADDER_DOWN": LADDER_DOWN,
    "PRICE_MIN": PRICE_MIN,
    "PRICE_MAX": PRICE_MAX,
    "MIN_LEAD": MIN_LEAD,
    "MAX_FEE_SHARE": MAX_FEE_SHARE,
    "FEE_OPEN": FEE_OPEN,
    "FEE_TOP": FEE_TOP,
    "FEE_STEPS": FEE_STEPS,
    "TOP_BEFORE": TOP_BEFORE,
    "DAWN": DAWN,
}


def jack_prices(request: PriceRequest, factor: float, minutes: dict[tuple[str, str], int]) -> dict[str, int]:
    """Rule 1, the price: every option with time for a driver, at its list price times the dealer's `factor`, or
    nothing when no option is left or the driver costs too much. `minutes` are the road minutes between places."""
    drive = sum(minutes[leg["pickup"]["placeId"], leg["delivery"]["placeId"]] for leg in request["legs"])
    prices = {
        option["kind"]: round(option["listPriceCents"] * factor)
        for option in request["options"]
        if option["deadline"] - drive - request["respondBy"] >= MIN_LEAD
    }
    if not prices or request["referenceFeeCents"] > MAX_FEE_SHARE * min(prices.values()):
        return {}
    return prices


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
        prices = jack_prices(request, self.ladder.factor(request["dealerId"]), self.pricing.minutes)
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
        self.quoted: dict[str, str] = {}  # request id -> its dealer, for the requests we quoted to win
        self.declined = self.won = self.lost = 0

    def factor(self, dealer: str) -> float:
        return self.factors.get(dealer, PRICE)

    def observe(self, event: DeskEvent) -> None:
        if event["kind"] == "order_won":
            self.learn(event["order"]["id"], won=True)
        elif event["kind"] == "order_lost":
            self.learn(event["requestId"], won=False)

    def learn(self, request_id: str, won: bool) -> None:
        dealer = self.quoted.pop(request_id, None)
        if dealer is None:
            return
        self.won, self.lost = self.won + won, self.lost + (not won)
        factor = self.factor(dealer) * (1 + LADDER_UP if won else 1 - LADDER_DOWN)
        self.factors[dealer] = min(PRICE_MAX, max(PRICE_MIN, factor))

    def summary(self) -> str:
        factors = sorted(self.factors.values())
        spread = f"x{factors[0]:.2f} to x{factors[-1]:.2f}" if factors else "none"
        return (
            f"Simply Jack: {self.won} won, {self.lost} lost, {self.declined} declined; dealer prices {spread}. "
            f"Numbers: {NUMBERS}"
        )


# The root loop (play_practice, play_final) plays with this desk, and main() saves its weeks as `simply-jack`.
root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
