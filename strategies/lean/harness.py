"""The harness that `lean` plays in, a port of the TypeScript one (`src/harness/`): the desk keeps the books and does
the order mechanics that every strategy needs, the guard keeps a failing strategy from stopping the week, the journal
keeps our half of the week for a rebuild, and two loops play a practice week (`advance`) or a final (the event stream).
The strategy only decides: `quote`, `gig`, `hold`, `tick`, and it learns from `observe` and `sent`.

Against the TypeScript harness:
- It is synchronous. The desk sends when the TypeScript one would wait for its answer; live, it sends the quotes
  first, as the TypeScript one does.
- The time budget of each call holds in the final only. In a practice week a slow answer counts as `late` but is
  kept, so the week decides as the TypeScript one does however fast this machine is.
- When a strategy fails, the safe gig is the ops' gig shape with the starter's rising fees."""

from __future__ import annotations

import json
import math
import os
import re
import sys
import time
import traceback
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

from spread.client import SpreadError, Unreachable, World

from strategies.lean.js import js_round
from strategies.lean.note import read_note
from strategies.lean.ops import FIRST_TRY, Context, Roads, gig_shape, retry_after, undelivered, without_windows

HOUR, DAY = 60, 24 * 60
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DECLINE = 10  # a declined request is quoted at this many times its list price
OTHERS_PER_SEND = 10  # live, the most actions besides quotes in one request
BUDGET = {"build": 5.0, "observe": 1.5, "sent": 1.5, "quote": 1.5, "gig": 1.5, "tick": 3.0, "summary": 1.5}
WAKE_ON = [
    "price_request",
    "order_won",
    "order_changed",
    "order_cancelled",
    "visit_failed",
    "gig_expired",
    "deadline_close",
]
STEP = 10  # while dealers ask for prices the world moves in steps of this many minutes
OPENS, CLOSES = 8 * 60 - STEP, 18 * 60 + 20
QUIET_STEP = 60  # outside those hours it runs to the next event that needs an answer, and stops at least this often
ROOT = Path(__file__).resolve().parents[2]
JOURNALS = Path(os.environ.get("SPREAD_JOURNAL_DIR") or ROOT / "out" / "journal")
IDS = re.compile(r"\b[A-Za-z]?\d[\w:]*")


# ------------------------------------------------------------------------------------------------------- guard


class Guard:
    """Runs strategy calls so that no strategy can stop the week: an error, a late answer (live) or an answer that
    the world would refuse gives the safe answer."""

    def __init__(self, live: bool = False) -> None:
        self.live = live
        self.faults: Counter[str] = Counter()
        self.messages: dict[str, str] = {}

    def run[T](self, call: str, decide: Callable[[], T]) -> T | None:
        started = time.monotonic()
        try:
            answer = decide()
        except Exception as error:  # noqa: BLE001  (any error of the strategy takes the safe action)
            self.fault(f"{call} error", error)
            return None
        if time.monotonic() - started <= BUDGET[call]:
            return answer
        self.fault(f"{call} late")
        return None if self.live else answer

    def admit(self, call: str, actions: list[dict], request: dict | None = None) -> list[dict]:
        """The actions, rounded to whole numbers, that the world can take; each other one is a fault."""
        admitted = []
        for action in actions:
            try:
                rounded = whole(action)
                if sound(rounded, request):
                    admitted.append(rounded)
                    continue
            except ValueError, OverflowError, TypeError, RecursionError:
                pass
            self.fault(f"{call} invalid", json.dumps(action, default=str)[:300])
        return admitted

    def fault(self, kind: str, error: object = None) -> None:
        self.faults[kind] += 1
        if self.faults[kind] > 1:
            return
        why = "" if error is None else f": {error}"
        self.messages[kind] = why[2:]
        print(f"strategy {kind}{why}. The harness takes the safe action.", file=sys.stderr, flush=True)


def whole(value: Any) -> Any:
    """The value with every number rounded: the API takes whole minutes and cents only."""
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, int | float):
        return js_round(value)
    if isinstance(value, list):
        return [whole(item) for item in value]
    if isinstance(value, dict):
        return {key: whole(item) for key, item in value.items()}
    return value


def is_id(value: Any) -> bool:
    return isinstance(value, str) and len(value) > 0


