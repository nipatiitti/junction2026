"""Answers by experiment what no scrape can. Forks one practice world at one minute, tries one varied action in each
copy, and bisects to the value where the outcome flips. A copy has the same future draws as its parent, so a change in
outcome comes from the action alone. README.md says how to run it.

    uv run --env-file .env probe.py quote --level 8 --seed scrape-1 --share 0.05
    uv run --env-file .env probe.py fee --level 8 --seed scrape-1 --requests R00042,R00100

`quote`: at a request's arrival, quotes one option at different prices in copies and advances to its respondBy. The
flip price is the highest price that wins this request with this world's draws: the competitor and the dealer's
value, as one number. `fee`: wins the request cheaply, then posts its cars at different flat fees in copies and
advances `--window` minutes. The flip fee is the lowest flat fee that a driver books within the window.

The parent plays no gigs and declines every request that it does not probe (10 times the list price, which costs
nothing), so each probe sees drivers who have learned nothing and dealers with no history. Rows go to
out/probe/<mode>-L<level>-<seed>.jsonl, one per probed option or order, and a probe that is run again skips the rows
that it has. Every copy is deleted after its step; Ctrl-C deletes the parent too.
"""

from __future__ import annotations

import argparse
import json
import random
import signal
import sys
import time
from pathlib import Path
from typing import Any

from spread.client import Client, SpreadError, World

from dispatch import HOUR
from spread_proxy import ProxyClient

PRACTICE_SLOTS = 8
DECLINE = 10  # a quote at this multiple of the list price loses at no cost


class Probe:
    """One probe world: the parent, its copies, and the slots that they take."""

    def __init__(self, client: Client, keep_free: int):
        self.client, self.keep_free = client, keep_free
        self.copies = 0  # copies made, for the report
        self.live: list[World] = []  # worlds to delete when the probe stops

    def wait_slot(self) -> None:
        """Waits until a world can be made without taking the slots left for teammates."""
        while sum(1 for w in self.client.worlds() if not w["ended"]) >= PRACTICE_SLOTS - self.keep_free:
            time.sleep(5)

    def create(self, level: int, seed: str) -> World:
        self.wait_slot()
        world = self.client.create(level=level, seed=seed)
        self.live.append(world)
        return world

    def fork(self, parent: World) -> World:
        while True:
            self.wait_slot()
            try:
                copy = parent.fork()
            except SpreadError as error:
                if error.status != 409:  # 409: a teammate took the slot first
                    raise
                time.sleep(5)
                continue
            self.copies += 1
            self.live.append(copy)
            return copy

    def drop(self, world: World) -> None:
        try:
            world.delete()
        except SpreadError:
            pass
        if world in self.live:
            self.live.remove(world)

    def close(self) -> None:
        for world in list(self.live):
            self.drop(world)


def decline(request: dict) -> dict:
    first = request["options"][0]
    return {"type": "quote", "requestId": request["id"], "prices": {first["kind"]: DECLINE * first["listPriceCents"]}}


def outcome(events: list[dict], request_id: str) -> tuple[str | None, dict | None]:
    """won or lost for the request, with the order when won; None while the dealer has not decided."""
    for event in events:
        if event["kind"] == "order_won" and event["order"]["id"] == request_id:
            return "won", event["order"]
        if event["kind"] == "order_lost" and event["requestId"] == request_id:
            return "lost", None
    return None, None


def bisect(test, low: int, high: int, resolution: int) -> dict:
    """The flip of a test that is True at low values and False at high ones (or the reverse, with `rising`).
    Tries both ends first: a test that does not flip inside them says so. Returns the bracket and every trial."""
    trials: dict[int, bool] = {}

    def run(value: int) -> bool:
        trials[value] = test(value)
        return trials[value]

    at_low, at_high = run(low), run(high)
    if at_low == at_high:
        return {"flip": None, "bracket": None, "sameAtBothEnds": at_low, "trials": trials}
    lo, hi = low, high  # test(lo) == at_low, test(hi) == at_high
    while hi - lo > resolution:
        mid = (lo + hi) // 2
        if run(mid) == at_low:
            lo = mid
        else:
            hi = mid
    return {"flip": (lo + hi) / 2, "bracket": [lo, hi], "sameAtBothEnds": None, "trials": trials}


def monotone(trials: dict[int, bool]) -> bool:
    """True when the outcomes, in order of value, change at most once: a threshold, not a coin."""
    outcomes = [trials[v] for v in sorted(trials)]
    return sum(a != b for a, b in zip(outcomes, outcomes[1:])) <= 1


