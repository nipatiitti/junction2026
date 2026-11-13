"""Loads weeks saved by scrape.py into one SQLite database, for queries with SQL. Needs no network.

    uv run db.py out/scrape                      # every saved week under out/scrape into out/spread.sqlite
    sqlite3 out/spread.sqlite "select kind, count(*) from events group by kind"

A week already in the database is skipped. README.md lists the tables.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from stats import Week, find_weeks, load_map, load_week

SCHEMA = """
create table if not exists weeks (
  id integer primary key, world_id text unique not null, seed text, level int, policy text,
  quote_range text, fee_range text, margin_cents int, revenue_cents int, won_orders int, on_time_share real,
  undelivered_share real, events int, requests int, seconds real, folder text
);
create table if not exists places (id text primary key, name text, lat real, lon real);
create table if not exists roads (from_id text, to_id text, km real, minutes int, primary key (from_id, to_id));
-- Every event, as the server sent it. json_extract(data, '$.request.legs[0].car.premium') reads any field.
-- gig_viewed events, the bulk of a played week, keep only their columns: the views table has them with the fee.
create table if not exists events (
  week_id int, seq int, at int, kind text, gig_id text, order_id text, driver_id text, data text,
  primary key (week_id, seq)
);
create table if not exists requests (
  week_id int, id text, dealer_id text, batch_id text, arrived_at int, respond_by int, legs int,
  reference_fee_cents int, note_text text, note_language text, outcome text, option_taken text,
  primary key (week_id, id)
);
-- One row per car of a request. The truth columns come from the reveal, for the orders that the week won.
create table if not exists legs (
  week_id int, request_id text, leg int, pickup_place text, delivery_place text, km real, minutes int,
  pickup_private int, delivery_private int, pickup_from int, pickup_to int, delivery_from int, delivery_to int,
  pickup_hours text, delivery_hours text, premium int, electric int, charge_percent int,
  ready_at int, released_at int, real_pickup_hours text, real_delivery_hours text, manual_gearbox int,
  needs_plates int, summer_tyres int, note_deadline int, picked_up_at int, delivered_at int,
  primary key (week_id, request_id, leg)
);
-- One row per delivery option, with our last quote for it (null when not quoted) and whether the dealer took it.
create table if not exists options (
  week_id int, request_id text, kind text, deadline int, list_price_cents int, quote_cents int, taken int,
  primary key (week_id, request_id, kind)
);
create table if not exists orders (
  week_id int, id text, dealer_id text, option text, price_cents int, deadline int, status text,
  last_pickup_at int, delivered_at int, late_minutes int, primary key (week_id, id)
);
create table if not exists gigs (
  week_id int, id text, order_id text, cars int, status text, posted_at int, opening_fee_cents int,
  fee_cents int, driver_id text, experienced int, manual_licence int, schedule text, stops text,
  primary key (week_id, id)
);
-- Each view of our gigs, with the fee that the driver saw (from the reveal).
create table if not exists views (week_id int, gig_id text, driver_id text, at int, fee_cents int);
create table if not exists drivers (
  week_id int, id text, home_place text, rating real, licence text, completed_gigs int, drops int,
  primary key (week_id, id)
);
create table if not exists ledger (
  week_id int, seq int, at int, kind text, cents int, order_id text, gig_id text, detail text,
  primary key (week_id, seq)
);
create table if not exists forecasts (
  week_id int, seq int, from_min int, to_min int, places text, text text, primary key (week_id, seq)
);
create index if not exists events_kind on events (kind, week_id);
create index if not exists legs_lane on legs (pickup_place, delivery_place);
create index if not exists views_gig on views (week_id, gig_id);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=120)  # several scrapes can write to one database: wait for its lock
    db.executescript(SCHEMA)
    return db


def dump(value) -> str | None:
    return None if value is None else json.dumps(value, separators=(",", ":"))


def add_map(db: sqlite3.Connection, world_map: dict) -> None:
    db.executemany(
        "insert or ignore into places values (?,?,?,?)",
        ((p["id"], p["name"], p["lat"], p["lon"]) for p in world_map["places"]),
    )
    db.executemany(
        "insert or ignore into roads values (?,?,?,?)",
        ((r["from"], r["to"], r["km"], r["minutes"]) for r in world_map["roads"]),
    )


