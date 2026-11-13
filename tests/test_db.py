"""Fast tests without network: db.py loads a synthetic week into SQLite."""

from db import add_map, add_week, connect
from tests.test_stats import WORLD_MAP, synthetic_week


def loaded(tmp_path):
    db = connect(tmp_path / "spread.sqlite")
    add_map(db, WORLD_MAP)
    week = synthetic_week()
    week.meta["worldId"] = "w-test"
    assert add_week(db, week) is True
    return db, week


def test_a_week_fills_every_table(tmp_path):
    db, week = loaded(tmp_path)

    def one(sql):
        return db.execute(sql).fetchone()

    assert one("select seed, level, policy, margin_cents, events from weeks") == ("t-1", 8, "explore", 1200, 9)
    assert one("select count(*) from events") == (len(week.events),)
    assert one("select count(*) from events where kind = 'gig_viewed'") == (2,)
    assert one("select json_extract(data, '$.request.note.language') from events where seq = 0") == ("fi",)
    assert one("select outcome, option_taken, note_language from requests where id = 'R1'") == ("won", "next_day", "fi")
    assert one("select pickup_place, delivery_place, km, minutes from legs where request_id = 'R1'") == (
        "a",
        "b",
        100,
        60,
    )
    assert one("select list_price_cents, quote_cents, taken from options where request_id = 'R2'") == (2500, 5000, 0)
    assert one("select status, delivered_at, late_minutes from orders") == ("delivered", 900, 0)
    assert one("select order_id, cars, opening_fee_cents, fee_cents from gigs") == ("R1", 1, 3000, 3300)
    assert one("select count(*), sum(licence = 'manual') from drivers") == (2, 1)
    assert one("select kind, cents from ledger") == ("revenue", 4500)
    assert one("select count(*) from roads") == (3,)


def test_a_week_already_in_the_database_is_skipped(tmp_path):
    db, week = loaded(tmp_path)
    assert add_week(db, week) is False
    assert db.execute("select count(*) from weeks").fetchone() == (1,)
    assert db.execute("select count(*) from events").fetchone() == (len(week.events),)
