"""Builds out/quotas.sqlite: every incoming price request ("quota") of every saved week, one row per delivery option,
for analysis across seeds and policies.

    uv run python -m analysis.quotas                         # out/spread.sqlite -> out/quotas.sqlite
    uv run python -m analysis.quotas --rebuild               # drop it and build every week again
    uv run python -m analysis.quotas --db other.sqlite --out /tmp/quotas.sqlite

Reads the raw tables of `out/spread.sqlite` (built by `uv run python -m tools.db`), and only the weeks that the
target does not hold yet, so a rerun after new runs is quick. analysis/README.md lists the tables, the columns and
the queries they answer.

A quota is the demand side only: ids, dealer, times, legs, the note, and each option's kind, deadline and list
price. The columns after `quote_cents` are the world's own answer, so a row is still readable on its own; they are
excluded from the stream hash, which is over the incoming fields alone. That hash is what lets `seed_stream` say
whether the worlds of one seed saw the same requests.
"""

from __future__ import annotations

import argparse
import hashlib
import sqlite3
import time
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path

DAY = 1440  # minutes in a day
DECLINE_RATIO = 5.0  # a quote at 5 x the list price or more is a decline (analysis/facts.py)
LOW_CHARGE_KM = 200.0  # an electric car under 30% over this many km needs a charging stop
OPTION_RANK = {"same_day": 0, "next_day": 1, "within_3_days": 2}
TABLES = ("quota", "world_stream", "seed_stream")
COLUMNS = [
    "week_id",
    "level",
    "seed",
    "policy",
    "world_id",
    "request_id",
    "dealer_id",
    "batch_id",
    "arrived_at",
    "respond_by",
    "day",
    "hour",
    "legs",
    "km",
    "minutes",
    "pickup_place",
    "delivery_place",
    "private_pickup",
    "private_delivery",
    "pickup_from",
    "pickup_to",
    "delivery_from",
    "delivery_to",
    "premium",
    "electric",
    "charge_percent",
    "low_charge",
    "has_note",
    "note_language",
    "option_rank",
    "option_kind",
    "deadline",
    "hours_to_deadline",
    "list_price_cents",
    "reference_fee_cents",
    "quote_cents",
    "ratio",
    "declined",
    "taken",
    "outcome",
]
FIELDS = COLUMNS[5:]  # the incoming fields and the answer, without the five that name the world
INSERT = f"insert into quota ({', '.join(COLUMNS)}) values ({', '.join('?' * len(COLUMNS))})"

SCHEMA = """
create table if not exists quota (
  week_id int, level int, seed text, policy text, world_id text,
  request_id text, dealer_id text, batch_id text,
  arrived_at int, respond_by int, day int, hour int,
  legs int, km real, minutes real,
  pickup_place text, delivery_place text, private_pickup int, private_delivery int,
  pickup_from int, pickup_to int, delivery_from int, delivery_to int,
  premium int, electric int, charge_percent int, low_charge int,
  has_note int, note_language text,
  option_rank int, option_kind text, deadline int, hours_to_deadline real,
  list_price_cents int, reference_fee_cents int,
  quote_cents int, ratio real, declined int, taken int, outcome text
);

create table if not exists world_stream (
  week_id int primary key, level int, seed text, policy text, world_id text, requests int, stream_hash text
);

create table if not exists seed_stream (
  level int, seed text, worlds int, distinct_streams int,
  requests_min int, requests_max int, consistent int,
  primary key (level, seed)
);
"""