def probe_quote(probe: Probe, parent: World, request: dict, args: argparse.Namespace, others: list[dict]) -> list[dict]:
    """Bisects each option of the request on its own: in each copy, only that option is quoted."""
    rows = []
    for option in request["options"]:
        list_price = option["listPriceCents"]

        def wins(price: int, option=option) -> bool:
            copy = probe.fork(parent)
            try:
                actions = [decline(r) for r in others]
                actions.append({"type": "quote", "requestId": request["id"], "prices": {option["kind"]: price}})
                step = copy.advance(to=request["respondBy"] + 1, actions=actions)
                result, _ = outcome(step["events"], request["id"])
                return result == "won"
            finally:
                probe.drop(copy)

        found = bisect(
            wins,
            round(list_price * args.low),
            round(list_price * args.high),
            max(1, round(list_price * args.resolution)),
        )
        # A few prices away from the bisection's path test whether the dealer's answer is a threshold.
        rng = random.Random(f"{request['id']}:{option['kind']}")
        for _ in range(args.checks):
            price = round(list_price * rng.uniform(args.low, args.high))
            found["trials"][price] = wins(price)
        rows.append(
            {
                "requestId": request["id"],
                "option": option["kind"],
                "options": [o["kind"] for o in request["options"]],
                "dealerId": request["dealerId"],
                "arrivedAt": request["arrivedAt"],
                "lane": [request["legs"][0]["pickup"]["placeId"], request["legs"][0]["delivery"]["placeId"]],
                "legs": len(request["legs"]),
                "listPriceCents": list_price,
                "referenceFeeCents": request["referenceFeeCents"],
                "flipCents": found["flip"],
                "flipRatio": None if found["flip"] is None else found["flip"] / list_price,
                "bracketCents": found["bracket"],
                "sameAtBothEnds": found["sameAtBothEnds"],
                "monotone": monotone(found["trials"]),
                "trials": sorted(found["trials"].items()),
            }
        )
    return rows


def stops(order: dict) -> list[dict]:
    """A pickup and a delivery for each car, without windows of their own: the world plans them in the order's."""
    out = []
    for i, leg in enumerate(order["legs"]):
        car = leg["car"]
        low = car["electric"] and car["chargePercent"] is not None and car["chargePercent"] < 30
        out.append({"orderId": order["id"], "leg": i, "kind": "pickup", "withPlates": False, "withCharging": low})
        out.append({"orderId": order["id"], "leg": i, "kind": "delivery"})
    return out


def probe_fee(probe: Probe, parent: World, order: dict, request: dict, args: argparse.Namespace) -> dict:
    """Bisects the flat fee at which a driver books the order's gig within the window."""
    reference = request["referenceFeeCents"]
    post = {
        "type": "post",
        "stops": stops(order),
        "audience": {"experienced": any(leg["car"]["premium"] for leg in order["legs"]), "manualLicence": False},
    }
    bookings: dict[int, dict] = {}

    def booked(fee: int) -> bool:
        copy = probe.fork(parent)
        try:
            now = copy.snapshot()["now"]
            step = copy.advance(
                until=["gig_booked"],
                max=now + args.window,
                actions=[{**post, "schedule": [{"at": now, "feeCents": fee}]}],
            )
            result = step["results"][-1]
            if not result["ok"]:
                raise SpreadError(400, f"post refused: {result['reason']}")
            event = next((e for e in step["events"] if e["kind"] == "gig_booked" and e["gigId"] == result["id"]), None)
            if event:
                bookings[fee] = {"driverId": event["driverId"], "minutes": event["at"] - now}
            return event is None  # True while too low: the bisection wants True at the low end
        finally:
            probe.drop(copy)

    found = bisect(
        booked,
        round(reference * args.low),
        round(reference * args.high),
        max(1, round(reference * args.resolution)),
    )
    rng = random.Random(f"{order['id']}:fee")
    for _ in range(args.checks):
        fee = round(reference * rng.uniform(args.low, args.high))
        found["trials"][fee] = booked(fee)
    flip = found["flip"]
    at_flip = bookings.get(found["bracket"][1]) if found["bracket"] else None
    return {
        "orderId": order["id"],
        "option": order["option"],
        "dealerId": order["dealerId"],
        "wonAt": order.get("wonAt"),
        "lastPickupAt": order["lastPickupAt"],
        "deadline": order["deadline"],
        "lane": [order["legs"][0]["pickup"]["placeId"], order["legs"][0]["delivery"]["placeId"]],
        "legs": len(order["legs"]),
        "premium": post["audience"]["experienced"],
        "referenceFeeCents": reference,
        "windowMinutes": args.window,
        "flipCents": flip,
        "flipRatio": None if flip is None else flip / reference,
        "bracketCents": found["bracket"],
        "neverOrAlways": None
        if found["sameAtBothEnds"] is None
        else ("never" if found["sameAtBothEnds"] else "always"),
        "bookedBy": at_flip,  # the driver who booked at the low end of the bracket's booked side, and how soon
        "monotone": monotone(found["trials"]),
        "trials": sorted((fee, not unbooked) for fee, unbooked in found["trials"].items()),
    }


