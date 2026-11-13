"""The hindsight oracle: where each week's margin went, and what a perfect dispatcher could have kept.

    uv run python -m analysis.oracle                      # every played week of out/spread.sqlite
    uv run python -m analysis.oracle --weeks --experiment explore-win
    uv run python -m analysis.oracle --json -             # print only, write no JSON

It reads the facts tables of analysis/facts.py (read-only) and the quote probes of probe.py. Every bound is an upper
bound on margin under the assumptions in `ASSUMPTIONS` (and analysis/README.md); the bounds are nested, so the gains
add up to the oracle without counting anything twice.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
import statistics
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

VERSION = 1
DAY = 1440
BUCKETS = ("le_2h", "le_24h", "le_2bd", "gt_2bd", "late_other")
ACCOUNTS = (
    "revenue_cents",
    "driver_fee_cents",
    "late_refund_cents",
    "undelivered_penalty_cents",
    "fine_cents",
    "failed_visit_cents",
    "waiting_cents",
    "release_fee_cents",
    "other_cents",
    "margin_cents",
)
PROBE_MIN_REQUESTS = 20  # a probe with fewer valid requests leaves the quote gain to the brackets
CURVE_MIN_ROWS = 200  # a win-curve cell with fewer rows pools the level's days
CURVE_BINS, CURVE_LO, CURVE_STEP = 40, 0.5, 0.05
MIDS = [round(CURVE_LO + CURVE_STEP / 2 + CURVE_STEP * i, 3) for i in range(CURVE_BINS)]
PROBE_FILE = re.compile(r"quote-L(\d+)-(.+)\.jsonl$")

ASSUMPTIONS = {
    "selection": (
        "We decline (quote far above list) every order that lost money; nothing else changes. Costs are those that"
        " happened; declining costs nothing (a losing quote is free); dealer trust and the competitor's answer to"
        " fewer wins are ignored; the drivers freed by dropped orders are not reused. Cancelled orders are declined."
    ),
    "delivery": (
        "Every kept order arrives on time: no refund, penalty, fine, failed visit, waiting or release fee; the driver"
        " fees are the ones we paid. A driver was there in time for every kept order at the fee finally paid; notes"
        " are read perfectly. An order that was never delivered is costed at the week's paid fee ratio"
        " (undelivered_costed)."
    ),
    "fee": (
        "Each gig that a driver completed is paid the lowest fee, as a share of the typical fee, that a driver"
        " completed a comparable gig for in the same world (same seed and level): the same car in any of our weeks"
        " (twin), or the same lane booked the same day for the same audience (lane). The driver who took the"
        " comparable could have taken this gig too, whatever the hour, deadline option and what drivers had learned;"
        " it is the lowest of several draws, so it flatters. A gig without a cheaper comparable saves nothing."
        " Dropped bookings are not comparables."
    ),
    "quote_probe": (
        "A probe flip is the world's first answer: dealer trust 0, no late history, a competitor that has not answered"
        " our wins. Trust lets on-time weeks win above it later (understates); the competitor lowers prices for"
        " dealers we mostly win (overstates); neither is added: an order won above its flip counts 0 (won_above_flip)."
        " The probe's parent wins nothing, so the competitor raises its prices each morning and flips after Monday"
        " read high; the week figure extrapolates the probed window (extrapolated). Capacity is ignored and new_cost"
        " is the week's average paid fee ratio, not the marginal driver's fee: the loosest bound. An order the"
        " selection bound dropped is still repriced to its flip in full."
    ),
    "quote_brackets": (
        "An estimate, not a bound: the expected flip given our quote's outcome, from a win curve that pools all our"
        " weeks of that level and weekday (one priced option only). It knows neither this world's price level nor"
        " the war or outage day, and it contains the trust our own weeks built by that weekday. Lost quotes give a"
        " strict ceiling (lost_ceiling_cents); lost_below_similar measures how uneven the market is, not money."
    ),
    "combining": (
        "Not measurable: no scraped gig carries cars of two orders, so no combined fee was ever observed."
        " candidates is the pool of counted single-leg orders sharing lane and deadline day, not a saving."
    ),
}


# ---------------------------------------------------------------------------------------------------------- loading


def rows_by_week(db: sqlite3.Connection, sql: str) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = defaultdict(list)
    cur = db.execute(sql)
    names = [d[0] for d in cur.description]
    for values in cur:
        row = dict(zip(names, values, strict=True))
        out[row["week_id"]].append(row)
    return out


def load_probes(probe_dir: Path | None) -> dict[tuple[str, int], dict]:
    """Probe rows by (seed, level): {"rows": {(requestId, option): row}, "bad_lines": n}. Missing folder = none."""
    probes: dict[tuple[str, int], dict] = {}
    if probe_dir is None or not probe_dir.is_dir():
        return probes
    for path in sorted(probe_dir.glob("quote-L*.jsonl")):
        match = PROBE_FILE.search(path.name)
        if not match:
            continue
        rows, bad = {}, 0
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:  # a line still being written by a running probe
                bad += 1
                continue
            if "requestId" in row and "option" in row:
                rows[(row["requestId"], row["option"])] = row
        probes[(match.group(2), int(match.group(1)))] = {"rows": rows, "bad_lines": bad}
    return probes


def probe_flip(row: dict) -> float | None:
    """The highest price known to win for one probe row; None when the row is not usable."""
    if row.get("error") or row.get("ends") == "inverted" or row.get("monotone") is False:
        return None
    if row.get("ends") == "false":
        return 0.0
    if row.get("ends") == "true":
        won = [t[0] for t in row.get("trials") or [] if len(t) > 1 and t[1] is True]
        return float(max(won)) if won else None
    bracket = row.get("bracketCents")
    return float(bracket[0]) if bracket else None


# -------------------------------------------------------------------------------------------------------- win curve


def curve_bin(ratio: float) -> int:
    return min(max(math.floor((ratio - CURVE_LO) / CURVE_STEP), 0), CURVE_BINS - 1)


def fit_curve(counts: list[list[int]]) -> list[float]:
    """Non-increasing win share per bin from [n, taken] per bin (empty bins filled, then weighted PAV)."""
    raw, last = [], 1.0
    for n, taken in counts:
        if n:
            last = taken / n
        raw.append(last)
    blocks: list[list[float]] = []  # [value, weight, bins]
    for value, (n, _) in zip(raw, counts, strict=True):
        blocks.append([value, float(n), 1])
        while len(blocks) > 1 and blocks[-2][0] < blocks[-1][0]:
            v2, w2, k2 = blocks.pop()
            v1, w1, k1 = blocks.pop()
            w = w1 + w2
            blocks.append([(v1 * w1 + v2 * w2) / w if w else max(v1, v2), w, k1 + k2])
    out = []
    for value, _, k in blocks:
        out.extend([value] * k)
    return out


def win_curves(quote_rows: list[dict]) -> dict[tuple[int, int], dict]:
    """S[(level, day)] from quoted rows with one priced option, pooled over the level's days when a cell is thin."""
    cells: dict[tuple[int, int], list[list[int]]] = {}
    levels: dict[int, list[list[int]]] = {}
    days: dict[int, set[int]] = defaultdict(set)
    for r in quote_rows:
        days[r["level"]].add(r["day"])
        if r["quoted"] != 1 or r["options_quoted"] != 1 or r["ratio"] is None:
            continue
        i = curve_bin(r["ratio"])
        for counts in (
            cells.setdefault((r["level"], r["day"]), [[0, 0] for _ in range(CURVE_BINS)]),
            levels.setdefault(r["level"], [[0, 0] for _ in range(CURVE_BINS)]),
        ):
            counts[i][0] += 1
            counts[i][1] += r["taken"] or 0
    curves = {}
    for level in sorted(days):
        pooled_counts = levels.get(level)
        if pooled_counts is None or sum(n for n, _ in pooled_counts) < CURVE_MIN_ROWS:
            continue
        pooled = fit_curve(pooled_counts)
        for day in sorted(days[level]):
            counts = cells.get((level, day))
            rows = sum(n for n, _ in counts) if counts else 0
            if rows >= CURVE_MIN_ROWS:
                s, is_pooled = fit_curve(counts), False
            else:
                s, is_pooled, rows = pooled, True, sum(n for n, _ in pooled_counts)
            p = [s[i] - (s[i + 1] if i + 1 < CURVE_BINS else 0.0) for i in range(CURVE_BINS)]
            curves[(level, day)] = {"level": level, "day": day, "rows": rows, "pooled": is_pooled, "s": s, "p": p}
    return curves


