"""Loads weeks saved by scrape.py into one SQLite database, for queries with SQL. Needs no network.

    uv run db.py                                 # the team's committed weeks in data/scrape into out/spread.sqlite
    uv run db.py out/scrape                      # every saved week under out/scrape into out/spread.sqlite
    uv run db.py out/scrape out/probe            # the saved weeks and the probe rows (quote, fee, shape)
    sqlite3 out/spread.sqlite "select kind, count(*) from events group by kind"

A week already in the database is skipped. A probe file is loaded again when its size or mtime has changed.
README.md lists the tables.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path

from stats import OFFLINE_DATA, Week, find_weeks, load_map, load_week

SCHEMA = """
create table if not exists weeks (
  id integer primary key, world_id text unique not null, seed text, level int, policy text,
  quote_range text, fee_range text, margin_cents int, revenue_cents int, won_orders int, on_time_share real,
  undelivered_share real, events int, requests int, seconds real, folder text, settings text
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
-- Each action that the scrape sent, with the minute it was applied and the world's answer (actions.jsonl.gz).
-- A quote, post, reprice or offer keeps its whole body in data; reprices give each gig's fee schedule over time.
create table if not exists actions (
  week_id int, seq int, at int, type text, request_id text, gig_id text, driver_id text, fee_cents int,
  ok int, result_id text, reason text, data text, primary key (week_id, seq)
);
-- The driver list at each midnight and at the end (rosters.jsonl.gz): changes in completed_gigs and drops show who
-- worked when. The drivers table holds the list at the start.
create table if not exists rosters (
  week_id int, at int, driver_id text, rating real, completed_gigs int, drops int, primary key (week_id, at, driver_id)
);
-- Where our drivers were, sampled during the week with scrape.py --sample-every (positions.jsonl.gz).
create table if not exists positions (week_id int, at int, driver_id text, place_id text, gig_id text);
-- One row per probe file that was loaded, with its size and mtime: an unchanged file is skipped.
create table if not exists probe_files (
  file text primary key, mode text, level int, seed text, size int, mtime_ns int, rows int, bad_lines int
);
-- One row per probed delivery option (probe.py quote). Joins quote_facts by weeks.seed, level, request_id, option.
create table if not exists probes (
  level int, seed text, request_id text, option text, options text, dealer_id text, arrived_at int,
  day int, hour int, pickup_place text, delivery_place text, legs int, list_price_cents int,
  reference_fee_cents int, flip_cents real, flip_ratio real, bracket_low_cents int, bracket_high_cents int,
  ends text, monotone int, error text, trials text, file text,
  primary key (level, seed, request_id, option)
);
-- One row per probed order (probe.py fee).
create table if not exists fee_probes (
  level int, seed text, order_id text, option text, dealer_id text, won_at int, day int, hour int,
  last_pickup_at int, deadline int, pickup_place text, delivery_place text, legs int, premium int,
  reference_fee_cents int, window_minutes int, flip_cents real, flip_ratio real, bracket_low_cents int,
  bracket_high_cents int, ends text, monotone int, error text, expired_at_top int, booked_driver_id text,
  booked_minutes int, booked_views int, booked_expired int, trials text, file text,
  primary key (level, seed, order_id)
);
-- One row per probed pair of requests (probe.py shape): each car's single flip, the flip of both as one gig, the
-- saving, and who booked at each flip. A trade-in has one order id; its two cars are lanes 0 and 1.
create table if not exists shape_probes (
  level int, seed text, pair_id text, kind text, order_ids text, day int, hour int, probed_at int, gap_minutes int,
  pickup_place_0 text, delivery_place_0 text, pickup_place_1 text, delivery_place_1 text, pair_reference_cents int,
  window_minutes int, single0_flip_cents real, single1_flip_cents real, combined_flip_cents real,
  sum_single_flip_cents real, saving_cents real, saving_ratio real, combined_over_sum real, same_driver int,
  single0_driver_id text, single0_home text, single1_driver_id text, single1_home text, combined_driver_id text,
  combined_home text, ends text, monotone int, error text, trials text, file text,
  primary key (level, seed, pair_id)
);
create index if not exists events_kind on events (kind, week_id);
create index if not exists legs_lane on legs (pickup_place, delivery_place);
create index if not exists views_gig on views (week_id, gig_id);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=120)  # several scrapes can write to one database: wait for its lock
    db.executescript(SCHEMA)
    if "settings" not in {row[1] for row in db.execute("pragma table_info(weeks)")}:  # a database from before #49
        db.execute("alter table weeks add column settings text")
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
            " won_orders, on_time_share, undelivered_share, events, requests, seconds, folder, settings)"
            " values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
                dump(meta.get("settings")),
            ),
        ).lastrowid
        roads = {(r[0], r[1]): (r[2], r[3]) for r in db.execute("select from_id, to_id, km, minutes from roads")}
        add_events(db, week_id, week.events)
        add_requests(db, week_id, week, roads)
        add_outcomes(db, week_id, week)
        add_records(db, week_id, week)
    return True