def run(args: argparse.Namespace) -> None:
    out = Path(args.out) / f"{args.mode}-L{args.level}-{args.seed}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out.exists():
        done = {json.loads(line)["requestId" if args.mode == "quote" else "orderId"] for line in out.open()}
    wanted = set(args.requests.split(",")) if args.requests else None
    pick = random.Random(f"{args.seed}:{args.level}:{args.mode}")
    client = ProxyClient()
    probe = Probe(client, args.keep_free)
    started, requests_before = time.monotonic(), client.requests
    probed = 0
    try:
        parent = probe.create(args.level, args.seed)
        ends_at = parent.snapshot()["endsAt"]
        last_request = 4 * 24 * HOUR + 18 * HOUR + 15  # Friday 18:15: no request comes later
        winning: dict[str, dict] = {}  # fee mode: request id -> request, quoted cheaply to win
        now = parent.snapshot()["now"]
        while now < min(ends_at, last_request + 30) and (args.limit is None or probed < args.limit):
            step = parent.advance(until=["price_request", "order_won"], max=min(ends_at, last_request + 30))
            now = step["now"]
            arrived = [e["request"] for e in step["events"] if e["kind"] == "price_request"]
            targets = [
                r
                for r in arrived
                if r["id"] not in done and (r["id"] in wanted if wanted is not None else pick.random() < args.share)
            ]
            actions = []
            if args.mode == "quote":
                with out.open("a") as f:
                    for request in targets:
                        others = [r for r in arrived if r["id"] != request["id"]]
                        for row in probe_quote(probe, parent, request, args, others):
                            f.write(json.dumps(row) + "\n")
                            print(
                                f"{row['requestId']} {row['option']:<13} flip {row['flipRatio'] or row['sameAtBothEnds']}"
                                f"{'' if row['monotone'] else '  NOT MONOTONE'}",
                                flush=True,
                            )
                        probed += 1
                actions = [decline(r) for r in arrived]
            else:
                for request in arrived:
                    if request in targets:
                        winning[request["id"]] = request
                        first = request["options"][0]
                        price = round(first["listPriceCents"] * args.win_ratio)
                        actions.append({"type": "quote", "requestId": request["id"], "prices": {first["kind"]: price}})
                    else:
                        actions.append(decline(request))
                for event in step["events"]:
                    if event["kind"] == "order_won" and event["order"]["id"] in winning:
                        order = {**event["order"], "wonAt": event["at"]}
                        row = probe_fee(probe, parent, order, winning.pop(order["id"]), args)
                        with out.open("a") as f:
                            f.write(json.dumps(row) + "\n")
                        print(
                            f"{row['orderId']} fee flip {row['flipRatio'] or row['neverOrAlways']}"
                            f"{'' if row['monotone'] else '  NOT MONOTONE'}",
                            flush=True,
                        )
                        probed += 1
            if actions:
                parent.act(actions)
    finally:
        probe.close()
    print(
        f"{probed} probed, {probe.copies} copies, {client.requests - requests_before} requests, "
        f"{time.monotonic() - started:.0f}s, into {out}",
        flush=True,
    )


def stop_on_signal(signum: int, frame: Any) -> None:
    raise KeyboardInterrupt


def ratio_pair(text: str) -> tuple[float, float]:
    low, high = (float(x) for x in text.split(","))
    if not 0 < low < high:
        raise argparse.ArgumentTypeError("give low,high with 0 < low < high")
    return low, high


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Bisects quotes or fees on copies of one practice world.")
    parser.add_argument("mode", choices=("quote", "fee"))
    parser.add_argument("--level", type=int, choices=range(4, 9), default=8, help="4 to 8: a level with a competitor")
    parser.add_argument("--seed", required=True)
    parser.add_argument("--requests", help="comma-separated request ids to probe (default: a random --share)")
    parser.add_argument("--share", type=float, default=0.05, help="share of the week's requests to probe")
    parser.add_argument("--limit", type=int, help="stop after this many probed requests or orders")
    parser.add_argument(
        "--range", type=ratio_pair, help="low,high: quote / list price (default 0.6,2.5) or fee / typical fee (0.2,3)"
    )
    parser.add_argument("--resolution", type=float, default=0.01, help="bracket width / list price or typical fee")
    parser.add_argument("--checks", type=int, default=2, help="extra random trials per probe to test for a threshold")
    parser.add_argument("--window", type=int, default=180, help="fee: minutes a copy waits for a booking")
    parser.add_argument("--win-ratio", type=float, default=0.5, help="fee: the price / list price to win the order")
    parser.add_argument("--keep-free", type=int, default=2, help="practice slots left for teammates (default 2)")
    parser.add_argument("--out", default="out/probe", help="output folder (default out/probe)")
    args = parser.parse_args(argv)
    args.low, args.high = args.range or ((0.6, 2.5) if args.mode == "quote" else (0.2, 3.0))
    for name in ("SIGTERM", "SIGHUP"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), stop_on_signal)
    try:
        run(args)
    except SpreadError as error:
        sys.exit(f"spread: {error}")
    except KeyboardInterrupt:
        sys.exit("Stopped. The probe's worlds are deleted; the rows saved so far stay.")


if __name__ == "__main__":
    main()