# ------------------------------------------------------------------------------------------------------ fee bound


def fee_comparables(gig_rows: list[dict]) -> tuple[dict, dict]:
    """Lowest fee_ratio of done single-order gigs by twin key (same car) and lane key, both within one world."""
    twin: dict[tuple, float] = {}
    lane: dict[tuple, float] = {}
    for g in gig_rows:
        if g["outcome"] != "done" or g["fee_ratio"] is None or g["orders"] != 1:
            continue
        tk = (g["seed"], g["level"], g["order_id"], g["pickup_place"], g["delivery_place"], g["cars"])
        lk = (g["seed"], g["level"], g["pickup_place"], g["delivery_place"], g["cars"], g["experienced"])
        lk = (*lk, g["booked_at"] // DAY if g["booked_at"] is not None else None)
        twin[tk] = min(twin.get(tk, math.inf), g["fee_ratio"])
        lane[lk] = min(lane.get(lk, math.inf), g["fee_ratio"])
    return twin, lane


def gig_saving(g: dict, seed: str, level: int, twin: dict, lane: dict) -> tuple[int, str]:
    """(saving in cents, 'twin' | 'lane' | 'own') of one done gig at the lowest comparable fee ratio."""
    own = g["fee_ratio"]
    if own is None or g["typical_fee_cents"] is None or g["fee_cents"] is None:
        return 0, "own"
    t = twin.get((seed, level, g["order_id"], g["pickup_place"], g["delivery_place"], g["cars"]), math.inf)
    booked_day = g["booked_at"] // DAY if g["booked_at"] is not None else None
    lk = (seed, level, g["pickup_place"], g["delivery_place"], g["cars"], g["experienced"], booked_day)
    ln = lane.get(lk, math.inf)
    rho = min(own, t, ln)
    if rho >= own:
        return 0, "own"
    by = "twin" if t == rho else "lane"
    return max(g["fee_cents"] - round(g["typical_fee_cents"] * rho), 0), by


# ---------------------------------------------------------------------------------------------------- quote side


def requests_of(quotes: list[dict], orders_by_id: dict[str, dict]) -> dict[str, dict]:
    """Per request of the week: its option rows, state, day, arrival, reference fee."""
    reqs: dict[str, dict] = {}
    for q in quotes:
        r = reqs.setdefault(q["request_id"], {"rows": [], "day": q["day"], "arrived_at": q["arrived_at"]})
        r["rows"].append(q)
        r["ref"] = q["reference_fee_cents"] or 0
    for rid, r in reqs.items():
        r["rows"].sort(key=lambda q: q["option_rank"] if q["option_rank"] is not None else 9)
        order = orders_by_id.get(rid)
        if order is not None and order["cancelled"] == 1:
            r["state"] = "cancelled"
        elif order is not None and order["counted"] == 1:
            r["state"], r["order"] = "won", order
        elif any(q["quoted"] == 1 for q in r["rows"]):
            r["state"] = "lost"
        else:
            r["state"] = "not_quoted"
    return reqs


def bracket_request(r: dict, curve: dict, new_cost: int) -> dict:
    """Bracket estimate for one request: flip revenue and gain (floats, cents)."""
    s, p = curve["s"], curve["p"]
    if r["state"] == "won":
        order = r["order"]
        row = next((q for q in r["rows"] if q["option"] == order["option"]), r["rows"][0])
        L, ratio = row["list_price_cents"], row["ratio"] if row["ratio"] is not None else order["ratio"]
        j = curve_bin(ratio)
        e = ratio if s[j] <= 0 else max(ratio, sum(p[i] * MIDS[i] for i in range(j, CURVE_BINS)) / s[j])
        flip = round(L * e)
        return {"flip": flip, "underpriced": max(flip - order["price_cents"], 0)}
    if r["state"] == "lost":
        row = next(q for q in r["rows"] if q["quoted"] == 1)
        j = curve_bin(row["ratio"])
        if 1 - s[j] <= 0:
            return {"flip": 0.0, "winnable": 0.0}
        L, below = row["list_price_cents"], range(j)
        return {
            "flip": sum(p[i] * L * MIDS[i] for i in below) / (1 - s[j]),
            "winnable": sum(p[i] * max(L * MIDS[i] - new_cost, 0) for i in below) / (1 - s[j]),
        }
    L = r["rows"][0]["list_price_cents"]
    return {
        "flip": sum(p[i] * L * MIDS[i] for i in range(CURVE_BINS)),
        "winnable": sum(p[i] * max(L * MIDS[i] - new_cost, 0) for i in range(CURVE_BINS)),
    }


def brackets_block(reqs: dict, quotes: list[dict], level: int, curves: dict, cost_ratio: float) -> dict:
    taken_by_day: dict[int, list[float]] = defaultdict(list)
    for q in quotes:
        if q["taken"] == 1 and q["ratio"] is not None:
            taken_by_day[q["day"]].append(q["ratio"])
    week_taken = [x for v in taken_by_day.values() for x in v]
    week_ref = statistics.median(week_taken) if len(week_taken) >= 5 else None
    bins: dict[float, list[int]] = {}
    lost_n = lost_ceiling = below_n = below_rev = 0
    for r in reqs.values():
        if r["state"] != "lost":
            continue
        quoted = [q for q in r["rows"] if q["quoted"] == 1]
        low = min(quoted, key=lambda q: q["ratio"])
        ceiling = max(q["quote_cents"] for q in quoted)
        b = round(min(max(math.floor(low["ratio"] * 10) / 10, 0.5), 2.4), 1)
        cell = bins.setdefault(b, [0, 0])
        cell[0] += 1
        cell[1] += ceiling
        lost_n += 1
        lost_ceiling += ceiling
        day_taken = taken_by_day.get(r["day"], [])
        ref = statistics.median(day_taken) if len(day_taken) >= 5 else week_ref
        if ref is not None and low["ratio"] < ref:
            below_n += 1
            below_rev += low["quote_cents"]
    estimate = None
    if any(lv == level for lv, _ in curves):
        sums = dict.fromkeys(("flip", "underpriced", "lost", "not_quoted"), 0.0)
        for r in reqs.values():
            curve = curves.get((level, r["day"]))
            if curve is None or r["state"] == "cancelled":
                continue
            est = bracket_request(r, curve, round(r["ref"] * cost_ratio))
            sums["flip"] += est["flip"]
            if r["state"] == "won":
                sums["underpriced"] += est["underpriced"]
            else:
                sums[r["state"]] += est["winnable"]
        parts = [round(sums["underpriced"]), round(sums["lost"]), round(sums["not_quoted"])]
        estimate = {
            "flip_revenue_cents": round(sums["flip"]),
            "underpriced_cents": parts[0],
            "lost_winnable_cents": parts[1],
            "not_quoted_winnable_cents": parts[2],
            "week_gain_cents": sum(parts),
        }
    return {
        "lost_requests": lost_n,
        "lost_ceiling_cents": lost_ceiling,
        "lost_bins": [{"ratio": b, "requests": n, "ceiling_cents": c} for b, (n, c) in sorted(bins.items())],
        "lost_below_similar": {"requests": below_n, "revenue_cents": below_rev},
        "estimate": estimate,
    }


def probe_requests(reqs: dict, probe: dict) -> tuple[dict[str, float], int, int]:
    """Flip F per probed request of the week ({request_id: F}), skipped rows, mismatched requests."""
    flips: dict[str, float] = {}
    skipped = 0
    bad: set[str] = set()
    for (rid, option), row in sorted(probe["rows"].items()):
        flip = probe_flip(row)
        if flip is None:
            skipped += 1
            continue
        r = reqs.get(rid)
        q = next((q for q in r["rows"] if q["option"] == option), None) if r else None
        if q is None or q["list_price_cents"] != row.get("listPriceCents"):
            bad.add(rid)
            continue
        flips[rid] = max(flips.get(rid, 0.0), flip)
    for rid in bad:
        flips.pop(rid, None)
    return flips, skipped + probe["bad_lines"], len(bad)


def probe_block(reqs: dict, probe: dict, cost_ratio: float) -> dict | None:
    flips, skipped, mismatched = probe_requests(reqs, probe)
    flips = {rid: f for rid, f in flips.items() if reqs[rid]["state"] != "cancelled"}
    n = len(flips)
    if n == 0:
        return None
    t0 = min(reqs[rid]["arrived_at"] for rid in flips)
    t1 = max(reqs[rid]["arrived_at"] for rid in flips)
    n_window = sum(1 for r in reqs.values() if t0 <= r["arrived_at"] <= t1)
    n_week = len(reqs)
    counts = dict.fromkeys(("won", "lost", "not_quoted", "unwinnable", "won_above_flip"), 0)
    cents = dict.fromkeys(("flip", "won_rev", "underpriced", "lost", "not_quoted"), 0.0)
    for rid, flip in flips.items():
        r = reqs[rid]
        counts[r["state"]] += 1
        counts["unwinnable"] += flip == 0
        cents["flip"] += flip
        if r["state"] == "won":
            price = r["order"]["price_cents"]
            cents["won_rev"] += price
            cents["underpriced"] += max(flip - price, 0)
            counts["won_above_flip"] += price > flip
        else:
            cents[r["state"]] += max(flip - round(r["ref"] * cost_ratio), 0)
    scale = n_window / n
    window_gain = round(scale * (cents["underpriced"] + cents["lost"] + cents["not_quoted"]))
    return {
        "requests": n,
        "skipped_rows": skipped,
        "mismatched": mismatched,
        "days": sorted({reqs[rid]["day"] for rid in flips}),
        "window": [t0, t1],
        "window_requests": n_window,
        "week_requests": n_week,
        "scale": round(scale, 2),
        "extrapolated": n_window < n_week,
        **counts,
        "flip_revenue_cents": round(cents["flip"]),
        "won_revenue_cents": round(cents["won_rev"]),
        "underpriced_cents": round(cents["underpriced"]),
        "lost_winnable_cents": round(cents["lost"]),
        "not_quoted_winnable_cents": round(cents["not_quoted"]),
        "window_gain_cents": window_gain,
        "week_gain_cents": round(window_gain * n_week / n_window),
    }


# --------------------------------------------------------------------------------------------------------- one week


def drops_to_rank(counted: int, late: int) -> int:
    k = 0
    while late - k > (counted - k) // 10:
        k += 1
    return k


def week_gap(w: dict, orders: list[dict], gigs: list[dict], quotes: list[dict], refunds: list[dict], ctx: dict) -> dict:
    """The oracle of one week: waterfall, nested bounds, quote side, on-time slack, combining, split."""
    warnings: list[str] = []
    margin = w["margin_cents"]
    unallocated = margin - sum(o["margin_cents"] for o in orders)
    by_bucket = {r["late_bucket"]: r for r in refunds}
    waterfall = {k: w[k] for k in ACCOUNTS}
    waterfall["unallocated_cents"] = unallocated
    waterfall["refunds"] = {
        b: {"orders": by_bucket[b]["orders"], "cents": by_bucket[b]["cents"]}
        if b in by_bucket
        else {"orders": 0, "cents": 0}
        for b in BUCKETS
    }
    if w["other_cents"] > 0:
        warnings.append(f"week {w['week_id']}: other_cents > 0 ({w['other_cents']})")
    counted = [o for o in orders if o["counted"] == 1]

    # Selection: decline every order that lost money.
    kept = [o for o in counted if o["margin_cents"] > 0]
    sel_margin = unallocated + sum(o["margin_cents"] for o in kept)
    if sel_margin < margin:
        warnings.append(f"week {w['week_id']}: selection gain clamped at 0")
        sel_margin = margin
    on_time_kept = sum(o["on_time"] or 0 for o in kept)
    share_after = on_time_kept / len(kept) if kept else None
    selection = {
        "margin_cents": sel_margin,
        "gain_cents": sel_margin - margin,
        "orders_kept": len(kept),
        "orders_dropped": len(counted) - len(kept),
        "cancelled_dropped": len(orders) - len(counted),
        "dropped_margin_cents": sum(o["margin_cents"] for o in orders) - sum(o["margin_cents"] for o in kept),
        "on_time_share_after": share_after,
        "ranked_after": share_after is not None and share_after >= 0.9,
    }

    # Delivery: every order on time at the fees paid.
    delivered = [o for o in counted if o["delivered_at"] is not None]
    paid = sum(-o["driver_fee_cents"] for o in delivered)
    ref = sum(o["reference_fee_cents"] or 0 for o in delivered)
    ratio_paid = paid / ref if delivered and ref else 1.0
    fee_o, d_o = {}, {}
    for o in counted:
        fee = -o["driver_fee_cents"]
        if o["delivered_at"] is None:
            fee = max(fee, round((o["reference_fee_cents"] or 0) * ratio_paid))
        fee_o[o["order_id"]] = fee
        d_o[o["order_id"]] = o["price_cents"] - fee
    keep_del = [o for o in counted if d_o[o["order_id"]] > 0]
    del_margin = unallocated + sum(d_o[o["order_id"]] for o in keep_del)
    if del_margin < sel_margin:
        warnings.append(f"week {w['week_id']}: delivery gain clamped at 0")
        del_margin = sel_margin
    delivery = {
        "margin_cents": del_margin,
        "gain_cents": del_margin - sel_margin,
        "orders_kept": len(keep_del),
        "cost_ratio_paid": round(ratio_paid, 4),
        "undelivered_costed": len(counted) - len(delivered),
        "refunds_avoided_cents": -sum(o["late_refund_cents"] for o in keep_del),
        "penalties_avoided_cents": -sum(o["undelivered_penalty_cents"] for o in keep_del),
        "handling_avoided_cents": -sum(
            o["failed_visit_cents"] + o["waiting_cents"] + o["release_fee_cents"] + o["fine_cents"] for o in keep_del
        ),
    }

    # Fee: every done gig at the lowest comparable fee ratio.
    counted_ids = set(fee_o)
    saving_o: dict[str, int] = defaultdict(int)
    gigs_done = gigs_lower = save_twin = save_lane = 0
    for g in gigs:
        if g["outcome"] != "done" or g["order_id"] not in counted_ids:
            continue
        saving, by = gig_saving(g, w["seed"], w["level"], ctx["twin"], ctx["lane"])
        gigs_done += 1
        if saving > 0:
            gigs_lower += 1
            saving_o[g["order_id"]] += saving
            if by == "twin":
                save_twin += saving
            else:
                save_lane += saving
    f_o = {oid: d + saving_o[oid] for oid, d in d_o.items()}
    keep_fee = [oid for oid, f in f_o.items() if f > 0]
    fee_margin = unallocated + sum(f_o[oid] for oid in keep_fee)
    if fee_margin < del_margin:
        warnings.append(f"week {w['week_id']}: fee gain clamped at 0")
        fee_margin = del_margin
    bound = sum(fee_o[o["order_id"]] - saving_o[o["order_id"]] for o in delivered)
    fee = {
        "margin_cents": fee_margin,
        "gain_cents": fee_margin - del_margin,
        "orders_kept": len(keep_fee),
        "gigs_done": gigs_done,
        "gigs_with_lower": gigs_lower,
        "saving_twin_cents": save_twin,
        "saving_lane_cents": save_lane,
        "cost_ratio_bound": round(bound / ref, 4) if delivered and ref else 1.0,
    }

    # Quote side: probe flips where there are any, censored brackets everywhere.
    reqs = requests_of(quotes, {o["order_id"]: o for o in orders})
    probe = ctx["probes"].get((w["seed"], w["level"]))
    probe_out = probe_block(reqs, probe, ratio_paid) if probe else None
    brackets = brackets_block(reqs, quotes, w["level"], ctx["curves"], ratio_paid)
    if probe_out and probe_out["requests"] >= PROBE_MIN_REQUESTS:
        source, quote_gain = "probe", probe_out["week_gain_cents"]
    elif brackets["estimate"] is not None:
        source, quote_gain = "brackets", brackets["estimate"]["week_gain_cents"]
    else:
        source, quote_gain = None, 0
    quote = {"source": source, "gain_cents": quote_gain, "probe": probe_out, "brackets": brackets}

    # On-time slack.
    late = w["late"] + w["undelivered"]
    on_time = {
        "counted": w["counted"],
        "on_time": w["on_time"],
        "late": w["late"],
        "undelivered": w["undelivered"],
        "share": w["on_time_share"],
        "ranked": w["on_time_share"] is not None and w["on_time_share"] >= 0.9,
        "late_slack": w["late_slack"],
        "drops_to_rank": drops_to_rank(w["counted"], late),
    }

    # Combining: the pool of single-leg orders that share lane and deadline day.
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for o in counted:
        if o["legs"] == 1 and o["deadline_won"] is not None:
            groups[(o["pickup_place"], o["delivery_place"], o["deadline_won"] // DAY)].append(o)
    pool = [o for g in groups.values() if len(g) > 1 for o in g]
    combining = {"candidates": len(pool), "candidate_fee_cents": sum(-o["driver_fee_cents"] for o in pool)}

    oracle = fee_margin + quote_gain
    return {
        "week_id": w["week_id"],
        "world_id": w["world_id"],
        "seed": w["seed"],
        "level": w["level"],
        "experiment": w["experiment"],
        "waterfall": waterfall,
        "selection": selection,
        "delivery": delivery,
        "fee": fee,
        "quote": quote,
        "on_time": on_time,
        "combining": combining,
        "oracle_cents": oracle,
        "gap_cents": oracle - margin,
        "split": {
            "quoting_cents": selection["gain_cents"] + quote_gain,
            "driver_fees_cents": fee["gain_cents"],
            "delivery_cents": delivery["gain_cents"],
            "combining_cents": None,
        },
        "warnings": warnings,
        "_sums": {"on_time_kept": on_time_kept, "paid": paid, "ref": ref, "bound": bound},
    }


# ------------------------------------------------------------------------------------------------------ experiments


def add_into(total: dict, part: dict) -> None:
    """Sum every number of `part` into `total` (bools count weeks), recursing into dicts."""
    for k, v in part.items():
        if isinstance(v, dict):
            add_into(total.setdefault(k, {}), v)
        elif isinstance(v, bool):
            total[k] = total.get(k, 0) + int(v)
        elif isinstance(v, int | float) and not k.startswith(("cost_ratio", "scale", "share", "on_time_share")):
            total[k] = total.get(k, 0) + v


def aggregate(week_dicts: list[dict]) -> list[dict]:
    """One row per (experiment, level): every cents and count summed, shares recomputed, per-week means."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for wk in week_dicts:
        groups[(wk["level"], wk["experiment"])].append(wk)
    out = []
    for (level, name), weeks in sorted(groups.items()):
        t: dict = {}
        sums: dict = {}
        for wk in weeks:
            for key in ("waterfall", "selection", "delivery", "fee", "on_time", "combining"):
                add_into(t.setdefault(key, {}), wk[key])
            add_into(sums, wk["_sums"])
        n = len(weeks)
        sel, dlv, fee, ot = t["selection"], t["delivery"], t["fee"], t["on_time"]
        share_after = sums["on_time_kept"] / sel["orders_kept"] if sel["orders_kept"] else None
        sel["on_time_share_after"] = share_after
        dlv["cost_ratio_paid"] = round(sums["paid"] / sums["ref"], 4) if sums["ref"] else 1.0
        fee["cost_ratio_bound"] = round(sums["bound"] / sums["ref"], 4) if sums["ref"] else 1.0
        ot["share"] = ot["on_time"] / ot["counted"] if ot["counted"] else None
        ot["late_slack"] = min(wk["on_time"]["late_slack"] for wk in weeks)

        sources = [wk["quote"]["source"] for wk in weeks]
        weeks_probe, weeks_brackets = sources.count("probe"), sources.count("brackets")
        source = (
            "mixed"
            if weeks_probe and weeks_brackets
            else "probe"
            if weeks_probe
            else "brackets"
            if weeks_brackets
            else None
        )
        probes = [wk["quote"]["probe"] for wk in weeks if wk["quote"]["probe"]]
        probe = None
        if probes:
            probe = {}
            for p in probes:
                add_into(probe, {k: v for k, v in p.items() if k not in ("days", "window")})
            probe["days"] = sorted({d for p in probes for d in p["days"]})
            probe["window"] = None
            probe["scale"] = round(probe["window_requests"] / probe["requests"], 2)
        brackets: dict = {}
        bins: dict[float, list[int]] = defaultdict(lambda: [0, 0])
        estimates = [wk["quote"]["brackets"]["estimate"] for wk in weeks if wk["quote"]["brackets"]["estimate"]]
        for wk in weeks:
            b = wk["quote"]["brackets"]
            add_into(brackets, {k: v for k, v in b.items() if k not in ("lost_bins", "estimate")})
            for cell in b["lost_bins"]:
                bins[cell["ratio"]][0] += cell["requests"]
                bins[cell["ratio"]][1] += cell["ceiling_cents"]
        brackets["lost_bins"] = [{"ratio": r, "requests": c[0], "ceiling_cents": c[1]} for r, c in sorted(bins.items())]
        brackets["estimate"] = None
        if estimates:
            brackets["estimate"] = {}
            for e in estimates:
                add_into(brackets["estimate"], e)
        quote = {
            "source": source,
            "gain_cents": sum(wk["quote"]["gain_cents"] for wk in weeks),
            "weeks_probe": weeks_probe,
            "weeks_brackets": weeks_brackets,
            "probe": probe,
            "brackets": brackets,
        }
        split = {
            k: sum(wk["split"][k] for wk in weeks) for k in ("quoting_cents", "driver_fees_cents", "delivery_cents")
        }
        per_week = {
            k: round(sum(v(wk) for wk in weeks) / n)
            for k, v in {
                "margin_cents": lambda wk: wk["waterfall"]["margin_cents"],
                "selection_gain_cents": lambda wk: wk["selection"]["gain_cents"],
                "delivery_gain_cents": lambda wk: wk["delivery"]["gain_cents"],
                "fee_gain_cents": lambda wk: wk["fee"]["gain_cents"],
                "quote_gain_cents": lambda wk: wk["quote"]["gain_cents"],
                "oracle_cents": lambda wk: wk["oracle_cents"],
                "gap_cents": lambda wk: wk["gap_cents"],
            }.items()
        }
        per_week["waterfall"] = {k: round(t["waterfall"][k] / n) for k in (*ACCOUNTS, "unallocated_cents")}
        out.append(
            {
                "experiment": name,
                "level": level,
                "weeks": n,
                "week_ids": [wk["week_id"] for wk in weeks],
                "ranked_weeks": ot["ranked"],
                "waterfall": t["waterfall"],
                "selection": sel,
                "delivery": dlv,
                "fee": fee,
                "quote": quote,
                "on_time": ot,
                "combining": t["combining"],
                "oracle_cents": sum(wk["oracle_cents"] for wk in weeks),
                "gap_cents": sum(wk["gap_cents"] for wk in weeks),
                "split": {**split, "combining_cents": None},
                "per_week": per_week,
                "warnings": [m for wk in weeks for m in wk["warnings"]],
            }
        )
    return out


# ---------------------------------------------------------------------------------------------------------- build


def analyse(db_path: Path, probe_dir: Path | None) -> tuple[list[dict], dict]:
    """The week dicts of every played week (won > 0), with their private `_sums`, and the win curves."""
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=120)
    try:
        if not db.execute("select 1 from sqlite_master where type = 'table' and name = 'week_facts'").fetchone():
            sys.exit(f"No facts tables in {db_path}: run uv run python -m analysis.facts first.")
        weeks = [r for rows in rows_by_week(db, "select * from week_facts order by week_id").values() for r in rows]
        orders = rows_by_week(db, "select * from order_facts order by week_id, order_id")
        gig_rows = rows_by_week(
            db,
            "select g.week_id, w.seed, w.level, g.gig_id, g.order_id, g.orders, g.cars, g.pickup_place,"
            " g.delivery_place, g.experienced, g.outcome, g.booked_at, g.fee_cents, g.typical_fee_cents, g.fee_ratio"
            " from gig_facts g join week_facts w using (week_id) where g.outcome = 'done' order by g.week_id, g.gig_id",
        )
        quotes = rows_by_week(
            db,
            "select q.week_id, q.level, q.request_id, q.option, q.option_rank, q.day, q.arrived_at,"
            " q.list_price_cents, q.reference_fee_cents, q.quote_cents, q.ratio, q.quoted, q.options_quoted, q.taken"
            " from quote_facts q order by q.week_id, q.request_id, q.option",
        )
        refunds = rows_by_week(
            db,
            "select week_id, late_bucket, count(*) orders, sum(late_refund_cents) cents"
            " from order_facts where late_refund_cents < 0 group by 1, 2",
        )
    finally:
        db.close()
    twin, lane = fee_comparables([g for rows in gig_rows.values() for g in rows])
    curves = win_curves([q for rows in quotes.values() for q in rows])
    ctx = {"twin": twin, "lane": lane, "curves": curves, "probes": load_probes(probe_dir)}
    played = [w for w in weeks if (w["won"] or 0) > 0]
    week_dicts = [
        week_gap(
            w,
            orders.get(w["week_id"], []),
            gig_rows.get(w["week_id"], []),
            quotes.get(w["week_id"], []),
            refunds.get(w["week_id"], []),
            ctx,
        )
        for w in played
    ]
    return week_dicts, curves


def build(db_path: Path, probe_dir: Path | None) -> dict:
    """The full oracle JSON object of every played week (won > 0) of the database."""
    week_dicts, curves = analyse(db_path, probe_dir)
    return assemble(week_dicts, curves, db_path)


def assemble(week_dicts: list[dict], curves: dict, db_path: Path) -> dict:
    return {
        "version": VERSION,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "db": str(db_path),
        "assumptions": ASSUMPTIONS,
        "weeks": [{k: v for k, v in wk.items() if k != "_sums"} for wk in week_dicts],
        "experiments": aggregate(week_dicts),
        "win_curves": [
            {
                "level": c["level"],
                "day": c["day"],
                "rows": c["rows"],
                "pooled": c["pooled"],
                "mid": MIDS,
                "win": [round(x, 4) for x in c["s"]],
            }
            for _, c in sorted(curves.items())
        ],
    }


# ---------------------------------------------------------------------------------------------------------- print


def euros(cents: float | None) -> str:
    return "" if cents is None else f"{round(cents / 100):,}"


def table_row(r: dict, head: list[str], per_week: dict | None = None) -> list[str]:
    """Printed columns of one week or experiment (per_week: the means line of an experiment)."""
    wf = per_week["waterfall"] if per_week else r["waterfall"]
    handling = sum(
        wf[k] for k in ("failed_visit_cents", "waiting_cents", "release_fee_cents", "fine_cents", "other_cents")
    )
    if per_week:
        gains = [per_week[k] for k in ("selection_gain_cents", "delivery_gain_cents", "fee_gain_cents")]
        quote, oracle, gap = euros(per_week["quote_gain_cents"]), per_week["oracle_cents"], per_week["gap_cents"]
        tail = ["", ""]
    else:
        gains = [r["selection"]["gain_cents"], r["delivery"]["gain_cents"], r["fee"]["gain_cents"]]
        q = r["quote"]
        if "weeks_probe" in q:
            src = f"probe {q['weeks_probe']}/{r['weeks']}"
        else:
            src = q["source"] or "none"
        quote, oracle, gap = f"{euros(q['gain_cents'])} ({src})", r["oracle_cents"], r["gap_cents"]
        share = r["on_time"]["share"]
        tail = ["" if share is None else f"{share:.1%}", f"{r['on_time']['late_slack']:+d}"]
    money = [wf["revenue_cents"], wf["driver_fee_cents"], wf["late_refund_cents"], wf["undelivered_penalty_cents"]]
    return [
        *head,
        *map(euros, [*money, handling, wf["margin_cents"]]),
        "|",
        *map(euros, gains),
        quote,
        euros(oracle),
        euros(gap),
        "|",
        *tail,
    ]


def print_table(rows: list[list[str]], columns: list[str]) -> None:
    """Plain text, left-aligned first column, right-aligned numbers, a header and a rule."""
    widths = [max(len(str(x)) for x in col) for col in zip(columns, *rows, strict=True)]

    def line(cells: list[str]) -> str:
        return "  ".join(
            str(c).ljust(w) if i == 0 else str(c).rjust(w) for i, (c, w) in enumerate(zip(cells, widths, strict=True))
        ).rstrip()

    print(line(columns))
    print("-" * len(line(columns)))
    for r in rows:
        print(line(r))


MONEY_COLUMNS = [
    "revenue",
    "fees",
    "refunds",
    "penalty",
    "handling",
    "margin",
    "|",
    "+select",
    "+deliver",
    "+fees",
    "+quote(src)",
    "oracle",
    "gap",
    "|",
    "on-time",
    "slack",
]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="The hindsight oracle: the margin gap report of the played weeks.")
    parser.add_argument("--db", type=Path, default=Path("out/spread.sqlite"), help="the database (out/spread.sqlite)")
    parser.add_argument("--probe", type=Path, default=Path("out/probe"), help="folder of probe.py quote files")
    parser.add_argument("--json", default="out/oracle.json", help="where to write the JSON (- for none)")
    parser.add_argument("--week", type=int, action="append", default=[], help="print only this week (weeks.id)")
    parser.add_argument("--experiment", action="append", default=[], help="print only this experiment")
    parser.add_argument("--weeks", action="store_true", help="print the week table first")
    args = parser.parse_args(argv)
    if not args.db.exists():
        sys.exit(f"No database at {args.db}.")
    week_dicts, curves = analyse(args.db, args.probe)
    result = assemble(week_dicts, curves, args.db)
    if args.json != "-":
        path = Path(args.json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=1) + "\n")
    if not result["weeks"]:
        print("No played weeks.")
        return
    weeks = [
        wk
        for wk in week_dicts
        if (not args.week or wk["week_id"] in args.week)
        and (not args.experiment or wk["experiment"] in args.experiment)
    ]
    if not weeks:
        print("No played week matches the filters.")
        return
    if args.weeks:
        rows = [
            table_row(
                wk,
                [
                    wk["experiment"],
                    str(wk["level"]),
                    wk["seed"],
                    str(wk["week_id"]),
                    "yes" if wk["on_time"]["ranked"] else "no",
                ],
            )
            for wk in weeks
        ]
        print_table(rows, ["experiment", "L", "seed", "week", "ranked", *MONEY_COLUMNS])
        print()
    experiments = aggregate(weeks)
    rows = []
    for e in experiments:
        rows.append(table_row(e, [e["experiment"], str(e["level"]), str(e["weeks"]), str(e["ranked_weeks"])]))
        rows.append(table_row(e, ["  per week", "", "", ""], per_week=e["per_week"]))
    print_table(rows, ["experiment", "L", "weeks", "ranked", *MONEY_COLUMNS])
    lost = sum(e["quote"]["brackets"]["lost_requests"] for e in experiments)
    ceiling = sum(e["quote"]["brackets"]["lost_ceiling_cents"] for e in experiments)
    below = sum(e["quote"]["brackets"]["lost_below_similar"]["requests"] for e in experiments)
    below_rev = sum(e["quote"]["brackets"]["lost_below_similar"]["revenue_cents"] for e in experiments)
    cand = sum(e["combining"]["candidates"] for e in experiments)
    cand_fee = sum(e["combining"]["candidate_fee_cents"] for e in experiments)
    print()
    print(
        f"Lost quotes: {lost:,} requests, ceiling €{euros(ceiling)}; {below:,} lost below what similar requests won at"
        f" (€{euros(below_rev)} at our quotes)"
    )
    print(
        f"Car combining: not measurable (no gig with two orders); {cand:,} candidate orders, €{euros(cand_fee)} of fees"
    )
    print(
        "Every bound is an upper bound under the assumptions in analysis/README.md; the gains add up without overlap."
    )
    for e in experiments:
        for message in e["warnings"]:
            print(f"warning: {message}")


if __name__ == "__main__":
    main()