def has_week(db: sqlite3.Connection, world_id: str) -> bool:
    return db.execute("select 1 from weeks where world_id = ?", (world_id,)).fetchone() is not None


def add_week(db: sqlite3.Connection, week: Week, folder: str = "") -> bool:
    """Inserts one week in one transaction. False when the database has it already."""
    meta = week.meta
    if has_week(db, meta["worldId"]):
        return False
    score = meta.get("score") or {}
    with db:
        week_id = db.execute(
            "insert into weeks (world_id, seed, level, policy, quote_range, fee_range, margin_cents, revenue_cents,"
            " won_orders, on_time_share, undelivered_share, events, requests, seconds, folder)"
            " values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                meta["worldId"],
                meta["seed"],
                meta["level"],
                meta["policy"],
                dump(meta.get("quoteRange")),
                dump(meta.get("feeRange")),
                score.get("marginCents"),
                score.get("revenueCents"),
                score.get("wonOrders"),
                score.get("onTimeShare"),
                score.get("undeliveredShare"),
                len(week.events),
                meta.get("requests"),
                meta.get("seconds"),
                folder,
            ),
        ).lastrowid
        roads = {(r[0], r[1]): (r[2], r[3]) for r in db.execute("select from_id, to_id, km, minutes from roads")}
        add_events(db, week_id, week.events)
        add_requests(db, week_id, week, roads)
        add_outcomes(db, week_id, week)
    return True


def add_events(db: sqlite3.Connection, week_id: int, events: list[dict]) -> None:
    db.executemany(
        "insert into events values (?,?,?,?,?,?,?,?)",
        (
            (
                week_id,
                e["seq"],
                e["at"],
                e["kind"],
                e.get("gigId"),
                e.get("orderId") or e.get("requestId"),
                e.get("driverId"),
                None if e["kind"] == "gig_viewed" else dump(e),
            )
            for e in events
        ),
    )
    lines = [e for e in events if e["kind"] == "ledger"]
    db.executemany(
        "insert into ledger values (?,?,?,?,?,?,?,?)",
        (
            (
                week_id,
                e["seq"],
                e["at"],
                e["line"]["kind"],
                e["line"]["cents"],
                e["line"]["orderId"],
                e["line"]["gigId"],
                e["line"]["detail"],
            )
            for e in lines
        ),
    )
    db.executemany(
        "insert into forecasts values (?,?,?,?,?,?)",
        (
            (week_id, e["seq"], e["from"], e["to"], dump(e["placeIds"]), e["text"])
            for e in events
            if e["kind"] == "forecast"
        ),
    )


def add_requests(db: sqlite3.Connection, week_id: int, week: Week, roads: dict) -> None:
    """Requests, their legs and options from the reveal, which has every request with our quote and its outcome.
    A week without a reveal falls back to the price_request events."""
    revealed = week.reveal.get("requests") or [
        {"request": e["request"], "quote": None, "outcome": None, "option": None}
        for e in week.events
        if e["kind"] == "price_request"
    ]
    truths = {o["orderId"]: o["legs"] for o in week.reveal.get("orders", [])}
    for item in revealed:
        r, quote = item["request"], item["quote"] or {}
        note = r["note"] or {}
        db.execute(
            "insert into requests values (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                week_id,
                r["id"],
                r["dealerId"],
                r["batchId"],
                r["arrivedAt"],
                r["respondBy"],
                len(r["legs"]),
                r["referenceFeeCents"],
                note.get("text"),
                note.get("language"),
                item["outcome"],
                item["option"],
            ),
        )
        db.executemany(
            "insert into options values (?,?,?,?,?,?,?)",
            (
                (
                    week_id,
                    r["id"],
                    o["kind"],
                    o["deadline"],
                    o["listPriceCents"],
                    quote.get(o["kind"]),
                    None if item["outcome"] is None else int(item["option"] == o["kind"]),
                )
                for o in r["options"]
            ),
        )
        truth = truths.get(r["id"], [])
        for i, leg in enumerate(r["legs"]):
            p, d, car = leg["pickup"], leg["delivery"], leg["car"]
            t = truth[i] if i < len(truth) else {}
            km, minutes = roads.get((p["placeId"], d["placeId"]), (None, None))
            db.execute(
                "insert into legs values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    week_id,
                    r["id"],
                    i,
                    p["placeId"],
                    d["placeId"],
                    km,
                    minutes,
                    p["privateAddress"],
                    d["privateAddress"],
                    p["window"]["from"],
                    p["window"]["to"],
                    d["window"]["from"],
                    d["window"]["to"],
                    dump(p["hours"]),
                    dump(d["hours"]),
                    car["premium"],
                    car["electric"],
                    car["chargePercent"],
                    t.get("readyAt"),
                    t.get("releasedAt"),
                    dump(t.get("pickupHours")),
                    dump(t.get("deliveryHours")),
                    t.get("manualGearbox"),
                    t.get("needsPlates"),
                    t.get("summerTyres"),
                    t.get("noteDeadline"),
                    t.get("pickedUpAt"),
                    t.get("deliveredAt"),
                ),
            )


