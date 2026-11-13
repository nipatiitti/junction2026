"""Offline replay of every strategy on the saved weeks (#119).

There is no offline model of the Spread world, so this replays the saved weeks instead: it feeds each week's
recorded events, in order, to each strategy of `strategies/` the way `dispatch.py` feeds them, records what the
strategy decides, and scores each decision against what the week shows really happened. Where the week cannot tell
how a different decision would have ended, the decision counts as unknown. No server, no key, nothing played.

    uv run python -m analysis.replay [FOLDER ...] [--out out/replay.html] [--csv out/replay.csv] [--jobs 4]
                                     [--probe out/probe] [--port 8001] [--no-serve]

Without folders it reads every week under `out/scrape` (the team's release) and `data/scrape` (the committed weeks
and our saved runs). It also scores pricing and fees on probe.py's rows in `out/probe` (#145), and puts the starter's
weeks next to ours. analysis/README.md ("Offline replay") says what each strategy's numbers mean.
"""

from __future__ import annotations

import argparse
import copy
import csv
import gzip
import heapq
import itertools
import json
import os
import random
import re
import statistics
import subprocess
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import dispatch
from analysis import report as r
from strategies.baseline import BaselineFees
from strategies.bundling.bundling import fee_share, saving
from strategies.notes import check

ROOTS = ["out/scrape", "data/scrape"]
HOUR = 60
DECLINE = 5  # a quote at five times the list price or more is a decline (as in analysis.facts)
FILES = ("events.jsonl.gz", "reveal.json.gz", "snapshot.json.gz", "drivers.json.gz", "meta.json")
STRATEGIES = ["notes", "admission", "pricing", "fees", "bundling", "offers"]
FIRST = ("price_request", "order_won", "order_changed", "order_lost", "forecast")  # before a post of the same minute


# ---------------------------------------------------------------- the saved weeks


class OfflineWorld:
    """What `dispatch.Desk` reads from a world when it starts: the driver list and the map. It acts on nothing,
    so the desk can be built, and its strategies with it, exactly as `dispatch.py` builds them."""

    def __init__(self, roster: list[dict], world_map: dict):
        self._roster = roster
        self.client = self  # `Desk` reads the map as `world.client.map()`
        self._map = world_map

    def roster(self) -> list[dict]:
        return self._roster

    def map(self) -> dict:
        return self._map

    def act(self, actions: list[dict]) -> list[dict]:
        raise RuntimeError("the offline replay sends no actions")


def find_weeks(roots: list[str]) -> tuple[list[Path], int]:
    """Every saved week that was played (not passive) and has its reveal, once per world, and the number of played
    worlds skipped because no saved copy has a reveal (a ranking run's week has none)."""
    found: dict[str, Path] = {}
    no_reveal: set[str] = set()
    for root in roots:
        for meta_path in sorted(Path(root).rglob("meta.json")):
            folder = meta_path.parent
            if not all((folder / name).exists() for name in FILES) or find_map(folder) is None:
                continue
            meta = json.loads(meta_path.read_text())
            if meta.get("policy") == "passive" or not (meta.get("score") or {}).get("wonOrders"):
                continue
            world = meta.get("worldId") or str(folder)
            if world in found:
                continue
            if not has_reveal(folder):
                no_reveal.add(world)
                continue
            found[world] = folder
    return list(found.values()), len(no_reveal - found.keys())


def has_reveal(folder: Path) -> bool:
    """Whether the week's reveal has the requests. A ranking run is not revealed: its `reveal.json.gz` is `{}`."""
    return "requests" in read_gz(folder / "reveal.json.gz")


def find_map(folder: Path) -> Path | None:
    """The map of a week: `map.json` in the experiment's folder (or in `runs/`), above the week's folder."""
    for parent in folder.parents:
        if (parent / "map.json").exists():
            return parent / "map.json"
        if parent.name == "scrape":
            return None
    return None


def experiment_of(folder: Path) -> str:
    """The folder after `scrape/`: `runs` (our dispatch.py), `starter`, `explore-win`, ..."""
    parts = folder.parts
    return parts[parts.index("scrape") + 1] if "scrape" in parts else folder.parent.name


