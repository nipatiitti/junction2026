"""Builds derived analysis tables (the facts) from the raw tables of db.py, in the same SQLite database.

    uv run python -m analysis.facts                       # build the weeks that have no facts yet
    uv run python -m analysis.facts --db out/spread.sqlite --rebuild
    uv run python -m analysis.facts --week 71 --week 72   # rebuild these weeks (weeks.id)

Each week is built in one transaction, so a rerun is safe. analysis/README.md lists the tables and columns.
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from db import connect

VERSION = 1  # bump on any column or definition change: the next run rebuilds every week
DAY = 1440
WORLD_END = 14280  # Wednesday 22:00, the last roster of every recorded week
DECLINE_RATIO = 5.0  # a quote at 5 x list or more is a decline
NEAR_KM = 30.0  # the notification radius of the rules
WAKE, SLEEP = 7 * 60, 23 * 60  # no driver reads a notification from 23:00 to 07:00
ACCOUNTS = (
    "revenue",
    "driver_fee",
    "late_refund",
    "undelivered_penalty",
    "failed_visit",
    "waiting",
    "release_fee",
    "fine",
)
EXTRA_DRIVING = "Extra driving after a change of plan"
LATE_DETAIL = re.compile(r"Late by (\d+) minutes, (\d+)% back")
LATE_BUCKETS = {10: "le_2h", 25: "le_24h", 50: "le_2bd", 100: "gt_2bd"}
OPTION_RANK = {"same_day": 0, "next_day": 1, "within_3_days": 2}
EVENT_KINDS = (
    "order_won",
    "order_lost",
    "order_cancelled",
    "order_changed",
    "deadline_close",
    "gig_booked",
    "gig_dropped",
    "no_show",
    "gig_expired",
    "gig_started",
    "offer_answered",
    "visit_failed",
)
ACCOUNT_COLUMNS = ",\n  ".join(f"{k}_cents int" for k in (*ACCOUNTS, "other"))

SCHEMA = f"""
create table if not exists week_facts (
  week_id int primary key, world_id text, seed text, level int, policy text, experiment text, recorded int,
  quote_share real, fee_shape text, fee_cap real, offers int, quote_lo real, quote_hi real, fee_lo real, fee_hi real,
  drivers int, drivers_experienced int, drivers_manual int, towns_with_drivers int,
  requests int, quoted int, declined int, unquoted int,
  won int, cancelled int, counted int, delivered int, on_time int, late int, undelivered int,
  on_time_share real, late_slack int,
  {ACCOUNT_COLUMNS},
  margin_cents int, gigs int, bookings int, drops int, no_shows int, expired int, views int, war_day int,
  facts_version int
);
create table if not exists quote_facts (
  week_id int, level int, request_id text, option text, dealer_id text, batch_id text, batch_size int,
  arrived_at int, respond_by int, day int, hour int, legs int, pickup_place text, delivery_place text,
  km real, km_total real, minutes_total int, private_pickup int, private_delivery int, premium int, electric int,
  low_charge int, has_note int, note_language text, options_offered int, option_rank int, deadline int,
  lead_minutes int, hours_to_deadline real, list_price_cents int, reference_fee_cents int, fee_share real,
  quote_cents int, ratio real, declined int, quoted int, options_quoted int, cheapest int, min_other_ratio real,
  outcome text, taken int, dealer_trust int, dealer_on_time_before int, dealer_late_before int,
  dealer_open_orders int, dealer_overdue_open int, dealer_requests_before int, dealer_quoted_before int,
  dealer_won_before int, dealer_unquoted_before int, drivers_pickup int, drivers_delivery int,
  drivers_near_pickup int, drivers_near_delivery int, war_guess int,
  primary key (week_id, request_id, option)
);
create table if not exists order_facts (
  week_id int, level int, order_id text, dealer_id text, option text, won_at int, day int, hour int,
  legs int, pickup_place text, delivery_place text, km real, km_total real,
  private_pickup int, private_delivery int, premium int, electric int, has_note int,
  price_cents int, list_price_cents int, ratio real, reference_fee_cents int,
  deadline_won int, last_pickup_won int, deadline int, changes int, place_changed int,
  ready_late int, held int, needs_plates int, manual_gearbox int, summer_tyres int, note_deadline int,
  hours_differ int, status text, cancelled int, cancelled_at int, counted int, delivered_at int,
  {ACCOUNT_COLUMNS},
  extra_driving_cents int, margin_cents int, refund_pct int, late_minutes int, late_bucket text, on_time int,
  gigs int, bookings int, drops int, no_shows int, expired int, reprices int, failed_visits int,
  views int, viewers int, shared_gig int, first_posted_at int, minutes_to_post int, first_fee_ratio real,
  first_view_fee_cents int, first_booked_at int, minutes_to_booking int, first_booked_ratio real,
  paid_ratio real, open_minutes int, dealer_trust_won int,
  primary key (week_id, order_id)
);
create table if not exists gig_facts (
  week_id int, level int, gig_id text, source text, order_id text, orders int, cars int, order_post_no int,
  pickup_place text, delivery_place text, km real, drive_minutes int, private_pickup int, private_delivery int,
  premium int, experienced int, manual_licence int, with_plates int, with_charging int,
  posted_at int, posted_day int, posted_hour int, typical_fee_cents int, opening_fee_cents int,
  opening_ratio real, top_fee_cents int, steps int, reprices int, spells int, open_minutes int,
  views int, viewers int, bookings int, drops int, no_shows int, failed_visits int,
  first_booked_at int, first_booked_fee_cents int, minutes_to_booking int, outcome text, driver_id text,
  booked_at int, fee_cents int, fee_ratio real, paid_cents int, started_at int,
  last_pickup_at_post int, minutes_to_last_pickup int, driver_home text,
  home_to_pickup_km real, delivery_to_home_km real,
  primary key (week_id, gig_id)
);
create table if not exists gig_spells (
  week_id int, level int, gig_id text, spell int, fee_run int, interval int, source text, order_id text,
  order_post_no int, cars int, orders int, pickup_place text, delivery_place text, km real, drive_minutes int,
  private_pickup int, premium int, experienced int, manual_licence int,
  start_at int, end_at int, minutes int, day_minutes int, day int, hour int,
  fee_cents int, typical_fee_cents int, fee_ratio real, next_fee_cents int,
  last_pickup_at int, minutes_to_last_pickup int, deadline_warned int, opened_by text, order_age_minutes int,
  views int, viewers int, new_viewers int, order_views_before int, order_viewers_before int,
  order_viewed_before int, first_view_fee_cents int, fee_over_first_view real, order_bookings_before int,
  taught_orders int, taught_raise real, taught_wait real, drivers_pickup int, drivers_near_pickup int,
  snow int, offers int, end_kind text, end_estimated int, booked int, driver_id text, booked_fee_cents int,
  via_offer int, kept int, view_fee_mismatches int,
  primary key (week_id, gig_id, spell)
);
create table if not exists town_days (
  week_id int, level int, place text, day int, drivers_home int, experienced_home int, manual_home int,
  drivers_near int, snow int, requests int, requests_delivery int, won int, viewers_home int, views_home int,
  bookers_home int, bookings_home int, starters_home int, gigs_posted int, gigs_open int, open_minutes int,
  views int, viewers int, bookings int, booked_share real, mean_booked_ratio real, min_booked_ratio real,
  primary key (week_id, place, day)
);
create table if not exists week_days (
  week_id int, level int, day int, requests int, quoted int, won int, band_n int, band_won int,
  band_share real, war_score real, war_guess int,
  primary key (week_id, day)
);
create index if not exists quote_facts_lane on quote_facts (level, pickup_place, delivery_place);
create index if not exists quote_facts_dealer on quote_facts (week_id, dealer_id);
create index if not exists order_facts_dealer on order_facts (week_id, dealer_id);
create index if not exists gig_facts_lane on gig_facts (pickup_place, delivery_place, posted_day);
create index if not exists gig_facts_order on gig_facts (week_id, order_id);
create index if not exists gig_spells_order on gig_spells (week_id, order_id);
create index if not exists gig_spells_town on gig_spells (week_id, pickup_place, day);
"""
TABLES = ("week_facts", "quote_facts", "order_facts", "gig_facts", "gig_spells", "town_days", "week_days")


def _columns() -> dict[str, list[str]]:
    mem = sqlite3.connect(":memory:")
    mem.executescript(SCHEMA)
    return {t: [row[1] for row in mem.execute(f"pragma table_info({t})")] for t in TABLES}


COLUMNS = _columns()  # column order of each table, read from SCHEMA: the order of the insert tuples


# ---------------------------------------------------------------- helpers


def shown_fee(schedule: list[dict], t: int) -> int:
    """The fee of the last step with at <= t; before the first step, the first step's fee."""
    fee = schedule[0]["feeCents"]
    for step in schedule:
        if step["at"] > t:
            break
        fee = step["feeCents"]
    return fee


