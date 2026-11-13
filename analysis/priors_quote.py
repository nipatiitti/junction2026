"""Exports the priors of the quote models (src/models/quote/) from the scrape database to src/params/quote.json.

    uv run python -m analysis.priors_quote                       # out/spread.sqlite -> src/params/quote.json
    uv run python -m analysis.priors_quote --db data/spread.sqlite --out /tmp/quote.json

It reads the level 8 quote probes (`probes`: where each request's price flips, at trust 0) and the played weeks
(`quote_facts`, `week_facts`, `town_days`), so run `uv run python -m analysis.facts` first. No value is keyed to a
seed, a dealer, a driver or a place: each is a share, a ratio or a slope that holds in every world.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import statistics
from collections import defaultdict
from pathlib import Path

LEVEL = 8
OPTIONS = ("same_day", "next_day", "within_3_days")
REFERENCE = "next_day"  # the ladder and the start level are counted for this option
PROBS = [0.005] + [round(0.025 * i, 3) for i in range(1, 40)] + [0.995]  # the quantile grid: every 2.5%
PREMIUMS = [round(0.05 * i, 2) for i in range(21)]  # the choice curve: the fastest option's premium, 0 to +100%
TRUST_CAP = 25  # RULES.md: a dealer counts at most 25 orders on time


def quantile(sorted_xs: list[float], p: float) -> float:
    """The p-quantile, linearly interpolated between the order statistics."""
    i = p * (len(sorted_xs) - 1)
    lo = math.floor(i)
    hi = min(lo + 1, len(sorted_xs) - 1)
    return sorted_xs[lo] + (i - lo) * (sorted_xs[hi] - sorted_xs[lo])


def near_bucket(drivers_near: int) -> float:
    """Drivers living within 30 km of a place, on the log2 scale that the lane offsets pool by."""
    return math.log2(1 + drivers_near)


def flips(db: sqlite3.Connection) -> dict:
    """Splits each probed flip (price over list) into the world-day level, the option ladder, the lane's slope against
    the drivers near the delivery place, and what is left: the request's own scatter. A least-squares fit on the log
    flip, by alternating means."""
    near = {
        (seed, place): n
        for seed, place, n in db.execute(
            "select w.seed, t.place, max(t.drivers_near) from town_days t join weeks w on w.id = t.week_id "
            "where t.level = ? group by 1, 2",
            (LEVEL,),
        )
    }
    rows = [
        {
            "world_day": (seed, day),
            "option": option,
            "y": math.log(ratio),
            "x": near_bucket(near.get((seed, delivery), 0)),
        }
        for seed, day, option, ratio, delivery in db.execute(
            "select seed, day, option, flip_ratio, delivery_place from probes "
            "where level = ? and flip_ratio is not null and monotone = 1 and error is null",
            (LEVEL,),
        )
    ]
    if not rows:
        raise SystemExit("no level 8 quote probes: get the team's data (README.md) and run analysis.facts")
    center = statistics.fmean(r["x"] for r in rows)
    level: dict[tuple, float] = {}
    ladder = dict.fromkeys(OPTIONS, 0.0)
    slope = 0.0
    for _ in range(50):
        by_day = defaultdict(list)
        for r in rows:
            by_day[r["world_day"]].append(r["y"] - ladder[r["option"]] - slope * (r["x"] - center))
        level = {k: statistics.fmean(v) for k, v in by_day.items()}
        for option in OPTIONS:
            rest = [r["y"] - level[r["world_day"]] - slope * (r["x"] - center) for r in rows if r["option"] == option]
            ladder[option] = statistics.fmean(rest) if rest else 0.0
        ladder = {o: v - ladder[REFERENCE] for o, v in ladder.items()}
        lane = [(r["y"] - level[r["world_day"]] - ladder[r["option"]], r["x"] - center) for r in rows]
        slope = sum(y * x for y, x in lane) / sum(x * x for _, x in lane)
    residual = sorted(
        math.exp(r["y"] - level[r["world_day"]] - ladder[r["option"]] - slope * (r["x"] - center)) for r in rows
    )
    raw = sorted(math.exp(r["y"]) for r in rows)
    worlds = defaultdict(list)
    for (seed, _day), v in level.items():
        worlds[seed].append(v)
    world_means = [statistics.fmean(v) for v in worlds.values()]
    day_moves = [v - statistics.fmean(vs) for vs in worlds.values() for v in vs]
    return {
        "flips": len(rows),
        "worlds": len(worlds),
        "ratio": [round(quantile(raw, p), 4) for p in PROBS],
        "residual": [round(quantile(residual, p), 4) for p in PROBS],
        "start": round(math.exp(statistics.fmean(level.values())), 4),
        "world_sd": round(statistics.pstdev(world_means), 4),
        # a day's move around its world's level, from worlds with two probed days: the sd of a two-point mean's
        # deviations is half the sd of the difference, so scale it back to one day's own spread
        "day_sd": round(statistics.pstdev(day_moves) * math.sqrt(2), 4),
        "ladder": {o: round(math.exp(v), 4) for o, v in ladder.items()},
        "lane_slope": round(slope, 4),
        "lane_center": round(center, 3),
    }


def choice(db: sqlite3.Connection) -> tuple[list[float], int]:
    """The share of won requests with several priced options where the dealer took the fastest, by its premium
    over the cheapest priced option (finding 4), made non-increasing."""
    by_request = defaultdict(list)
    for week, request, rank, cents, taken in db.execute(
        "select week_id, request_id, option_rank, quote_cents, taken from quote_facts "
        "where level = ? and quoted = 1 and options_quoted > 1 and outcome = 'won'",
        (LEVEL,),
    ):
        by_request[(week, request)].append((rank, cents, taken))
    counts = [[0, 0] for _ in PREMIUMS]
    for options in by_request.values():
        fastest = min(options)
        premium = fastest[1] / min(o[1] for o in options) - 1
        i = min(len(PREMIUMS) - 1, max(0, round(premium / 0.05)))
        counts[i][0] += 1
        counts[i][1] += fastest[2]
    shares = [t / n if n else 0.0 for n, t in counts]
    return [round(s, 3) for s in non_increasing(shares, [n for n, _ in counts])], len(by_request)


def non_increasing(values: list[float], weights: list[int]) -> list[float]:
    """Pool adjacent violators: the closest non-increasing sequence, weighted by the counts."""
    blocks: list[list[float]] = []  # [value, weight, length]
    for v, w in zip(values, weights, strict=True):
        blocks.append([v, max(w, 1), 1])
        while len(blocks) > 1 and blocks[-2][0] < blocks[-1][0]:
            v2, w2, n2 = blocks.pop()
            v1, w1, n1 = blocks.pop()
            blocks.append([(v1 * w1 + v2 * w2) / (w1 + w2), w1 + w2, n1 + n2])
    return [b[0] for b in blocks for _ in range(int(b[2]))]


def trust(db: sqlite3.Connection) -> tuple[float, int]:
    """The trust effect as a log-level per counted order: a logistic fit of the win on the log price over list, the
    dealer's trust count and the weekday, on single-option quotes outside the guessed war day. The ratio of the trust
    and price coefficients is how far one order moves the price that wins."""
    rows = db.execute(
        "select ln(ratio), min(dealer_trust, ?), taken, day from quote_facts where level = ? and quoted = 1 "
        "and options_quoted = 1 and coalesce(war_guess, 0) = 0 and ratio between 0.5 and 3",
        (TRUST_CAP, LEVEL),
    ).fetchall()
    xs = [[1.0, lr, t] + [1.0 * (day == d) for d in (1, 2, 3, 4)] for lr, t, _won, day in rows]
    ys = [won for _lr, _t, won, _day in rows]
    b = logistic(xs, ys)
    return round(-b[2] / b[1], 4), len(rows)


def logistic(xs: list[list[float]], ys: list[int]) -> list[float]:
    """Maximum-likelihood logistic regression by Newton's method."""
    k = len(xs[0])
    b = [0.0] * k
    for _ in range(25):
        grad = [0.0] * k
        hess = [[0.0] * k for _ in range(k)]
        for x, y in zip(xs, ys, strict=True):
            p = 1 / (1 + math.exp(-sum(bi * xi for bi, xi in zip(b, x, strict=True))))
            for i in range(k):
                grad[i] += (y - p) * x[i]
                for j in range(k):
                    hess[i][j] += p * (1 - p) * x[i] * x[j]
        b = [bi + di for bi, di in zip(b, solve(hess, grad), strict=True)]
    return b