def read_gz(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as file:
        return json.load(file)


class Week:
    """One saved week: its events in order, the reveal, the end snapshot, the driver list and the map."""

    def __init__(self, folder: Path):
        self.folder = folder
        self.meta = json.loads((folder / "meta.json").read_text())
        self.level: int = self.meta["level"]
        self.experiment = experiment_of(folder)
        if self.experiment == "runs" and self.meta.get("policy") not in (None, "dispatch"):
            self.experiment = f"runs-{self.meta['policy']}"  # saved weeks of another system
        with gzip.open(folder / "events.jsonl.gz", "rt", encoding="utf-8") as file:
            self.events = sorted((json.loads(line) for line in file), key=lambda e: (e["at"], e["seq"]))
        self.reveal = read_gz(folder / "reveal.json.gz")
        self.snapshot = read_gz(folder / "snapshot.json.gz")
        self.roster = read_gz(folder / "drivers.json.gz")
        self.map = json.loads(find_map(folder).read_text())
        self.requests = {e["request"]["id"]: e["request"] for e in self.events if e["kind"] == "price_request"}
        self.recorded = {row["request"]["id"]: row for row in self.reveal["requests"]}
        self.gigs = {g["id"]: g for g in self.snapshot["gigs"]}
        self.gig_orders = {g["id"]: dispatch.orders_in(g) for g in self.snapshot["gigs"]}
        self.orders = {o["id"]: o for o in self.snapshot["orders"]}  # every order won, as it ended
        # The world judges lateness (a note's deadline counts too), so the ledger says which orders were late.
        self.late = {
            e["line"]["orderId"]
            for e in self.events
            if e["kind"] == "ledger" and e["line"]["kind"] in ("late_refund", "undelivered_penalty")
        }
        self.versions: dict[str, list[tuple[int, dict]]] = defaultdict(list)  # order id -> (minute, order) in order
        for e in self.events:
            if e["kind"] in ("order_won", "order_changed"):
                self.versions[e["order"]["id"]].append((e["at"], e["order"]))
        # The gigs the week posted, at the minute it posted them: after that minute's requests and wins, which
        # they answer, and before its other events, such as a booking of the new gig.
        posts = [(g["postedAt"], 1, i, "post", g) for i, g in enumerate(self.snapshot["gigs"])]
        events = [(e["at"], 0 if e["kind"] in FIRST else 2, e["seq"], "event", e) for e in self.events]
        self.timeline = [(at, kind, item) for at, _, _, kind, item in sorted(posts + events, key=lambda x: x[:3])]

    def info(self) -> dict:
        score = self.meta.get("score") or {}
        return {
            "experiment": self.experiment,
            "level": self.level,
            "seed": self.meta.get("seed"),
            "world": self.meta.get("worldId") or self.folder.name,
            "policy": self.meta.get("policy"),
            "margin": score.get("marginCents"),
            "won": score.get("wonOrders"),
            "on_time": score.get("onTimeShare"),
            # For "Every strategy against none" and "Every saved week": the rest of the score, what the week paid
            # its drivers per car delivered, and the commit of a saved run (record.py).
            "revenue": score.get("revenueCents"),
            "undelivered": score.get("undeliveredShare"),
            "ranked": score.get("ranked"),
            "driver_fees": -sum(
                e["line"]["cents"] for e in self.events if e["kind"] == "ledger" and e["line"]["kind"] == "driver_fee"
            ),
            "cars": sum(1 for e in self.events if e["kind"] == "delivered"),
            "version": self.meta.get("version"),
        }

    def desk(self) -> dispatch.Desk:
        """A fresh desk of our dispatch.py for this week, with every strategy built as dispatch.py builds it."""
        return dispatch.Desk(OfflineWorld(self.roster, self.map), self.level, 0)

    def on_time(self, order: dict) -> bool:
        """Every car delivered and no late refund or penalty: the score's on-time share counts the same."""
        return order["id"] not in self.late and all(at is not None for at in order["deliveredAt"])

    def order_at(self, order_id: str, at: int) -> dict | None:
        """The order as the week knew it at that minute: its last `order_won` or `order_changed` by then."""
        known = [order for minute, order in self.versions.get(order_id, []) if minute <= at]
        return known[-1] if known else None

    def order_margins(self) -> dict[str, int]:
        """Each order's account lines: its revenue less its drivers' fees, refunds and penalties, in cents.
        A fee for a bundle is split evenly over the bundle's orders."""
        margins: dict[str, float] = defaultdict(float)
        for e in self.events:
            if e["kind"] != "ledger":
                continue
            line = e["line"]
            if line.get("orderId"):
                margins[line["orderId"]] += line["cents"]
            elif line.get("gigId") in self.gig_orders:
                orders = self.gig_orders[line["gigId"]]
                for order_id in orders:
                    margins[order_id] += line["cents"] / len(orders)
        return {k: round(v) for k, v in margins.items()}


def share(part: float, whole: float) -> float | None:
    return part / whole if whole else None


def median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def real_quote(row: dict | None) -> dict[str, int] | None:
    """The prices the week quoted for a request, or None when it declined (five times the list price) or sent none."""
    if not row or not row.get("quote"):
        return None
    lists = {o["kind"]: o["listPriceCents"] for o in row["request"]["options"]}
    prices = {k: v for k, v in row["quote"].items() if k in lists}
    if not prices or all(v >= DECLINE * lists[k] for k, v in prices.items()):
        return None
    return prices


# ---------------------------------------------------------------- the strategies


def replay_notes(w: Week) -> dict:
    """strategies/notes: reads every won car's note and compares each fact with the reveal's truth, next to the
    organisers' starter reader. The scoring is strategies/notes/check.py's."""
    truths = {o["orderId"]: o for o in w.reveal["orders"]}
    legs: list[check.Leg] = []
    for row in w.reveal["requests"]:
        request, order = row["request"], truths.get(row["request"]["id"])
        if row.get("outcome") != "won" or not request.get("note") or order is None:
            continue
        deadlines = {o["kind"]: o["deadline"] for o in request["options"]}
        for i, truth in enumerate(order["legs"]):
            stated = request["legs"][i]
            legs.append(
                check.Leg(
                    note=request["note"]["text"],
                    language=request["note"].get("language") or "",
                    leg=i,
                    arrived_at=request["arrivedAt"],
                    deadline=deadlines.get(row.get("option"), max(deadlines.values())),
                    latest=max(deadlines.values()),
                    stated_from=stated["pickup"]["window"]["from"],
                    stated_to=stated["pickup"]["window"]["to"],
                    delivery_from=stated["delivery"]["window"]["from"],
                    pickup_hours=hours(stated["pickup"].get("hours")),
                    delivery_hours=hours(stated["delivery"].get("hours")),
                    truth={
                        "earliest pickup": max(truth["readyAt"], truth.get("releasedAt") or 0),
                        "pickup hours": hours(truth.get("pickupHours")),
                        "delivery hours": hours(truth.get("deliveryHours")),
                        "deadline": truth.get("noteDeadline"),
                        "manual gearbox": bool(truth.get("manualGearbox")),
                        "no plates": bool(truth.get("needsPlates")),
                        "summer tyres": bool(truth.get("summerTyres")),
                    },
                )
            )
    ours, starter = check.score(legs, check.ours), check.score(legs, check.starters)

    def total(scores: dict, i: int) -> int:
        return sum(v[i] for v in scores.values())

    return {
        "cars": len(legs),
        "facts": total(ours, 0),
        "changed": total(ours, 2),
        "caught_n": total(ours, 3),
        "starter_caught_n": total(starter, 3),
        "agree": share(total(ours, 1), total(ours, 0)),
        "caught": share(total(ours, 3), total(ours, 2)),
        "starter_agree": share(total(starter, 1), total(starter, 0)),
        "starter_caught": share(total(starter, 3), total(starter, 2)),
        "_facts": {fact: [*ours[fact], starter[fact][1], starter[fact][3]] for fact in check.FACTS},
    }


def hours(h: dict | None) -> tuple[int, int] | None:
    return None if not h or h.get("opens") is None or h.get("closes") is None else (h["opens"], h["closes"])


def replay_quotes(w: Week) -> dict:
    """strategies/admission and strategies/pricing, through `Desk.quote` of dispatch.py (which also declines a
    request whose note's deadline passes before the car can be collected). The desk sees the week's events, its
    gigs and its drivers' bookings, but holds only the orders it would have quoted: an order it declines is no
    load for admission and no dealer for pricing's trust. Pricing learns a quote's answer only where the week can
    tell it (`classify`): the week's answer to its own, different price would teach it a wrong lesson."""
    desk = w.desk()
    accepted: dict[str, dict[str, int]] = {}  # request id -> the prices the replay quotes
    for at, kind, item in w.timeline:
        desk.now = at
        if kind == "post":
            for stop in item["stops"]:
                desk.leg_gigs.setdefault(stop["orderId"], {})[stop["leg"]] = item["id"]
            continue
        e, k = item, item["kind"]
        ours = e.get("order", {}).get("id") in accepted
        rid = e["order"]["id"] if k == "order_won" else e.get("requestId") if k == "order_lost" else None
        if rid in accepted and classify(accepted[rid], w.recorded.get(rid)) not in ("win", "lose"):
            desk.pricing.quotes.pop(rid, None)  # the week cannot tell this quote's answer: pricing learns nothing
        if k == "order_won" and not ours:
            pass  # an order the replay would not have taken
        elif k in ("gig_booked", "gig_dropped") and not any(o in accepted for o in w.gig_orders.get(e["gigId"], [])):
            pass  # drops and bookings of other orders' gigs say nothing about how our gigs fare
        else:
            desk.admission.observe(e)
            desk.pricing.observe(e)
        if k == "price_request":
            desk.quote(e["request"])
            action = desk.outbox.pop() if desk.outbox else None
            prices = (action or {}).get("prices") or {}
            lists = {o["kind"]: o["listPriceCents"] for o in e["request"]["options"]}
            if prices and all(v < DECLINE * lists[o] for o, v in prices.items()):
                accepted[e["request"]["id"]] = prices
        elif k in ("order_won", "order_changed") and ours:
            desk.orders[e["order"]["id"]] = copy.deepcopy(e["order"])
        elif k == "order_cancelled":
            desk.orders.pop(e["orderId"], None)
            desk.leg_gigs.pop(e["orderId"], None)
        elif k == "delivered":
            desk.delivered(e["orderId"], e["leg"], at)
        elif k == "gig_booked" or k == "offer_answered" and e["answer"] == "accepted":
            desk.booked.add(e["gigId"])
        elif k in ("gig_dropped", "no_show"):
            desk.booked.discard(e["gigId"])
        elif k == "gig_expired":
            for legs in desk.leg_gigs.values():
                for leg in [leg for leg, gig in legs.items() if gig == e["gigId"]]:
                    del legs[leg]
        elif k == "forecast":
            desk.notes.observe(e)
    return {"admission": admission_scores(w, accepted), "pricing": pricing_scores(w, accepted)}


def admission_scores(w: Week, accepted: dict) -> dict:
    """The week's orders split by whether the replay's admission would have taken them: the share on time and the
    margin of each part, from what really happened to them in the week."""
    counted = [o for o in w.orders.values() if o["status"] != "cancelled"]
    kept = [o for o in counted if o["id"] in accepted]
    margins = w.order_margins()
    quoted = sum(1 for rid in w.requests if real_quote(w.recorded.get(rid)))
    return {
        "requests": len(w.requests),
        "accepted": share(len(accepted), len(w.requests)),
        "recorded_quoted": share(quoted, len(w.requests)),
        "orders": len(counted),
        "kept": len(kept),
        "kept_share": share(len(kept), len(counted)),
        "on_time_all": share(sum(map(w.on_time, counted)), len(counted)),
        "on_time_kept": share(sum(map(w.on_time, kept)), len(kept)),
        "on_time_dropped": share(sum(map(w.on_time, counted)) - sum(map(w.on_time, kept)), len(counted) - len(kept)),
        "margin_all": sum(margins.get(o["id"], 0) for o in counted),
        "margin_kept": sum(margins.get(o["id"], 0) for o in kept),
        "on_time_all_n": sum(map(w.on_time, counted)),
        "on_time_kept_n": sum(map(w.on_time, kept)),
        "margin_per_order_all": share(sum(margins.get(o["id"], 0) for o in counted), len(counted)),
        "margin_per_order_kept": share(sum(margins.get(o["id"], 0) for o in kept), len(kept)),
    }


PRICING_CLASSES = [
    ("win", "would win", "s3"),
    ("lose", "would lose", "s2"),
    ("dearer", "unknown: dearer than the week's winning quote", "q2"),
    ("cheaper", "unknown: cheaper than the week's losing quote", "q1"),
    ("other", "unknown: no comparable quote", "total"),
]


def classify(prices: dict[str, int], row: dict | None) -> str:
    """What the week says of a replayed quote, from its own quote for the same request: a dealer takes a quote at or
    under the price that won it in the week, and refuses one at or over a price it refused (probe.py found the
    dealers' answers to be thresholds). A key of PRICING_CLASSES."""
    quote = real_quote(row)
    if quote is None:
        return "other"
    option = row.get("option")
    if row.get("outcome") == "won" and option in prices and option in quote:
        return "win" if prices[option] <= quote[option] else "dearer"
    if row.get("outcome") == "lost" and all(k in quote for k in prices):
        return "lose" if all(prices[k] >= quote[k] for k in prices) else "cheaper"
    return "other"


def pricing_scores(w: Week, accepted: dict) -> dict:
    """Each replayed quote by what the week says of it (`classify`), and the replayed prices over the list price."""
    classes: Counter[str] = Counter()
    ratios, recorded_ratios = [], []
    revenue = left = 0
    for rid, prices in accepted.items():
        lists = {o["kind"]: o["listPriceCents"] for o in w.requests[rid]["options"]}
        ratios += [v / lists[k] for k, v in prices.items()]
        row = w.recorded.get(rid)
        cls = classify(prices, row)
        classes[cls] += 1
        if (quote := real_quote(row)) is not None:
            recorded_ratios += [v / lists[k] for k, v in quote.items()]
        if cls == "win":
            revenue += prices[row["option"]]
            left += quote[row["option"]] - prices[row["option"]]
    known = classes["win"] + classes["lose"]
    return {
        "quotes": len(accepted),
        **{k: classes[k] for k, _, _ in PRICING_CLASSES},
        "win_of_known": share(classes["win"], known),
        "known": share(known, len(accepted)),
        "median_ratio": median(ratios),
        "recorded_median_ratio": median(recorded_ratios),
        "revenue_won": revenue,
        "below_winning": left,
    }


def replay_fees(w: Week) -> dict:
    """strategies/fees: plans each one-order gig's fee schedule from the minute the week posted it, and compares it
    with the fee its first driver booked at. A driver who took a fee takes any fee at least as high, so where the
    plan reaches that fee by the minute they booked, the plan finds them too and pays the first planned fee that
    reaches it; where it stays below, the week cannot say who would have taken it."""
    desk = w.desk()
    first: dict[str, dict | None] = {}  # gig id -> its first gig_booked; None when an accepted offer came first
    for e in w.events:
        if e["kind"] == "gig_booked":
            first.setdefault(e["gigId"], e)
        elif e["kind"] == "offer_answered" and e["answer"] == "accepted":
            first.setdefault(e["gigId"], None)
    books = below = 0
    paid = planned = 0
    paid_all = 0
    over_typical, opening_over_typical = [], []
    for gig in w.snapshot["gigs"]:
        orders, booking = w.gig_orders[gig["id"]], first.get(gig["id"])
        if len(orders) != 1 or booking is None:
            continue
        order, request = w.order_at(orders[0], gig["postedAt"]), w.requests.get(orders[0])
        if order is None or request is None:
            continue
        cars = dispatch.pickups(gig)
        plan = desk.fees.schedule(order, request, cars, gig["postedAt"])
        typical = desk.fees.typical(order, request) * cars / len(order["legs"])
        fee = booking["feeCents"]
        paid_all += fee
        if typical > 0:
            over_typical.append(fee / typical)
            opening_over_typical.append(plan[0]["feeCents"] / typical)
        reach = next((step for step in plan if step["feeCents"] >= fee), None)
        if reach is not None and reach["at"] <= booking["at"]:
            books += 1
            paid += fee
            planned += reach["feeCents"]
        else:
            below += 1
    return {
        "gigs": books + below,
        "books": books,
        "below": below,
        "books_share": share(books, books + below),
        "cost_ratio": share(planned, paid),
        "paid": paid_all,
        "median_booked_over_typical": median(over_typical),
        "median_opening_over_typical": median(opening_over_typical),
    }


def replay_bundling(w: Week) -> dict:
    """strategies/bundling: the week's won orders go through the bundler's pool as dispatch.py sends them, and its
    chains are counted, with the driver-minutes they save and the typical fees they save (the bundle's fee share)."""
    desk = w.desk()
    if w.level < 3:
        return {"orders": 0}
    groups: list[list] = []
    for at, minute in itertools.groupby(w.events, key=lambda e: e["at"]):
        while (due := desk.bundler.next_due()) is not None and due < at:
            desk.now = due
            groups += desk.bundler.due(due, desk.unit)
        desk.now = at
        for e in minute:
            k = e["kind"]
            if k == "price_request":
                desk.requests[e["request"]["id"]] = e["request"]
                desk.bundler.request(e["request"])
            elif k == "order_won" and e["order"]["id"] in desk.requests:
                order = copy.deepcopy(e["order"])
                desk.orders[order["id"]] = order
                desk.bundler.hold(order["id"], desk.requests[order["id"]].get("batchId"), order["lastPickupAt"], at)
            elif k == "order_changed" and e["order"]["id"] in desk.orders:
                desk.orders[e["order"]["id"]] = copy.deepcopy(e["order"])
            elif k == "order_cancelled":
                desk.bundler.forget(e["orderId"])
                desk.orders.pop(e["orderId"], None)
            elif k == "delivered":
                desk.delivered(e["orderId"], e["leg"], at)
            elif k == "forecast":
                desk.notes.observe(e)
        groups += desk.bundler.due(at, desk.unit)
    bundles = [g for g in groups if len(g) > 1]
    market, minutes, params = desk.bundler.market, desk.bundler.minutes, desk.bundler.params
    in_bundles = {o for g in w.snapshot["gigs"] if len(w.gig_orders[g["id"]]) > 1 for o in w.gig_orders[g["id"]]}
    won = [o for o in w.orders.values() if o["status"] != "cancelled"]
    orders = sum(len(g) for g in groups)
    return {
        "orders": orders,
        "bundles": len(bundles),
        "bundled_orders": sum(len(g) for g in bundles),
        "bundled_share": share(sum(len(g) for g in bundles), orders),
        "recorded_bundled_share": share(sum(1 for o in won if o["id"] in in_bundles), len(won)),
        "driver_hours_saved": sum(saving(g, market, minutes, params) for g in bundles) / HOUR,
        "typical_fees_saved": round(
            sum(sum(u.typical for u in g) * (1 - fee_share(g, market, minutes, params)) for g in bundles)
        ),
    }


def replay_offers(w: Week) -> dict:
    """strategies/offers: registers each gig the week posted, follows where our drivers finish, and asks for the
    offers at each post, delivery, drop, deadline warning and at least every hour. Scored on the week's bookings:
    did an offer reach the driver who took the gig, before they took it."""
    desk = w.desk()
    offers = desk.offers
    if w.level < 3:
        return {"offers": 0}
    known: dict[str, dict] = {}  # order id -> the order as the week knows it now
    gigs_of: dict[str, set[str]] = defaultdict(set)
    sent: dict[tuple[str, str], tuple[int, int]] = {}  # (gig, driver) -> (minute, fee) of the first offer
    last_tick = None
    for at, minute in itertools.groupby(w.timeline, key=lambda x: x[0]):
        trigger = False
        for _, kind, item in minute:
            if kind == "post":
                orders = w.gig_orders[item["id"]]
                if all(o in known for o in orders):
                    info = dispatch.gig_info(known, item, desk.admission.minutes)
                    offers.register(item["id"], info, item["schedule"])
                    for o in orders:
                        gigs_of[o].add(item["id"])
                    trigger = True
                continue
            offers.observe(item)
            k = item["kind"]
            if k in ("order_won", "order_changed"):
                known[item["order"]["id"]] = item["order"]
            elif k == "deadline_close":
                for gig_id in gigs_of.get(item["orderId"], ()):
                    if gig_id in offers.open:
                        offers.rescue(gig_id)
                trigger = True
            elif k in ("delivered", "gig_dropped", "no_show"):
                trigger = True
        if trigger or last_tick is None or at >= last_tick + HOUR:
            for action in offers.due(at):
                sent.setdefault((action["gigId"], action["driverId"]), (at, action["feeCents"]))
            last_tick = at
    bookings: dict[str, tuple[str, int, int | None, bool]] = {}  # gig -> (driver, minute, fee, by an offer)
    for e in w.events:
        if e["kind"] == "gig_booked":
            bookings.setdefault(e["gigId"], (e["driverId"], e["at"], e["feeCents"], False))
        elif e["kind"] == "offer_answered" and e["answer"] == "accepted":
            bookings.setdefault(e["gigId"], (e["driverId"], e["at"], None, True))
    hits, fee_ratios = 0, []
    for gig_id, (driver, at, fee, _) in bookings.items():
        offer = sent.get((gig_id, driver))
        if offer and offer[0] <= at:
            hits += 1
            if fee:
                fee_ratios.append(offer[1] / fee)
    return {
        "offers": len(sent),
        "bookings": len(bookings),
        "hits": hits,
        "hit_share": share(hits, len(bookings)),
        "precision": share(hits, len(sent)),
        "recorded_offer_share": share(sum(1 for b in bookings.values() if b[3]), len(bookings))
        if any(e["kind"] == "offer_answered" for e in w.events)
        else None,
        "median_offer_over_booked_fee": median(fee_ratios),
    }


def replay_week(folder: str) -> dict:
    """Every strategy on one week. A strategy that fails gives its error and leaves the others to run."""
    w = Week(Path(folder))
    out: dict = {"week": w.info()}
    for name, fn in (
        ("notes", replay_notes),
        ("quotes", replay_quotes),
        ("fees", replay_fees),
        ("bundling", replay_bundling),
        ("offers", replay_offers),
    ):
        start = time.perf_counter()
        try:
            result = fn(w)
        except Exception as error:  # noqa: BLE001  # one strategy's failure must not hide the others
            result = {"error": f"{type(error).__name__}: {error}"}
        seconds = time.perf_counter() - start
        if name != "quotes":
            parts = {name: result}
        elif "error" in result:
            parts = {"admission": result, "pricing": result}
        else:
            parts = result
        for strategy, scores in parts.items():
            out[strategy] = {**scores, "seconds": seconds}
    return out


# ---------------------------------------------------------------- the probes
#
# A saved week can judge a quote or a fee only against its own. probe.py measured the answers directly, in copies of
# a world: a quote row's flip is the highest multiple of the list price that wins the request, a fee row's flip the
# lowest flat fee a driver books within its window. Each seed's request stream is its passive week.

PROBES = "out/probe"
PROBE_FILE = re.compile(r"(quote|fee)-L(\d+)-(.+)\.jsonl$")
PROBE_TOP = 2.5  # a quote row that won at both ends of probe.py's range (0.6 to 2.5) wins up to at least this
MULTIPLES = [round(0.6 + 0.05 * i, 2) for i in range(33)]  # fixed multiples of the list price, 0.6 to 2.2
DAY = 24 * HOUR


def load_probes(folder: str) -> dict[tuple[str, int, str], list[dict]]:
    """probe.py's rows by (mode, level, seed), without the rows that ended in an error."""
    found: dict[tuple[str, int, str], list[dict]] = defaultdict(list)
    for path in sorted(Path(folder).glob("*.jsonl")) if os.path.isdir(folder) else []:
        if (m := PROBE_FILE.match(path.name)) is None:
            continue
        for line in path.read_text().splitlines():
            if line.strip() and not (row := json.loads(line)).get("error"):
                found[(m[1], int(m[2]), m[3])].append(row)
    return found


class Stream:
    """A seed's request stream, from its passive week, with that week's drivers and map: what probe.py probed."""

    def __init__(self, folder: Path):
        with gzip.open(folder / "events.jsonl.gz", "rt", encoding="utf-8") as file:
            events = [json.loads(line) for line in file]
        self.requests = {e["request"]["id"]: e["request"] for e in events if e["kind"] == "price_request"}
        self.roster = read_gz(folder / "drivers.json.gz")
        self.map = json.loads(find_map(folder).read_text())

    def desk(self, level: int) -> dispatch.Desk:
        return dispatch.Desk(OfflineWorld(self.roster, self.map), level, 0)


def passive_week(level: int, seed: str, roots: list[str]) -> Path | None:
    for root in roots:
        folder = Path(root) / "passive" / f"L{level}" / seed
        if (folder / "events.jsonl.gz").exists() and (folder / "drivers.json.gz").exists() and find_map(folder):
            return folder
    return None


def flip_of(row: dict) -> float | None:
    """A quote row's flip; one that lost at both ends of the range wins at no price, one that won at both up to the top."""
    if row.get("flipRatio") is not None:
        return row["flipRatio"]
    ends = str(row.get("ends")).lower()
    return 0.0 if ends == "false" else PROBE_TOP if ends == "true" else None


def replay_quote_probes(level: int, seed: str, rows: list[dict], stream: Stream) -> dict:
    """strategies/pricing through the seed's request stream on the probed days, each request quoted at its first
    option, as the starter quotes. A quote wins under its flip: the probed one where there is one, else one drawn
    from the probed flips of the same day, so the model learns as in a week. Only the probed requests are scored."""
    flips = {(row["requestId"], row["option"]): f for row in rows if (f := flip_of(row)) is not None}
    probed = {rid for rid, _ in flips}
    days = sorted({req["arrivedAt"] // DAY for rid, req in stream.requests.items() if rid in probed})
    requests = sorted(
        (req for req in stream.requests.values() if req["arrivedAt"] // DAY in days),
        key=lambda req: (req["arrivedAt"], req["id"]),
    )
    pool: dict[int, list[float]] = defaultdict(list)  # day -> the probed flips of that day
    for req in requests:
        for option in req["options"]:
            if (req["id"], option["kind"]) in flips:
                pool[req["arrivedAt"] // DAY].append(flips[(req["id"], option["kind"])])
    pricing = stream.desk(level).pricing
    rng = random.Random(f"probe-{level}-{seed}")  # the same draws on every run
    pending: list[tuple[int, int, dict]] = []  # (respondBy, n, the outcome event) in time order
    scored: list[tuple[int, float, float]] = []  # (list price, flip, the model's multiple) of each probed request
    won = revenue = 0
    for n, req in enumerate(requests):
        while pending and pending[0][0] <= req["arrivedAt"]:
            pricing.observe(heapq.heappop(pending)[2])
        first = req["options"][0]
        truth = flips.get((req["id"], first["kind"]))
        flip = truth if truth is not None else rng.choice(pool[req["arrivedAt"] // DAY])
        ratio = pricing.price(req, req["arrivedAt"])[first["kind"]] / first["listPriceCents"]
        outcome = (
            {"kind": "order_won", "at": req["respondBy"], "order": {"id": req["id"], "dealerId": req["dealerId"]}}
            if ratio < flip
            else {"kind": "order_lost", "at": req["respondBy"], "requestId": req["id"]}
        )
        heapq.heappush(pending, (req["respondBy"], n, outcome))
        won += ratio < flip
        revenue += round(first["listPriceCents"] * ratio) if ratio < flip else 0
        if truth is not None:
            scored.append((first["listPriceCents"], truth, ratio))

    def at(multiple: float) -> dict:
        wins = [(price, flip) for price, flip, _ in scored if multiple < flip]
        return {"multiple": multiple, "won": len(wins), "revenue": sum(round(price * multiple) for price, _ in wins)}

    model = [(price, ratio) for price, flip, ratio in scored if ratio < flip]
    return {
        "days": days,
        "requests": len(requests),
        "probed": len(scored),
        "model_won": len(model),
        "model_revenue": sum(round(price * ratio) for price, ratio in model),
        "model_ratio": statistics.fmean(ratio for _, _, ratio in scored) if scored else None,
        "list_won": at(1.0)["won"],
        "list_revenue": at(1.0)["revenue"],
        "flip_won": sum(1 for _, flip, _ in scored if flip > 0),
        "flip_revenue": sum(round(price * flip) for price, flip, _ in scored if flip > 0),
        "stream_won": won,
        "stream_revenue": revenue,
        "_curve": [at(m) for m in MULTIPLES],
    }


def first_reach(plan: list[dict], flip: int | None, last_pickup: int) -> tuple[int, int] | None:
    """The first step of a schedule at or over the flip, before the last pickup: (minute, fee), or None."""
    for step in plan if flip is not None else []:
        if step["at"] > last_pickup:
            return None
        if step["feeCents"] >= flip:
            return step["at"], step["feeCents"]
    return None


def replay_fee_probes(level: int, seed: str, rows: list[dict], stream: Stream) -> dict:
    """strategies/fees and the starter's fees (strategies/baseline) plan each fee-probed order's schedule from the
    minute it was won; each books at its first step at or over the order's flip, before its last pickup."""
    desk = stream.desk(level)
    baseline = BaselineFees(stream.roster, stream.map, level)
    orders = []
    for row in rows:
        request = stream.requests.get(row["orderId"])
        if request is None:
            continue
        option = next((o for o in request["options"] if o["kind"] == row["option"]), request["options"][0])
        legs = request["legs"]
        order = {
            "id": request["id"],
            "dealerId": request["dealerId"],
            "option": row["option"],
            "legs": legs,
            "deliveredAt": [None] * len(legs),
            "priceCents": option["listPriceCents"],  # what the order would earn at the list price
            "lastPickupAt": row["lastPickupAt"],
            "deadline": row["deadline"],
        }
        now, flip = row["wonAt"], (round(row["flipCents"]) if row.get("flipCents") is not None else None)
        found = {"order": request["id"], "typical": request["referenceFeeCents"], "flip": flip}
        for name, planner in (("ours", desk.fees), ("starter", baseline)):
            plan = planner.schedule(order, request, len(legs), now)
            reach = first_reach(plan, flip, row["lastPickupAt"])
            found[name] = {
                "opening": plan[0]["feeCents"],
                "minutes": reach[0] - now if reach else None,
                "fee": reach[1] if reach else None,
            }
        orders.append(found)
    known = [o for o in orders if o["flip"] is not None]

    def part(name: str) -> dict:
        booked = [o for o in known if o[name]["fee"] is not None]
        return {
            f"{name}_booked": len(booked),
            f"{name}_paid": sum(o[name]["fee"] for o in booked),
            f"{name}_over_typical": statistics.fmean(o[name]["fee"] / o["typical"] for o in booked) if booked else None,
            f"{name}_over_flip": statistics.fmean(o[name]["fee"] / o["flip"] for o in booked) if booked else None,
            f"{name}_at_post": sum(1 for o in booked if o[name]["minutes"] == 0),
        }

    return {
        "orders": len(known),
        "never": len(orders) - len(known),
        "flip_over_typical": statistics.fmean(o["flip"] / o["typical"] for o in known) if known else None,
        **part("ours"),
        **part("starter"),
        "_orders": known,
    }


def replay_probes(probe_dir: str, roots: list[str]) -> list[dict]:
    """Both probe replays on every probed seed whose passive week is saved: one result per mode, level and seed."""
    out = []
    for (mode, level, seed), rows in sorted(load_probes(probe_dir).items()):
        folder = passive_week(level, seed, roots)
        result: dict = {"mode": mode, "level": level, "seed": seed, "rows": len(rows)}
        if folder is None:
            out.append({**result, "error": f"no passive week of {seed} at level {level}"})
            continue
        try:
            replay = replay_quote_probes if mode == "quote" else replay_fee_probes
            out.append({**result, **replay(level, seed, rows, Stream(folder))})
        except Exception as error:  # noqa: BLE001  # one seed's failure must not hide the others
            out.append({**result, "error": f"{type(error).__name__}: {error}"})
    return out


# ---------------------------------------------------------------- the page

GROUP_ORDER = ["runs", "runs-ladder", "starter", "explore-win", "explore-flat", "explore-slow", "explore-ceiling"]
GROUP_NAME = {"runs": "our dispatch.py", "runs-ladder": "our ladder", "starter": "starter"}


def group_key(week: dict) -> tuple:
    exp = week["experiment"]
    return (GROUP_ORDER.index(exp) if exp in GROUP_ORDER else len(GROUP_ORDER), exp, week["level"])


def groups(results: list[dict]) -> list[tuple[str, str, list[dict]]]:
    """The weeks by experiment and level: (label, sub, weeks)."""
    by: dict[tuple, list[dict]] = defaultdict(list)
    for res in results:
        by[group_key(res["week"])].append(res)
    out = []
    for key in sorted(by):
        weeks = sorted(by[key], key=lambda res: (str(res["week"]["seed"]), res["week"]["world"]))
        exp, level = key[1], key[2]
        out.append((GROUP_NAME.get(exp, exp), f"level {level} · {len(weeks)} weeks", weeks))
    return out


def values(weeks: list[dict], strategy: str, metric: str) -> list[tuple[dict, float]]:
    return [
        (res["week"], v)
        for res in weeks
        if isinstance(v := res.get(strategy, {}).get(metric), (int, float)) and not isinstance(v, bool)
    ]


def pooled(results: list[dict], strategy: str, part: str, whole: str | tuple) -> float | None:
    """A share over all weeks: the sum of `part` over the sum of `whole` (one metric, or several summed)."""
    wholes = (whole,) if isinstance(whole, str) else whole
    p = sum(res.get(strategy, {}).get(part) or 0 for res in results)
    q = sum(res.get(strategy, {}).get(w) or 0 for res in results for w in wholes)
    return share(p, q)


def jitter(i: int) -> float:
    return ((i % 5) - 2) * 2.5


def tip(week: dict, text: str) -> str:
    return f"{week['seed']} ({week['world']}): {text}"


def strip(
    results: list[dict],
    strategy: str,
    filled: str,
    ring: str | None,
    fmt,
    *,
    x_range=(0.0, 1.0),
    x_ticks=None,
    x_label: str,
    refs=(),
    aria: str,
) -> str:
    """One row per experiment: a filled dot per week for the replay's `filled` metric, a ring for `ring` (the
    week's own number to compare with), and a tick at the replay's mean."""
    rows = []
    for label, sub, weeks in groups(results):
        dots = []
        for i, (week, v) in enumerate(values(weeks, strategy, ring) if ring else []):
            dots.append((v, False, "s2", jitter(i), tip(week, f"the week: {fmt(v)}")))
        mine = values(weeks, strategy, filled)
        for i, (week, v) in enumerate(mine):
            dots.append((v, True, "s1", jitter(i), tip(week, f"replay: {fmt(v)}")))
        if not dots:
            continue
        mean = statistics.fmean(v for _, v in mine) if mine else None
        rows.append(
            {
                "label": label,
                "sub": sub,
                "dots": dots,
                "mark": mean,
                "mark_tip": f"mean of the replay: {fmt(mean)}" if mean is not None else "",
                "end": fmt(mean) if mean is not None else "",
            }
        )
    if not rows:
        return r.muted("No weeks with numbers for this chart.")
    ticks = x_ticks or [(v, f"{v:.0%}") for v in r.SHARE_TICKS]
    return r.strip_chart(rows, x_range=x_range, x_ticks=ticks, x_label=x_label, refs=refs, aria=aria)


def euro_axis(results: list[dict], strategy: str, metrics: list[str]) -> tuple[tuple[float, float], list]:
    vals = [v / 100 for m in metrics for res in results if isinstance(v := res.get(strategy, {}).get(m), (int, float))]
    lo, hi = (min(vals + [0]), max(vals + [0])) if vals else (0, 1)
    ticks = r.nice_ticks(lo, hi, 4)
    return (ticks[0] * 100, ticks[-1] * 100), [(t * 100, r.short_eur(t)) for t in ticks]


def share_axis(results: list[dict], strategy: str, metrics: list[str]) -> dict:
    """A share axis from 0 that fits the data: 0 to 100% unless every value is small."""
    vals = [v for m in metrics for res in results if isinstance(v := res.get(strategy, {}).get(m), (int, float))]
    top = max(vals, default=1.0)
    if top > 0.5:
        return {}
    ticks = r.nice_ticks(0, max(top, 0.01), 4)
    return {
        "x_range": (0.0, ticks[-1]),
        "x_ticks": [(t, f"{t:.0%}" if ticks[-1] >= 0.05 else f"{t:.1%}") for t in ticks],
    }


def ratio_axis(results: list[dict], strategy: str, metrics: list[str]) -> tuple[tuple[float, float], list]:
    vals = [v for m in metrics for res in results if isinstance(v := res.get(strategy, {}).get(m), (int, float))]
    lo, hi = (min(vals + [1.0]), max(vals + [1.0])) if vals else (0.5, 1.5)
    ticks = r.nice_ticks(lo, hi, 4)
    return (ticks[0], ticks[-1]), [(t, f"{t:g}×") for t in ticks]


def section_notes(results: list[dict]) -> str:
    ours = pooled(results, "notes", "caught_n", "changed")
    theirs = pooled(results, "notes", "starter_caught_n", "changed")
    facts: dict[str, list[int]] = defaultdict(lambda: [0] * 6)
    for res in results:
        for fact, counts in (res.get("notes", {}).get("_facts") or {}).items():
            facts[fact] = [a + b for a, b in zip(facts[fact], counts, strict=True)]
    table = r.table(
        [
            [fact, f"{n:,}", f"{c:,}", r.pct(share(a0, n)), r.pct(share(a, n)), f"{k0:,} of {c:,}", f"{k:,} of {c:,}"]
            for fact, (n, a, c, k, a0, k0) in facts.items()
        ],
        [
            "Fact",
            "Cars",
            "Changed by the note",
            "Starter agrees",
            "Reader agrees",
            "Starter reads it",
            "Reader reads it",
        ],
    )
    chart = strip(
        results,
        "notes",
        "caught",
        "starter_caught",
        r.pct,
        x_label="share of the facts a note changes that the reader gets right",
        aria="Note reader against the starter's, per week",
    )
    card = r.card(
        f"Our note reader gets {r.pct(ours)} of the facts a note changes right; the starter's reader {r.pct(theirs)}",
        chart,
        r.legend([("dot:s1", "our reader (strategies/notes)"), ("ring:s2", "the starter's reader")]),
        notes=[
            (
                "Every won car with a note, against the reveal's truth: ready time, real opening hours, the note's "
                "deadline, manual gearbox, plates and summer tyres. A fact counts when the note made it differ from "
                "what the request alone says. Scored with strategies/notes/check.py. Summed over weeks, so a seed "
                "played several times counts several times."
            )
        ],
        data=table,
    )
    return r.section("notes", "Notes: reading the dealers' notes", r.grid([card]))


def section_admission(results: list[dict]) -> str:
    kept = pooled(results, "admission", "kept", "orders")
    on_all = pooled(results, "admission", "on_time_all_n", "orders")
    on_kept = pooled(results, "admission", "on_time_kept_n", "kept")
    chart = strip(
        results,
        "admission",
        "on_time_kept",
        "on_time_all",
        r.pct,
        x_label="share of the orders on time",
        refs=((0.9, "90% to be ranked", "ref"),),
        aria="On-time share of the orders admission keeps, per week",
    )
    card1 = r.card(
        f"Admission keeps {r.pct(kept)} of the orders the weeks won; "
        f"{r.pct(on_kept)} of those were on time, against {r.pct(on_all)} of all",
        chart,
        r.legend([("dot:s1", "orders the replay's admission takes"), ("ring:s2", "all orders the week won")]),
        notes=[
            (
                "The quotes go through Desk.quote of dispatch.py: admission, the price of strategies/pricing that "
                "admission weighs, and the decline of a note whose deadline has passed. The desk holds only the orders "
                "it would have taken, and sees the week's gigs and bookings. On time is what happened to each order "
                "in the week, where every order competed for drivers: freeing those drivers would help the rest."
            )
        ],
    )
    span, ticks = euro_axis(results, "admission", ["margin_per_order_all", "margin_per_order_kept"])
    chart2 = strip(
        results,
        "admission",
        "margin_per_order_kept",
        "margin_per_order_all",
        r.eur,
        x_range=span,
        x_ticks=ticks,
        x_label="margin per order, €",
        refs=((0, "0", "ref"),),
        aria="Margin per order of the orders admission keeps, per week",
    )
    m_all = pooled(results, "admission", "margin_all", "orders")
    m_kept = pooled(results, "admission", "margin_kept", "kept")
    card2 = r.card(
        f"The orders it keeps made {r.eur(m_kept)} each, against {r.eur(m_all)} for all the orders",
        chart2,
        r.legend([("dot:s1", "orders the replay's admission takes"), ("ring:s2", "all orders the week won")]),
        notes=[
            (
                "Each order's account lines in the week, revenue less driver fees, refunds, penalties and failed "
                "visits (a bundle's fee split evenly over its orders), per order. It is the margin those orders made "
                "at the week's own prices, not at the replay's."
            )
        ],
    )
    return r.section("admission", "Admission: which requests to take", r.grid([card1, card2]))


def mean_of(results: list[dict], strategy: str, metric: str) -> float | None:
    vals = [v for res in results if isinstance(v := res.get(strategy, {}).get(metric), (int, float))]
    return statistics.fmean(vals) if vals else None


def section_pricing(results: list[dict]) -> str:
    rows = []
    for label, sub, weeks in groups(results):
        counts = {k: sum(res.get("pricing", {}).get(k) or 0 for res in weeks) for k, _, _ in PRICING_CLASSES}
        total = sum(counts.values())
        if total:
            rows.append(
                {
                    "label": label,
                    "sub": sub,
                    "parts": {k: (counts[k], f"{name}: {counts[k]:,} of {total:,}") for k, name, _ in PRICING_CLASSES},
                }
            )
    win = pooled(results, "pricing", "win", ("win", "lose"))
    known = pooled(results, "pricing", "win", ("win", "lose", "dearer", "cheaper", "other"))
    chart = (
        r.stacked_hbar(
            rows, PRICING_CLASSES, "Replayed quotes by what the week says of them", "share of the replayed quotes"
        )
        if rows
        else r.muted("No quotes.")
    )
    card1 = r.card(
        f"Where the week can tell, {r.pct(win)} of the replayed quotes would win",
        chart,
        r.legend([(f"{cls}", name) for _, name, cls in PRICING_CLASSES]),
        notes=[
            (
                "Each quote of the replay against the week's own quote for the same request and option. At or under a "
                "price that won, it wins; at or over a price that lost, it loses. A dearer quote than a winning one, or "
                "a cheaper one than a losing one, could go either way. The explore weeks quoted random prices, so they "
                f"judge the most quotes. {r.pct(known)} of all replayed quotes would win for sure."
            )
        ],
    )
    span, ticks = ratio_axis(results, "pricing", ["median_ratio", "recorded_median_ratio"])
    chart2 = strip(
        results,
        "pricing",
        "median_ratio",
        "recorded_median_ratio",
        lambda v: "–" if v is None else f"{v:.2f}×",
        x_range=span,
        x_ticks=ticks,
        x_label="median price over the list price",
        refs=((1.0, "list", "ref"),),
        aria="Median replayed price over list, per week",
    )
    mine, theirs = mean_of(results, "pricing", "median_ratio"), mean_of(results, "pricing", "recorded_median_ratio")
    card2 = r.card(
        f"The replay quotes {mine or 0:.2f}× the list price (median), the weeks quoted {theirs or 0:.2f}×",
        chart2,
        r.legend([("dot:s1", "the replay's quotes"), ("ring:s2", "the week's own quotes")]),
        notes=[
            (
                "strategies/pricing learns from the week's answers to the week's quotes, as if they were its own. "
                "Where it would have quoted differently, its real answers might have differed too."
            )
        ],
    )
    return r.section("pricing", "Pricing: the price of each quote", r.grid([card1, card2]))


def section_fees(results: list[dict]) -> str:
    rows = []
    for label, sub, weeks in groups(results):
        books = sum(res.get("fees", {}).get("books") or 0 for res in weeks)
        below = sum(res.get("fees", {}).get("below") or 0 for res in weeks)
        if books + below:
            rows.append(
                {
                    "label": label,
                    "sub": sub,
                    "parts": {
                        "books": (books, f"plan reaches the booked fee in time: {books:,} gigs"),
                        "below": (below, f"plan stays below it: {below:,} gigs"),
                    },
                }
            )
    segments = [
        ("books", "plan reaches the fee the driver took, by then", "s3"),
        ("below", "plan stays below it", "q1"),
    ]
    books = pooled(results, "fees", "books", ("books", "below"))
    card1 = r.card(
        f"Our fee plan reaches the fee a driver took, by the minute they took it, on {r.pct(books)} of the gigs",
        r.stacked_hbar(rows, segments, "Gigs by whether the fee plan reaches the booked fee", "share of the gigs")
        if rows
        else r.muted("No gigs."),
        r.legend([(cls, name) for _, name, cls in segments]),
        notes=[
            (
                "Each gig of one order that a driver booked from the app: strategies/fees plans its schedule from the "
                "minute the week posted it, for the order as it was then. A driver who took a fee takes any higher "
                "one, so where the plan reaches it in time the plan finds that driver too. Where the plan stays below, "
                "the week cannot say whether someone would have taken the lower fee."
            )
        ],
    )
    span, ticks = ratio_axis(results, "fees", ["cost_ratio"])
    chart2 = strip(
        results,
        "fees",
        "cost_ratio",
        None,
        lambda v: "–" if v is None else f"{v:.2f}×",
        x_range=span,
        x_ticks=ticks,
        x_label="planned fee over the fee the driver took",
        refs=((1.0, "same fee", "ref"),),
        aria="What the fee plan pays over the booked fee, per week",
    )
    cost = mean_of(results, "fees", "cost_ratio")
    card2 = r.card(
        f"On those gigs it pays {cost or 0:.2f}× the fee the driver took, a week on average",
        chart2,
        r.legend([("dot:s1", "the replay's fee plan")]),
        notes=[
            (
                "The first planned fee at or over the booked fee, summed, over the booked fees, on the gigs where the "
                "plan reaches it in time: an upper bound of what the plan pays, since another driver might take a "
                "lower step."
            )
        ],
    )
    return r.section("fees", "Fees: what we pay drivers", r.grid([card1, card2]))


def section_bundling(results: list[dict]) -> str:
    chart = strip(
        results,
        "bundling",
        "bundled_share",
        "recorded_bundled_share",
        r.pct,
        x_range=(0.0, 0.5),
        x_ticks=[(v, f"{v:.0%}") for v in (0, 0.1, 0.2, 0.3, 0.4, 0.5)],
        x_label="share of the won orders in a gig with another order",
        aria="Share of orders bundled, per week",
    )
    shared = pooled(results, "bundling", "bundled_orders", "orders")
    card1 = r.card(
        f"Bundling would put {r.pct(shared)} of the won orders in a gig with another order",
        chart,
        r.legend([("dot:s1", "the replay's bundler"), ("ring:s2", "what the week posted")]),
        notes=[
            (
                "Every order the week won goes through the bundler's pool as dispatch.py sends it: an order of a batch "
                "waits for the batch's other cars, then the pool builds chains. The ring is the share the week itself "
                "posted in gigs with several orders (the starter and the explore weeks never bundle)."
            )
        ],
    )
    span, ticks = euro_axis(results, "bundling", ["typical_fees_saved"])
    chart2 = strip(
        results,
        "bundling",
        "typical_fees_saved",
        None,
        r.eur,
        x_range=span,
        x_ticks=ticks,
        x_label="typical fees saved a week, €",
        aria="Typical fees saved by bundles, per week",
    )
    saved, hours_ = (
        mean_of(results, "bundling", "typical_fees_saved"),
        mean_of(results, "bundling", "driver_hours_saved"),
    )
    card2 = r.card(
        f"Its bundles save {r.eur(saved)} of typical fees and {hours_ or 0:.0f} driver-hours a week",
        chart2,
        r.legend([("dot:s1", "the replay's bundler")]),
        notes=[
            (
                "Per bundle: the summed typical fee of its cars times one less the bundle's fee share (what "
                "strategies/bundling pays for the chain over the cars alone), and the driver-minutes the chain saves "
                "against each car alone. Whether drivers book the chains is not in the week."
            )
        ],
    )
    return r.section("bundling", "Bundling: several orders in one gig", r.grid([card1, card2]))


def section_offers(results: list[dict]) -> str:
    chart = strip(
        results,
        "offers",
        "hit_share",
        "recorded_offer_share",
        r.pct,
        **share_axis(results, "offers", ["hit_share", "recorded_offer_share"]),
        x_label="share of the bookings",
        aria="Share of bookings an offer reached first, per week",
    )
    hits = pooled(results, "offers", "hits", "bookings")
    card1 = r.card(
        f"The replay's offers reach the driver who took the gig, before they took it, on {r.pct(hits)} of the bookings",
        chart,
        r.legend([("dot:s1", "the replay's offers"), ("ring:s2", "bookings by an accepted offer in the week")]),
        notes=[
            (
                "strategies/offers sees each gig the week posted and where our drivers finish, and is asked for "
                "offers at each post, delivery, drop and deadline warning, and at least hourly. The replay's offers "
                "get no answers, so the limits per driver and gig fill as if nobody answered."
            )
        ],
    )
    chart2 = strip(
        results,
        "offers",
        "precision",
        None,
        r.pct,
        **share_axis(results, "offers", ["precision"]),
        x_label="share of the offers that went to the driver who took the gig",
        aria="Share of offers that reached the driver who took the gig, per week",
    )
    precision = pooled(results, "offers", "hits", "offers")
    card2 = r.card(
        f"{r.pct(precision)} of its offers go to the driver who then took that gig",
        chart2,
        r.legend([("dot:s1", "the replay's offers")]),
        notes=["The rest went to drivers who did not take that gig in the week; they might have, at the offer's fee."],
    )
    return r.section("offers", "Offers: gigs sent straight to drivers", r.grid([card1, card2]))


def seed_key(seed: str) -> tuple:
    stem, _, n = str(seed).rpartition("-")
    return (stem, int(n)) if n.isdigit() else (str(seed), 0)


def ratio_fmt(v: float | None) -> str:
    return "–" if v is None else f"{v:.2f}×"


def section_quote_probes(probes: list[dict]) -> str:
    """Pricing scored on probe.py's quote flips: the model, the list price and every fixed multiple."""
    rows = [p for p in probes if p["mode"] == "quote" and "error" not in p and p["probed"]]
    if not rows:
        return r.section("quote-probes", "Pricing on the probes", r.muted("No quote probes in out/probe."))
    cards = []
    for level in sorted({p["level"] for p in rows}, reverse=True):
        seeds = sorted((p for p in rows if p["level"] == level), key=lambda p: seed_key(p["seed"]))
        probed = sum(p["probed"] for p in seeds)
        model, listed, flip = (sum(p[k] for p in seeds) for k in ("model_revenue", "list_revenue", "flip_revenue"))
        curve = [
            {
                "multiple": m,
                "won": sum(p["_curve"][i]["won"] for p in seeds),
                "revenue": sum(p["_curve"][i]["revenue"] for p in seeds),
            }
            for i, m in enumerate(MULTIPLES)
        ]
        best = max(curve, key=lambda c: c["revenue"])
        ratio = statistics.fmean(p["model_ratio"] for p in seeds if p["model_ratio"] is not None)
        y_max = r.nice_ticks(0, max(flip, best["revenue"]) / 100, 4)[-1]
        chart = r.line_chart(
            [
                {
                    "name": "every quote at one multiple",
                    "short": "one multiple for all",
                    "cls": "s1",
                    "pts": [
                        (
                            c["multiple"],
                            c["revenue"] / 100,
                            f"{c['multiple']:.2f}× the list price: {c['won']} of {probed} won, {r.eur(c['revenue'])}",
                        )
                        for c in curve
                    ],
                },
                {
                    "name": "every request at its flip",
                    "short": "at the flip",
                    "cls": "total",
                    "pts": [
                        (m, flip / 100, f"Every request at its flip: {r.eur(flip)}")
                        for m in (MULTIPLES[0], MULTIPLES[-1])
                    ],
                },
                {
                    "name": "pricing model",
                    "short": "model",
                    "cls": "s2",
                    "pts": [(ratio, model / 100, f"strategies/pricing, {ratio:.2f}× on average: {r.eur(model)}")],
                },
            ],
            x_range=(MULTIPLES[0], MULTIPLES[-1]),
            x_ticks=[(v, f"{v:.1f}×") for v in (0.6, 1.0, 1.4, 1.8, 2.2)],
            x_label="quote over the list price",
            y_max=y_max,
            y_ticks=r.nice_ticks(0, y_max, 4),
            y_fmt=r.short_eur,
            y_label="revenue won, €",
            refs=((1.0, "list"),),
            aria=f"Revenue won on the probed requests by quote multiple, level {level}",
        )
        table = r.table(
            [
                [
                    p["seed"],
                    ", ".join(r.DAYS[d] for d in p["days"]),
                    f"{p['requests']:,}",
                    f"{p['probed']:,}",
                    ratio_fmt(p["model_ratio"]),
                    f"{p['model_won']} / {p['list_won']} / {p['flip_won']}",
                    r.eur(p["model_revenue"]),
                    r.eur(p["list_revenue"]),
                    r.eur(p["flip_revenue"]),
                ]
                for p in seeds
            ],
            ["Seed", "Days", "Requests", "Probed", "Model", "Won: model / list / flip", "Model", "List", "Flip"],
        )
        cards.append(
            r.card(
                f"Level {level}: the pricing model wins {r.eur(model)} on {probed} probed requests, the list price "
                f"{r.eur(listed)}; one multiple, {best['multiple']:.2f}×, would win {r.eur(best['revenue'])}",
                chart,
                r.legend(
                    [("s1", "every quote at one multiple"), ("s2", "strategies/pricing"), ("total", "at the flip")]
                ),
                notes=[
                    (
                        f"{probed} requests on {len(seeds)} seeds have a probed flip: the highest multiple of the list "
                        "price that wins them, from probe.py quote. A quote wins below its flip. Each request is quoted "
                        "at its first option, as the starter quotes."
                    ),
                    (
                        "The pricing model runs through the seed's whole request stream on the probed days (its "
                        "passive week) and learns from each answer: the probed flip where there is one, else a flip "
                        "drawn from the same day's probed requests. Dealer trust stays at zero: it needs deliveries."
                    ),
                    (
                        "probe.py's parent world wins nothing, so the competitor has not raised its prices for these "
                        "dealers, and it probed Monday and Tuesday at level 8."
                    ),
                ],
                data=table,
            )
        )
        diffs = [
            {
                "label": p["seed"],
                "sub": f"{p['probed']} probed, {ratio_fmt(p['model_ratio'])}",
                "dots": [
                    (
                        p["model_revenue"] - p["list_revenue"],
                        True,
                        "s1" if p["model_revenue"] >= p["list_revenue"] else "s2",
                        0,
                        f"{p['seed']}: the model {r.eur(p['model_revenue'])}, the list price {r.eur(p['list_revenue'])}",
                    )
                ],
                "end": r.eur_signed(p["model_revenue"] - p["list_revenue"]),
            }
            for p in seeds
        ]
        span, ticks = cents_axis([p["model_revenue"] - p["list_revenue"] for p in seeds])
        higher = sum(1 for p in seeds if p["model_revenue"] > p["list_revenue"])
        cards.append(
            r.card(
                f"Level {level}: the model wins more than the list price on {higher} of {len(seeds)} seeds",
                r.strip_chart(
                    diffs,
                    x_range=span,
                    x_ticks=ticks,
                    x_label="the model's revenue less the list price's, € on the probed requests",
                    refs=((0, "", "ref"),),
                    aria=f"Model revenue less list-price revenue per seed, level {level}",
                ),
                r.legend([("dot:s1", "the model wins more"), ("dot:s2", "the list price wins more")]),
            )
        )
    return r.section("quote-probes", "Pricing on the probes: what each price would win", r.grid(cards))


def cents_axis(values: list[float]) -> tuple[tuple[float, float], list]:
    """An axis in cents, labelled in euros, that holds the values and zero."""
    ticks = r.nice_ticks(min([*values, 0]) / 100, max([*values, 0]) / 100, 4)
    return (ticks[0] * 100, ticks[-1] * 100), [(t * 100, r.short_eur(t)) for t in ticks]


FEE_TIMES = [
    ("now", "at the post", "s1"),
    ("hour", "within 1 h", "q2"),
    ("three", "within 3 h", "q1"),
    ("later", "later", "o1"),
    ("never", "never reaches the flip", "total"),
]


def section_fee_probes(probes: list[dict]) -> str:
    """Our fee schedules and the starter's scored on probe.py's fee flips."""
    seeds = sorted(
        (p for p in probes if p["mode"] == "fee" and "error" not in p and p["orders"]),
        key=lambda p: seed_key(p["seed"]),
    )
    if not seeds:
        return r.section("fee-probes", "Fees on the probes", r.muted("No fee probes in out/probe."))
    orders = [{**o, "seed": p["seed"], "level": p["level"]} for p in seeds for o in p["_orders"]]
    names = (("ours", "Ours", "s1"), ("starter", "Starter", "s2"))

    def booked(name: str) -> list[dict]:
        return [o for o in orders if o[name]["fee"] is not None]

    def mean_over_typical(name: str) -> float | None:
        b = booked(name)
        return statistics.fmean(o[name]["fee"] / o["typical"] for o in b) if b else None

    strip_rows = [
        {
            "label": "Flip",
            "sub": "lowest fee booked",
            "dots": [
                (
                    o["flip"] / o["typical"],
                    True,
                    "total",
                    jitter(i),
                    f"{o['seed']} {o['order']}: flip {r.eur(o['flip'])}",
                )
                for i, o in enumerate(orders)
            ],
            "mark": statistics.fmean(o["flip"] / o["typical"] for o in orders),
            "mark_tip": "mean flip over the typical fee",
            "end": ratio_fmt(statistics.fmean(o["flip"] / o["typical"] for o in orders)),
        }
    ]
    for name, label, cls in names:
        strip_rows.append(
            {
                "label": label,
                "sub": f"{len(booked(name))} of {len(orders)} booked",
                "dots": [
                    (
                        o[name]["fee"] / o["typical"],
                        True,
                        cls,
                        jitter(i),
                        f"{o['seed']} {o['order']}: {label.lower()} pays {r.eur(o[name]['fee'])}, flip {r.eur(o['flip'])}",
                    )
                    for i, o in enumerate(booked(name))
                ],
                "mark": mean_over_typical(name),
                "mark_tip": f"mean fee paid over the typical fee, {label.lower()}",
                "end": ratio_fmt(mean_over_typical(name)),
            }
        )
    top = max(row[0] for s in strip_rows for row in s["dots"])
    ticks = r.nice_ticks(0, top, 5)
    per_seed = r.table(
        [
            [
                p["seed"],
                p["orders"],
                p["never"],
                ratio_fmt(p["flip_over_typical"]),
                f"{p['ours_booked']} / {p['starter_booked']}",
                ratio_fmt(p["ours_over_typical"]),
                ratio_fmt(p["starter_over_typical"]),
                r.eur(p["ours_paid"]),
                r.eur(p["starter_paid"]),
            ]
            for p in seeds
        ],
        [
            "Seed",
            "Orders",
            "Never booked",
            "Flip",
            "Booked: ours / starter",
            "Ours paid",
            "Starter paid",
            "Ours, €",
            "Starter, €",
        ],
    )
    card1 = r.card(
        f"Our fees book {len(booked('ours'))} of {len(orders)} probed orders and pay {ratio_fmt(mean_over_typical('ours'))} "
        f"the typical fee; the starter's book {len(booked('starter'))} and pay {ratio_fmt(mean_over_typical('starter'))}",
        r.strip_chart(
            strip_rows,
            x_range=(0, ticks[-1]),
            x_ticks=[(t, f"{t:g}×") for t in ticks],
            x_label="fee over the typical fee",
            refs=((1.0, "typical", "ref"),),
            aria="Fee paid over the typical fee per probed order",
        ),
        r.legend([("dot:total", "the flip"), ("dot:s1", "strategies/fees"), ("dot:s2", "the starter's fees")]),
        notes=[
            (
                "probe.py fee won each order and posted its cars at one flat fee in copies of the world: the flip is "
                "the lowest fee a driver booked within the window (180 minutes, never past the last pickup). Our "
                "schedule (strategies/fees) and the starter's (strategies/baseline) are planned from the minute the "
                "order was won, at its list price; each books at its first step at or over the flip, before the last "
                "pickup, and pays that step."
            ),
            (
                "A driver who took the flat fee at the post may not be there for a step that reaches it hours later, "
                "and the starter's steep fees after a deadline warning are left out."
            ),
        ],
        data=per_seed,
    )
    timing = []
    for name, label, _ in names:
        parts: Counter[str] = Counter()
        for o in orders:
            m = o[name]["minutes"]
            parts[
                "never" if m is None else "now" if m == 0 else "hour" if m <= 60 else "three" if m <= 180 else "later"
            ] += 1
        timing.append(
            {
                "label": label,
                "sub": f"{len(orders)} orders",
                "parts": {k: (parts[k], f"{label}: {name_} {parts[k]} orders") for k, name_, _ in FEE_TIMES},
            }
        )
    card2 = r.card(
        f"Ours reaches the flip at the post on {sum(1 for o in booked('ours') if o['ours']['minutes'] == 0)} orders, "
        f"the starter's on {sum(1 for o in booked('starter') if o['starter']['minutes'] == 0)}",
        r.stacked_hbar(timing, FEE_TIMES, "When each schedule reaches the order's flip", "share of the probed orders"),
        r.legend([(cls, name_) for _, name_, cls in FEE_TIMES]),
        notes=[f"{sum(p['never'] for p in seeds)} more probed orders found no driver even at the top fee tried."],
    )
    every = r.details_block(
        f"Every probed order ({len(orders)})",
        r.table(
            [
                [
                    o["seed"],
                    o["order"],
                    r.eur(o["typical"]),
                    r.eur(o["flip"]),
                    r.eur(o["ours"]["opening"]),
                    r.eur(o["ours"]["fee"]) if o["ours"]["fee"] is not None else "–",
                    o["ours"]["minutes"] if o["ours"]["minutes"] is not None else "–",
                    r.eur(o["starter"]["fee"]) if o["starter"]["fee"] is not None else "–",
                    o["starter"]["minutes"] if o["starter"]["minutes"] is not None else "–",
                ]
                for o in orders
            ],
            [
                "Seed",
                "Order",
                "Typical",
                "Flip",
                "Our opening",
                "Ours paid",
                "Ours, min",
                "Starter paid",
                "Starter, min",
            ],
        ),
    )
    return r.section("fee-probes", "Fees on the probes: what each schedule would pay", r.grid([card1, card2]) + every)


def section_overview(results: list[dict]) -> str:
    """The starter's played weeks next to our saved runs, level by level, from each week's own score."""
    shown = {
        "starter": "None (the starter)",
        "runs": "Every strategy (dispatch.py)",
        "runs-ladder": "The ladder",
        "runs-ts-starter": "The starter in TypeScript",
    }
    colour = {"starter": "total", "runs": "s1", "runs-ladder": "s3", "runs-ts-starter": "s4"}
    label = {"starter": "None", "runs": "Every strategy", "runs-ladder": "The ladder", "runs-ts-starter": "TS starter"}
    by: dict[tuple[int, str], list[dict]] = defaultdict(list)
    for res in results:
        w = res["week"]
        if w["experiment"] in shown:
            by[(w["level"], w["experiment"])].append(w)
    levels = sorted({level for level, exp in by if exp == "starter" and (level, "runs") in by}, reverse=True)
    if not levels:
        return ""
    cards, table_rows = [], []
    for level in levels:
        groups_ = [(exp, by[(level, exp)]) for exp in shown if (level, exp) in by]
        rows = []
        for exp, weeks in groups_:
            mean = statistics.fmean(w["margin"] for w in weeks)
            rows.append(
                {
                    "label": label[exp],
                    "sub": f"{len(weeks)} weeks",
                    "dots": [
                        (
                            w["margin"],
                            True,
                            colour[exp],
                            jitter(i),
                            tip(w, f"{r.eur(w['margin'])}, {r.pct(w['on_time'])} on time"),
                        )
                        for i, w in enumerate(weeks)
                    ],
                    "mark": mean,
                    "mark_tip": f"mean {r.eur(mean)} a week",
                    "end": r.eur(mean),
                }
            )
            won = sum(w["won"] or 0 for w in weeks)
            table_rows.append(
                [
                    f"L{level}",
                    shown[exp],
                    len(weeks),
                    r.eur(mean),
                    r.eur(statistics.fmean(w["revenue"] or 0 for w in weeks)),
                    f"{won / len(weeks):,.0f}",
                    r.pct(share(sum((w["on_time"] or 0) * (w["won"] or 0) for w in weeks), won)),
                    r.pct(share(sum((w["undelivered"] or 0) * (w["won"] or 0) for w in weeks), won)),
                    f"{sum(1 for w in weeks if w['ranked'])} of {len(weeks)}",
                    r.eur(statistics.fmean(w["driver_fees"] for w in weeks)),
                    r.eur(share(sum(w["driver_fees"] for w in weeks), sum(w["cars"] for w in weeks))),
                ]
            )
        span, ticks = cents_axis([w["margin"] for _, weeks in groups_ for w in weeks])
        ours, none = (
            statistics.fmean(w["margin"] for w in by[(level, "runs")]),
            statistics.fmean(w["margin"] for w in by[(level, "starter")]),
        )
        cards.append(
            r.card(
                f"Level {level}: every strategy makes {r.eur(ours)} a week, the starter {r.eur(none)}",
                r.strip_chart(
                    rows,
                    x_range=span,
                    x_ticks=ticks,
                    x_label="margin, € per week",
                    refs=((0, "", "ref"),),
                    aria=f"Margin per week, the starter against our systems, level {level}",
                ),
                r.legend([(f"dot:{colour[exp]}", shown[exp]) for exp, _ in groups_]),
                notes=[
                    (
                        "Each played week's own score. The starter's weeks are the team's scrapes; ours are every saved "
                        "run with a reveal. The seeds differ (scrape-N against spread-N), the level is the same."
                    )
                ],
            )
        )
    table = r.table(
        table_rows,
        [
            "Level",
            "System",
            "Weeks",
            "Margin / week",
            "Revenue / week",
            "Orders / week",
            "On time",
            "Not delivered",
            "Ranked",
            "Driver fees / week",
            "Fees / car",
        ],
    )
    card = r.card("Each system's weeks, per week", table)
    return r.section("overview", "Every strategy against none", r.grid(cards) + card)


def column_dots(groups_: list[dict], *, y_ticks, y_fmt, y_label: str, x_label: str, refs=(), aria: str) -> str:
    """Groups along x in order (commits), a dot per week and a line through the groups' means. Each group has `x`
    (its tick label), `dots` [(y, tip)], `mean` and `mean_tip`. Unlike r.line_chart, y may be negative."""
    h = 230
    x0, x1, y0, y1 = r.ML, r.W - 14, r.MT, h - r.MB
    lo, hi = y_ticks[0], y_ticks[-1]
    step = (x1 - x0) / max(len(groups_), 1)

    def px(i: float) -> float:
        return x0 + step * (i + 0.5)

    def py(v: float) -> float:
        return y1 - (min(max(v, lo), hi) - lo) / ((hi - lo) or 1) * (y1 - y0)

    out = [r.svg_open(h, aria), r.y_grid([(py(v), y_fmt(v)) for v in y_ticks], x0, x1)]
    out.append(f'<line x1="{x0}" x2="{x1}" y1="{y1}" y2="{y1}" class="axis"/>')
    if lo < 0 < hi:
        out.append(f'<line x1="{x0}" x2="{x1}" y1="{py(0):.1f}" y2="{py(0):.1f}" class="axis"/>')
    for v, name in refs:
        out.append(f'<line x1="{x0}" x2="{x1}" y1="{py(v):.1f}" y2="{py(v):.1f}" class="ref"/>')
        out.append(r.t(x1, py(v) - 4, name, "tk", "end"))
    every = max(1, -(-len(groups_) // 12))
    for i, g in enumerate(groups_):
        if i % every == 0 or i == len(groups_) - 1:
            out.append(r.t(px(i), y1 + 14, g["x"], "tk", "middle"))
    out.append(r.t((x0 + x1) / 2, h - 4, x_label, "al", "middle"))
    out.append(r.t(11, (y0 + y1) / 2, y_label, "al", "middle", f' transform="rotate(-90 11 {(y0 + y1) / 2:.1f})"'))
    spread = min(step * 0.35, 9)
    for i, g in enumerate(groups_):
        for j, (y, text) in enumerate(g["dots"]):
            x = px(i) + ((j % 5) - 2) / 2 * spread
            out.append(
                f'<g><circle cx="{x:.1f}" cy="{py(y):.1f}" r="2.6" class="pt q2"/>'
                f'<circle cx="{x:.1f}" cy="{py(y):.1f}" r="8" class="hit">{r.title(text)}</circle></g>'
            )
    means = [(px(i), py(g["mean"])) for i, g in enumerate(groups_)]
    if len(means) > 1:
        out.append('<path d="M' + " L".join(f"{a:.1f},{b:.1f}" for a, b in means) + '" class="line s1"/>')
    for (x, y), g in zip(means, groups_, strict=True):
        out.append(r.point(x, y, "s1", g["mean_tip"]))
    out.append("</svg>")
    return "".join(out)


def git_commit(sha: str) -> dict | None:
    """The time and subject of a commit, or None when this checkout does not have it."""
    done = subprocess.run(
        ["git", "log", "-1", "--format=%ct%x09%h%x09%s", sha], capture_output=True, text=True, check=False
    )
    if done.returncode != 0 or not done.stdout.strip():
        return None
    at, short, subject = done.stdout.strip().split("\t", 2)
    return {"at": int(at), "short": short, "subject": subject}


def section_history(results: list[dict]) -> str:
    """Every saved run of dispatch.py with a reveal, by the commit that played it (meta.json's `version`)."""
    weeks = [res["week"] for res in results if res["week"]["experiment"] == "runs"]
    if not weeks:
        return ""
    level = max({w["level"] for w in weeks}, key=lambda lv: sum(1 for w in weeks if w["level"] == lv))
    weeks = [w for w in weeks if w["level"] == level]
    by: dict[str, list[dict]] = defaultdict(list)
    for w in weeks:
        by[(w["version"] or "unknown").removesuffix("-dirty")].append(w)
    commits = []
    for sha, ws in by.items():
        info = git_commit(sha) if sha != "unknown" else None
        commits.append({"sha": sha, "info": info, "weeks": sorted(ws, key=lambda w: seed_key(w["seed"]))})
    commits.sort(key=lambda c: (c["info"]["at"] if c["info"] else float("inf"), c["sha"]))
    for n, c in enumerate(commits, 1):
        c.update(
            n=n,
            name=c["info"]["short"] if c["info"] else c["sha"][:7],
            margin=statistics.fmean(w["margin"] for w in c["weeks"]),
            on_time=statistics.fmean(w["on_time"] or 0 for w in c["weeks"]),
        )
    commit_of = {w["world"]: c for c in commits for w in c["weeks"]}

    def week_tip(c: dict, w: dict) -> str:
        return f"#{c['n']} {c['name']} on {w['seed']}: {r.eur(w['margin'])}, {r.pct(w['on_time'])} on time"

    margins = [w["margin"] / 100 for w in weeks]
    shares = [w["on_time"] or 0 for w in weeks]
    top = max(commits, key=lambda c: c["margin"])
    card1 = r.card(
        f"The best commit, #{top['n']} {top['name']}, averaged {r.eur(top['margin'])} a week over "
        f"{len(top['weeks'])} saved weeks",
        column_dots(
            [
                {
                    "x": str(c["n"]),
                    "dots": [(w["margin"] / 100, week_tip(c, w)) for w in c["weeks"]],
                    "mean": c["margin"] / 100,
                    "mean_tip": f"#{c['n']} {c['name']}: mean {r.eur(c['margin'])} over {len(c['weeks'])} weeks",
                }
                for c in commits
            ],
            y_ticks=r.nice_ticks(min([*margins, 0]), max([*margins, 0]), 4),
            y_fmt=r.short_eur,
            y_label="margin, € per week",
            x_label="commit, in time order (table below)",
            aria="Margin of every saved week by commit",
        ),
        r.legend([("dot:q2", "one week"), ("s1", "mean of the commit's weeks")]),
        notes=[
            (
                f"Every saved run of dispatch.py at level {level} that has a reveal, by the commit that played it. The "
                "seeds differ between commits, and the fee bench played other fee constants on some, so a commit's "
                "mean is a rough guide, not a measurement. Weeks are grouped by meta.json's policy, so a week "
                "that another system saved as dispatch counts here too."
            )
        ],
    )
    card2 = r.card(
        f"{sum(1 for w in weeks if w['ranked'])} of {len(weeks)} saved weeks are ranked (90% or more on time)",
        column_dots(
            [
                {
                    "x": str(c["n"]),
                    "dots": [(w["on_time"] or 0, week_tip(c, w)) for w in c["weeks"]],
                    "mean": c["on_time"],
                    "mean_tip": f"#{c['n']} {c['name']}: mean {r.pct(c['on_time'])} on time",
                }
                for c in commits
            ],
            y_ticks=r.nice_ticks(min([*shares, 0.9]), 1.0, 4),
            y_fmt=lambda v: f"{v * 100:g}%",
            y_label="orders on time",
            x_label="commit, in time order (table below)",
            refs=((0.9, "ranked from 90%"),),
            aria="On-time share of every saved week by commit",
        ),
        r.legend([("dot:q2", "one week"), ("s1", "mean of the commit's weeks")]),
    )
    commit_table = r.table(
        [
            [
                c["n"],
                c["name"],
                time.strftime("%a %H:%M", time.localtime(c["info"]["at"])) if c["info"] else "–",
                (c["info"]["subject"][:72] + ("…" if len(c["info"]["subject"]) > 72 else "")) if c["info"] else "–",
                len(c["weeks"]),
                r.eur(c["margin"]),
                r.pct(c["on_time"]),
                f"{sum(1 for w in c['weeks'] if w['ranked'])} of {len(c['weeks'])}",
            ]
            for c in commits
        ],
        ["#", "Commit", "When", "Subject", "Weeks", "Mean margin", "On time", "Ranked"],
    )
    by_seed: dict[str, list[dict]] = defaultdict(list)
    for w in weeks:
        by_seed[w["seed"]].append(w)
    seed_rows = []
    for seed in sorted(by_seed, key=seed_key):
        ws = by_seed[seed]
        best, worst = max(ws, key=lambda w: w["margin"]), min(ws, key=lambda w: w["margin"])
        seed_rows.append(
            [
                seed,
                len(ws),
                r.eur(best["margin"]),
                f"#{commit_of[best['world']]['n']} {commit_of[best['world']]['name']}",
                r.eur(worst["margin"]),
                r.eur(statistics.fmean(w["margin"] for w in ws)),
                r.pct(statistics.fmean(w["on_time"] or 0 for w in ws)),
            ]
        )
    seed_table = r.table(seed_rows, ["Seed", "Weeks", "Best", "Best by", "Worst", "Mean", "On time"])
    body = (
        r.grid([card1, card2])
        + r.card("Commits that played saved weeks", commit_table)
        + r.card("Best and worst week of each seed", seed_table)
    )
    return r.section("history", "Every saved week, by commit", body)


def scoreboard(results: list[dict]) -> str:
    """One row per experiment: the headline number of each strategy."""
    out = []
    for label, sub, weeks in groups(results):
        out.append(
            [
                label,
                sub,
                r.pct(pooled(weeks, "notes", "caught_n", "changed")),
                r.pct(pooled(weeks, "admission", "kept", "orders")),
                r.pct(pooled(weeks, "admission", "on_time_kept_n", "kept")),
                r.pct(pooled(weeks, "pricing", "win", ("win", "lose"))),
                r.pct(pooled(weeks, "fees", "books", ("books", "below"))),
                r.pct(pooled(weeks, "bundling", "bundled_orders", "orders")),
                r.pct(pooled(weeks, "offers", "hits", "bookings")),
            ]
        )
    return r.table(
        out,
        [
            "Weeks",
            "",
            "Notes read right",
            "Orders admission keeps",
            "Kept on time",
            "Quotes that win (of known)",
            "Fee plan finds the driver",
            "Orders bundled",
            "Bookings an offer reached",
        ],
    )


def errors(results: list[dict]) -> str:
    rows = [
        [res["week"]["experiment"], res["week"]["seed"], res["week"]["world"], s, res[s]["error"]]
        for res in results
        for s in STRATEGIES
        if "error" in res.get(s, {})
    ]
    if not rows:
        return ""
    return r.section("errors", "Errors", r.table(rows, ["Experiment", "Seed", "World", "Strategy", "Error"]))


SECTIONS = [
    ("scoreboard", "Scoreboard"),
    ("overview", "All or none"),
    ("notes", "Notes"),
    ("admission", "Admission"),
    ("pricing", "Pricing"),
    ("quote-probes", "Pricing on probes"),
    ("fees", "Fees"),
    ("fee-probes", "Fees on probes"),
    ("bundling", "Bundling"),
    ("offers", "Offers"),
    ("history", "Saved weeks"),
]


def page(results: list[dict], seconds: float, no_reveal: int = 0, probes: list[dict] | None = None) -> str:
    probes = probes or []
    built = (
        f"Built {time.strftime('%Y-%m-%d %H:%M')} from {len(results)} saved weeks in {seconds:.0f} s, with the "
        "strategies of this checkout. Each week's recorded events go to each strategy in order, as dispatch.py "
        "feeds them; its decisions are scored against what the week shows happened, and count as unknown where the "
        "week cannot tell. Hover a dot for its week; the method of each chart is under “Method”."
    )
    if no_reveal:
        built += f" {skipped(no_reveal)}."
    nav = "".join(f'<a href="#{sid}">{i}. {r.E(n)}</a>' for i, (sid, n) in enumerate(SECTIONS, 1))
    body = (
        r.section("scoreboard", "Scoreboard", scoreboard(results))
        + section_overview(results)
        + section_notes(results)
        + section_admission(results)
        + section_pricing(results)
        + section_quote_probes(probes)
        + section_fees(results)
        + section_fee_probes(probes)
        + section_bundling(results)
        + section_offers(results)
        + section_history(results)
        + errors(results)
        + probe_errors(probes)
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta name="color-scheme" content="light dark">'
        f"<title>Strategy replay</title><style>{r.CSS}</style></head><body>"
        f"<header><h1>Strategy replay on the saved weeks</h1><nav>{nav}</nav></header>"
        f'<p class="built">{r.E(built)}</p>{body}</body></html>'
    )


# ---------------------------------------------------------------- output


def probe_errors(probes: list[dict]) -> str:
    rows = [[p["mode"], p["level"], p["seed"], p["error"]] for p in probes if "error" in p]
    return r.section("probe-errors", "Probe errors", r.table(rows, ["Probe", "Level", "Seed", "Error"])) if rows else ""


def write_csv(results: list[dict], path: str, probes: list[dict] | None = None) -> None:
    """One row per week, strategy and number; then one per probed seed and number, with the experiment `probe`,
    the strategy `pricing-probes` or `fees-probes` and no world."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["experiment", "level", "seed", "world", "policy", "strategy", "metric", "value"])
        for res in results:
            w = res["week"]
            for strategy in STRATEGIES:
                for metric, value in res.get(strategy, {}).items():
                    if metric.startswith("_") or isinstance(value, dict):
                        continue
                    writer.writerow(
                        [w["experiment"], w["level"], w["seed"], w["world"], w["policy"], strategy, metric, value]
                    )
        for p in probes or []:
            strategy = "pricing-probes" if p["mode"] == "quote" else "fees-probes"
            for metric, value in p.items():
                if metric.startswith("_") or metric in ("mode", "level", "seed") or isinstance(value, (dict, list)):
                    continue
                writer.writerow(["probe", p["level"], p["seed"], "", "", strategy, metric, value])


def skipped(no_reveal: int) -> str:
    """The note on the played weeks left out because they have no reveal, such as ranking runs."""
    weeks = "week" if no_reveal == 1 else "weeks"
    return f"Skipped {no_reveal} played {weeks} without a reveal (ranking runs are not revealed)"


def print_summary(results: list[dict]) -> None:
    head = f"{'Experiment':<20} {'Weeks':>5} {'Notes':>6} {'Kept':>6} {'OnTime':>7} {'Win':>6} {'Fees':>6} {'Bundle':>7} {'Offers':>7}"
    print(head)
    for label, sub, weeks in groups(results):
        cells = [
            pooled(weeks, "notes", "caught_n", "changed"),
            pooled(weeks, "admission", "kept", "orders"),
            pooled(weeks, "admission", "on_time_kept_n", "kept"),
            pooled(weeks, "pricing", "win", ("win", "lose")),
            pooled(weeks, "fees", "books", ("books", "below")),
            pooled(weeks, "bundling", "bundled_orders", "orders"),
            pooled(weeks, "offers", "hits", "bookings"),
        ]
        level = sub.split(" · ")[0].replace("level ", "L")
        widths = [6, 6, 7, 6, 6, 7, 7]
        print(
            f"{label + ' ' + level:<20} {len(weeks):>5} "
            + " ".join(f"{r.pct(c, 0):>{wd}}" for c, wd in zip(cells, widths, strict=True))
        )


def print_probes(probes: list[dict]) -> None:
    """One line per probe mode and level: the strategy against the starter's way, summed over the probed seeds."""
    for (mode, level), group in itertools.groupby(
        sorted((p for p in probes if "error" not in p), key=lambda p: (p["mode"], -p["level"])),
        key=lambda p: (p["mode"], p["level"]),
    ):
        ps = list(group)
        if mode == "quote":
            print(
                f"Pricing on {sum(p['probed'] for p in ps)} probed requests, L{level}: model "
                f"{r.eur(sum(p['model_revenue'] for p in ps))}, list price {r.eur(sum(p['list_revenue'] for p in ps))}, "
                f"at the flip {r.eur(sum(p['flip_revenue'] for p in ps))}"
            )
        else:
            n = sum(p["orders"] for p in ps)
            print(
                f"Fees on {n} probed orders, L{level}: ours book {sum(p['ours_booked'] for p in ps)}, the starter's "
                f"{sum(p['starter_booked'] for p in ps)}"
            )


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        description="Replay every strategy on the saved weeks, offline, and chart the results."
    )
    ap.add_argument("folders", nargs="*", help=f"folders to search for saved weeks (default: {' '.join(ROOTS)})")
    ap.add_argument("--out", default="out/replay.html")
    ap.add_argument("--csv", default="out/replay.csv")
    ap.add_argument("--probe", default=PROBES, help=f"probe.py's rows (default {PROBES})")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 1, help="weeks replayed at once (CPU only)")
    ap.add_argument("--no-serve", action="store_true", help="only write the files")
    ap.add_argument("--port", type=int, default=8001, help="port to serve on; a free one is used if it is taken")
    args = ap.parse_args(argv)
    folders, no_reveal = find_weeks(args.folders or [root for root in ROOTS if os.path.isdir(root)])
    if no_reveal:
        print(f"{skipped(no_reveal)}.", flush=True)
    if not folders:
        sys.exit("No saved weeks with a reveal found. Get the team's data first (README.md).")
    print(f"Replaying {len(folders)} weeks with {args.jobs} jobs.", flush=True)
    start = time.perf_counter()
    results = []
    with ProcessPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futures = {pool.submit(replay_week, str(folder)): folder for folder in folders}
        for done, future in enumerate(as_completed(futures), 1):
            res = future.result()
            results.append(res)
            w = res["week"]
            failed = [s for s in STRATEGIES if "error" in res.get(s, {})]
            note = f", failed: {', '.join(failed)}" if failed else ""
            print(f"  {done:>3}/{len(folders)} {w['experiment']} L{w['level']} {w['seed']}{note}", flush=True)
    probes = replay_probes(args.probe, ROOTS)
    seconds = time.perf_counter() - start
    write_csv(results, args.csv, probes)
    text = page(results, seconds, no_reveal, probes)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    Path(args.out).write_text(text, encoding="utf-8")
    print()
    print_summary(results)
    print_probes(probes)
    print(f"\nWrote {args.out} ({len(text.encode()) // 1024} kB) and {args.csv} in {seconds:.0f} s.")
    if not args.no_serve:
        r.serve(text, args.port)


if __name__ == "__main__":
    main()
