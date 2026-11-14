"""Simply Jack: a dispatch system that anyone can follow. See README.md next to this file.

Jack makes two decisions, and each is a few plain rules with its numbers at the top of this file:

1. The price. Quote every option of a request at its list price times PRICE, plus TRUST_SHARE of the dealer's
   trust: 1% for each order we delivered to that dealer on time, up to 25. Leave out an option that gives a
   driver less than MIN_LEAD to reach the car: its deadline, less the drive, less the minute the dealer decides.
   Decline a request with no option left, or whose typical driver fee is more than MAX_FEE_SHARE of our price.
2. The driver fee. Post each gig at FEE_OPEN times the typical fee, then raise it in FEE_STEPS even steps to
   FEE_TOP times the typical fee, which it reaches TOP_BEFORE minutes before the car's last pickup.

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
from spread.types import FeeStep, Order, PriceRequest

import dispatch as root
from tools import record

POLICY = "simply-jack"  # its saved weeks form their own group in out/spread.sqlite
HOUR = 60

# Jack's numbers. Change one, play a week, and keep it if the margin goes up.
PRICE = 1.55  # quote the list price times this: at level 8 the competitor asks 26% to 54% more than the list
TRUST_SHARE = 0.0  # level 8: add this share of the dealer's trust (1% an order on time) to the price
MIN_LEAD = 6 * HOUR  # leave out an option whose driver would have less than this to reach the car
MAX_FEE_SHARE = 0.75  # decline when the typical fee is more than this share of our price
FEE_OPEN = 0.8  # post a gig at the typical fee times this
FEE_TOP = 1.8  # and raise it to the typical fee times this
FEE_STEPS = 6  # in this many even steps, the opening fee included
TOP_BEFORE = 3 * HOUR  # the top fee is reached this long before the car's last pickup

NUMBERS = {
    "PRICE": PRICE,
    "TRUST_SHARE": TRUST_SHARE,
    "MIN_LEAD": MIN_LEAD,
    "MAX_FEE_SHARE": MAX_FEE_SHARE,
    "FEE_OPEN": FEE_OPEN,
    "FEE_TOP": FEE_TOP,
    "FEE_STEPS": FEE_STEPS,
    "TOP_BEFORE": TOP_BEFORE,
}


def jack_prices(request: PriceRequest, trust: int, minutes: dict[tuple[str, str], int]) -> dict[str, int]:
    """Rule 1, the price: every option with time for a driver, at its list price times PRICE, lifted by the
    dealer's trust, or nothing when no option is left or the driver costs too much. `trust` is the dealer's count
    of our orders on time, 0 to 25, and `minutes` the road minutes between two places."""
    drive = sum(minutes[leg["pickup"]["placeId"], leg["delivery"]["placeId"]] for leg in request["legs"])
    factor = PRICE * (1 + TRUST_SHARE * trust / 100)
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
    TOP_BEFORE minutes before the last pickup. With an hour or less to go, it posts at the top at once."""
    top_at = last_pickup_at - TOP_BEFORE
    if top_at - now <= HOUR:
        return [{"at": now, "feeCents": max(1, round(typical * FEE_TOP))}]
    steps: list[FeeStep] = []
    for k in range(FEE_STEPS):
        share = k / (FEE_STEPS - 1)  # 0 at the opening, 1 at the top
        at = now + round((top_at - now) * share)
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
        self.quoted = self.declined = 0
        self.strategies.append(JackLine(self))  # prints Jack's line at the end of a practice week

    def quote(self, request: PriceRequest) -> None:
        self.requests[request["id"]] = request
        if self.level <= 3:  # every quote wins up to level 3: no quote needed
            return
        # The root pricing model counts each dealer's trust from the ledger: +1 an order on time, halved when late.
        trust = self.pricing.trust.get(request["dealerId"], 0) if self.level >= 8 else 0
        prices = jack_prices(request, trust, self.pricing.minutes)
        if prices:
            self.quoted += 1
        else:  # a price far above the list price loses at no cost
            self.declined += 1
            prices = {option["kind"]: 10 * option["listPriceCents"] for option in request["options"][:1]}
        self.outbox.append({"type": "quote", "requestId": request["id"], "prices": prices})

    def fees_for(self, order: Order, cars: int) -> list[FeeStep]:
        typical = self.fees.typical(order, self.requests[order["id"]]) * cars / len(order["legs"])
        return jack_fees(typical, self.now, order["lastPickupAt"])


class JackLine:
    """Learns nothing; at the end of a practice week the root loop prints its line with the other strategies'."""

    def __init__(self, desk: Desk):
        self.desk = desk

    def observe(self, event: object) -> None:
        pass

    def summary(self) -> str:
        return f"Simply Jack: {self.desk.quoted} requests quoted, {self.desk.declined} declined. Numbers: {NUMBERS}"


# The root loop (play_practice, play_final) plays with this desk, and main() saves its weeks as `simply-jack`.
root.Desk = Desk
root.Recorder = Recorder

if __name__ == "__main__":
    root.main()