def day_minutes(start: int, end: int) -> int:
    """Minutes of [start, end) between 07:00 and 23:00."""
    total, day = 0, start // DAY
    while day * DAY < end:
        lo, hi = max(start, day * DAY + WAKE), min(end, day * DAY + SLEEP)
        total += max(0, hi - lo)
        day += 1
    return total


def near_places(places: dict[str, tuple[float, float]]) -> dict[str, set[str]]:
    """Places within NEAR_KM straight-line km of each place, the place included."""

    def km(a, b):
        (lat1, lon1), (lat2, lon2) = (map(math.radians, p) for p in (a, b))
        h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
        return 2 * 6371 * math.asin(math.sqrt(h))

    return {p: {q for q in places if km(places[p], places[q]) <= NEAR_KM} for p in places}


def gig_number(gig_id: str) -> int:
    digits = re.sub(r"\D", "", gig_id or "")
    return int(digits) if digits else 0


def div(a, b) -> float | None:
    return None if a is None or not b else a / b


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def flag(value) -> int:
    return 1 if value else 0


def any_flag(rows: list[dict], key: str) -> int:
    return flag(any(r[key] for r in rows))


def experiment_of(folder: str | None, policy: str) -> str:
    parts = (folder or "").split("/")
    marks = [i for i, p in enumerate(parts) if p == "scrape"]
    if marks and marks[-1] + 1 < len(parts) and parts[marks[-1] + 1]:
        return parts[marks[-1] + 1]
    return policy


def two(value: str | None) -> tuple:
    pair = json.loads(value) if value else None
    return (pair[0], pair[1]) if isinstance(pair, list) and len(pair) == 2 else (None, None)


def snowy(forecasts: list[tuple], place: str, start: int, end: int) -> int:
    return flag(any(place in places and lo < end and hi > start for lo, hi, places in forecasts))


def load_world(db: sqlite3.Connection) -> dict:
    places = {p: (lat, lon) for p, lat, lon in db.execute("select id, lat, lon from places")}
    roads = {(a, b): km for a, b, km in db.execute("select from_id, to_id, km from roads")}
    return {"places": sorted(places), "roads": roads, "near": near_places(places)}


# ---------------------------------------------------------------- the raw week


def read_week(db: sqlite3.Connection, week_id: int) -> dict:
    """Every raw row the facts need, read once, filtered by week_id."""

    def rows(sql: str, *extra) -> list[sqlite3.Row]:
        cur = db.execute(sql, (week_id, *extra))
        cur.row_factory = sqlite3.Row
        return cur.fetchall()

    w = {"week_id": week_id, "meta": rows("select * from weeks where id = ?")[0]}
    w["level"] = w["meta"]["level"]
    w["requests"] = {r["id"]: r for r in rows("select * from requests where week_id = ?")}
    w["legs"] = defaultdict(list)
    for r in rows("select * from legs where week_id = ? order by request_id, leg"):
        w["legs"][r["request_id"]].append(r)
    w["options"] = defaultdict(list)
    for r in rows("select * from options where week_id = ?"):
        w["options"][r["request_id"]].append(r)
    w["orders"] = {r["id"]: r for r in rows("select * from orders where week_id = ?")}
    w["drivers"] = {r["id"]: r for r in rows("select * from drivers where week_id = ?")}
    w["ledger"] = rows("select * from ledger where week_id = ? order by seq")
    w["forecasts"] = [
        (lo, hi, set(json.loads(p or "[]")))
        for lo, hi, p in db.execute("select from_min, to_min, places from forecasts where week_id = ?", (week_id,))
    ]
    w["gigs"] = {}
    for r in rows("select * from gigs where week_id = ?"):
        g = dict(r)
        g["schedule"] = json.loads(g["schedule"] or "[]")
        g["stops"] = json.loads(g["stops"] or "[]")
        w["gigs"][g["id"]] = g
    w["views"] = db.execute(
        "select gig_id, driver_id, at, fee_cents from views where week_id = ? order by rowid", (week_id,)
    ).fetchall()
    w["recorded"] = db.execute("select 1 from actions where week_id = ? limit 1", (week_id,)).fetchone() is not None
    w["actions"] = [
        (seq, at, kind, gig, driver, fee, json.loads(data) if data else {})
        for seq, at, kind, gig, driver, fee, data in db.execute(
            "select seq, at, type, gig_id, driver_id, fee_cents, data from actions"
            " where week_id = ? and ok = 1 and type in ('post','reprice','withdraw','release','offer') order by seq",
            (week_id,),
        )
    ]
    marks = ",".join("?" * len(EVENT_KINDS))
    w["events"] = [
        (seq, at, kind, gig, order, driver, json.loads(data) if data else {})
        for seq, at, kind, gig, order, driver, data in db.execute(
            f"select seq, at, kind, gig_id, order_id, driver_id, data from events"
            f" where week_id = ? and kind in ({marks}) order by seq",
            (week_id, *EVENT_KINDS),
        )
    ]
    return w


def last_pickup_timelines(w: dict) -> tuple[dict, dict]:
    """Per order: (ats, values) of lastPickupAt in event order, and the first deadline_close minute."""
    timeline, warned = defaultdict(lambda: ([], [])), {}
    for _seq, at, kind, _gig, order, _driver, data in w["events"]:
        if kind in ("order_won", "order_changed"):
            oid, value = data["order"]["id"], data["order"].get("lastPickupAt")
        elif kind == "deadline_close":
            oid, value = order, data.get("lastPickupAt")
            warned.setdefault(oid, at)
        else:
            continue
        if value is not None:
            timeline[oid][0].append(at)
            timeline[oid][1].append(value)
    return timeline, warned


def known_at(timeline: dict, order: str, t: int) -> int | None:
    ats, values = timeline.get(order, ([], []))
    i = bisect.bisect_right(ats, t)
    return values[i - 1] if i else None


# ---------------------------------------------------------------- quote_facts