def solve(a: list[list[float]], v: list[float]) -> list[float]:
    """Solves a x = v by Gauss-Jordan elimination with partial pivoting."""
    n = len(v)
    m = [row[:] + [v[i]] for i, row in enumerate(a)]
    for i in range(n):
        pivot = max(range(i, n), key=lambda r: abs(m[r][i]))
        m[i], m[pivot] = m[pivot], m[i]
        for r in range(n):
            if r != i:
                f = m[r][i] / m[i][i]
                m[r] = [x - f * y for x, y in zip(m[r], m[i], strict=True)]
    return [m[i][n] / m[i][i] for i in range(n)]


def volume(db: sqlite3.Connection) -> tuple[int, int]:
    """Requests a week and dealers that send them: the week's size, not anyone's identity."""
    (per_week,) = db.execute("select avg(requests) from week_facts where level = ?", (LEVEL,)).fetchone()
    (dealers,) = db.execute("select count(distinct dealer_id) from quote_facts where level = ?", (LEVEL,)).fetchone()
    return round(per_week), dealers


def build(db: sqlite3.Connection) -> dict:
    f = flips(db)
    fastest, choice_wins = choice(db)
    per_order, trust_rows = trust(db)
    per_week, dealers = volume(db)
    return {
        "about": "Priors of src/models/quote, level 8. Written by `uv run python -m analysis.priors_quote`.",
        "sample": {"flips": f["flips"], "worlds": f["worlds"], "choiceWins": choice_wins, "trustQuotes": trust_rows},
        "probs": PROBS,
        "flipRatio": f["ratio"],
        "flipResidual": f["residual"],
        "startLevel": f["start"],
        "worldSd": f["world_sd"],
        "daySd": f["day_sd"],
        "ladder": f["ladder"],
        "laneSlope": f["lane_slope"],
        "laneCenter": f["lane_center"],
        "trustPerOrder": per_order,
        "trustCap": TRUST_CAP,
        "choicePremium": PREMIUMS,
        "choiceFastest": fastest,
        "requestsPerWeek": per_week,
        "dealers": dealers,
    }