def add_records(db: sqlite3.Connection, week_id: int, week: Week) -> None:
    """What the scrape recorded beside the server's own records: actions, driver lists and positions."""
    rows = []
    for row in week.actions:
        a, r = row["action"], row["result"]
        fee = a.get("feeCents") or (a["schedule"][0]["feeCents"] if a.get("schedule") else None)
        rows.append(
            (
                week_id,
                row["seq"],
                row["at"],
                a["type"],
                a.get("requestId"),
                a.get("gigId") or (r.get("id") if a["type"] == "post" else None),
                a.get("driverId"),
                fee,
                int(r["ok"]),
                r.get("id"),
                r.get("reason"),
                dump(a),
            )
        )
    db.executemany("insert into actions values (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    db.executemany(
        "insert or ignore into rosters values (?,?,?,?,?,?)",
        (
            (week_id, r["at"], d["id"], d["rating"], d["completedGigs"], d["drops"])
            for r in week.rosters
            for d in r["drivers"]
        ),
    )
    db.executemany(
        "insert into positions values (?,?,?,?,?)",
        ((week_id, s["at"], p["driverId"], p["placeId"], p["gigId"]) for s in week.positions for p in s["positions"]),
    )


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


PROBE_FILE = re.compile(r"(quote|fee|shape)-L(\d+)-(.+)\.jsonl$")


def as_int(value) -> int | None:
    return None if value is None else int(value)


def probe_row(mode: str, level: int, seed: str, row: dict, key: str) -> tuple:
    """One row of probes (quote) or fee_probes (fee). A missing field becomes null."""
    lane = row.get("lane") or [None, None]
    bracket = row.get("bracketCents") or [None, None]
    flip = (row.get("flipCents"), row.get("flipRatio"), bracket[0], bracket[1], row.get("ends"))
    if mode == "quote":
        return (
            level,
            seed,
            row["requestId"],
            row["option"],
            dump(row.get("options")),
            row.get("dealerId"),
            row.get("arrivedAt"),
            row.get("day"),
            row.get("hour"),
            lane[0],
            lane[1],
            row.get("legs"),
            row.get("listPriceCents"),
            row.get("referenceFeeCents"),
            *flip,
            as_int(row.get("monotone")),
            row.get("error"),
            dump(row.get("trials")),
            key,
        )
    booked = row.get("atFlip") or {}
    return (
        level,
        seed,
        row["orderId"],
        row.get("option"),
        row.get("dealerId"),
        row.get("wonAt"),
        row.get("day"),
        row.get("hour"),
        row.get("lastPickupAt"),
        row.get("deadline"),
        lane[0],
        lane[1],
        row.get("legs"),
        as_int(row.get("premium")),
        row.get("referenceFeeCents"),
        row.get("windowMinutes"),
        *flip,
        as_int(row.get("monotone")),
        row.get("error"),
        as_int(row.get("expiredAtTop")),
        booked.get("driverId"),
        booked.get("minutes"),
        booked.get("views"),
        as_int(booked.get("expired")),
        dump(row.get("trials")),
        key,
    )