def dealer_pass(w: dict, quoted_requests: set, unquoted_requests: set) -> dict[str, dict]:
    """The dealer's state at each request's decision, from one pass over the week in event order (spec 5.1)."""
    dealer_of = {rid: r["dealer_id"] for rid, r in w["requests"].items()}
    for oid, o in w["orders"].items():
        dealer_of.setdefault(oid, o["dealer_id"])
    deadline_of = {oid: o["deadline"] for oid, o in w["orders"].items()}
    late_orders = {line["order_id"] for line in w["ledger"] if line["kind"] == "late_refund"}
    changes = [
        (seq, at, kind, data["order"]["id"] if kind == "order_won" else order)
        for seq, at, kind, _gig, order, _driver, data in w["events"]
        if kind in ("order_won", "order_lost", "order_cancelled")
    ]
    changes += [
        (line["seq"], line["at"], "revenue", line["order_id"]) for line in w["ledger"] if line["kind"] == "revenue"
    ]
    changes.sort()
    keys = ("trust", "on_time", "late", "requests", "quoted", "won", "unquoted")
    state = defaultdict(lambda: {**dict.fromkeys(keys, 0), "open": {}})
    at_decision = {}
    for _seq, at, kind, oid in changes:
        dealer = dealer_of.get(oid)
        if dealer is None:
            continue
        s = state[dealer]
        if kind in ("order_won", "order_lost"):
            if oid in at_decision:
                continue
            at_decision[oid] = {
                "dealer_trust": s["trust"],
                "dealer_on_time_before": s["on_time"],
                "dealer_late_before": s["late"],
                "dealer_open_orders": len(s["open"]),
                "dealer_overdue_open": sum(1 for d in s["open"].values() if d is not None and d < at),
                "dealer_requests_before": s["requests"],
                "dealer_quoted_before": s["quoted"],
                "dealer_won_before": s["won"],
                "dealer_unquoted_before": s["unquoted"],
            }
            s["requests"] += 1
            s["quoted"] += oid in quoted_requests
            s["unquoted"] += oid in unquoted_requests
            if kind == "order_won":
                s["won"] += 1
                s["open"][oid] = deadline_of.get(oid)
        elif kind == "revenue":
            s["open"].pop(oid, None)
            if oid in late_orders:
                s["trust"] //= 2
                s["late"] += 1
            else:
                s["trust"] = min(25, s["trust"] + 1)
                s["on_time"] += 1
        else:  # order_cancelled
            s["open"].pop(oid, None)
    return at_decision


def quote_rows(w: dict, world: dict) -> list[dict]:
    level, near = w["level"], world["near"]
    home = Counter(d["home_place"] for d in w["drivers"].values())
    batches = Counter(r["batch_id"] for r in w["requests"].values() if r["batch_id"] is not None)
    by_request = {}
    for rid, r in w["requests"].items():
        legs, opts = w["legs"].get(rid, []), w["options"].get(rid, [])
        leg0 = legs[0] if legs else None
        pickup = leg0["pickup_place"] if leg0 else None
        delivery = leg0["delivery_place"] if leg0 else None
        base = {
            "week_id": w["week_id"],
            "level": level,
            "request_id": rid,
            "dealer_id": r["dealer_id"],
            "batch_id": r["batch_id"],
            "batch_size": batches[r["batch_id"]] if r["batch_id"] is not None else 1,
            "arrived_at": r["arrived_at"],
            "respond_by": r["respond_by"],
            "day": r["arrived_at"] // DAY,
            "hour": r["arrived_at"] % DAY // 60,
            "legs": r["legs"],
            "pickup_place": pickup,
            "delivery_place": delivery,
            "km": leg0["km"] if leg0 else None,
            "km_total": sum(x["km"] or 0 for x in legs) if legs else None,
            "minutes_total": sum(x["minutes"] or 0 for x in legs) if legs else None,
            "private_pickup": any_flag(legs, "pickup_private"),
            "private_delivery": any_flag(legs, "delivery_private"),
            "premium": any_flag(legs, "premium"),
            "electric": any_flag(legs, "electric"),
            "low_charge": flag(
                any(
                    x["electric"]
                    and x["charge_percent"] is not None
                    and x["charge_percent"] < 30
                    and (x["km"] or 0) > 200
                    for x in legs
                )
            ),
            "has_note": flag(r["note_text"] is not None),
            "note_language": r["note_language"],
            "options_offered": len(opts),
            "lead_minutes": leg0["pickup_from"] - r["arrived_at"] if leg0 and leg0["pickup_from"] is not None else None,
            "reference_fee_cents": r["reference_fee_cents"],
            "outcome": r["outcome"],
            "drivers_pickup": home[pickup] if pickup else 0,
            "drivers_delivery": home[delivery] if delivery else 0,
            "drivers_near_pickup": sum(home[p] for p in near.get(pickup, ())),
            "drivers_near_delivery": sum(home[p] for p in near.get(delivery, ())),
            "war_guess": 0,
        }
        rows = []
        for o in opts:
            ratio = div(o["quote_cents"], o["list_price_cents"])
            declined = flag(ratio is not None and ratio >= DECLINE_RATIO)
            rows.append(
                {
                    **base,
                    "option": o["kind"],
                    "option_rank": OPTION_RANK.get(o["kind"]),
                    "deadline": o["deadline"],
                    "hours_to_deadline": (o["deadline"] - r["arrived_at"]) / 60 if o["deadline"] is not None else None,
                    "list_price_cents": o["list_price_cents"],
                    "fee_share": div(r["reference_fee_cents"], o["list_price_cents"]),
                    "quote_cents": o["quote_cents"],
                    "ratio": ratio,
                    "declined": declined,
                    "quoted": flag(o["quote_cents"] is not None and not declined),
                    "taken": o["taken"],
                }
            )
        quoted = [x for x in rows if x["quoted"]]
        for x in rows:
            x["options_quoted"] = len(quoted)
            others = [y for y in quoted if y is not x]
            x["cheapest"] = flag(all(y["quote_cents"] >= x["quote_cents"] for y in others)) if x["quoted"] else None
            x["min_other_ratio"] = min((y["ratio"] for y in others), default=None)
        by_request[rid] = rows
    quoted_requests = {rid for rid, rows in by_request.items() if any(x["quoted"] for x in rows)}
    unquoted_requests = {rid for rid, r in w["requests"].items() if r["outcome"] == "unquoted"}
    decisions = dealer_pass(w, quoted_requests, unquoted_requests)
    empty = dict.fromkeys(
        (
            "dealer_trust",
            "dealer_on_time_before",
            "dealer_late_before",
            "dealer_open_orders",
            "dealer_overdue_open",
            "dealer_requests_before",
            "dealer_quoted_before",
            "dealer_won_before",
            "dealer_unquoted_before",
        )
    )
    out = []
    for rid, rows in by_request.items():
        state = decisions.get(rid, empty)
        for x in rows:
            x.update(state)
            out.append(x)
    return out


# ---------------------------------------------------------------- gig_facts and gig_spells


