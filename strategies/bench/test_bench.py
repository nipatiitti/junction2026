"""Fast tests of the seed bench: no network, no child processes."""

import csv
from pathlib import Path

import pytest

from strategies.bench.bench import (
    Result,
    Version,
    command,
    csv_rows,
    parse_seeds,
    split_ref,
    table,
    totals,
    write_csv,
)


def score(margin: int, orders: int, on_time: float, undelivered: float = 0.0, ranked: bool = True) -> dict:
    return {
        "marginCents": margin,
        "revenueCents": margin * 3,
        "marginShare": 0.1,
        "wonOrders": orders,
        "onTimeShare": on_time,
        "undeliveredShare": undelivered,
        "ranked": ranked,
    }


# Two versions on two seeds. "new" has 100 orders at 90% and 300 at 50%: 60% of all its orders on time.
RESULTS = [
    Result("new", "spread-1", "w-1", score(150_000, 100, 0.9, 0.0, True)),
    Result("main", "spread-1", "w-2", score(-7_261_251, 949, 0.455, 0.2, False)),
    Result("new", "spread-2", "w-3", score(-50_000, 300, 0.5, 0.1, False)),
    Result("main", "spread-2", "w-4", score(-100_000, 200, 0.95, 0.0, True)),
]
VERSIONS, SEEDS = ["new", "main"], ["spread-1", "spread-2"]


def test_seed_range_gives_each_seed_in_order():
    assert parse_seeds("spread-1..spread-5") == [f"spread-{n}" for n in range(1, 6)]


def test_seed_range_can_leave_out_the_text_at_its_end():
    assert parse_seeds("spread-9..11") == ["spread-9", "spread-10", "spread-11"]


def test_seed_list_mixes_seeds_and_ranges():
    assert parse_seeds("study-1, spread-2..spread-3,x") == ["study-1", "spread-2", "spread-3", "x"]


@pytest.mark.parametrize(
    ("text", "error"),
    [
        ("spread-5..spread-1", "counts down"),
        ("spread-1..study-3", "same text"),
        ("spread..spread-3", "not a range"),
        ("spread-1,,spread-2", "empty seed"),
        ("spread-1..2,spread-2", "more than once"),
    ],
)
def test_bad_seed_list_says_what_is_wrong(text, error):
    with pytest.raises(ValueError, match=error):
        parse_seeds(text)


def test_totals_share_is_over_all_orders_not_an_average_of_shares():
    total = totals([RESULTS[0].score, RESULTS[2].score])
    assert total.on_time_share == pytest.approx(0.6)  # (90 + 150) / 400, not (0.9 + 0.5) / 2
    assert total.undelivered_share == pytest.approx(0.075)  # 30 / 400
    assert (total.margin_cents, total.won_orders, total.ranked, total.weeks) == (100_000, 400, 1, 2)


def test_totals_of_weeks_without_orders_have_no_share():
    assert totals([score(0, 0, 0.0)]).on_time_share == 0.0


def test_table_has_a_line_per_seed_and_version_then_totals_and_the_comparison():
    lines = table(RESULTS, VERSIONS, SEEDS, 8).splitlines()
    assert lines[0] == "Level 8, 2 seeds."
    assert lines[2].split()[:3] == ["Seed", "Version", "Margin"]
    assert lines[3].split() == ["spread-1", "new", "€1,500.00", "100", "90.0%", "0.0%", "yes"]
    assert lines[4].split() == ["spread-1", "main", "-€72,612.51", "949", "45.5%", "20.0%", "no"]
    assert ["Total", "new", "€1,000.00", "400", "60.0%", "7.5%", "1", "of", "2"] in [line.split() for line in lines]
    # (€1,500.00 + €72,612.51) on spread-1 and (-€500.00 + €1,000.00) on spread-2
    assert lines[-1] == "new against main: margin +€74,612.51 in total, higher on 2 of 2 seeds; ranked on 1 against 1."


def test_table_of_one_version_has_no_comparison():
    text = table(RESULTS[:1], ["new"], ["spread-1"], 6)
    assert text.startswith("Level 6, 1 seed.")
    assert "against" not in text


def test_csv_has_a_row_per_run_then_a_total_per_version(tmp_path: Path):
    path = tmp_path / "out" / "bench.csv"
    write_csv(path, csv_rows(RESULTS, VERSIONS, SEEDS, 8))
    rows = list(csv.DictReader(path.open()))
    assert [(r["seed"], r["version"]) for r in rows] == [
        ("spread-1", "new"),
        ("spread-1", "main"),
        ("spread-2", "new"),
        ("spread-2", "main"),
        ("total", "new"),
        ("total", "main"),
    ]
    assert rows[1] == {
        "seed": "spread-1",
        "version": "main",
        "level": "8",
        "world_id": "w-2",
        "margin_eur": "-72612.51",
        "revenue_eur": "-217837.53",
        "won_orders": "949",
        "on_time_share": "0.4550",
        "undelivered_share": "0.2000",
        "ranked": "no",
    }
    assert (rows[4]["on_time_share"], rows[4]["ranked"], rows[4]["world_id"]) == ("0.6000", "1 of 2", "")


def test_command_plays_a_practice_week_and_never_a_ranking_run_or_a_final():
    args = command(Version("main", Path("/x/dispatch.py")), "spread-3", 7)
    assert args[1:] == ["/x/dispatch.py", "--level", "7", "--seed", "spread-3"]
    assert "--board" not in args and "--final" not in args


def test_git_version_plays_dispatch_py_unless_it_names_a_file():
    assert split_ref("origin/main") == ("origin/main", "dispatch.py")
    assert split_ref("abc123:strategies/x.py") == ("abc123", "strategies/x.py")