def shape_row(level: int, seed: str, row: dict, key: str) -> tuple:
    """One row of shape_probes. A missing field (a pair that ended in an error) becomes null."""
    lanes = (row.get("lanes") or []) + [[None, None]] * 2
    treatments = [*(row.get("single") or [None, None]), row.get("combined")]
    flips, drivers = [], []
    for found in treatments:
        found = found or {}
        booked = found.get("atFlip") or {}
        flips.append(found.get("flipCents"))
        drivers += [booked.get("driverId"), booked.get("homePlaceId")]
    together = row.get("together") or {}
    return (
        level,
        seed,
        row["pairId"],
        row.get("kind"),
        dump(row.get("orderIds")),
        row.get("day"),
        row.get("hour"),
        row.get("probedAt"),
        row.get("gapMinutes"),
        *lanes[0],
        *lanes[1],
        row.get("pairReferenceCents"),
        row.get("windowMinutes"),
        *flips,
        row.get("sumSingleFlipCents"),
        row.get("savingCents"),
        row.get("savingRatio"),
        row.get("combinedOverSum"),
        as_int(together.get("sameDriver")),
        *drivers,
        row.get("ends"),
        as_int(row.get("monotone")),
        row.get("error"),
        dump({name: (t or {}).get("trials") for name, t in zip(("single0", "single1", "combined"), treatments)}),
        key,
    )


# The table of each probe mode and the fields a row needs. The scout's requests-L<level>-<seed>.json cache is skipped.
PROBE_TABLES = {
    "quote": ("probes", ("requestId", "option")),
    "fee": ("fee_probes", ("orderId",)),
    "shape": ("shape_probes", ("pairId",)),
}


def load_probes(db: sqlite3.Connection, roots: list[Path]) -> tuple[int, int]:
    """Loads every probe file under the folders. Returns (loaded, unchanged).

    A file whose size and mtime match its probe_files row is skipped; a changed file replaces its rows in full.
    A line that is not a JSON object with the key fields (the last line of a file a probe is still writing) is
    skipped and counted in bad_lines. Rows of a probe file that was deleted from disk stay in the database."""
    loaded = unchanged = 0
    for root in roots:
        for path in sorted(root.rglob("*.jsonl")):
            match = PROBE_FILE.fullmatch(path.name)
            if not match:
                continue
            mode, level, seed = match[1], int(match[2]), match[3]
            key, stat = str(path.resolve()), path.stat()
            known = db.execute("select size, mtime_ns from probe_files where file = ?", (key,)).fetchone()
            if known == (stat.st_size, stat.st_mtime_ns):
                unchanged += 1
                continue
            table, fields = PROBE_TABLES[mode]
            rows, bad = [], 0
            for line in path.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    row = None
                if not isinstance(row, dict) or any(row.get(f) is None for f in fields):
                    bad += 1
                    continue
                rows.append(
                    shape_row(level, seed, row, key) if mode == "shape" else probe_row(mode, level, seed, row, key)
                )
            with db:
                db.execute(f"delete from {table} where file = ?", (key,))
                if rows:
                    db.executemany(f"insert or replace into {table} values ({','.join('?' * len(rows[0]))})", rows)
                db.execute(
                    "insert or replace into probe_files values (?,?,?,?,?,?,?,?)",
                    (key, mode, level, seed, stat.st_size, stat.st_mtime_ns, len(rows), bad),
                )
            loaded += 1
    return loaded, unchanged


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Loads weeks saved by scrape.py and rows saved by probe.py into a SQLite database."
    )
    parser.add_argument(
        "folders",
        nargs="*",
        type=Path,
        help="scrape or probe output folders (default: the committed data/scrape and out/probe)",
    )
    parser.add_argument("--db", type=Path, default=Path("out/spread.sqlite"), help="default out/spread.sqlite")
    args = parser.parse_args(argv)
    db = connect(args.db)
    added, skipped = load_folders(db, args.folders or [OFFLINE_DATA])
    loaded, unchanged = load_probes(db, args.folders or [Path("out/probe")])
    weeks = db.execute("select count(*) from weeks").fetchone()[0]
    print(f"{added} weeks added, {skipped} already there; {args.db} holds {weeks} weeks")
    q = db.execute("select count(*) from probes").fetchone()[0]
    f = db.execute("select count(*) from fee_probes").fetchone()[0]
    s = db.execute("select count(*) from shape_probes").fetchone()[0]
    print(
        f"{loaded} probe files loaded, {unchanged} unchanged; {args.db} holds {q} quote probe rows, "
        f"{f} fee probe rows and {s} shape probe rows"
    )


if __name__ == "__main__":
    main()