def add_outcomes(db: sqlite3.Connection, week_id: int, week: Week) -> None:
    """Orders and gigs from the snapshot at the end, views from the reveal, and the driver list."""
    for o in week.snapshot.get("orders", []):
        done = [t for t in o["deliveredAt"] if t is not None]
        delivered = max(done) if len(done) == len(o["legs"]) else None
        db.execute(
            "insert into orders values (?,?,?,?,?,?,?,?,?,?)",
            (
                week_id,
                o["id"],
                o["dealerId"],
                o["option"],
                o["priceCents"],
                o["deadline"],
                o["status"],
                o["lastPickupAt"],
                delivered,
                None if delivered is None else max(0, delivered - o["deadline"]),
            ),
        )
    db.executemany(
        "insert into gigs values (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            (
                week_id,
                g["id"],
                g["stops"][0]["orderId"],
                sum(s["kind"] == "pickup" for s in g["stops"]),
                g["status"],
                g["postedAt"],
                g["schedule"][0]["feeCents"],
                g["feeCents"],
                g["driverId"],
                g["audience"]["experienced"],
                g["audience"]["manualLicence"],
                dump(g["schedule"]),
                dump(g["stops"]),
            )
            for g in week.snapshot.get("gigs", [])
        ),
    )
    db.executemany(
        "insert into views values (?,?,?,?,?)",
        ((week_id, v["gigId"], v["driverId"], v["at"], v["feeCents"]) for v in week.reveal.get("views", [])),
    )
    db.executemany(
        "insert into drivers values (?,?,?,?,?,?,?)",
        (
            (week_id, d["id"], d["homePlaceId"], d["rating"], d["licence"], d["completedGigs"], d["drops"])
            for d in week.drivers
        ),
    )


def load_folders(db: sqlite3.Connection, roots: list[Path]) -> tuple[int, int]:
    """Adds every saved week under the folders. Returns (added, skipped)."""
    world_map = load_map(roots)
    if world_map:
        with db:
            add_map(db, world_map)
    added = skipped = 0
    for folder in find_weeks(roots):
        meta = json.loads((folder / "meta.json").read_text())
        if has_week(db, meta["worldId"]):
            skipped += 1
            continue
        add_week(db, load_week(folder), str(folder))
        added += 1
    return added, skipped


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Loads weeks saved by scrape.py into a SQLite database.")
    parser.add_argument("folders", nargs="+", type=Path, help="scrape output folders")
    parser.add_argument("--db", type=Path, default=Path("out/spread.sqlite"), help="default out/spread.sqlite")
    args = parser.parse_args(argv)
    db = connect(args.db)
    added, skipped = load_folders(db, args.folders)
    weeks = db.execute("select count(*) from weeks").fetchone()[0]
    print(f"{added} weeks added, {skipped} already there; {args.db} holds {weeks} weeks")


if __name__ == "__main__":
    main()