def fee_pieces(schedule: list[dict], start: int, end: int, kind: str) -> list[tuple]:
    """The pieces of an open interval [start, end) at one fee within one day: (start, end, fee, end_kind, cont),
    cont = 1 for a piece that continues the one before it after a midnight cut (spec 7.2)."""
    end = max(end, start)
    steps = {s["at"] for s in schedule if start < s["at"] < end or (kind == "booked" and start < s["at"] == end)}
    cuts = [start, *sorted(steps)]
    merged = []
    for i, cut in enumerate(cuts):
        stop, last = (cuts[i + 1], False) if i + 1 < len(cuts) else (end, True)
        fee = shown_fee(schedule, cut)
        end_kind = kind if last else "raise"
        if merged and merged[-1][2] == fee:
            merged[-1] = (merged[-1][0], stop, fee, end_kind)
        else:
            merged.append((cut, stop, fee, end_kind))
    pieces = []
    for a, b, fee, end_kind in merged:
        cont, midnight = 0, (a // DAY + 1) * DAY
        while midnight < b:
            pieces.append((a, midnight, fee, "midnight", cont))
            a, cont, midnight = midnight, 1, midnight + DAY
        pieces.append((a, b, fee, end_kind, cont))
    return [p for p in pieces if p[0] < p[1] or p[3] == "booked"]


def gig_and_spell_rows(w: dict, world: dict, ctx: dict) -> tuple[list[dict], list[dict]]:
    """One pass per gig: its open periods at one fee (gig_spells) and its summary (gig_facts).
    Leaves per-gig and per-order lookups in ctx for order_rows and town_day_rows."""
    level, week_id, gigs = w["level"], w["week_id"], w["gigs"]
    legs_of = {(rid, x["leg"]): x for rid, legs in w["legs"].items() for x in legs}
    source = "actions" if any(a[2] == "post" for a in w["actions"]) else "gigs"
    home = Counter(d["home_place"] for d in w["drivers"].values())
    near = world["near"]

    changes, versions, posted = defaultdict(list), defaultdict(list), set()
    reprices, offers, releases, withdraws = Counter(), defaultdict(list), set(), set()
    for seq, at, kind, gig, driver, fee, data in w["actions"]:
        if kind in ("post", "reprice") and source == "actions":
            changes[gig].append((at, 1, seq, kind, data.get("schedule") or []))
            versions[gig].append(data.get("schedule") or [])
            if kind == "post":
                posted.add(gig)
            else:
                reprices[gig] += 1
        elif kind == "withdraw":
            changes[gig].append((at, 1, seq, kind, None))
            withdraws.add(gig)
        elif kind == "release":
            changes[gig].append((at, 1, seq, kind, None))
            releases.add(gig)
        elif kind == "offer":
            offers[gig].append((at, seq, driver, fee))
    for gid, g in gigs.items():
        if gid not in posted:
            changes[gid].append((g["posted_at"], 1, -1, "post", g["schedule"]))
            versions[gid] = [g["schedule"]]

    gig_events = defaultdict(Counter)
    bookings = defaultdict(list)  # gig -> [(at, driver, fee)]
    started, cancelled_gigs, expired_gigs = {}, set(), set()
    booked_minutes, accepted = set(), set()
    for seq, at, kind, gig, _order, driver, data in w["events"]:
        if kind == "order_cancelled":
            for item in data.get("gigs") or []:
                changes[item["gigId"]].append((at, 0, seq, "cancel", item.get("outcome")))
                cancelled_gigs.add(item["gigId"])
            continue
        if gig is None:
            continue
        gig_events[gig][kind] += 1
        if kind == "gig_booked":
            bookings[gig].append((at, driver, data.get("feeCents")))
            booked_minutes.add((gig, at))
        elif kind == "gig_started":
            started[gig] = at
        elif kind == "gig_expired":
            expired_gigs.add(gig)
        elif kind == "offer_answered" and data.get("answer") == "accepted":
            accepted.add((gig, driver, at))
        if kind in ("gig_booked", "gig_dropped", "no_show", "gig_expired", "offer_answered"):
            changes[gig].append((at, 0, seq, kind, (driver, data)))

    gig_views = defaultdict(list)  # gig -> [(index, at, driver, fee)]
    for i, (gig, driver, at, fee) in enumerate(w["views"]):
        gig_views[gig].append((i, at, driver, fee))

    # what each gig carries
    info = {}
    for gid, g in gigs.items():
        stops = g["stops"]
        pickups = [s for s in stops if s.get("kind") == "pickup"]
        deliveries = [s for s in stops if s.get("kind") == "delivery"]
        orders = list(dict.fromkeys(s["orderId"] for s in stops))
        cars = list(dict.fromkeys((s["orderId"], s["leg"]) for s in pickups))
        car_legs = [legs_of[c] for c in cars if c in legs_of]
        per_order = Counter(s["orderId"] for s in pickups)
        typical = 0.0
        for oid, n in per_order.items():
            r = w["requests"].get(oid)
            if r is not None and r["reference_fee_cents"] is not None and r["legs"]:
                typical += r["reference_fee_cents"] * n / r["legs"]
        first_pickup = legs_of.get((pickups[0]["orderId"], pickups[0]["leg"])) if pickups else None
        last_delivery = legs_of.get((deliveries[-1]["orderId"], deliveries[-1]["leg"])) if deliveries else None
        info[gid] = {
            "order_id": stops[0]["orderId"] if stops else g["order_id"],
            "orders": orders,
            "per_order": per_order,
            "cars": len(pickups),
            "pickup_place": first_pickup["pickup_place"] if first_pickup else None,
            "delivery_place": last_delivery["delivery_place"] if last_delivery else None,
            "km": sum(x["km"] or 0 for x in car_legs),
            "drive_minutes": sum(x["minutes"] or 0 for x in car_legs),
            "private_pickup": any_flag(car_legs, "pickup_private"),
            "private_delivery": any_flag(car_legs, "delivery_private"),
            "premium": any_flag(car_legs, "premium"),
            "with_plates": flag(any(s.get("withPlates") for s in pickups)),
            "with_charging": flag(any(s.get("withCharging") for s in pickups)),
            "typical_fee_cents": round(typical),
        }

    order_gigs = defaultdict(list)  # gigs by their first stop's order, in post order
    for gid in sorted(gigs, key=lambda g: (gigs[g]["posted_at"], gig_number(g))):
        order_gigs[info[gid]["order_id"]].append(gid)
    post_no = {gid: i + 1 for gids in order_gigs.values() for i, gid in enumerate(gids)}

    # the state machine of each gig (spec 7.2)
    raw = {}
    for gid, g in gigs.items():
        rows = []
        st = {"schedule": None, "open_from": None, "opened_by": None, "interval": -1}

        def close(end, kind, booking=None, estimated=0, st=st, rows=rows):
            for a, b, fee, end_kind, cont in fee_pieces(st["schedule"], st["open_from"], end, kind):
                row = {
                    "start_at": a,
                    "end_at": b,
                    "fee_cents": fee,
                    "end_kind": end_kind,
                    "cont": cont,
                    "interval": st["interval"],
                    "opened_by": st["opened_by"],
                    "end_estimated": estimated if end_kind == kind else 0,
                    "driver_id": None,
                    "booked_fee_cents": None,
                    "via_offer": None,
                }
                if end_kind == "booked" and b == end and booking:
                    row["driver_id"], row["booked_fee_cents"], row["via_offer"] = booking
                rows.append(row)
            st["open_from"] = None

        for at, _phase, _seq, kind, payload in sorted(changes.get(gid, []), key=lambda c: c[:3]):
            is_open = st["open_from"] is not None
            if kind == "post":
                if is_open:
                    close(at, "reprice")
                st["schedule"], st["open_from"], st["opened_by"] = payload, at, "post"
                st["interval"] += 1
            elif kind == "reprice":
                if is_open:
                    close(at, "reprice")
                    st["open_from"] = at
                st["schedule"] = payload
            elif kind == "gig_booked" and is_open:
                driver, data = payload
                close(at, "booked", (driver, data.get("feeCents"), flag((gid, driver, at) in accepted)))
            elif kind == "offer_answered" and is_open and (gid, at) not in booked_minutes:
                driver, data = payload
                if data.get("answer") == "accepted":
                    fee = None
                    for o_at, _s, o_driver, o_fee in offers.get(gid, []):
                        if o_driver == driver and o_at <= at:
                            fee = o_fee
                    close(at, "booked", (driver, fee, 1))
            elif kind in ("gig_dropped", "no_show") and not is_open and st["schedule"] is not None:
                st["open_from"], st["opened_by"] = at, "drop" if kind == "gig_dropped" else "no_show"
                st["interval"] += 1
            elif kind == "gig_expired" and is_open:
                close(at, "expired")
            elif kind == "withdraw" and is_open:
                close(at, "withdrawn")
            elif kind == "cancel" and payload == "withdrawn" and is_open:
                close(at, "cancelled")
        if st["open_from"] is not None:
            if source == "gigs" and g["status"] == "withdrawn":
                later = [
                    gigs[o]["posted_at"]
                    for o in order_gigs[info[gid]["order_id"]]
                    if gigs[o]["posted_at"] > g["posted_at"]
                ]
                seen = [v[1] for v in gig_views.get(gid, [])]
                end = min(later) if later else max(seen) if seen else st["open_from"]
                close(end, "withdrawn", estimated=1)
            else:
                close(WORLD_END, "end")
        rows.sort(key=lambda r: (r["start_at"], r["end_at"]))
        # views: the last row at their fee, else the row they fall in, else a row ending in their minute
        for row in rows:
            row["seen"], row["view_fee_mismatches"] = [], 0
        for view in gig_views.get(gid, []):
            _i, t, _driver, fee = view
            hit = [r for r in rows if r["start_at"] <= t <= r["end_at"] and r["fee_cents"] == fee]
            if hit:
                hit[-1]["seen"].append(view)
                continue
            row = next((r for r in rows if r["start_at"] <= t < r["end_at"]), None)
            row = row or next((r for r in reversed(rows) if r["end_at"] == t), None)
            if row:
                row["seen"].append(view)
                row["view_fee_mismatches"] += row["fee_cents"] != fee
        raw[gid] = rows

    # order-level lookups
    timeline, warned = last_pickup_timelines(w)
    order_views = {}  # order -> sorted [(at, index, driver, fee)] over the gigs with that first-stop order
    for oid, gids in order_gigs.items():
        order_views[oid] = sorted((at, i, d, fee) for gid in gids for i, at, d, fee in gig_views.get(gid, []))
    first_view, view_ats, viewer_firsts, driver_first = {}, {}, {}, {}
    for oid, views in order_views.items():
        first_view[oid] = views[0] if views else None
        view_ats[oid] = [v[0] for v in views]
        firsts = {}
        for at, i, d, _fee in views:
            firsts.setdefault(d, (at, i))
        driver_first[oid] = firsts
        viewer_firsts[oid] = sorted(at for at, _i in firsts.values())
    first_posted = {oid: gigs[gids[0]]["posted_at"] for oid, gids in order_gigs.items()}
    booked_ends = defaultdict(list)
    for gid, rows in raw.items():
        for r in rows:
            if r["end_kind"] == "booked":
                booked_ends[info[gid]["order_id"]].append(r["end_at"])
    for ends in booked_ends.values():
        ends.sort()
    # what the week's bookings teach: per booking, its fee over and its minutes after the order's first view
    taught = []
    for gid, items in bookings.items():
        fv = first_view.get(info[gid]["order_id"]) if gid in info else None
        for at, _d, fee in items:
            raise_ = div(fee, fv[3]) if fv else None
            taught.append((at, raise_, at - fv[0] if fv else None))
    taught.sort(key=lambda x: x[0])
    taught_ats = [x[0] for x in taught]
    cum = [(0, 0.0, 0, 0.0, 0)]
    for _at, r_, wait in taught:
        n, rs, rn, ws, wn = cum[-1]
        cum.append((n + 1, rs + (r_ or 0), rn + (r_ is not None), ws + (wait or 0), wn + (wait is not None)))
    offer_ats = {gid: [o[0] for o in items] for gid, items in offers.items()}

    spells, facts = [], []
    for gid, g in gigs.items():
        gi, rows = info[gid], raw[gid]
        oid, typical = gi["order_id"], gi["typical_fee_cents"]
        pickup = gi["pickup_place"]
        last_booked = max((i for i, r in enumerate(rows) if r["end_kind"] == "booked"), default=None)
        fee_run = -1
        for n, r in enumerate(rows):
            start, end = r["start_at"], r["end_at"]
            fee_run += 0 if r["cont"] and n else 1
            booked = r["end_kind"] == "booked"
            known = known_at(timeline, oid, start)
            fv = first_view.get(oid)
            fv = fv if fv and fv[0] < start else None
            k = bisect.bisect_left(taught_ats, start)
            cn, rs, rn, ws, wn = cum[k]
            viewers = {v[2] for v in r["seen"]}
            seen_index = {v[0] for v in r["seen"]}
            ends = booked_ends.get(oid, [])
            ats = offer_ats.get(gid, [])
            spells.append(
                {
                    "week_id": week_id,
                    "level": level,
                    "gig_id": gid,
                    "spell": n,
                    "fee_run": fee_run,
                    "interval": r["interval"],
                    "source": source,
                    "order_id": oid,
                    "order_post_no": post_no[gid],
                    "cars": gi["cars"],
                    "orders": len(gi["orders"]),
                    "pickup_place": pickup,
                    "delivery_place": gi["delivery_place"],
                    "km": gi["km"],
                    "drive_minutes": gi["drive_minutes"],
                    "private_pickup": gi["private_pickup"],
                    "premium": gi["premium"],
                    "experienced": g["experienced"],
                    "manual_licence": g["manual_licence"],
                    "start_at": start,
                    "end_at": end,
                    "minutes": end - start,
                    "day_minutes": day_minutes(start, end),
                    "day": start // DAY,
                    "hour": start % DAY // 60,
                    "fee_cents": r["fee_cents"],
                    "typical_fee_cents": typical,
                    "fee_ratio": div(r["fee_cents"], typical),
                    "next_fee_cents": rows[n + 1]["fee_cents"]
                    if r["end_kind"] in ("raise", "reprice", "midnight") and n + 1 < len(rows)
                    else None,
                    "last_pickup_at": known,
                    "minutes_to_last_pickup": known - start if known is not None else None,
                    "deadline_warned": flag(oid in warned and warned[oid] <= start),
                    "opened_by": r["opened_by"],
                    "order_age_minutes": start - first_posted[oid],
                    "views": len(r["seen"]),
                    "viewers": len(viewers),
                    "new_viewers": sum(1 for d in viewers if driver_first[oid][d][1] in seen_index),
                    "order_views_before": bisect.bisect_left(view_ats[oid], start),
                    "order_viewers_before": bisect.bisect_left(viewer_firsts[oid], start),
                    "order_viewed_before": flag(bisect.bisect_left(view_ats[oid], start)),
                    "first_view_fee_cents": fv[3] if fv else None,
                    "fee_over_first_view": div(r["fee_cents"], fv[3]) if fv else None,
                    "order_bookings_before": bisect.bisect_right(ends, start) - (1 if booked and end <= start else 0),
                    "taught_orders": cn,
                    "taught_raise": rs / rn if rn else None,
                    "taught_wait": ws / wn if wn else None,
                    "drivers_pickup": home[pickup] if pickup else 0,
                    "drivers_near_pickup": sum(home[p] for p in near.get(pickup, ())),
                    "snow": snowy(w["forecasts"], pickup, start, max(end, start + 1)),
                    "offers": bisect.bisect_right(ats, end) - bisect.bisect_left(ats, start),
                    "end_kind": r["end_kind"],
                    "end_estimated": r["end_estimated"],
                    "booked": flag(booked),
                    "driver_id": r["driver_id"],
                    "booked_fee_cents": r["booked_fee_cents"],
                    "via_offer": r["via_offer"] if booked else None,
                    "kept": flag(n == last_booked and g["status"] in ("booked", "working", "done")) if booked else None,
                    "view_fee_mismatches": r["view_fee_mismatches"],
                }
            )
        first_version, last_version = versions[gid][0], versions[gid][-1]
        views = gig_views.get(gid, [])
        events = gig_events[gid]
        booked_list = bookings.get(gid, [])
        driver = g["driver_id"]
        if g["status"] == "withdrawn":
            outcome = (
                "expired"
                if gid in expired_gigs
                else "cancelled"
                if gid in cancelled_gigs
                else "released"
                if gid in releases
                else "withdrawn"
            )
        else:
            outcome = g["status"]
        paid = [line["cents"] for line in w["ledger"] if line["kind"] == "driver_fee" and line["gig_id"] == gid]
        known = known_at(timeline, oid, g["posted_at"])
        driver_home = w["drivers"][driver]["home_place"] if driver in w["drivers"] else None
        opening = first_version[0]["feeCents"] if gid in posted and first_version else g["opening_fee_cents"]
        facts.append(
            {
                "week_id": week_id,
                "level": level,
                "gig_id": gid,
                "source": source,
                "order_id": oid,
                "orders": len(gi["orders"]),
                "cars": gi["cars"],
                "order_post_no": post_no[gid],
                **{
                    k: gi[k]
                    for k in (
                        "pickup_place",
                        "delivery_place",
                        "km",
                        "drive_minutes",
                        "private_pickup",
                        "private_delivery",
                        "premium",
                        "with_plates",
                        "with_charging",
                        "typical_fee_cents",
                    )
                },
                "experienced": g["experienced"],
                "manual_licence": g["manual_licence"],
                "posted_at": g["posted_at"],
                "posted_day": g["posted_at"] // DAY,
                "posted_hour": g["posted_at"] % DAY // 60,
                "opening_fee_cents": opening,
                "opening_ratio": div(opening, typical),
                "top_fee_cents": last_version[-1]["feeCents"] if last_version else None,
                "steps": len(first_version),
                "reprices": reprices[gid],
                "spells": len(rows),
                "open_minutes": sum(r["end_at"] - r["start_at"] for r in rows),
                "views": len(views),
                "viewers": len({v[2] for v in views}),
                "bookings": events["gig_booked"],
                "drops": events["gig_dropped"],
                "no_shows": events["no_show"],
                "failed_visits": events["visit_failed"],
                "first_booked_at": booked_list[0][0] if booked_list else None,
                "first_booked_fee_cents": booked_list[0][2] if booked_list else None,
                "minutes_to_booking": booked_list[0][0] - g["posted_at"] if booked_list else None,
                "outcome": outcome,
                "driver_id": driver,
                "booked_at": booked_list[-1][0] if driver is not None and booked_list else None,
                "fee_cents": g["fee_cents"] if driver is not None else None,
                "fee_ratio": div(g["fee_cents"], typical) if driver is not None else None,
                "paid_cents": -sum(paid) if paid else None,
                "started_at": started.get(gid),
                "last_pickup_at_post": known,
                "minutes_to_last_pickup": known - g["posted_at"] if known is not None else None,
                "driver_home": driver_home,
                "home_to_pickup_km": world["roads"].get((driver_home, pickup)),
                "delivery_to_home_km": world["roads"].get((gi["delivery_place"], driver_home)),
            }
        )
    ctx.update(
        info=info,
        gig_views=gig_views,
        gig_events=gig_events,
        bookings=bookings,
        reprices=reprices,
        source=source,
    )
    return facts, spells


# ---------------------------------------------------------------- order_facts


def allocate_ledger(w: dict, info: dict) -> dict[str, list[tuple]]:
    """Each ledger line's cents by order: [(kind, cents, at, detail)] (spec 6, ledger allocation)."""
    by_order = defaultdict(list)
    for line in w["ledger"]:
        item = (line["kind"], line["cents"], line["at"], line["detail"])
        oid, gid = line["order_id"], line["gig_id"]
        if oid is not None:
            if oid in w["orders"]:
                by_order[oid].append(item)
        elif gid in info and info[gid]["per_order"]:
            per_order = info[gid]["per_order"]
            total = sum(per_order.values())
            shares = {o: line["cents"] * n // total for o, n in per_order.items()}
            first = next(iter(per_order))
            shares[first] += line["cents"] - sum(shares.values())
            for o, cents in shares.items():
                if o in w["orders"]:
                    by_order[o].append((line["kind"], cents, line["at"], line["detail"]))
    return by_order


def order_rows(w: dict, quotes: list[dict], gig_facts: list[dict], spells: list[dict], ctx: dict) -> list[dict]:
    info, gig_views, gig_events, bookings = ctx["info"], ctx["gig_views"], ctx["gig_events"], ctx["bookings"]
    trust_won = {q["request_id"]: q["dealer_trust"] for q in quotes}
    gig_fact = {g["gig_id"]: g for g in gig_facts}
    open_minutes = Counter()
    for s in spells:
        open_minutes[s["gig_id"]] += s["minutes"]
    gigs_of = defaultdict(list)
    for gid, gi in info.items():
        for oid in gi["orders"]:
            gigs_of[oid].append(gid)
    won, changed, cancelled_at, failed = {}, defaultdict(list), {}, Counter()
    for _seq, at, kind, _gig, order, _driver, data in w["events"]:
        if kind == "order_won":
            won.setdefault(data["order"]["id"], (at, data["order"]))
        elif kind == "order_changed":
            changed[data["order"]["id"]].append(data["order"])
        elif kind == "order_cancelled":
            cancelled_at.setdefault(order, at)
        elif kind == "visit_failed":
            failed[order] += 1
    lines = allocate_ledger(w, info)
    out = []
    for oid, o in w["orders"].items():
        r = w["requests"].get(oid)
        legs = w["legs"].get(oid, [])
        leg0 = legs[0] if legs else None
        option = next((x for x in w["options"].get(oid, []) if x["kind"] == o["option"]), None)
        list_price = option["list_price_cents"] if option else None
        won_at, won_order = won.get(oid, (None, {}))
        place_changed = 0
        for change in changed.get(oid, []):
            for i, leg in enumerate(change.get("legs") or []):
                if i < len(legs) and (
                    (leg.get("pickup") or {}).get("placeId") != legs[i]["pickup_place"]
                    or (leg.get("delivery") or {}).get("placeId") != legs[i]["delivery_place"]
                ):
                    place_changed = 1
        account = Counter()
        extra, refund, revenue_at, fee_lines = 0, None, None, 0
        for kind, cents, at, detail in lines.get(oid, []):
            account[kind if kind in ACCOUNTS else "other"] += cents
            if kind == "driver_fee":
                fee_lines += 1
                if detail == EXTRA_DRIVING:
                    extra += cents
            elif kind == "late_refund" and refund is None:
                refund = (cents, detail)
            elif kind == "revenue" and revenue_at is None:
                revenue_at = at
        is_cancelled = flag(o["status"] == "cancelled")
        refund_pct = late_minutes = None
        if refund is not None:
            match = LATE_DETAIL.search(refund[1] or "")
            if match:
                late_minutes, refund_pct = int(match[1]), int(match[2])
            elif o["price_cents"]:
                refund_pct = round(100 * -refund[0] / o["price_cents"])
        elif revenue_at is not None:
            late_minutes = 0
        if is_cancelled:
            bucket = "cancelled"
        elif revenue_at is None:
            bucket = "undelivered"
        elif refund is None:
            bucket = "on_time"
        else:
            bucket = LATE_BUCKETS.get(refund_pct, "late_other")
        gids = gigs_of.get(oid, [])
        firsts = sorted(gids, key=lambda g: (gig_fact[g]["posted_at"], gig_number(g)))
        views = [v for g in gids for v in gig_views.get(g, [])]
        first_view = min(views, key=lambda v: (v[1], v[0])) if views else None
        booked = sorted((at, g, fee) for g in gids for at, _d, fee in bookings.get(g, []))
        first_posted = gig_fact[firsts[0]]["posted_at"] if firsts else None
        ref = r["reference_fee_cents"] if r else None
        out.append(
            {
                "week_id": w["week_id"],
                "level": w["level"],
                "order_id": oid,
                "dealer_id": o["dealer_id"],
                "option": o["option"],
                "won_at": won_at,
                "day": won_at // DAY if won_at is not None else None,
                "hour": won_at % DAY // 60 if won_at is not None else None,
                "legs": r["legs"] if r else None,
                "pickup_place": leg0["pickup_place"] if leg0 else None,
                "delivery_place": leg0["delivery_place"] if leg0 else None,
                "km": leg0["km"] if leg0 else None,
                "km_total": sum(x["km"] or 0 for x in legs) if legs else None,
                "private_pickup": any_flag(legs, "pickup_private"),
                "private_delivery": any_flag(legs, "delivery_private"),
                "premium": any_flag(legs, "premium"),
                "electric": any_flag(legs, "electric"),
                "has_note": flag(r and r["note_text"] is not None),
                "price_cents": o["price_cents"],
                "list_price_cents": list_price,
                "ratio": div(o["price_cents"], list_price),
                "reference_fee_cents": ref,
                "deadline_won": won_order.get("deadline"),
                "last_pickup_won": won_order.get("lastPickupAt"),
                "deadline": o["deadline"],
                "changes": len(changed.get(oid, [])),
                "place_changed": place_changed,
                "ready_late": flag(
                    any(
                        x["ready_at"] is not None and x["pickup_from"] is not None and x["ready_at"] > x["pickup_from"]
                        for x in legs
                    )
                ),
                "held": flag(any(x["released_at"] is not None for x in legs)),
                "needs_plates": any_flag(legs, "needs_plates"),
                "manual_gearbox": any_flag(legs, "manual_gearbox"),
                "summer_tyres": any_flag(legs, "summer_tyres"),
                "note_deadline": flag(any(x["note_deadline"] is not None for x in legs)),
                "hours_differ": flag(
                    any(
                        x["real_pickup_hours"] != x["pickup_hours"] or x["real_delivery_hours"] != x["delivery_hours"]
                        for x in legs
                    )
                ),
                "status": o["status"],
                "cancelled": is_cancelled,
                "cancelled_at": cancelled_at.get(oid),
                "counted": 1 - is_cancelled,
                "delivered_at": revenue_at,
                **{f"{k}_cents": account[k] for k in (*ACCOUNTS, "other")},
                "extra_driving_cents": extra,
                "margin_cents": sum(account.values()),
                "refund_pct": refund_pct,
                "late_minutes": late_minutes,
                "late_bucket": bucket,
                "on_time": None if is_cancelled else flag(bucket == "on_time"),
                "gigs": len(gids),
                "bookings": sum(gig_events[g]["gig_booked"] for g in gids),
                "drops": sum(gig_events[g]["gig_dropped"] for g in gids),
                "no_shows": sum(gig_events[g]["no_show"] for g in gids),
                "expired": sum(gig_events[g]["gig_expired"] for g in gids),
                "reprices": sum(ctx["reprices"][g] for g in gids),
                "failed_visits": failed[oid],
                "views": len(views),
                "viewers": len({v[2] for v in views}),
                "shared_gig": flag(any(len(info[g]["orders"]) > 1 for g in gids)),
                "first_posted_at": first_posted,
                "minutes_to_post": first_posted - won_at if first_posted is not None and won_at is not None else None,
                "first_fee_ratio": gig_fact[firsts[0]]["opening_ratio"] if firsts else None,
                "first_view_fee_cents": first_view[3] if first_view else None,
                "first_booked_at": booked[0][0] if booked else None,
                "minutes_to_booking": booked[0][0] - first_posted if booked else None,
                "first_booked_ratio": div(booked[0][2], info[booked[0][1]]["typical_fee_cents"]) if booked else None,
                "paid_ratio": div(-(account["driver_fee"] - extra), ref) if fee_lines else None,
                "open_minutes": sum(open_minutes[g] for g in gids),
                "dealer_trust_won": trust_won.get(oid),
            }
        )
    return out


# ---------------------------------------------------------------- town_days, week_days, week_facts


def town_day_rows(
    w: dict, world: dict, quotes: list[dict], orders: list[dict], gigs: list[dict], spells: list[dict]
) -> list[dict]:
    drivers = w["drivers"].values()
    home_of = {d["id"]: d["home_place"] for d in drivers}
    home = Counter(d["home_place"] for d in drivers)
    experienced = Counter(
        d["home_place"] for d in drivers if (d["rating"] or 0) >= 4.8 and (d["completed_gigs"] or 0) >= 50
    )
    manual = Counter(d["home_place"] for d in drivers if d["licence"] == "manual")
    pickup_of = {g["gig_id"]: g["pickup_place"] for g in gigs}
    cell = defaultdict(Counter)  # (place, day) -> counts
    sets = defaultdict(set)  # (name, place, day) -> drivers or gigs
    ratios = defaultdict(list)
    seen = set()
    for q in quotes:
        if q["request_id"] in seen:
            continue
        seen.add(q["request_id"])
        cell[(q["pickup_place"], q["day"])]["requests"] += 1
        cell[(q["delivery_place"], q["day"])]["requests_delivery"] += 1
    for o in orders:
        if o["won_at"] is not None:
            cell[(o["pickup_place"], o["day"])]["won"] += 1
    for gid, driver, at, _fee in w["views"]:
        day = at // DAY
        h = home_of.get(driver)
        cell[(h, day)]["views_home"] += 1
        sets[("viewers_home", h, day)].add(driver)
        p = pickup_of.get(gid)
        cell[(p, day)]["views"] += 1
        sets[("viewers", p, day)].add(driver)
    for _seq, at, kind, _gig, _order, driver, _data in w["events"]:
        if kind in ("gig_booked", "gig_started"):
            h, day = home_of.get(driver), at // DAY
            if kind == "gig_booked":
                cell[(h, day)]["bookings_home"] += 1
                sets[("bookers_home", h, day)].add(driver)
            else:
                sets[("starters_home", h, day)].add(driver)
    for g in gigs:
        cell[(g["pickup_place"], g["posted_day"])]["gigs_posted"] += 1
    for s in spells:
        key = (s["pickup_place"], s["day"])
        sets[("gigs_open", *key)].add(s["gig_id"])
        cell[key]["open_minutes"] += s["minutes"]
        if s["booked"]:
            cell[key]["bookings"] += 1
            if s["booked_fee_cents"] is not None and s["typical_fee_cents"]:
                ratios[key].append(s["booked_fee_cents"] / s["typical_fee_cents"])
    out = []
    for place in world["places"]:
        near = sum(home[p] for p in world["near"].get(place, ()))
        for day in range(10):
            c, key = cell[(place, day)], (place, day)
            gigs_open = len(sets[("gigs_open", *key)])
            out.append(
                {
                    "week_id": w["week_id"],
                    "level": w["level"],
                    "place": place,
                    "day": day,
                    "drivers_home": home[place],
                    "experienced_home": experienced[place],
                    "manual_home": manual[place],
                    "drivers_near": near,
                    "snow": snowy(w["forecasts"], place, day * DAY, (day + 1) * DAY),
                    "requests": c["requests"],
                    "requests_delivery": c["requests_delivery"],
                    "won": c["won"],
                    "viewers_home": len(sets[("viewers_home", *key)]),
                    "views_home": c["views_home"],
                    "bookers_home": len(sets[("bookers_home", *key)]),
                    "bookings_home": c["bookings_home"],
                    "starters_home": len(sets[("starters_home", *key)]),
                    "gigs_posted": c["gigs_posted"],
                    "gigs_open": gigs_open,
                    "open_minutes": c["open_minutes"],
                    "views": c["views"],
                    "viewers": len(sets[("viewers", *key)]),
                    "bookings": c["bookings"],
                    "booked_share": div(c["bookings"], gigs_open),
                    "mean_booked_ratio": mean(ratios[key]),
                    "min_booked_ratio": min(ratios[key], default=None),
                }
            )
    return out


def week_day_rows(w: dict, quotes: list[dict]) -> list[dict]:
    days = {d: {"requests": set(), "quoted": set(), "won": set(), "band_n": 0, "band_won": 0} for d in range(5)}
    for q in quotes:
        d = days.get(q["day"])
        if d is None:
            continue
        d["requests"].add(q["request_id"])
        if q["quoted"]:
            d["quoted"].add(q["request_id"])
            if 1.0 <= q["ratio"] < 1.25 and 480 <= q["arrived_at"] % DAY < 1080:
                d["band_n"] += 1
                d["band_won"] += q["taken"] == 1
        if q["outcome"] == "won":
            d["won"].add(q["request_id"])
    share = {day: div(d["band_won"], d["band_n"]) for day, d in days.items()}
    rows = []
    for day, d in days.items():
        others = [share[o] for o in days if o != day and days[o]["band_n"] >= 10]
        score = share[day] - mean(others) if d["band_n"] >= 10 and len(others) >= 2 else None
        rows.append(
            {
                "week_id": w["week_id"],
                "level": w["level"],
                "day": day,
                "requests": len(d["requests"]),
                "quoted": len(d["quoted"]),
                "won": len(d["won"]),
                "band_n": d["band_n"],
                "band_won": d["band_won"],
                "band_share": share[day],
                "war_score": score,
                "war_guess": 0,
            }
        )
    scored = [r for r in rows if r["war_score"] is not None]
    if w["level"] == 8 and scored:
        low = min(scored, key=lambda r: r["war_score"])
        if low["war_score"] <= -0.25:
            low["war_guess"] = 1
    return rows


def week_row(w: dict, quotes: list[dict], orders: list[dict], gigs: list[dict], days: list[dict]) -> dict:
    m = w["meta"]
    settings = json.loads(m["settings"]) if m["settings"] else None
    drivers = w["drivers"].values()
    by_request = defaultdict(list)
    for q in quotes:
        by_request[q["request_id"]].append(q)
    quoted = sum(1 for rows in by_request.values() if any(q["quoted"] for q in rows))
    declined = sum(
        1 for rows in by_request.values() if any(q["declined"] for q in rows) and not any(q["quoted"] for q in rows)
    )
    account = Counter()
    for line in w["ledger"]:
        account[line["kind"] if line["kind"] in ACCOUNTS else "other"] += line["cents"]
    counted = sum(o["counted"] for o in orders)
    delivered = [o for o in orders if o["delivered_at"] is not None]
    on_time = sum(1 for o in orders if o["on_time"] == 1)
    late = sum(1 for o in delivered if o["counted"] and o["on_time"] != 1)
    undelivered = sum(1 for o in orders if o["late_bucket"] == "undelivered")
    events = Counter(kind for _s, _a, kind, *_rest in w["events"])
    quote_lo, quote_hi = two(m["quote_range"])
    fee_lo, fee_hi = two(m["fee_range"])
    war = [d["day"] for d in days if d["war_guess"]]
    return {
        "week_id": w["week_id"],
        "world_id": m["world_id"],
        "seed": m["seed"],
        "level": m["level"],
        "policy": m["policy"],
        "experiment": experiment_of(m["folder"], m["policy"]),
        "recorded": flag(w["recorded"]),
        "quote_share": settings.get("quoteShare") if settings else None,
        "fee_shape": settings.get("feeShape") if settings else None,
        "fee_cap": settings.get("feeCap") if settings else None,
        "offers": settings.get("offers") if settings else None,
        "quote_lo": quote_lo,
        "quote_hi": quote_hi,
        "fee_lo": fee_lo,
        "fee_hi": fee_hi,
        "drivers": len(drivers),
        "drivers_experienced": sum(
            1 for d in drivers if (d["rating"] or 0) >= 4.8 and (d["completed_gigs"] or 0) >= 50
        ),
        "drivers_manual": sum(1 for d in drivers if d["licence"] == "manual"),
        "towns_with_drivers": len({d["home_place"] for d in drivers}),
        "requests": len(w["requests"]),
        "quoted": quoted,
        "declined": declined,
        "unquoted": sum(1 for r in w["requests"].values() if r["outcome"] == "unquoted"),
        "won": len(orders),
        "cancelled": sum(o["cancelled"] for o in orders),
        "counted": counted,
        "delivered": len(delivered),
        "on_time": on_time,
        "late": late,
        "undelivered": undelivered,
        "on_time_share": div(on_time, counted),
        "late_slack": counted // 10 - (late + undelivered),
        **{f"{k}_cents": account[k] for k in (*ACCOUNTS, "other")},
        "margin_cents": sum(line["cents"] for line in w["ledger"]),
        "gigs": len(gigs),
        "bookings": events["gig_booked"],
        "drops": events["gig_dropped"],
        "no_shows": events["no_show"],
        "expired": events["gig_expired"],
        "views": len(w["views"]),
        "war_day": war[0] if war else None,
        "facts_version": VERSION,
    }


# ---------------------------------------------------------------- building


def as_tuples(table: str, rows: list[dict]) -> list[tuple]:
    columns = COLUMNS[table]
    return [tuple(row[c] for c in columns) for row in rows]


def build_week(db: sqlite3.Connection, week_id: int, world: dict) -> dict:
    """Reads one week's raw rows, computes its facts and writes them in one transaction. Returns the row counts."""
    w = read_week(db, week_id)
    ctx = {}
    quotes = quote_rows(w, world)
    gigs, spells = gig_and_spell_rows(w, world, ctx)
    orders = order_rows(w, quotes, gigs, spells, ctx)
    towns = town_day_rows(w, world, quotes, orders, gigs, spells)
    days = week_day_rows(w, quotes)
    war = {d["day"] for d in days if d["war_guess"]}
    for q in quotes:
        q["war_guess"] = flag(q["day"] in war)
    week = week_row(w, quotes, orders, gigs, days)
    tables = {
        "week_facts": [week],
        "quote_facts": quotes,
        "order_facts": orders,
        "gig_facts": gigs,
        "gig_spells": spells,
        "town_days": towns,
        "week_days": days,
    }
    with db:
        for table, rows in tables.items():
            db.execute(f"delete from {table} where week_id = ?", (week_id,))
            marks = ",".join("?" * len(COLUMNS[table]))
            db.executemany(f"insert into {table} values ({marks})", as_tuples(table, rows))
    return {"meta": w["meta"], "week": week, **{t: len(rows) for t, rows in tables.items()}}


def stale(db: sqlite3.Connection) -> bool:
    """True when the facts tables exist but were built by another VERSION (or cannot be read)."""
    if not db.execute("select 1 from sqlite_master where type = 'table' and name = 'week_facts'").fetchone():
        return False
    try:
        versions = {v for (v,) in db.execute("select distinct facts_version from week_facts")}
    except sqlite3.Error:
        return True
    return bool(versions - {VERSION})


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Build the derived analysis tables (the facts) of the scrape database."
    )
    parser.add_argument("--db", type=Path, default=Path("out/spread.sqlite"), help="the database (out/spread.sqlite)")
    parser.add_argument("--rebuild", action="store_true", help="drop the facts tables and build every week")
    parser.add_argument("--week", type=int, action="append", default=[], help="rebuild only this week (weeks.id)")
    args = parser.parse_args(argv)
    db = connect(args.db)
    rebuild = args.rebuild or stale(db)
    if rebuild:
        with db:
            for table in TABLES:
                db.execute(f"drop table if exists {table}")
    db.executescript(SCHEMA)
    world = load_world(db)
    weeks = [w for (w,) in db.execute("select id from weeks order by id")]
    if args.week:
        missing = set(args.week) - set(weeks)
        if missing:
            sys.exit(f"no such week: {', '.join(map(str, sorted(missing)))}")
        todo = sorted(set(args.week)) if not rebuild else weeks
    elif rebuild:
        todo = weeks
    else:
        done = {w for (w,) in db.execute("select week_id from week_facts where facts_version = ?", (VERSION,))}
        todo = [w for w in weeks if w not in done]
    for week_id in todo:
        start = time.perf_counter()
        built = build_week(db, week_id, world)
        week = built["week"]
        print(
            f"week {week_id} {week['experiment']} L{week['level']} {week['seed']}: {built['quote_facts']} quotes,"
            f" {built['order_facts']} orders, {built['gig_facts']} gigs, {built['gig_spells']} spells,"
            f" {time.perf_counter() - start:.1f}s",
            flush=True,
        )
    counts = ", ".join(f"{t} {db.execute(f'select count(*) from {t}').fetchone()[0]}" for t in TABLES)
    print(f"{len(todo)} weeks built, {len(weeks) - len(todo)} up to date; {args.db} holds: {counts} rows")


if __name__ == "__main__":
    main()