def dump(value: object, indent: int = 0, width: int = 120) -> str:
    """JSON as `pnpm format` (Biome) writes it: objects one key a line, number lists filled to the line width."""
    pad, inner = " " * indent, " " * (indent + 2)
    if isinstance(value, dict):
        items = [f"{inner}{json.dumps(k)}: {dump(v, indent + 2, width)}" for k, v in value.items()]
        return "{\n" + ",\n".join(items) + f"\n{pad}}}"
    if isinstance(value, list):
        words = [json.dumps(v) for v in value]
        lines, line = [], ""
        for word in words:
            candidate = f"{line} {word}," if line else f"{word},"
            if len(inner) + len(candidate) > width and line:
                lines.append(line)
                candidate = f"{word},"
            line = candidate
        lines.append(line[:-1])
        return "[\n" + "\n".join(inner + text for text in lines) + f"\n{pad}]"
    return json.dumps(value)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Export the quote models' priors to src/params/quote.json.")
    parser.add_argument("--db", type=Path, default=Path("out/spread.sqlite"), help="the database (out/spread.sqlite)")
    parser.add_argument("--out", type=Path, default=Path("src/params/quote.json"), help="the file to write")
    args = parser.parse_args(argv)
    db = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    priors = build(db)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(dump(priors) + "\n")
    q = dict(zip(PROBS, priors["flipRatio"], strict=True))
    print(f"wrote {args.out}: {priors['sample']['flips']} flips in {priors['sample']['worlds']} worlds")
    print("flip / list at 10, 25, 50, 75, 90%:", [q[p] for p in (0.1, 0.25, 0.5, 0.75, 0.9)])
    print(f"start level {priors['startLevel']} ({REFERENCE}), ladder {priors['ladder']}")
    print(f"world sd {priors['worldSd']}, day sd {priors['daySd']} (log)")
    print(f"lane slope {priors['laneSlope']} log per doubling of drivers near the delivery")
    print(f"trust {priors['trustPerOrder']} log per order; fastest taken at +0/10/20/50%:", end=" ")
    print([priors["choiceFastest"][i] for i in (0, 2, 4, 10)])


if __name__ == "__main__":
    main()