# Built after the option rows, so the first full build inserts without maintaining them.
INDICES = """
create index if not exists quota_seed on quota (level, seed);
create index if not exists quota_dealer on quota (dealer_id);
create index if not exists quota_lane on quota (pickup_place, delivery_place);
create index if not exists quota_option on quota (option_kind);
create index if not exists quota_arrived on quota (arrived_at);
create index if not exists world_stream_seed on world_stream (level, seed);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=120)  # a scrape can write to the source while this reads it
    db.executescript(SCHEMA)
    return db


def week_data(src: sqlite3.Connection, week_id: int) -> tuple[list[dict], str, int]:
    """The request stream of one week: one dict per delivery option, the stream's hash, and the number of requests.
    The hash covers the incoming quota alone, so two worlds of a seed hash the same whatever the system did. The
    reveal's truth for won cars (ready times, hours, pickup and delivery) is not incoming and is left out."""
    requests = list(
        src.execute(
            "select id, dealer_id, batch_id, arrived_at, respond_by, legs, reference_fee_cents,"
            " note_text, note_language, outcome from requests where week_id = ? order by arrived_at, id",
            (week_id,),
        )
    )
    legs: dict[str, list[tuple]] = defaultdict(list)
    for row in src.execute(
        "select request_id, leg, pickup_place, delivery_place, km, minutes, pickup_private, delivery_private,"
        " pickup_from, pickup_to, delivery_from, delivery_to, premium, electric, charge_percent"
        " from legs where week_id = ? order by request_id, leg",
        (week_id,),
    ):
        legs[row[0]].append(row)
    options: dict[str, list[tuple]] = defaultdict(list)
    for row in src.execute(
        "select request_id, kind, deadline, list_price_cents, quote_cents, taken"
        " from options where week_id = ? order by request_id, kind",
        (week_id,),
    ):
        options[row[0]].append(row)

    rows: list[dict] = []
    signature: list[tuple] = []
    for rid, dealer, batch, arrived, respond_by, nlegs, ref, note, language, outcome in requests:
        cars = legs.get(rid, [])
        first = cars[0] if cars else (None,) * 15
        request_options = options.get(rid, [])
        signature.append(
            (
                rid,
                dealer,
                batch,
                arrived,
                respond_by,
                nlegs,
                ref,
                note,
                language,
                tuple(car[1:] for car in cars),  # the incoming legs: places, km, windows, car type
                tuple((opt[1], opt[2], opt[3]) for opt in request_options),  # kind, deadline, list price
            )
        )
        for _, kind, deadline, list_price, quote, taken in request_options:
            ratio = round(quote / list_price, 6) if quote is not None and list_price else None
            rows.append(
                {
                    "request_id": rid,
                    "dealer_id": dealer,
                    "batch_id": batch,
                    "arrived_at": arrived,
                    "respond_by": respond_by,
                    "day": arrived // DAY,
                    "hour": arrived % DAY // 60,
                    "legs": nlegs,
                    "km": round(sum(car[4] or 0 for car in cars), 4),
                    "minutes": sum(car[5] or 0 for car in cars),
                    "pickup_place": first[2],
                    "delivery_place": first[3],
                    "private_pickup": first[6],
                    "private_delivery": first[7],
                    "pickup_from": first[8],
                    "pickup_to": first[9],
                    "delivery_from": first[10],
                    "delivery_to": first[11],
                    "premium": int(any(car[12] for car in cars)),
                    "electric": int(any(car[13] for car in cars)),
                    "charge_percent": min((car[14] for car in cars if car[14] is not None), default=None),
                    "low_charge": int(
                        any(car[13] and (car[14] or 100) < 30 and (car[4] or 0) > LOW_CHARGE_KM for car in cars)
                    ),
                    "has_note": int(bool(note)),
                    "note_language": language,
                    "option_rank": OPTION_RANK.get(kind, 99),
                    "option_kind": kind,
                    "deadline": deadline,
                    "hours_to_deadline": round((deadline - arrived) / 60, 4),
                    "list_price_cents": list_price,
                    "reference_fee_cents": ref,
                    "quote_cents": quote,
                    "ratio": ratio,
                    "declined": int(ratio is not None and ratio >= DECLINE_RATIO),
                    "taken": int(bool(taken)),
                    "outcome": outcome,
                }
            )
    stream_hash = hashlib.sha1(repr(signature).encode()).hexdigest()[:16]
    return rows, stream_hash, len(requests)


def build_week(src: sqlite3.Connection, dst: sqlite3.Connection, week: tuple) -> int:
    """One week's option rows and its stream row, in one transaction."""
    week_id, world_id, seed, level, policy = week
    rows, stream_hash, requests = week_data(src, week_id)
    with dst:
        dst.executemany(
            INSERT, [[week_id, level, seed, policy, world_id, *[row[field] for field in FIELDS]] for row in rows]
        )
        dst.execute(
            "insert or replace into world_stream values (?,?,?,?,?,?,?)",
            (week_id, level, seed, policy, world_id, requests, stream_hash),
        )
    return len(rows)


def rebuild_seed_stream(dst: sqlite3.Connection) -> None:
    with dst:
        dst.execute("delete from seed_stream")
        dst.execute(
            "insert into seed_stream"
            " select level, seed, count(*), count(distinct stream_hash), min(requests), max(requests),"
            " case when count(distinct stream_hash) = 1 then 1 else 0 end"
            " from world_stream group by level, seed"
        )


def weeks(src: sqlite3.Connection) -> Iterator[tuple]:
    yield from src.execute("select id, world_id, seed, level, policy from weeks order by id")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build out/quotas.sqlite: every price request of every saved week.")
    parser.add_argument("--db", type=Path, default=Path("out/spread.sqlite"), help="the source database")
    parser.add_argument("--out", type=Path, default=Path("out/quotas.sqlite"), help="the quotas database to write")
    parser.add_argument("--rebuild", action="store_true", help="drop the tables and build every week again")
    args = parser.parse_args(argv)
    src = sqlite3.connect(args.db, timeout=120)
    dst = connect(args.out)
    if args.rebuild:
        with dst:
            for table in TABLES:
                dst.execute(f"drop table if exists {table}")
        dst.executescript(SCHEMA)
    done = {week_id for (week_id,) in dst.execute("select week_id from world_stream")}
    todo = [week for week in weeks(src) if week[0] not in done]
    start = time.perf_counter()
    built = sum(build_week(src, dst, week) for week in todo)
    dst.executescript(INDICES)
    rebuild_seed_stream(dst)  # cheap next to the option rows, and keeps a rerun's new seeds correct
    inconsistent = dst.execute("select count(*) from seed_stream where consistent = 0").fetchone()[0]
    total = dst.execute("select count(*) from quota").fetchone()[0]
    seeds = dst.execute("select count(*) from seed_stream").fetchone()[0]
    print(
        f"built {len(todo)} weeks ({len(done)} already there): {built} option rows, {total} in all,"
        f" {seeds} seeds, {inconsistent} with an inconsistent stream"
        f" ({time.perf_counter() - start:.1f}s); wrote {args.out}"
    )
    if inconsistent:
        rows = dst.execute(
            "select level, seed, worlds, distinct_streams from seed_stream where consistent = 0 order by seed"
        ).fetchall()
        print(f"seeds whose worlds disagree on the request stream: {rows}")


if __name__ == "__main__":
    main()