def is_minute(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def is_cents(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def sound(action: Any, request: dict | None = None) -> bool:
    """Whether the world can take an action: every number whole, prices and fees at least 1 cent, a schedule of 1 to
    48 steps in time order whose fee never falls, and the ids, stops and audience present."""
    if not isinstance(action, dict):
        return False
    kind = action.get("type")
    if kind == "quote":
        prices = action.get("prices")
        if not isinstance(prices, dict) or not prices:
            return False
        offered = {o["kind"] for o in request["options"]} if request else None
        return is_id(action.get("requestId")) and all(
            (offered is None or k in offered) and is_cents(v) for k, v in prices.items()
        )
    if kind == "post":
        return (
            is_stops(action.get("stops"))
            and is_audience(action.get("audience"))
            and is_schedule(action.get("schedule"))
        )
    if kind == "reprice":
        return is_id(action.get("gigId")) and is_schedule(action.get("schedule"))
    if kind == "offer":
        return is_id(action.get("gigId")) and is_id(action.get("driverId")) and is_cents(action.get("feeCents"))
    if kind in ("withdraw", "release"):
        return is_id(action.get("gigId"))
    return False


def is_stops(stops: Any) -> bool:
    def is_stop(stop: Any) -> bool:
        if not isinstance(stop, dict) or not is_id(stop.get("orderId")) or not is_minute(stop.get("leg")):
            return False
        if stop.get("kind") not in ("pickup", "delivery"):
            return False
        window = stop.get("window")
        if window is not None and not (
            isinstance(window, dict) and is_minute(window.get("from")) and is_minute(window.get("to"))
        ):
            return False
        return all(stop.get(flag) is None or isinstance(stop[flag], bool) for flag in ("withPlates", "withCharging"))

    return isinstance(stops, list) and len(stops) > 0 and all(is_stop(stop) for stop in stops)


def is_audience(audience: Any) -> bool:
    return (
        isinstance(audience, dict)
        and isinstance(audience.get("experienced"), bool)
        and isinstance(audience.get("manualLicence"), bool)
    )


def is_schedule(schedule: Any) -> bool:
    if not isinstance(schedule, list) or not 1 <= len(schedule) <= 48:
        return False
    for i, step in enumerate(schedule):
        if not isinstance(step, dict) or not is_minute(step.get("at")) or not is_cents(step.get("feeCents")):
            return False
        if i > 0 and not (step["at"] > schedule[i - 1]["at"] and step["feeCents"] >= schedule[i - 1]["feeCents"]):
            return False
    return True


# ----------------------------------------------------------------------------------------------------- journal


class Journal:
    """Our half of the week: every action the desk sent, with the world's answer, one JSON line each in
    out/journal/<world id>.jsonl (SPREAD_JOURNAL_DIR changes the folder). A rebuild feeds a new strategy both."""

    def __init__(self, world_id: str) -> None:
        self.file = JOURNALS / f"{world_id}.jsonl"
        self.broken = False

    def read(self) -> list[dict]:
        if not self.file.exists():
            return []
        lines = []
        for text in self.file.read_text().split("\n"):
            try:
                if text:
                    lines.append(json.loads(text))
            except ValueError:
                pass
        return lines

    def write(self, line: dict) -> None:
        if self.broken:
            return
        try:
            self.file.parent.mkdir(parents=True, exist_ok=True)
            with self.file.open("a") as f:
                f.write(json.dumps(line, separators=(",", ":")) + "\n")
        except OSError as error:
            self.broken = True
            print(
                f"Could not write the journal {self.file}: {error}. A rebuild relearns the events only.",
                file=sys.stderr,
            )


# ------------------------------------------------------------------------------------------------- safe gig


def starter_gig(need: dict, books: Desk, level: int) -> dict:
    """The safe gig when the strategy fails: the ops' gig shape, and the starter's fees (rising, or steep from the
    deadline warning on)."""
    order, previous = need["order"], need.get("previous")
    request = books.requests[order["id"]]

    def fees(cars: int) -> list[dict]:
        fee = request["referenceFeeCents"] * cars / len(order["legs"])
        urgent = order["id"] in books.urgent
        ks = [0] if level == 1 else ([0, 1, 2, 3, 4] if urgent else [0, 1, 2, 3, 4, 5])
        if urgent:
            return [{"at": books.now + k * 30, "feeCents": max(1, js_round(fee * (1.5 + k / 4)))} for k in ks]
        return [{"at": books.now + k * HOUR, "feeCents": max(1, js_round(fee * (1 + k / 10)))} for k in ks]

    if previous:
        stops = without_windows(previous["stops"], math.inf) if need["why"] == "repost" else previous["stops"]
        cars = sum(1 for stop in previous["stops"] if stop["kind"] == "pickup")
        return {"stops": stops, "audience": previous["audience"], "schedule": fees(cars)}
    failed = need.get("failed")
    retry = retry_after(failed, order, request, need["legs"][0], books.now) if failed else FIRST_TRY
    facts = read_note(request.get("note"), request["arrivedAt"])
    context = Context(books.roads, [], level)
    shapes = gig_shape(order, need["legs"], facts, retry, books.now, context)
    stops = [stop for shape in shapes for stop in shape["stops"]]
    audience = {
        "experienced": any(leg["car"]["premium"] for leg in order["legs"]),
        "manualLicence": retry.manual_licence or facts.manual,
    }
    return {"stops": stops, "audience": audience, "schedule": fees(len(need["legs"]))}


class Declines:
    """What the harness plays when a strategy fails to build: it declines every request."""

    every = None
    books: Any = None

    def __init__(self, level: int) -> None:
        self.level = level

    def observe(self, event: dict) -> None:
        pass

    def quote(self, request: dict, books: Any) -> None:
        return None

    def gig(self, need: dict, books: Desk) -> dict:
        return starter_gig(need, books, self.level)

    def hold(self, need: dict, books: Any) -> bool:
        return False

    def sent(self, action: dict, result: dict, books: Any) -> None:
        pass

    def tick(self, books: Any) -> list:
        return []

    def summary(self) -> str:
        return ""


# -------------------------------------------------------------------------------------------------------- desk


def post_of(plan: Any) -> dict:
    plan = plan if isinstance(plan, dict) else {}
    return {
        "type": "post",
        "stops": plan.get("stops"),
        "audience": plan.get("audience"),
        "schedule": plan.get("schedule"),
    }


def carries(gig: dict, order_id: str, leg: int) -> bool:
    """Whether a gig or a post picks up the order's leg."""
    return any(s["orderId"] == order_id and s["leg"] == leg and s["kind"] == "pickup" for s in gig["stops"])


def legs_of(action: dict, order_id: str) -> list[int]:
    return [s["leg"] for s in action["stops"] if s["orderId"] == order_id and s["kind"] == "pickup"]


class Desk:
    """The books of the week, the order mechanics, and the outbox. The strategy decides each quote and each gig."""

    def __init__(self, world: World, strategy: Any, guard: Guard, snapshot: dict, roads: Roads, live: bool = False):
        self.world, self.strategy, self.guard, self.roads, self.live = world, strategy, guard, roads, live
        self.journal = Journal(world.id)
        self.level: int = strategy.level
        self.now: int = snapshot["now"]
        self.ends_at: int = snapshot["endsAt"]
        self.seen = -1
        self.next_tick = self.tick_after(self.now)
        self.outbox: list[dict] = []
        self.requests: dict[str, dict] = {}
        self.orders: dict[str, dict] = {}  # the orders won and not cancelled
        self.leg_gigs: dict[str, dict[int, str]] = {}  # order id -> leg -> the gig that carries the leg
        self.booked: set[str] = set()
        self.posts: dict[str, dict] = {}  # gig id -> the post that made it
        self.urgent: set[str] = set()  # the orders whose deadline warning has come
        self.refused: Counter[str] = Counter()
        self.swept: dict[str, int] = {}  # "<order id> <leg>" -> when the sweep last posted the leg
        strategy.books = self

    def rejoin(self, snapshot: dict, history: list[dict]) -> None:
        """Rebuilds the books from the world, and the strategy from the event log and the journal. Then answers what it
        missed: failed visits without a new gig, open requests, and the legs left without a gig."""
        for gig in snapshot["gigs"]:
            post = {"type": "post", "stops": gig["stops"], "audience": gig["audience"], "schedule": gig["schedule"]}
            self.posts[gig["id"]] = post
            if gig["status"] in ("booked", "working", "done"):
                self.booked.add(gig["id"])
            if gig["status"] in ("open", "booked", "working"):
                self.carry(post, gig["id"])
        for event in history:
            if event["kind"] == "price_request":
                self.requests[event["request"]["id"]] = event["request"]
            elif event["kind"] == "deadline_close":
                self.urgent.add(event["orderId"])
        for order in snapshot["orders"]:
            if order["id"] in self.requests and order["status"] != "cancelled":
                self.orders[order["id"]] = order
        self.replay(history, self.journal.read())
        self.now = snapshot["now"]
        self.seen = history[-1]["seq"] if history else -1
        for event in history:
            order = self.orders.get(event.get("orderId", "")) if event["kind"] == "visit_failed" else None
            if order is None or order["deliveredAt"][event["leg"]] is not None:
                continue
            later = any(
                g["postedAt"] >= event["at"]
                and g["id"] != event["gigId"]
                and carries(g, event["orderId"], event["leg"])
                for g in snapshot["gigs"]
            )
            if not later:
                self.retry(event["orderId"], event["leg"], event["reason"])
        for request in snapshot["openRequests"]:
            self.quote(request)
        self.sweep()

    def replay(self, history: list[dict], journal: list[dict]) -> None:
        """Feeds the strategy the week so far in the order it lived it."""
        index = 0

        def sent_before(seq: float) -> None:
            nonlocal index
            while index < len(journal) and journal[index]["seq"] < seq:
                line = journal[index]
                self.now = line["at"]
                self.guard.run("sent", lambda line=line: self.strategy.sent(line["action"], line["result"], self))
                index += 1

        for event in history:
            sent_before(event["seq"])
            self.now = event["at"]
            self.observe(event)
        sent_before(math.inf)

    def handle(self, event: dict) -> None:
        if event["seq"] <= self.seen:
            return
        self.seen = event["seq"]
        self.now = max(self.now, event["at"])
        self.observe(event)
        kind = event["kind"]
        if kind == "price_request":
            self.quote(event["request"])
        elif kind == "order_won":
            self.win(event["order"])
        elif kind == "order_changed":
            self.change(event["order"])
        elif kind == "order_cancelled":
            self.cancel(event)
        elif kind == "visit_failed":
            self.retry(event["orderId"], event["leg"], event["reason"])
        elif kind == "gig_expired":
            self.repost(event["gigId"])
        elif kind == "deadline_close":  # it comes again when a driver drops the car after the first warning
            self.raise_fees(event["orderId"])
        elif kind == "gig_booked" or (kind == "offer_answered" and event["answer"] == "accepted"):
            self.booked.add(event["gigId"])
        elif kind in ("gig_dropped", "no_show"):
            self.booked.discard(event["gigId"])
        elif kind == "delivered":
            self.delivered(event["orderId"], event["leg"], event["at"])

    def tick(self) -> None:
        """The strategy's periodic actions once `every` minutes have passed, then the sweep."""
        if self.now < self.next_tick:
            return
        self.next_tick = self.tick_after(self.now)
        actions = self.guard.run("tick", lambda: self.strategy.tick(self))
        self.outbox += self.guard.admit("tick", actions if isinstance(actions, list) else [])
        self.sweep()

    def tick_after(self, minute: int) -> float:
        every = self.strategy.every
        return math.inf if every is None else minute + max(1, js_round(every))

    def observe(self, event: dict) -> None:
        self.guard.run("observe", lambda: self.strategy.observe(event))

    def quote(self, request: dict) -> None:
        """The strategy's prices, or a decline: far above list, or no quote up to level 3."""
        self.requests[request["id"]] = request
        prices = self.guard.run("quote", lambda: self.strategy.quote(request, self))
        answer = [{"type": "quote", "requestId": request["id"], "prices": prices}] if prices else []
        admitted = self.guard.admit("quote", answer, request)
        if admitted:
            self.outbox.append(admitted[0])
        elif self.level > 3:
            first = request["options"][0]
            self.outbox.append(
                {
                    "type": "quote",
                    "requestId": request["id"],
                    "prices": {first["kind"]: first["listPriceCents"] * DECLINE},
                }
            )

    def plan(self, need: dict) -> list[dict]:
        """The strategy's gigs for the need, and the safe gig for every leg that they leave out."""

        def gigs() -> list:
            answer = self.strategy.gig(need, self)
            return answer if isinstance(answer, list) else [answer]

        answer = self.guard.run("gig", gigs)
        if answer == []:
            self.guard.fault("gig empty")
        plans = self.guard.admit("gig", [post_of(plan) for plan in answer or []])
        left = [leg for leg in need["legs"] if not any(carries(plan, need["order"]["id"], leg) for plan in plans)]
        if not left:
            return plans
        safe = self.guard.run("gig", lambda: starter_gig({**need, "legs": left}, self, self.level))
        return plans + self.guard.admit("gig", [post_of(safe)] if safe else [])

    def delivered(self, order_id: str, leg: int, at: int) -> None:
        self.leg_gigs.get(order_id, {}).pop(leg, None)
        order = self.orders.get(order_id)
        if order:
            order["deliveredAt"][leg] = at

    def win(self, order: dict) -> None:
        if order["id"] not in self.requests or order["id"] in self.orders:
            return
        self.orders[order["id"]] = order
        self.post("won", order, undelivered(order))

    def change(self, order: dict) -> None:
        if order["id"] not in self.orders:
            return
        self.orders[order["id"]] = order
        if self.withdraw(order["id"]):
            self.post("changed", order, undelivered(order))

    def cancel(self, event: dict) -> None:
        """The world has stopped a cancelled order's car. A withdrawn gig's other cars are left to the sweep."""
        self.orders.pop(event["orderId"], None)
        self.leg_gigs.pop(event["orderId"], None)
        for gig in event["gigs"]:
            if gig["outcome"] == "withdrawn":
                self.forget(gig["gigId"])

    def repost(self, gig_id: str) -> None:
        """Posts a gig again when one of its windows ended before a driver booked it."""
        previous = self.posts.get(gig_id)
        if not previous or not any(
            self.leg_gigs.get(s["orderId"], {}).get(s["leg"]) == gig_id for s in previous["stops"]
        ):
            return
        for stop in previous["stops"]:
            self.leg_gigs.get(stop["orderId"], {}).pop(stop["leg"], None)
        order = self.orders.get(previous["stops"][0]["orderId"])
        if not order:
            return
        self.outbox += self.plan(
            {"why": "repost", "order": order, "legs": legs_of(previous, order["id"]), "previous": previous}
        )

    def raise_fees(self, order_id: str) -> None:
        """From the order's deadline warning on, its gigs that no driver holds take the urgent fees."""
        order = self.orders.get(order_id)
        if not order:
            return
        self.urgent.add(order_id)
        self.send_post_of(order_id)
        for gig_id in self.gigs_of(order_id):
            previous = self.posts.get(gig_id)
            if gig_id in self.booked or not previous:
                continue
            plans = self.plan(
                {"why": "urgent", "order": order, "legs": legs_of(previous, order_id), "previous": previous}
            )
            if plans:
                self.outbox.append({"type": "reprice", "gigId": gig_id, "schedule": plans[0]["schedule"]})

    def retry(self, order_id: str, leg: int, reason: str) -> None:
        order = self.orders.get(order_id)
        if not order:
            return
        self.leg_gigs.get(order_id, {}).pop(leg, None)  # the world has taken the car out of the failed gig
        self.post("retry", order, [leg], reason)

    def post(self, why: str, order: dict, legs: list[int], failed: str | None = None) -> None:
        """Posts the strategy's gigs for the legs. A leg that none of them got goes again as a gig of its own."""
        need = {"why": why, "order": order, "legs": legs, "failed": failed}
        if self.held(need):
            return
        plans = self.plan(need)
        self.outbox += plans
        if len(legs) == 1:
            return
        self.answered(plans)
        left = [
            leg for leg in legs if leg not in self.leg_gigs.get(order["id"], {}) and not self.waiting(order["id"], leg)
        ]
        for leg in left:
            self.post("split", order, [leg], failed)

    def held(self, need: dict) -> bool:
        return self.guard.run("gig", lambda: self.strategy.hold(need, self)) is True

    def sweep(self) -> None:
        """Posts every undelivered leg of a live order that no gig carries and no post waits for, at most once an hour."""
        for order in list(self.orders.values()):
            legs = [
                leg
                for leg in undelivered(order)
                if leg not in self.leg_gigs.get(order["id"], {})
                and not self.waiting(order["id"], leg)
                and not self.now < self.swept.get(f"{order['id']} {leg}", -math.inf) + HOUR
            ]
            if not legs or self.held({"why": "lost", "order": order, "legs": legs}):
                continue
            for leg in legs:
                self.swept[f"{order['id']} {leg}"] = self.now
            self.post("lost", order, legs)

    def gigs_of(self, order_id: str) -> list[str]:
        """The gigs that carry the order's undelivered legs: one, or one for each leg of a split trade-in."""
        return list(dict.fromkeys(self.leg_gigs.get(order_id, {}).values()))

    def waiting(self, order_id: str, leg: int) -> bool:
        return any(action["type"] == "post" and carries(action, order_id, leg) for action in self.outbox)

    def carry(self, action: dict, gig_id: str) -> None:
        """Remembers a gig that the world accepted: the post that made it, and the legs it carries."""
        for stop in action["stops"]:
            self.leg_gigs.setdefault(stop["orderId"], {})[stop["leg"]] = gig_id
        self.posts[gig_id] = action

    def withdraw(self, order_id: str) -> bool:
        """Takes an order's gigs out of the app. False, and nothing withdrawn, when a driver holds one of them."""
        self.send_post_of(order_id)
        gigs = self.gigs_of(order_id)
        if any(gig_id in self.booked for gig_id in gigs):
            return False
        self.leg_gigs.pop(order_id, None)
        self.outbox += [{"type": "withdraw", "gigId": gig_id} for gig_id in gigs]
        return True

    def send_post_of(self, order_id: str) -> None:
        """A post of the order still waiting goes to the world now, so the desk knows its gig."""
        posts = [a for a in self.outbox if a["type"] == "post" and any(s["orderId"] == order_id for s in a["stops"])]
        if posts:
            self.answered(posts)

    def send(self) -> None:
        self.answered(list(self.outbox))

    def answered(self, actions: list[dict]) -> None:
        """Sends the outbox until the world has answered these actions."""
        while any(any(a is b for b in self.outbox) for a in actions):
            batch = self.take()
            self.read_results(batch, self.act(batch))

    def take(self) -> list[dict]:
        """The next request's actions: in practice all of them in order; live the quotes first, then posts and
        withdrawals, then the rest, with at most OTHERS_PER_SEND actions besides the quotes."""

        def rank(action: dict) -> int:
            if not self.live:
                return 0
            return 0 if action["type"] == "quote" else 1 if action["type"] in ("post", "withdraw") else 2

        ranked = sorted(self.outbox, key=rank)
        batch, others = [], 0
        for action in ranked:
            if self.live and rank(action) > 0:
                others += 1
                if others > OTHERS_PER_SEND:
                    continue
            batch.append(action)
        self.outbox = [a for a in self.outbox if not any(a is b for b in batch)]
        return batch

    def act(self, actions: list[dict]) -> list[dict]:
        """The world's answers. A batch the server refuses as a whole goes again in halves."""
        if not actions:
            return []
        try:
            return self.world.act(actions)
        except Unreachable:
            raise
        except SpreadError as error:
            if error.status not in (0, 400):
                raise
            if len(actions) == 1:
                return [{"ok": False, "reason": str(error)}]
            half = math.ceil(len(actions) / 2)
            return self.act(actions[:half]) + self.act(actions[half:])

    def read_results(self, actions: list[dict], results: list[dict]) -> None:
        """Books the gigs that the world made and the ones withdrawn, counts the refused actions, writes each to the
        journal and tells the strategy. A refused post of one car with windows of its own goes again without them."""
        for i, action in enumerate(actions):
            result = results[i] if i < len(results) else {"ok": False, "reason": "no answer"}
            if not result.get("ok"):
                self.refused[f"{action['type']}: {IDS.sub('#', str(result.get('reason', '')))}"] += 1
                cars = sum(1 for s in action.get("stops", []) if s["kind"] == "pickup")
                if action["type"] == "post" and cars == 1 and any(s.get("window") for s in action["stops"]):
                    stops = [{k: v for k, v in s.items() if k != "window"} for s in action["stops"]]
                    self.outbox.append({**action, "stops": stops})
            elif action["type"] == "post":
                self.carry(action, result["id"])
            elif action["type"] == "withdraw":
                self.forget(action["gigId"])
            self.journal.write({"seq": self.seen, "at": self.now, "action": action, "result": result})
            self.guard.run("sent", lambda action=action, result=result: self.strategy.sent(action, result, self))

    def forget(self, gig_id: str) -> None:
        """Drops a withdrawn gig from the legs it carried."""
        for legs in self.leg_gigs.values():
            for leg in [leg for leg, gig in legs.items() if gig == gig_id]:
                del legs[leg]


# ------------------------------------------------------------------------------------------------------- loops


def dealers_ask(minute: int) -> bool:
    """Whether a price request can be open at `minute`."""
    return (minute // DAY) % 7 < 5 and OPENS <= minute % DAY < CLOSES


def play_practice(world: World, desk: Desk) -> None:
    """Plays a practice world to its end, one request a step: the advance carries the actions decided on the step
    before, then moves the clock. It stops at each midnight for a report."""
    while desk.now < desk.ends_at:
        day = desk.now // DAY
        midnight = (day + 1) * DAY
        actions, desk.outbox = desk.outbox, []
        asking = dealers_ask(desk.now)
        until = min(desk.ends_at, midnight, desk.now + (STEP if asking else QUIET_STEP))
        if asking:
            step = world.advance(to=until, actions=actions)
        else:
            step = world.advance(until=WAKE_ON, max=until, actions=actions)  # type: ignore[arg-type]
        desk.read_results(actions, step["results"])
        desk.now = step["now"]
        for event in step["events"]:
            desk.handle(event)
        desk.tick()
        if desk.now // DAY > day:
            report(WEEKDAYS[day % 7], world.score())


def play_live(world: World, desk: Desk) -> None:
    """Answers events as they come, quotes first. After a second without an event it reads the clock and sweeps."""
    if desk.now >= desk.ends_at:
        return
    desk.live = True
    desk.send()
    for event in world.stream(after=desk.seen, idle=1.0):
        if desk.now >= desk.ends_at:
            break
        day = desk.now // DAY
        if event is not None:
            desk.handle(event)
        else:
            desk.now = max(desk.now, world.client.final()["now"])
            desk.sweep()
        desk.tick()
        desk.send()
        if desk.now // DAY > day:
            report(WEEKDAYS[day % 7], world.score())
        if desk.now >= desk.ends_at:
            break
    desk.send()


def report(label: str, score: dict) -> None:
    orders = (
        f"{score['wonOrders']:>4} orders  {score['onTimeShare']:6.1%} on time  "
        f"{score['undeliveredShare']:5.1%} not delivered"
    )
    print(
        f"{label:<9}  margin €{score['marginCents'] / 100:>11,.2f}  revenue €{score['revenueCents'] / 100:>11,.2f}  {orders}",
        flush=True,
    )


def all_events(world: World) -> list[dict]:
    events: list[dict] = []
    while True:
        page = world.events(after=events[-1]["seq"] if events else -1)
        if not page:
            return events
        events += page


def play(world: World, build: Callable[[list, dict], Any], level: int, live: bool) -> dict:
    """Plays the world from where it is now to its end, and returns its score. There is one way in, for the first
    start, our own restart and a server that went away alike: rebuild the books and a new strategy from the world, its
    event log and our journal, then run the loop. Live, any error is printed and the week rebuilt."""
    while True:
        try:
            history = all_events(world)
            snapshot = world.snapshot()
            roster, world_map = world.roster(), world.client.map()
            guard = Guard(live)
            strategy = guard.run(
                "build", lambda roster=roster, world_map=world_map: build(roster, world_map)
            ) or Declines(level)
            desk = Desk(world, strategy, guard, snapshot, Roads(dict(world_map)), live)
            desk.rejoin(snapshot, history)
            (play_live if live else play_practice)(world, desk)
            if live:
                desk.send()
            score = world.score()
            finish(score, desk)
            return score
        except Unreachable as error:
            print(f"spread: {error}. Rebuilding in a second.", file=sys.stderr, flush=True)
        except Exception:
            if not live:
                raise
            print(f"{traceback.format_exc()}Rebuilding in a second.", file=sys.stderr, flush=True)
        time.sleep(1)


def finish(score: dict, desk: Desk) -> None:
    """The end of a week: the score, whether it is ranked, and the strategy's line, faults and refused actions."""
    report("End", score)
    print(
        "Ranked."
        if score["ranked"]
        else "Not ranked: no order won."
        if score["wonOrders"] == 0
        else "Not ranked: the delivery minimum is 90% of the orders on time."
    )
    if isinstance(desk.strategy, Declines):
        why = desk.guard.messages.get("build error") or "too slow"
        print(f"The strategy did not build ({why}): the harness declined every request.")
    summary = desk.guard.run("summary", lambda: desk.strategy.summary())
    if summary:
        print(summary)
    if desk.guard.faults:
        print("Strategy faults: " + ", ".join(f"{k} {n}" for k, n in desk.guard.faults.most_common()) + ".")
    if desk.refused:
        print("Refused actions: " + ", ".join(f"{k} {n}" for k, n in desk.refused.most_common()) + ".")
