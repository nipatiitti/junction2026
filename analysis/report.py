"""Overview report of the scraped weeks: one static HTML page (#67, #102).

Reads the facts tables of `analysis.facts`, the probe rows of `probe.py` and, when present, the oracle JSON of
`analysis.oracle`, writes `out/report.html` (one file, inline SVG, no JavaScript, no network) and serves it on
localhost until Ctrl-C. Every chart's title is its takeaway, computed from the data.

    uv run python -m analysis.report [--db out/spread.sqlite] [--probe out/probe] [--oracle out/oracle.json]
                                     [--out out/report.html] [--port 8000] [--no-serve]
"""

from __future__ import annotations

import argparse
import datetime
import glob
import html
import http.server
import itertools
import json
import math
import os
import re
import sqlite3
import statistics
import sys
import zlib
from pathlib import Path

E = html.escape
MINUS = "−"
W = 360
ML, MR, MT, MB = 44, 62, 14, 34
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun", "Mon", "Tue", "Wed"]
LEVEL_CLS = {6: "s2", 7: "s3", 8: "s1"}
NO_DATA = "No quoted weeks at this level yet."


# ---------------------------------------------------------------- formatting


def eur(cents) -> str:
    """Cents as whole euros: `−55,694 €`."""
    if cents is None:
        return "–"
    v = round(cents / 100)
    s = f"{abs(v):,} €"
    return f"{MINUS}{s}" if v < 0 else s


def eur_signed(cents) -> str:
    s = eur(cents)
    return s if s.startswith(MINUS) or s == "0 €" else "+" + s


def pct(x, digits: int = 1) -> str:
    return "–" if x is None else f"{x * 100:.{digits}f}%"


def num(x, digits: int = 0) -> str:
    if x is None:
        return "–"
    s = f"{abs(x):,.{digits}f}"
    return f"{MINUS}{s}" if x < 0 and float(s.replace(",", "")) != 0 else s


def short_eur(v: float) -> str:
    """Axis tick in euros: `−4k`, `500`."""
    if abs(v) >= 1000 and v % 1000 == 0:
        s = f"{abs(v) / 1000:g}k"
    else:
        s = f"{abs(v):,.0f}"
    return f"{MINUS}{s}" if v < 0 else s


def f2(x) -> str:
    return f"{x:.2f}"


def text_w(s: str, size: float = 12) -> float:
    return len(s) * size * 0.56


def wrap(s: str, size: float, width: float, lines: int = 2) -> list[str]:
    if text_w(s, size) <= width:
        return [s]
    words, out, cur = s.split(" "), [], ""
    for w in words:
        if cur and text_w(cur + " " + w, size) > width and len(out) < lines - 1:
            out.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    return [*out, cur]


def nice_step(span: float, n: int = 5) -> float:
    raw = span / max(n, 1)
    mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            return m * mag
    return 10 * mag


def nice_ticks(lo: float, hi: float, n: int = 5) -> list[float]:
    if hi <= lo:
        hi = lo + 1
    step = nice_step(hi - lo, n)
    start = math.floor(lo / step) * step
    ticks, v = [], start
    while v < hi + step * 0.999:
        ticks.append(round(v, 10))
        v += step
    return ticks


# ---------------------------------------------------------------- SVG pieces


def svg_open(h: int, aria: str) -> str:
    return f'<svg viewBox="0 0 {W} {h}" width="100%" style="height:auto" role="img" aria-label="{E(aria)}">'


def t(x, y, s, cls="tl", anchor="start", extra="") -> str:
    return f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}" text-anchor="{anchor}"{extra}>{E(s)}</text>'


def title(s: str) -> str:
    return f"<title>{E(s)}</title>"


def point(x, y, cls, tip) -> str:
    return (
        f'<g><circle cx="{x:.1f}" cy="{y:.1f}" r="3" class="pt {cls}"/>'
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="9" class="hit">{title(tip)}</circle></g>'
    )


def y_grid(ys: list[tuple[float, str]], x0: float, x1: float) -> str:
    out = []
    for y, label in ys:
        out.append(f'<line x1="{x0}" x2="{x1}" y1="{y:.1f}" y2="{y:.1f}" class="grid"/>')
        out.append(t(x0 - 4, y + 4, label, "tk", "end"))
    return "".join(out)


def end_labels(items: list[tuple[float, float, str]], top: float, bottom: float) -> str:
    """Direct labels at the right end of lines, nudged apart vertically: items are (x, y, name)."""
    labs = []
    for x, y, name in items:
        lines = wrap(name, 12, W - x - 8)
        h = 12 * len(lines)
        labs.append([y - h / 2 + 4, x, lines, h])
    labs.sort(key=lambda a: a[0])
    for i in range(1, len(labs)):
        prev = labs[i - 1]
        labs[i][0] = max(labs[i][0], prev[0] + prev[3])
    overflow = (labs[-1][0] + labs[-1][3] - 8 - bottom) if labs else 0
    if overflow > 0:
        for lab in labs:
            lab[0] -= overflow
    out = []
    for y, x, lines, _ in labs:
        w = max(text_w(s, 12) for s in lines)
        x = min(x + 6, W - 2 - w)
        y = max(y, top + 8)
        for i, s in enumerate(lines):
            out.append(t(x, y + 12 * i, s, "lab"))
    return "".join(out)


def line_chart(
    series: list[dict],
    *,
    x_range: tuple[float, float],
    x_ticks: list[tuple[float, str]],
    x_label: str,
    y_max: float,
    y_ticks: list[float],
    y_fmt,
    y_label: str,
    refs: tuple = (),
    aria: str,
    height: int = 210,
) -> str:
    """Lines over a numeric x. Each series: name, cls, pts = [(x, y or None, tip)]; None breaks the line."""
    h = height
    x0, x1, y0, y1 = ML, W - MR, MT, h - MB

    def px(v):
        return x0 + (v - x_range[0]) / (x_range[1] - x_range[0]) * (x1 - x0)

    def py(v):
        return y1 - v / y_max * (y1 - y0)

    out = [svg_open(h, aria), y_grid([(py(v), y_fmt(v)) for v in y_ticks], x0, x1)]
    out.append(f'<line x1="{x0}" x2="{x1}" y1="{y1}" y2="{y1}" class="axis"/>')
    for v, label in x_ticks:
        out.append(t(px(v), y1 + 14, label, "tk", "middle"))
    out.append(t((x0 + x1) / 2, h - 4, x_label, "al", "middle"))
    out.append(t(11, (y0 + y1) / 2, y_label, "al", "middle", f' transform="rotate(-90 11 {(y0 + y1) / 2:.1f})"'))
    for v, label in refs:
        out.append(f'<line x1="{px(v):.1f}" x2="{px(v):.1f}" y1="{y0}" y2="{y1}" class="ref"/>')
        out.append(t(px(v) + 3, y0 - 3, label, "tk"))
    ends = []
    for s in series:
        segs, cur, last = [], [], None
        for x, y, _tip in s["pts"]:
            if y is None:
                if cur:
                    segs.append(cur)
                cur = []
                continue
            cur.append((px(x), py(min(y, y_max))))
            last = cur[-1]
        if cur:
            segs.append(cur)
        for seg in segs:
            if len(seg) > 1:
                d = "M" + " L".join(f"{a:.1f},{b:.1f}" for a, b in seg)
                out.append(f'<path d="{d}" class="line {s["cls"]}"/>')
        for x, y, tip in s["pts"]:
            if y is not None:
                out.append(point(px(x), py(min(y, y_max)), s["cls"], tip))
        if last:
            ends.append((last[0], last[1], s.get("short", s["name"])))
    out.append(end_labels(ends, y0, y1))
    out.append("</svg>")
    return "".join(out)


def histogram(
    bars: list[dict],
    *,
    x_range: tuple[float, float],
    x_ticks: list[tuple[float, str]],
    x_label: str,
    y_max: float,
    y_ticks: list[float],
    y_fmt,
    y_label: str,
    refs: tuple = (),
    aria: str,
    cls: str = "s1",
    height: int = 210,
) -> str:
    """Vertical bars: each bar has lo, hi (x), y (None = not drawn) and tip."""
    h = height
    x0, x1, y0, y1 = ML, W - 14, MT, h - MB

    def px(v):
        return x0 + (v - x_range[0]) / (x_range[1] - x_range[0]) * (x1 - x0)

    def py(v):
        return y1 - v / y_max * (y1 - y0)

    out = [svg_open(h, aria), y_grid([(py(v), y_fmt(v)) for v in y_ticks], x0, x1)]
    for b in bars:
        if b["y"] is None or b["y"] <= 0:
            continue
        a, c = px(b["lo"]) + 1, px(b["hi"]) - 1
        top = py(min(b["y"], y_max))
        out.append(
            f'<rect x="{a:.1f}" y="{top:.1f}" width="{max(c - a, 1):.1f}" height="{y1 - top:.1f}" rx="3" '
            f'class="{cls}">{title(b["tip"])}</rect>'
        )
    out.append(f'<line x1="{x0}" x2="{x1}" y1="{y1}" y2="{y1}" class="axis"/>')
    for v, label in x_ticks:
        out.append(t(px(v), y1 + 14, label, "tk", "middle"))
    out.append(t((x0 + x1) / 2, h - 4, x_label, "al", "middle"))
    out.append(t(11, (y0 + y1) / 2, y_label, "al", "middle", f' transform="rotate(-90 11 {(y0 + y1) / 2:.1f})"'))
    for v, label, kind in refs:
        out.append(f'<line x1="{px(v):.1f}" x2="{px(v):.1f}" y1="{y0}" y2="{y1}" class="{kind}"/>')
        room = min((px(o) - px(v) for o, _, _ in refs if o > v), default=W)
        left = room < text_w(label, 11) + 8 or px(v) + text_w(label, 11) > W
        cls = "tk" if kind == "ref" else "lab"
        out.append(t(px(v) - 3 if left else px(v) + 3, y0 - 3, label, cls, "end" if left else "start"))
    out.append("</svg>")
    return "".join(out)


LABEL_W = 104


def strip_chart(
    rows: list[dict],
    *,
    x_range: tuple[float, float],
    x_ticks: list[tuple[float, str]],
    x_label: str,
    refs: tuple = (),
    aria: str,
    row_h: int = 34,
    height: int | None = None,
) -> str:
    """One row per group: label (two lines), dots (x, filled, cls, jitter, tip), a mean tick and a right-end note."""
    h = height or 60 + row_h * len(rows)
    row_h = (h - 60) / max(len(rows), 1) if height else row_h
    x0, x1 = LABEL_W, W - MR
    top, bottom = MT + 12, h - MB

    def px(v):
        v = min(max(v, x_range[0]), x_range[1])
        return x0 + (v - x_range[0]) / (x_range[1] - x_range[0]) * (x1 - x0)

    out = [svg_open(h, aria)]
    for v, label in x_ticks:
        out.append(f'<line x1="{px(v):.1f}" x2="{px(v):.1f}" y1="{top}" y2="{bottom}" class="grid"/>')
        out.append(t(px(v), bottom + 14, label, "tk", "middle"))
    for v, label, kind in refs:
        out.append(f'<line x1="{px(v):.1f}" x2="{px(v):.1f}" y1="{top - 10}" y2="{bottom}" class="{kind}"/>')
        out.append(t(px(v) + 3, top - 3, label, "tk"))
    out.append(t((x0 + x1) / 2, h - 4, x_label, "al", "middle"))
    for i, r in enumerate(rows):
        cy = top + row_h * (i + 0.5)
        if i:
            out.append(f'<line x1="4" x2="{W - 4}" y1="{top + row_h * i:.1f}" y2="{top + row_h * i:.1f}" class="sep"/>')
        out.append(t(4, cy - 2, r["label"], "lab"))
        if r.get("sub"):
            out.append(t(4, cy + 11, r["sub"], "tk"))
        for x, filled, cls, jit, tip in r["dots"]:
            shape = f"pt {cls}" if filled else f"ring {cls}"
            out.append(
                f'<g><circle cx="{px(x):.1f}" cy="{cy + jit:.1f}" r="{4 if filled else 3.5}" class="{shape}"/>'
                f'<circle cx="{px(x):.1f}" cy="{cy + jit:.1f}" r="9" class="hit">{title(tip)}</circle></g>'
            )
        if r.get("mark") is not None:
            m = px(r["mark"])
            out.append(
                f'<line x1="{m:.1f}" x2="{m:.1f}" y1="{cy - 12:.1f}" y2="{cy + 12:.1f}" class="mark">'
                f"{title(r.get('mark_tip', ''))}</line>"
            )
        if r.get("end"):
            out.append(t(x1 + 8, cy + 4, r["end"], "lab"))
    out.append(f'<line x1="{x0}" x2="{x1}" y1="{bottom}" y2="{bottom}" class="axis"/>')
    out.append("</svg>")
    return "".join(out)


def waterfall_chart(steps: list[dict], aria: str) -> str:
    """Horizontal waterfall: steps have label, value (cents), kind 'abs' (from 0) or 'delta', cls."""
    h = 40 + 26 * len(steps)
    x0, x1 = 132, W - MR
    run, spans = 0, []
    for s in steps:
        if s["kind"] == "abs":
            a, b = 0, s["value"]
            run = s["value"]
        else:
            a, b = run, run + s["value"]
            run = b
        spans.append((a, b))
    vals = [0] + [v for ab in spans for v in ab]
    lo, hi = min(vals), max(vals)
    ticks = nice_ticks(lo / 100, hi / 100, 4)
    lo, hi = min(lo, ticks[0] * 100), max(hi, ticks[-1] * 100)

    def px(v):
        return x0 + (v - lo) / ((hi - lo) or 1) * (x1 - x0)

    out = [svg_open(h, aria)]
    for v in ticks:
        out.append(f'<line x1="{px(v * 100):.1f}" x2="{px(v * 100):.1f}" y1="8" y2="{h - 28}" class="grid"/>')
        out.append(t(px(v * 100), h - 14, short_eur(v), "tk", "middle"))
    out.append(t((x0 + x1) / 2, h - 2, "€ per week", "al", "middle"))
    out.append(f'<line x1="{px(0):.1f}" x2="{px(0):.1f}" y1="8" y2="{h - 28}" class="axis"/>')
    for i, (s, (a, b)) in enumerate(zip(steps, spans, strict=True)):
        y = 12 + 26 * i
        lines = wrap(s["label"], 11, 124)
        for j, line in enumerate(lines):
            out.append(t(126, y + 12 + 11 * j - 5.5 * (len(lines) - 1), line, "lab2", "end"))
        left, right = sorted((px(a), px(b)))
        out.append(
            f'<rect x="{left:.1f}" y="{y + 3}" width="{max(right - left, 1.5):.1f}" height="16" rx="3" '
            f'class="{s["cls"]}">{title(f"{s['label']}: {eur(s['value'])} per week")}</rect>'
        )
        out.append(
            t(
                min(right + 4, W - 2 - text_w(eur(s["value"]), 11)),
                y + 15,
                eur_signed(s["value"]) if s["kind"] == "delta" else eur(s["value"]),
                "tk",
            )
        )
        if i < len(steps) - 1:
            out.append(f'<line x1="{px(b):.1f}" x2="{px(b):.1f}" y1="{y + 19}" y2="{y + 29}" class="conn"/>')
    out.append("</svg>")
    return "".join(out)


def scatter_chart(
    pts: list[dict],
    *,
    x_ticks: list[float],
    x_label: str,
    y_ticks: list[float],
    y_fmt,
    y_label: str,
    labelled: set,
    aria: str,
    cls: str = "s1",
    height: int = 210,
) -> str:
    """Dots over a log x and a linear y from 0: points have name, x, y, tip; names in `labelled` are written out."""
    h = height
    x0, x1, y0, y1 = ML, W - 14, MT, h - MB
    lo, hi = math.log(x_ticks[0]), math.log(x_ticks[-1])

    def px(v):
        return x0 + (math.log(v) - lo) / ((hi - lo) or 1) * (x1 - x0)

    def py(v):
        return y1 - v / y_ticks[-1] * (y1 - y0)

    out = [svg_open(h, aria), y_grid([(py(v), y_fmt(v)) for v in y_ticks], x0, x1)]
    out.append(f'<line x1="{x0}" x2="{x1}" y1="{y1}" y2="{y1}" class="axis"/>')
    for v in x_ticks:
        out.append(t(px(v), y1 + 14, f"{v:g}", "tk", "middle"))
    out.append(t((x0 + x1) / 2, h - 4, x_label, "al", "middle"))
    out.append(t(11, (y0 + y1) / 2, y_label, "al", "middle", f' transform="rotate(-90 11 {(y0 + y1) / 2:.1f})"'))
    for p in pts:
        x, y = px(min(max(p["x"], x_ticks[0]), x_ticks[-1])), py(p["y"])
        out.append(
            f'<g><circle cx="{x:.1f}" cy="{y:.1f}" r="4" class="pt {cls}"/>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="9" class="hit">{title(p["tip"])}</circle></g>'
        )
    dots = [(px(min(max(p["x"], x_ticks[0]), x_ticks[-1])), py(p["y"])) for p in pts]
    placed: list[tuple] = []
    for p, (x, y) in zip(pts, dots, strict=True):
        if p["name"] not in labelled:
            continue
        w = text_w(p["name"])
        # above, below, right, left: the first spot that covers the fewest dots and labels
        spots = [
            (x - w / 2, y - 18, x, y - 8, "middle"),
            (x - w / 2, y + 7, x, y + 17, "middle"),
            (x + 7, y - 6, x + 7, y + 4, "start"),
            (x - 7 - w, y - 6, x - 7, y + 4, "end"),
        ]

        def cost(spot, w=w):
            bx, by = spot[0], spot[1]
            if bx < x0 or bx + w > W - 2 or by < 0:
                return 99
            hits = sum(1 for dx, dy in dots if bx - 4 < dx < bx + w + 4 and by - 4 < dy < by + 16)
            return hits + 3 * sum(1 for ax, ay, aw in placed if bx < ax + aw and ax < bx + w and abs(by - ay) < 13)

        bx, by, tx, ty, anchor = min(spots, key=cost)
        placed.append((bx, by, w))
        out.append(t(tx, ty, p["name"], "lab", anchor))
    out.append("</svg>")
    return "".join(out)


def stacked_hbar(rows: list[dict], segments: list[tuple[str, str, str]], aria: str, x_label: str) -> str:
    """100% bars: rows have label, sub, parts {key: (weight, tip)}; segments are (key, name, cls) in order."""
    h = 40 + 30 * len(rows)
    x0, x1 = LABEL_W, W - 12
    out = [svg_open(h, aria)]
    for v in (0, 0.25, 0.5, 0.75, 1):
        x = x0 + v * (x1 - x0)
        out.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="8" y2="{h - 30}" class="grid"/>')
        out.append(t(x, h - 16, pct(v, 0), "tk", "middle"))
    out.append(t(min((x0 + x1) / 2, W - 2 - text_w(x_label, 11) / 2), h - 3, x_label, "al", "middle"))
    for i, r in enumerate(rows):
        y = 10 + 30 * i
        out.append(t(4, y + 9, r["label"], "lab"))
        out.append(t(4, y + 21, r["sub"], "tk"))
        total = sum(n for n, _ in r["parts"].values()) or 1
        x = x0
        for key, _name, cls in segments:
            n, tip = r["parts"].get(key, (0, ""))
            if not n:
                continue
            w = n / total * (x1 - x0)
            out.append(
                f'<rect x="{x + 1:.1f}" y="{y + 2}" width="{max(w - 2, 0.8):.1f}" height="20" rx="3" '
                f'class="{cls}">{title(tip)}</rect>'
            )
            if w > 34:
                out.append(
                    t(x + w / 2, y + 16, pct(n / total, 0), "inbar dark" if cls in ("s4", "o1") else "inbar", "middle")
                )
            x += w
    out.append("</svg>")
    return "".join(out)


# ---------------------------------------------------------------- HTML pieces


def table(rows: list[list], columns: list[str]) -> str:
    if not rows:
        return muted("No rows.")
    numeric = re.compile(rf"^[{MINUS}+\-]?[\d.,]+( ?(%|€|×.*|h|min|kB))?$|^–$")
    head = "".join(f"<th>{E(c)}</th>" for c in columns)
    body = []
    for r in rows:
        cells = []
        for v in r:
            s = str(v)
            cls = ' class="n"' if numeric.match(s) else ""
            cells.append(f"<td{cls}>{E(s)}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return f'<div style="overflow-x:auto"><table><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'


def details_block(summary: str, body: str) -> str:
    return f"<details><summary>{E(summary)}</summary>{body}</details>"


def method(notes: list[str]) -> str:
    """The method and the caveats of a section, collapsed."""
    return details_block("Method and caveats", "<ul>" + "".join(f"<li>{E(n)}</li>" for n in notes) + "</ul>")


def muted(s: str) -> str:
    return f'<p class="muted">{E(s)}</p>'


def legend(items: list[tuple[str, str]]) -> str:
    """items: (cls or 'ring:cls' / 'dot:cls', name)."""
    out = []
    for cls, name in items:
        if cls.startswith("ring:"):
            sw = f'<svg width="12" height="12" aria-hidden="true"><circle cx="6" cy="6" r="4" class="ring {cls[5:]}"/></svg>'
        elif cls.startswith("dot:"):
            sw = f'<svg width="12" height="12" aria-hidden="true"><circle cx="6" cy="6" r="4.5" class="{cls[4:]}"/></svg>'
        else:
            sw = f'<svg width="12" height="12" aria-hidden="true"><rect width="12" height="12" rx="3" class="{cls}"/></svg>'
        out.append(f"<span>{sw} {E(name)}</span>")
    return f'<div class="legend">{"".join(out)}</div>'


def card(takeaway: str, body: str, legend_html: str = "", notes: tuple | list = (), data: str = "") -> str:
    """One chart: the title is its takeaway, computed from the data; the method and the numbers are collapsed."""
    more = "".join(f"<p>{E(n)}</p>" for n in notes) + data
    fold = details_block("Data and method" if data and notes else "Data" if data else "Method", more) if more else ""
    return f'<div class="card"><h3>{E(takeaway)}</h3>{body}{legend_html}{fold}</div>'


def section(sid: str, h2: str, body: str) -> str:
    return f'<section id="{sid}"><h2>{E(h2)}</h2>{body}</section>'


def grid(cards: list[str]) -> str:
    return f'<div class="cards">{"".join(cards)}</div>'


# ---------------------------------------------------------------- data


def rows(con: sqlite3.Connection, sql: str, args=()) -> list[dict]:
    cur = con.execute(sql, args)
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r, strict=True)) for r in cur.fetchall()]


def load_probes(probe_dir: str) -> list[dict]:
    out = []
    for path in sorted(glob.glob(os.path.join(probe_dir, "quote-L*-*.jsonl"))):
        m = re.match(r"quote-L(\d+)-(.+)\.jsonl$", os.path.basename(path))
        if not m:
            continue
        level, seed = int(m.group(1)), m.group(2)
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if (
                    not isinstance(r, dict)
                    or r.get("error")
                    or r.get("ends") == "inverted"
                    or r.get("monotone") is False
                ):
                    continue
                ends = r.get("ends")
                flip = r.get("flipRatio")
                if ends == "false":
                    flip = None
                elif ends == "true":
                    wins = [p for p, ok in r.get("trials") or [] if ok]
                    flip = max(wins) / r["listPriceCents"] if wins and r.get("listPriceCents") else None
                options = r.get("options") or [r.get("option")]
                out.append(
                    {
                        "level": level,
                        "seed": seed,
                        "request": r.get("requestId"),
                        "option": r.get("option"),
                        "first": r.get("option") == options[0],
                        "day": r.get("day"),
                        "ends": ends,
                        "flip": flip,
                    }
                )
    return out


def load_fee_probes(probe_dir: str) -> list[dict]:
    """Fee probe rows: the lowest flat fee, over the typical fee, at which a driver books within the window."""
    out = []
    for path in sorted(glob.glob(os.path.join(probe_dir, "fee-L*-*.jsonl"))):
        m = re.match(r"fee-L(\d+)-(.+)\.jsonl$", os.path.basename(path))
        if not m:
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:  # also a row that is being written right now
                    continue
                if not isinstance(r, dict) or r.get("error") or r.get("monotone") is False:
                    continue
                flip = r.get("flipRatio")
                if not isinstance(flip, (int, float)):
                    flip = None
                if flip is None and r.get("ends") not in ("never", "true"):
                    continue
                window = r.get("windowMinutes")
                out.append(
                    {
                        "level": int(m.group(1)),
                        "seed": m.group(2),
                        "flip": flip,
                        "window": window if isinstance(window, (int, float)) else None,
                    }
                )
    return out


def load_oracle(db_path: str, probe_dir: str, oracle_path: str) -> tuple[dict | None, str]:
    data, note = None, ""
    if oracle_path and os.path.exists(oracle_path):
        try:
            with open(oracle_path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            note = f"Could not read {oracle_path}: {exc}."
    else:
        try:
            from analysis import oracle

            if hasattr(oracle, "build"):
                data = oracle.build(Path(db_path), Path(probe_dir) if os.path.isdir(probe_dir) else None)
        except Exception as exc:  # noqa: BLE001  (the report never fails because #66 is absent or broken)
            if not isinstance(exc, ImportError):
                note = f"analysis.oracle failed: {exc}."
    if data is not None and (not isinstance(data, dict) or data.get("version") != 1):
        return None, "The oracle data has an unknown version, so it is left out."
    return data, note


def load(db: str, probe_dir: str, oracle_path: str) -> dict:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=120)
    has = {r[0] for r in con.execute("select name from sqlite_master where type = 'table'")}
    if "week_facts" not in has:
        sys.exit(f"No facts tables in {db}: run uv run python -m analysis.facts first.")
    d: dict = {"db": db, "built": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M UTC")}
    d["totals"] = rows(
        con,
        """select sum(won > 0) played, sum(coalesce(won, 0) = 0) passive, count(*) weeks,
                  coalesce(sum(requests), 0) requests, coalesce(sum(quoted), 0) quoted
           from week_facts""",
    )[0]
    d["totals"]["orders"] = con.execute("select count(*) from order_facts").fetchone()[0]
    d["experiments"] = rows(
        con,
        """select experiment, level, count(*) weeks, sum(on_time_share >= 0.9) ranked,
                  avg(requests) requests, avg(quoted) quoted, avg(won - cancelled) orders,
                  1.0 * sum(on_time) / sum(counted) on_time_share, min(on_time_share) worst_share,
                  avg(revenue_cents) revenue, avg(margin_cents) margin, min(margin_cents) worst, max(margin_cents) best,
                  min(quote_lo) qlo, max(quote_hi) qhi, min(fee_shape) fee_shape
           from week_facts where won > 0 group by 1, 2 order by 2, 1""",
    )
    d["passive"] = rows(
        con, "select level, count(*) n from week_facts where coalesce(won, 0) = 0 group by 1 order by 1"
    )
    d["weeks"] = rows(
        con,
        """select week_id, experiment, level, seed, margin_cents, on_time_share, counted, on_time, late, undelivered,
                  late_slack, late_refund_cents, undelivered_penalty_cents
           from week_facts where won > 0 order by level, experiment, week_id""",
    )
    # Section 2: win curves on one-option quotes
    base = "from quote_facts where quoted = 1 and options_quoted = 1 and ratio >= 0.6 and ratio < 2.0"
    d["win_sample"] = rows(
        con, "select level, count(*) n from quote_facts where quoted = 1 and options_quoted = 1 group by 1 order by 1"
    )
    d["win_level"] = rows(
        con, f"select level, cast(ratio * 10 as int) / 10.0 b, count(*) n, avg(taken) win {base} group by 1, 2"
    )
    d["win_day"] = rows(
        con,
        f"select day, cast(ratio * 10 as int) / 10.0 b, count(*) n, avg(taken) win {base} and level = 8 group by 1, 2",
    )
    d["win_war"] = rows(
        con,
        f"""select war_guess g, cast(ratio * 10 as int) / 10.0 b, count(*) n, avg(taken) win {base} and level = 8
            and week_id in (select week_id from week_facts where war_day is not null) group by 1, 2""",
    )
    d["war_days"] = rows(
        con, "select war_day, count(*) n from week_facts where level = 8 and quoted > 0 group by 1 order by 1"
    )
    d["win_trust"] = rows(
        con,
        f"""select case when dealer_trust <= 2 then 0 when dealer_trust <= 6 then 1 when dealer_trust <= 11 then 2
                   else 3 end g, cast(ratio * 5 as int) / 5.0 b, count(*) n, avg(taken) win
            {base} and level = 8 and dealer_trust is not null group by 1, 2""",
    )
    # Section 3
    d["probe_dir"] = probe_dir
    d["probes"] = load_probes(probe_dir) if os.path.isdir(probe_dir) else []
    d["fee_probes"] = load_fee_probes(probe_dir) if os.path.isdir(probe_dir) else []
    # Section 4
    d["book_fee"] = rows(
        con,
        """select level, cast(fee_ratio * 5 as int) / 5.0 b, count(*) spells, sum(booked) booked, sum(day_minutes) minutes
           from gig_spells where source = 'actions' and end_estimated = 0 and fee_ratio >= 0.2 and fee_ratio < 2.6
           group by 1, 2""",
    )
    d["book_left"] = rows(
        con,
        """select case when minutes_to_last_pickup < 0 then 0 when minutes_to_last_pickup < 180 then 1
                       when minutes_to_last_pickup < 360 then 2 when minutes_to_last_pickup < 720 then 3
                       when minutes_to_last_pickup < 1440 then 4 when minutes_to_last_pickup < 2880 then 5 else 6 end k,
                  case when fee_ratio < 0.9 then 0 when fee_ratio < 1.3 then 1 else 2 end band,
                  count(*) spells, sum(booked) booked, sum(day_minutes) minutes
           from gig_spells where source = 'actions' and end_estimated = 0 and level = 8
             and minutes_to_last_pickup is not null and fee_ratio is not null group by 1, 2""",
    )
    d["open_gigs"] = rows(
        con,
        """select opening_ratio r, minutes_to_booking m from gig_facts
           where source = 'actions' and level = 8 and opening_ratio >= 0.2 and opening_ratio < 1.8""",
    )
    # Section 5
    d["towns"] = rows(
        con,
        """select t.place, p.name, 1.0 * sum(t.drivers_home) / count(*) drivers_home,
                  1.0 * sum(t.drivers_near) / count(*) drivers_near,
                  sum(t.requests) requests, sum(t.gigs_open) gigs_open, sum(t.bookings) bookings,
                  1.0 * sum(t.bookings) / nullif(sum(t.gigs_open), 0) booked_share, avg(t.mean_booked_ratio) booked_ratio
           from town_days t join places p on p.id = t.place
           where t.level = 8 and t.day < 5
             and t.week_id in (select week_id from week_facts where gigs > 0 and level = 8)
           group by 1, 2""",
    )
    d["town_range"] = {
        r["place"]: r
        for r in rows(
            con,
            """select place, min(drivers_home) lo, max(drivers_home) hi from town_days
               where level = 8 and day = 0
                 and week_id in (select week_id from week_facts where gigs > 0 and level = 8) group by 1""",
        )
    }
    d["town_weeks"] = con.execute("select count(*) from week_facts where gigs > 0 and level = 8").fetchone()[0]
    # Section 6 fallback: the week's account from week_facts
    d["accounts"] = rows(
        con,
        """select experiment, level, count(*) weeks, avg(revenue_cents) revenue, avg(driver_fee_cents) driver_fee,
                  avg(late_refund_cents) late_refund, avg(undelivered_penalty_cents) undelivered_penalty,
                  avg(failed_visit_cents + waiting_cents + release_fee_cents + fine_cents + other_cents) handling,
                  avg(margin_cents) margin
           from week_facts where won > 0 group by 1, 2 order by 2, 1""",
    )
    # Section 7
    d["late"] = rows(
        con,
        """select w.experiment, w.level, o.late_bucket, count(*) n,
                  sum(o.late_refund_cents + o.undelivered_penalty_cents) cents
           from order_facts o join week_facts w using (week_id) where o.counted = 1 group by 1, 2, 3""",
    )
    d["on_time"] = rows(
        con,
        """select experiment, level, sum(counted) counted, sum(on_time) on_time, sum(late) late,
                  sum(undelivered) undelivered, 1.0 * sum(on_time) / sum(counted) share, sum(on_time_share >= 0.9) ranked,
                  count(*) weeks, min(late_slack) slack, sum(late_refund_cents) refunds,
                  sum(undelivered_penalty_cents) penalties
           from week_facts where won > 0 group by 1, 2 order by 2, 1""",
    )
    con.close()
    d["oracle"], d["oracle_note"] = load_oracle(db, probe_dir, oracle_path)
    return d


# ---------------------------------------------------------------- shared chart bits


def ratio_ticks(lo=0.6, hi=2.0, step=0.2):
    n = round((hi - lo) / step)
    return [(round(lo + i * step, 2), f"{lo + i * step:.1f}") for i in range(n + 1)]


SHARE_TICKS = [0, 0.25, 0.5, 0.75, 1.0]
LEVELS = [(6, "level 6", "L6", "s2"), (7, "level 7", "L7", "s3"), (8, "level 8", "L8", "s1")]


def pct0(v):
    return pct(v, 0)


def win_series(data: list[dict], key: str, groups: list[tuple], width: float, minimum: int) -> list[dict]:
    """groups: (value, name, short, cls). Points at bin middles from 0.6 to 2.0."""
    out = []
    n_bins = round(1.4 / width)
    for g, name, short, cls in groups:
        by_b = {round(r["b"], 2): r for r in data if r[key] == g}
        if not by_b:
            continue
        pts = []
        for i in range(n_bins):
            b = round(0.6 + i * width, 2)
            r = by_b.get(b)
            if r and r["n"] >= minimum:
                tip = f"{name}, {b:.1f}–{b + width:.1f} × list: {pct(r['win'], 0)} won ({r['n']:,} quotes)"
                pts.append((b + width / 2, r["win"], tip))
            else:
                pts.append((b + width / 2, None, ""))
        n = sum(r["n"] for r in by_b.values())
        out.append({"name": name, "short": short, "cls": cls, "pts": pts, "rows": by_b, "n": n})
    return out


def win_table(series: list[dict], width: float) -> str:
    out = []
    for s in series:
        for b, r in sorted(s["rows"].items()):
            out.append([s["name"], f"{b:.1f}–{b + width:.1f}", f"{r['n']:,}", pct(r["win"])])
    return table(out, ["Series", "Quote / list", "Quotes", "Won"])


def win_chart(series, aria, refs=((1.0, "list"),)) -> str:
    return line_chart(
        series,
        x_range=(0.6, 2.0),
        x_ticks=ratio_ticks(),
        x_label=f"quote / list price (n = {sum(s.get('n', 0) for s in series):,} quotes)",
        y_max=1.0,
        y_ticks=SHARE_TICKS,
        y_fmt=pct0,
        y_label="share of quotes won",
        refs=refs,
        aria=aria,
    )


def series_legend(series: list[dict]) -> str:
    return legend([(s["cls"], f"{s['name']} (n = {s['n']:,})") for s in series])


def curve_finding(s: dict) -> str:
    drawn = [(x, y) for x, y, _ in s["pts"] if y is not None]
    if len(drawn) < 2:
        return f"{s['name']}: too few quotes to draw"
    (xa, ya), (xb, yb) = drawn[0], drawn[-1]
    return f"{s['name']}: {pct(ya, 0)} won at {xa:.2f} × list, {pct(yb, 0)} at {xb:.2f} × list"


def widest_gap(a: dict, b: dict) -> tuple | None:
    """The bin where two series of the same bins differ most: (x, y of a, y of b)."""
    common = [
        (x, ya, yb)
        for (x, ya, _), (_, yb, _) in zip(a["pts"], b["pts"], strict=True)
        if ya is not None and yb is not None
    ]
    return max(common, key=lambda c: abs(c[1] - c[2])) if common else None


def bin_name(x: float, width: float) -> str:
    return f"{x - width / 2:.1f}–{x + width / 2:.1f} × list"


def exp_label(e: dict) -> str:
    return f"{e['experiment']} L{e['level']}"


def focus_experiment(d: dict) -> dict | None:
    """The experiment to build on: the best mean margin at the highest level that was played."""
    exps = d["experiments"]
    if not exps:
        return None
    top = max(e["level"] for e in exps)
    return max((e for e in exps if e["level"] == top), key=lambda e: e["margin"])


def spearman(xs: list[float], ys: list[float]) -> float | None:
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        out = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                out[order[k]] = (i + j) / 2
            i = j + 1
        return out

    if len(xs) < 3:
        return None
    try:
        return statistics.correlation(ranks(xs), ranks(ys))
    except statistics.StatisticsError:
        return None


# ---------------------------------------------------------------- sections

RANK_NOTE = "A week is ranked only with at least 90% of its counted orders on time, whatever its margin."


def week_groups(d: dict) -> dict:
    groups: dict = {}
    for w in d["weeks"]:
        groups.setdefault((w["experiment"], w["level"]), []).append(w)
    return groups


def off_scale(groups: dict) -> set:
    """Experiments whose every week lies far below all the others: they get a panel with its own axis."""
    off: set = set()
    while len(groups) - len(off) > 1:
        rest = {k: ws for k, ws in groups.items() if k not in off}
        key = min(rest, key=lambda k: max(w["margin_cents"] for w in rest[k]))
        others = [w["margin_cents"] for k, ws in rest.items() if k != key for w in ws]
        lo, hi = min(min(others), 0), max(max(others), 0)
        if max(w["margin_cents"] for w in rest[key]) >= lo - 2 * (hi - lo):
            break
        off.add(key)
    return off


def margin_panel(groups: dict, keys: list, aria: str, x_label: str) -> str:
    ms = [w["margin_cents"] / 100 for k in keys for w in groups[k]]
    ticks = nice_ticks(min(min(ms), 0), max(max(ms), 0), 4)
    srows = []
    for exp, lvl in keys:
        ws = groups[(exp, lvl)]
        mean = sum(w["margin_cents"] for w in ws) / len(ws) / 100
        srows.append(
            {
                "label": exp,
                "sub": f"L{lvl} · {len(ws)} weeks",
                "dots": [
                    (
                        w["margin_cents"] / 100,
                        (w["on_time_share"] or 0) >= 0.9,
                        LEVEL_CLS.get(lvl, "s4"),
                        zlib.crc32(str(w["week_id"]).encode()) % 17 - 8,
                        f"{w['seed']}: {eur(w['margin_cents'])}, {pct(w['on_time_share'])} on time",
                    )
                    for w in ws
                ],
                "mark": mean,
                "mark_tip": f"{exp} L{lvl} mean: {eur(mean * 100)}",
                "end": eur(mean * 100),
            }
        )
    return strip_chart(
        srows,
        x_range=(ticks[0], ticks[-1]),
        x_ticks=[(v, short_eur(v)) for v in ticks],
        x_label=x_label,
        refs=((0, "", "axis"),) if ticks[0] < 0 < ticks[-1] else (),
        aria=aria,
    )


def section_experiments(d: dict) -> str:
    exps = d["experiments"]
    passive = ", ".join(f"L{r['level']} {r['n']}" for r in d["passive"]) or "none"
    if not exps:
        return section(
            "experiments",
            "1. Experiments",
            muted("No experiment has won an order yet.") + muted(f"Passive weeks (requests only): {passive}."),
        )
    groups = week_groups(d)
    focus = focus_experiment(d)
    best = max(exps, key=lambda e: e["margin"])
    lvls = sorted({lvl for _, lvl in groups})
    dot_legend = legend(
        [("dot:pt " + LEVEL_CLS.get(lvl, "s4"), f"level {lvl}") for lvl in lvls]
        + [("dot:pt total", "ranked"), ("ring:total", "not ranked")]
    )
    # 1a margin
    off = off_scale(groups)
    main = [k for k in groups if k not in off]
    if focus["margin"] < 0 and best["margin"] < 0:
        ttl = f"No experiment makes money yet: {focus['experiment']} loses least at level {focus['level']}, {eur(-focus['margin'])} a week"
    else:
        ttl = f"{exp_label(focus)} is the one to build on: {eur_signed(focus['margin'])} a week"
    aria = "Margin of each played week. " + "; ".join(
        f"{exp_label(e)} mean {eur(e['margin'])}, {e['ranked']} of {e['weeks']} ranked" for e in exps
    )
    chart = margin_panel(groups, main, aria, "margin of the week (€); tick = mean")
    if off:
        names = ", ".join(k[0] for k in off)
        chart += f"<h4>Off that scale, on its own axis: {E(names)}</h4>" + margin_panel(
            groups,
            [k for k in groups if k in off],
            f"Margin of each week of {names}, own axis.",
            "margin of the week (€)",
        )
    trs = []
    for e in exps:
        setup = []
        if e["qlo"] is not None:
            setup.append(f"quotes {e['qlo']:g}–{e['qhi']:g} × list")
        if e["fee_shape"]:
            setup.append(f"fees {e['fee_shape']}")
        trs.append(
            [
                e["experiment"],
                e["level"],
                e["weeks"],
                f"{e['ranked']} of {e['weeks']}",
                num(e["requests"]),
                num(e["quoted"]),
                num(e["orders"]),
                pct(e["on_time_share"]),
                pct(e["worst_share"]),
                eur(e["revenue"]),
                eur(e["margin"]),
                f"{eur(e['worst'])} … {eur(e['best'])}",
                ", ".join(setup) or "–",
            ]
        )
    exp_table = table(
        trs,
        [
            "Experiment",
            "Level",
            "Weeks",
            "Ranked",
            "Requests/wk",
            "Quoted/wk",
            "Orders/wk",
            "On time",
            "Worst week",
            "Revenue/wk",
            "Margin/wk",
            "Margin range",
            "Setup",
        ],
    )
    week_rows = [
        [w["experiment"], w["level"], w["seed"], eur(w["margin_cents"]), pct(w["on_time_share"])] for w in d["weeks"]
    ]
    c1 = card(
        ttl,
        chart,
        dot_legend,
        [
            "One dot per played week, coloured by level; filled when the week is ranked. " + RANK_NOTE,
            f"Best mean margin over all levels: {exp_label(best)} at {eur(best['margin'])} a week.",
        ],
        table(week_rows, ["Experiment", "Level", "Seed", "Margin", "On time"]),
    )
    # 1b on time
    srows, clamped = [], 0
    for (exp, lvl), ws in groups.items():
        ranked = sum((w["on_time_share"] or 0) >= 0.9 for w in ws)
        dots = []
        for w in ws:
            s = w["on_time_share"] or 0
            clamped += s < 0.6
            dots.append(
                (
                    max(s, 0.6),
                    s >= 0.9,
                    LEVEL_CLS.get(lvl, "s4"),
                    zlib.crc32(str(w["week_id"]).encode()) % 17 - 8,
                    f"{w['seed']}: {pct(s)} on time ({w['on_time']} of {w['counted']}), {eur(w['margin_cents'])}",
                )
            )
        srows.append({"label": exp, "sub": f"L{lvl} · {len(ws)} weeks", "dots": dots, "end": f"{ranked} of {len(ws)}"})
    all_ranked, all_weeks = sum(e["ranked"] for e in exps), sum(e["weeks"] for e in exps)
    ttl = (
        f"{all_ranked} of {all_weeks} played weeks reach the 90% minimum; {focus['experiment']} ranks "
        f"{focus['ranked']} of {focus['weeks']}"
    )
    chart = strip_chart(
        srows,
        x_range=(0.6, 1.0),
        x_ticks=[(0.6, "≤60%" if clamped else "60%")] + [(v / 100, f"{v}%") for v in range(70, 101, 10)],
        x_label="on-time share of counted orders; right: ranked weeks",
        refs=((0.9, "minimum", "ref"),),
        aria="On-time share of each played week against the 90% minimum. "
        + "; ".join(f"{r['label']} {r['sub']}, ranked {r['end']}" for r in srows),
    )
    on_time_rows = [
        [
            r["experiment"],
            r["level"],
            num(r["counted"]),
            num(r["on_time"]),
            num(r["late"]),
            num(r["undelivered"]),
            pct(r["share"]),
            f"{r['ranked']} of {r['weeks']}",
            num(r["slack"]),
            eur(r["refunds"]),
            eur(r["penalties"]),
        ]
        for r in d["on_time"]
    ]
    notes = [RANK_NOTE]
    if clamped:
        notes.append(f"{clamped} weeks below 60% are drawn at 60%.")
    c2 = card(
        ttl,
        chart,
        dot_legend,
        notes,
        table(
            on_time_rows,
            [
                "Experiment",
                "Level",
                "Counted",
                "On time",
                "Late",
                "Undelivered",
                "Share",
                "Ranked weeks",
                "Lowest late slack",
                "Refunds",
                "Penalties",
            ],
        ),
    )
    # 1c lateness
    parts: dict = {}
    for r in d["late"]:
        parts.setdefault((r["experiment"], r["level"]), {})[r["late_bucket"]] = (r["n"], abs(r["cents"] or 0))
    names = {key: name for key, name, _ in BUCKETS}
    srows2, trs2 = [], []
    for (exp, lvl), pp in sorted(parts.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        tot = sum(n for n, _ in pp.values())
        srows2.append(
            {
                "label": exp,
                "sub": f"L{lvl} · {tot:,} orders",
                "parts": {
                    k: (n, f"{names.get(k, k)}: {n:,} orders ({pct(n / tot)}), {eur(-c) if c else '0 €'}")
                    for k, (n, c) in pp.items()
                },
            }
        )
        for key, name, _ in BUCKETS:
            n, cents = pp.get(key, (0, 0))
            trs2.append([f"{exp} L{lvl}", name, n, pct(n / tot if tot else 0), eur(cents)])
    if srows2:
        fp = parts.get((focus["experiment"], focus["level"]), {})
        tot = sum(n for n, _ in fp.values()) or 1
        late = tot - fp.get("on_time", (0, 0))[0]
        cost = sum(c for _, c in fp.values()) / focus["weeks"]
        worst = max(fp.items(), key=lambda kv: kv[1][1], default=None)
        ttl = f"In {exp_label(focus)}, {pct(late / tot)} of orders miss the deadline and cost {eur(cost)} a week"
        if worst and worst[1][1] and cost:
            ttl += f", {pct(worst[1][1] / focus['weeks'] / cost, 0)} of it from “{names.get(worst[0], worst[0])}”"
        aria = "Counted orders by lateness: " + "; ".join(
            f"{r['label']} {r['sub']}, {pct(r['parts'].get('on_time', (0, ''))[0] / max(sum(n for n, _ in r['parts'].values()), 1))} on time"
            for r in srows2
        )
        c3 = card(
            ttl,
            stacked_hbar(srows2, BUCKETS, aria, "share of counted orders"),
            legend([(cls, name) for _, name, cls in BUCKETS]),
            [
                (
                    "Refund by lateness: up to 2 h 10% of the price, 2–24 h 25%, up to 2 business days 50%, longer "
                    "100%; an undelivered order costs a penalty of 2 × the price. Hover a segment for its orders and cost."
                )
            ],
            table(trs2, ["Experiment", "Lateness", "Orders", "Share", "Refund or penalty"]),
        )
    else:
        c3 = card("No counted orders yet", "")
    extra = details_block("All experiments: the table", exp_table + muted(f"Passive weeks (requests only): {passive}."))
    return section("experiments", "1. Experiments", grid([c1, c2, c3]) + extra)


def section_dealers(d: dict) -> str:
    sample = ", ".join(f"{r['n']:,} at level {r['level']}" for r in d["win_sample"]) or "no rows"
    cards = []
    # 2a by level
    s = win_series(d["win_level"], "level", LEVELS, 0.1, 20)
    if s:
        hi, lo = s[-1], s[0]
        g = widest_gap(hi, lo) if hi is not lo else None
        if g:
            ttl = (
                f"At {bin_name(g[0], 0.1)}, {hi['name']} wins {pct(g[1], 0)} of quotes and {lo['name']} {pct(g[2], 0)}"
            )
        else:
            drawn = [(x, y) for x, y, _ in hi["pts"] if y is not None]
            half = next((x for x, y in drawn if y < 0.5), None)
            ttl = (
                f"{hi['name'].capitalize()} wins more than half of its quotes up to {half - 0.05:.1f} × list"
                if half
                else f"{hi['name'].capitalize()}: the win curve"
            )
        aria = "Win share by price over list, by level. " + "; ".join(curve_finding(x) for x in s)
        cards.append(card(ttl, win_chart(s, aria), series_legend(s), [], win_table(s, 0.1)))
    else:
        cards.append(card("Win share by level", muted(NO_DATA)))
    # 2b by trust
    s = win_series(
        d["win_trust"],
        "g",
        [
            (0, "trust 0–2", "0–2", "q2"),
            (1, "trust 3–6", "3–6", "q3"),
            (2, "trust 7–11", "7–11", "q4"),
            (3, "trust 12+", "12+", "q5"),
        ],
        0.2,
        15,
    )
    if s:
        g = widest_gap(s[0], s[-1]) if len(s) > 1 else None
        if g:
            verb = "raises" if g[2] >= g[1] else "lowers"
            ttl = f"Trust {verb} the win share from {pct(g[1], 0)} to {pct(g[2], 0)} at {bin_name(g[0], 0.2)}"
        else:
            ttl = "Win share by dealer trust, level 8"
        aria = "Level 8 win share by dealer trust. " + "; ".join(curve_finding(x) for x in s)
        cards.append(
            card(
                ttl,
                win_chart(s, aria),
                series_legend(s),
                [
                    (
                        "Level 8. Trust is the dealer's count of our on-time orders: each raises what the dealer accepts "
                        "by 1%, up to 25; a late order halves the count. Bins of 0.2."
                    )
                ],
                win_table(s, 0.2),
            )
        )
    else:
        cards.append(card("Win share by dealer trust, level 8", muted(NO_DATA)))
    # 2c war day
    s = win_series(
        d["win_war"], "g", [(1, "war day (guess)", "war day", "s2"), (0, "other days", "other", "s1")], 0.1, 20
    )
    found = sum(r["n"] for r in d["war_days"] if r["war_day"] is not None)
    total = sum(r["n"] for r in d["war_days"])
    per = ", ".join(f"{DAYS[i]} {next((r['n'] for r in d['war_days'] if r['war_day'] == i), 0)}" for i in range(5))
    war_notes = [
        (
            "Level 8. On one day a week the competitor quotes 20% lower. The day is guessed from the win share at "
            "1.0–1.25 × list, so the gap is partly by construction."
        ),
        f"War day found in {found} of {total} level 8 weeks: {per}.",
    ]
    if s:
        g = widest_gap(s[0], s[-1]) if len(s) > 1 else None
        ttl = (
            f"On the price-war day a quote at {bin_name(g[0], 0.1)} wins {pct(g[1], 0)}, against {pct(g[2], 0)} on "
            "other days"
            if g
            else "Win share on the price-war day, level 8"
        )
        aria = "Win share on the guessed price-war day against other days. " + "; ".join(curve_finding(x) for x in s)
        cards.append(card(ttl, win_chart(s, aria), series_legend(s), war_notes, win_table(s, 0.1)))
    else:
        cards.append(card("Win share on the price-war day, level 8", muted(NO_DATA), "", war_notes))
    # weekday curve: kept as data, and for the probe comparison
    s = win_series(d["win_day"], "day", [(i, DAYS[i], DAYS[i], f"q{i + 1}") for i in range(5)], 0.1, 20)
    d["monday_curve"] = next((x for x in s if x["name"] == "Mon"), None)
    extra = method(
        [
            (
                "Only requests where we priced one option: with several priced options the dealer also chooses between "
                f"them, and each option's win share reads about half as high. Sample: {sample}."
            ),
            "Points with fewer than 20 quotes (15 by trust) are not drawn; the line breaks there.",
        ]
    )
    if s:
        extra += details_block("Level 8 win share by weekday: the table", win_table(s, 0.1))
    return section("dealers", "2. Dealers: what price wins", grid(cards) + extra)


OPTIONS = ["same_day", "next_day", "within_3_days"]


def probe_level(p: list[dict]) -> int | None:
    """The level with the most probed first options (the highest on a tie)."""
    counts: dict = {}
    for r in p:
        if r["first"]:
            counts[r["level"]] = counts.get(r["level"], 0) + 1
    return max(counts, key=lambda k: (counts[k], k)) if counts else None


def probe_median(p: list[dict], level: int | None) -> float | None:
    flips = [r["flip"] for r in p if r["first"] and r["level"] == level and r["flip"] is not None]
    return statistics.median(flips) if flips else None


def probe_curve(d: dict) -> tuple[dict, dict | None, int] | None:
    """The share of level 8 Monday first options that a price would win, beside the Monday curve of our quotes."""
    mon = [r for r in d["probes"] if r["first"] and r["level"] == 8 and r["day"] == 0]
    if not mon:
        return None
    pts = []
    for i in range(14):
        x = 0.65 + i * 0.1
        won = sum(1 for r in mon if r["ends"] == "true" or (r["flip"] is not None and r["flip"] >= x))
        tip = f"probe, {x:.2f} × list: {pct(won / len(mon), 0)} would win ({len(mon)} requests)"
        pts.append((x, won / len(mon), tip))
    probe = {"name": "probe", "short": "probe", "cls": "s3", "pts": pts, "n": len(mon)}
    ours = d.get("monday_curve")
    if ours:
        ours = {**ours, "name": "our quotes", "short": "ours", "cls": "s1"}
    return probe, ours, len(mon)


def section_probe(d: dict) -> str:
    p, fees = d["probes"], d["fee_probes"]
    if not p and not fees:
        return section("probe", "3. Probe: where a quote flips", muted(f"No probe rows yet in {d['probe_dir']}."))
    cards = []
    notes = [
        (
            "A probe bisects one request on copies of one world: the flip is the highest price that still wins. The "
            "probe's world wins and delivers nothing, so these are a world's first answers, with no trust and no "
            "competitor reaction."
        )
    ]
    lvl = probe_level(p)
    if p:
        reqs = {(r["level"], r["seed"], r["request"]) for r in p}
        worlds = {(r["level"], r["seed"]) for r in p}
        days = sorted({r["day"] for r in p if r["day"] is not None})
        unwinnable = sum(1 for r in p if r["ends"] == "false")
        notes.append(
            f"{len(reqs):,} probed requests in {len(worlds)} worlds, days {', '.join(DAYS[x] for x in days)}; "
            f"{pct(unwinnable / len(p), 0)} of the options are won by no price in the range."
        )
        # 3a histogram of the main level
        first = [r for r in p if r["first"] and r["level"] == lvl]
        flips = sorted(r["flip"] for r in first if r["flip"] is not None)
        med = statistics.median(flips) if flips else None
        below = sum(1 for r in first if r["ends"] == "false" or (r["flip"] is not None and r["flip"] < 1.0))
        bins, outside = [0] * 24, 0
        for f in flips:
            i = math.floor((f - 0.6) / 0.05 + 1e-9)
            if 0 <= i < 24:
                bins[i] += 1
            else:
                outside += 1
        yt = nice_ticks(0, max(bins) or 1, 4)
        bars = [
            {
                "lo": 0.6 + i * 0.05,
                "hi": 0.65 + i * 0.05,
                "y": n,
                "tip": f"{0.6 + i * 0.05:.2f}–{0.65 + i * 0.05:.2f} × list: {n} requests",
            }
            for i, n in enumerate(bins)
        ]
        if med:
            ttl = (
                f"Half of level {lvl} requests still say yes at {med:.2f} × list; only {pct(below / len(first), 0)} "
                "flip below the list price"
            )
            chart = histogram(
                bars,
                x_range=(0.6, 1.8),
                x_ticks=ratio_ticks(0.6, 1.8, 0.2),
                x_label=f"flip price / list price (n = {len(flips)} first options)",
                y_max=yt[-1],
                y_ticks=yt,
                y_fmt=lambda v: f"{v:g}",
                y_label="requests",
                refs=[(1.0, "list", "ref"), (med, f"median {med:.2f}", "medline")],
                aria=f"Flip price of {len(flips)} level {lvl} first options; median {med:.2f} × list.",
            )
            cards.append(
                card(
                    ttl,
                    chart,
                    "",
                    [
                        (
                            f"The first delivery option of each level {lvl} request. Left out: {len(first) - len(flips)} "
                            f"that no price wins and {outside} outside 0.6–1.8 × list."
                        )
                    ],
                    table([[f"{b['lo']:.2f}–{b['hi']:.2f}", b["y"]] for b in bars], ["Flip / list", "Requests"]),
                )
            )
        # 3b by level and option
        srows, trs, meds = [], [], {}
        for level in sorted({r["level"] for r in p}, reverse=True):
            for opt in OPTIONS:
                fl = [r["flip"] for r in p if r["level"] == level and r["option"] == opt and r["flip"] is not None]
                if not fl:
                    continue
                m = statistics.median(fl)
                meds[(level, opt)] = m
                trs.append(
                    [level, opt, len(fl), f2(m), f2(sum(fl) / len(fl)), sum(1 for f in fl if f < 0.6 or f > 1.8)]
                )
                srows.append(
                    {
                        "label": opt,
                        "sub": f"L{level} · n = {len(fl)}",
                        "dots": [
                            (
                                f,
                                True,
                                LEVEL_CLS.get(level, "s4"),
                                zlib.crc32(f"{level}{opt}{i}".encode()) % 13 - 6,
                                f"L{level} {opt}: flip at {f:.2f} × list",
                            )
                            for i, f in enumerate(fl)
                        ],
                        "mark": m,
                        "mark_tip": f"L{level} {opt} median {m:.2f} × list",
                        "end": f"{m:.2f}",
                    }
                )
        if srows:
            mine = [(o, meds[(lvl, o)]) for o in OPTIONS if (lvl, o) in meds]
            slower = len(mine) > 1 and all(a[1] >= b[1] for a, b in itertools.pairwise(mine))
            if len(mine) > 1:
                ttl = (
                    "Dealers pay for speed: " if slower else f"Level {lvl} flips by option: "
                ) + f"{mine[0][0]} flips at {mine[0][1]:.2f} × list, {mine[-1][0]} at {mine[-1][1]:.2f}"
            else:
                ttl = f"Level {lvl} {mine[0][0]} flips at {mine[0][1]:.2f} × list" if mine else "Flip by option"
            others = sorted({r["level"] for r in p} - {lvl}, reverse=True)
            for o in others[:1]:
                m = probe_median(p, o)
                if m:
                    ttl += f"; level {o} flips at {m:.2f}"
            chart = strip_chart(
                srows,
                x_range=(0.6, 1.8),
                x_ticks=ratio_ticks(0.6, 1.8, 0.2),
                x_label="flip price / list price; tick and right = median",
                refs=((1.0, "list", "ref"),),
                aria="Flip price by level and delivery option; medians "
                + ", ".join(f"L{k[0]} {k[1]} {m:.2f}" for k, m in meds.items())
                + " × list.",
                row_h=30,
            )
            cards.append(
                card(
                    ttl,
                    chart,
                    legend(
                        [("dot:pt " + LEVEL_CLS.get(x, "s4"), f"level {x}") for x in sorted({r["level"] for r in p})]
                    )
                    if len({r["level"] for r in p}) > 1
                    else "",
                    ["Each option against its own list price. Values outside 0.6–1.8 are drawn at the edge."],
                    table(trs, ["Level", "Option", "Options with a flip", "Median", "Mean", "Outside 0.6–1.8"]),
                )
            )
    # agreement with our quotes: a sentence, and a chart only when there is no fee probe to show
    pc = probe_curve(d) if p else None
    if pc and pc[1]:
        probe, ours, n_mon = pc
        diffs = [abs(a[1] - b[1]) for a, b in zip(probe["pts"], ours["pts"], strict=True) if b[1] is not None]
        if diffs:
            agree = (
                f"The probe agrees with our own level 8 Monday quotes: the share won differs by "
                f"{statistics.mean(diffs) * 100:.0f} points on average, {max(diffs) * 100:.0f} at most "
                f"({n_mon} probed Monday requests)."
            )
            notes.append(agree)
            if not fees:
                aria = "Probe flips against the Monday win curve at level 8. " + "; ".join(
                    curve_finding(x) for x in (probe, ours)
                )
                cards.append(
                    card(
                        f"Probe and our Monday quotes agree within {statistics.mean(diffs) * 100:.0f} points on average",
                        win_chart([probe, ours], aria),
                        series_legend([probe, ours]),
                        ["Level 8 Mondays: exact flips in a few worlds against one-option quotes in all Monday data."],
                        table(
                            [[f2(x), pct(y)] for x, y, _ in probe["pts"]], ["Quote / list", "Probe: share that wins"]
                        ),
                    )
                )
    # 3c fee probe
    if fees:
        booked = sorted(r["flip"] for r in fees if r["flip"] is not None)
        never = sum(1 for r in fees if r["flip"] is None)
        window = statistics.median(r["window"] for r in fees if r["window"]) if any(r["window"] for r in fees) else 180
        flvls = "/".join(str(x) for x in sorted({r["level"] for r in fees}))
        if booked:
            med = statistics.median(booked)
            at_typical = sum(1 for f in booked if f <= 1.0) / len(fees)
            bins, outside = [0] * 14, 0
            for f in booked:
                i = math.floor((f - 0.4) / 0.1 + 1e-9)
                if 0 <= i < 14:
                    bins[i] += 1
                else:
                    outside += 1
            yt = nice_ticks(0, max(bins) or 1, 4)
            bars = [
                {
                    "lo": 0.4 + i * 0.1,
                    "hi": 0.5 + i * 0.1,
                    "y": n,
                    "tip": f"{0.4 + i * 0.1:.1f}–{0.5 + i * 0.1:.1f} × typical fee: {n} gigs",
                }
                for i, n in enumerate(bins)
            ]
            ttl = (
                f"A driver takes a gig within {window / 60:g} h at a median {med:.2f} × the typical fee; "
                f"{pct(at_typical, 0)} are taken at or below it"
            )
            chart = histogram(
                bars,
                x_range=(0.4, 1.8),
                x_ticks=ratio_ticks(0.4, 1.8, 0.2),
                x_label=f"lowest fee that books / typical fee (n = {len(booked)} gigs)",
                y_max=yt[-1],
                y_ticks=yt,
                y_fmt=lambda v: f"{v:g}",
                y_label="gigs",
                refs=[(1.0, "typical", "ref"), (med, f"median {med:.2f}", "medline")],
                aria=f"Lowest flat fee that books within the window, {len(booked)} gigs; median {med:.2f} × typical.",
                cls="s3",
            )
            cards.append(
                card(
                    ttl,
                    chart,
                    "",
                    [
                        (
                            f"The fee probe (level {flvls}) wins a request cheaply, posts its gig at flat fees on copies of "
                            f"the world and waits {window:g} minutes: the flip is the lowest fee a driver books at. "
                            f"{len(fees)} gigs in {len({(r['level'], r['seed']) for r in fees})} worlds; {never} found no "
                            f"driver at any fee and {outside} lie outside 0.4–1.8. A small sample from the first days of "
                            "a world that delivers nothing."
                        )
                    ],
                    table([[f"{b['lo']:.1f}–{b['hi']:.1f}", b["y"]] for b in bars], ["Fee / typical", "Gigs"]),
                )
            )
    return section("probe", "3. Probe: where a quote flips", grid(cards) + method(notes))


def rate(r) -> float | None:
    return 60.0 * r["booked"] / r["minutes"] if r and r["minutes"] else None


def section_drivers(d: dict) -> str:
    cards = []
    # 4a share booked within a day, by opening fee
    bins: dict[int, list] = {}
    for r in d["open_gigs"]:
        bins.setdefault(math.floor(r["r"] * 5 + 1e-9), []).append(r["m"])
    bars, trs = [], []
    for k in range(1, 9):
        ms = bins.get(k, [])
        lo = k / 5
        if not ms:
            continue
        within = sum(1 for m in ms if m is not None and m <= 1440)
        booked = sorted(m for m in ms if m is not None)
        medm = statistics.median(booked) if booked else None
        share = within / len(ms)
        med_s = f"{medm / 60:.1f} h" if medm is not None else "–"
        tip = f"{lo:.1f}–{lo + 0.2:.1f} × typical: {pct(share, 0)} booked within a day ({len(ms)} gigs, median {med_s} to booking)"
        bars.append({"lo": lo, "hi": lo + 0.2, "y": share if len(ms) >= 20 else None, "tip": tip, "n": len(ms)})
        trs.append([f"{lo:.1f}–{lo + 0.2:.1f}", len(ms), within, pct(share), med_s])
    rate_rows = []
    for lvl, name, _, _ in LEVELS:
        for r in sorted((r for r in d["book_fee"] if r["level"] == lvl), key=lambda r: r["b"]):
            rate_rows.append(
                [
                    name,
                    f"{r['b']:.1f}–{r['b'] + 0.2:.1f}",
                    r["spells"],
                    r["booked"],
                    num(r["minutes"] / 60),
                    f2(rate(r)),
                ]
            )
    rate_tbl = (
        "<p>Bookings per open daytime hour by fee and level:</p>"
        + table(rate_rows, ["Level", "Fee / typical", "Spells", "Booked", "Open hours", "Per hour"])
        if rate_rows
        else ""
    )
    drawn = [b for b in bars if b["y"] is not None]
    if drawn:
        best = max(drawn, key=lambda b: b["y"])
        base = min(drawn, key=lambda b: b["y"])
        ttl = (
            f"Whatever the opening fee, {pct(base['y'], 0)} to {pct(best['y'], 0)} of gigs book within a day: most at "
            f"{best['lo']:.1f}–{best['hi']:.1f} × the typical fee, fewest at {base['lo']:.1f}–{base['hi']:.1f}"
            if best is not base
            else f"{pct(best['y'], 0)} of gigs opened at {best['lo']:.1f}–{best['hi']:.1f} × typical book within a day"
        )
        chart = histogram(
            bars,
            x_range=(0.2, 1.8),
            x_ticks=ratio_ticks(0.2, 1.8, 0.4),
            x_label=f"opening fee / typical fee (n = {sum(b['n'] for b in drawn):,} gigs)",
            y_max=1.0,
            y_ticks=SHARE_TICKS,
            y_fmt=pct0,
            y_label="booked within a day",
            refs=((1.0, "typical", "ref"),),
            aria="Share of level 8 gigs booked within a day of posting, by opening fee: "
            + ", ".join(f"{b['lo']:.1f} {pct(b['y'], 0)}" for b in drawn),
            cls="s1",
        )
        cards.append(
            card(
                ttl,
                chart,
                "",
                [
                    "Level 8 gigs with an action log, by the fee they were first posted at. Bars with fewer than 20 gigs are not drawn."
                ],
                table(trs, ["Opening fee / typical", "Gigs", "Booked within a day", "Share", "Median time to booking"])
                + rate_tbl,
            )
        )
    else:
        cards.append(card("Share of gigs booked within a day, by opening fee", muted("No level 8 gigs yet.")))
    # 4b by hours left
    labels = ["48+", "24–48", "12–24", "6–12", "3–6", "0–3", "late"]  # left to right: k 6 … 0
    bands = [(0, "below 0.9", "<0.9", "q2"), (1, "0.9–1.3", "0.9–1.3", "q3"), (2, "1.3 and up", "≥1.3", "q5")]
    series, trs, ymax = [], [], 0.0
    for band, name, short, cls in bands:
        by = {r["k"]: r for r in d["book_left"] if r["band"] == band}
        if not by:
            continue
        pts = []
        for pos in range(7):
            r = by.get(6 - pos)
            ok = r and r["minutes"] >= 1500
            v = rate(r) if ok else None
            if v is not None:
                ymax = max(ymax, v)
            tip = (
                f"fee {name}, {labels[pos]} h left: {v:.2f} bookings per open hour ({r['minutes'] / 60:,.0f} h)"
                if ok
                else ""
            )
            pts.append((pos, v, tip))
            if r:
                trs.append([name, labels[pos], r["spells"], r["booked"], num(r["minutes"] / 60), f2(rate(r))])
        hours = sum(r["minutes"] for r in by.values()) / 60
        series.append({"name": name, "short": short, "cls": cls, "pts": pts, "hours": hours})
    if series and ymax > 0:
        last = sorted((s["pts"][5][1], s["name"]) for s in series if s["pts"][5][1] is not None)
        if len(last) > 1:
            (lo_v, lo_name), (hi_v, hi_name) = last[0], last[-1]
            ttl = (
                f"With under 3 h left, gigs priced {hi_name} × the typical fee book {hi_v:.2f} times per open hour; those priced "
                f"{lo_name} × book {lo_v:.2f}"
            )
        else:
            ttl = "Booking rate by hours left to the last pickup time, level 8"
        yt = nice_ticks(0, ymax, 4)
        chart = line_chart(
            series,
            x_range=(-0.3, 6.3),
            x_ticks=list(enumerate(labels)),
            x_label="hours left to collect the car on time",
            y_max=yt[-1],
            y_ticks=yt,
            y_fmt=lambda v: f"{v:g}",
            y_label="bookings per open hour",
            aria="Level 8 booking rate by hours left to the last pickup time, by fee band. "
            + "; ".join(
                f"{s['name']}: " + ", ".join(f"{labels[int(x)]} {y:.2f}" for x, y, _ in s["pts"] if y is not None)
                for s in series
            ),
        )
        cards.append(
            card(
                ttl,
                chart,
                legend([(s["cls"], f"fee {s['name']} × typical ({s['hours']:,.0f} open h)") for s in series]),
                [
                    (
                        "A rate, not a share: bookings divided by the daytime hours (07–23) that gigs stood open at that "
                        "fee, level 8 weeks with an action log. The deadline warning comes at 3 hours. Points with less "
                        "than 25 open hours are not drawn. The fee bands are not an experiment: a gig that is still open at a high "
                        "fee is a hard one, so a higher band can book more slowly."
                    )
                ],
                table(trs, ["Fee band", "Hours left", "Spells", "Booked", "Open hours", "Per hour"]),
            )
        )
    else:
        cards.append(card("Booking rate by hours left, level 8", muted("No level 8 gigs with an action log yet.")))
    # 4c supply by town
    towns = sorted(d["towns"], key=lambda r: -(r["drivers_home"] or 0))
    weeks = d["town_weeks"] or 1
    if towns:
        trs = []
        for r in towns:
            rg = d["town_range"].get(r["place"], {})
            trs.append(
                [
                    r["name"],
                    f"{r['drivers_home']:.1f}",
                    f"{rg.get('lo', '–')}–{rg.get('hi', '–')}",
                    f"{r['drivers_near']:.1f}",
                    num(r["requests"] / weeks, 1),
                    r["gigs_open"],
                    r["bookings"],
                    pct(r["booked_share"], 0),
                    f2(r["booked_ratio"]) if r["booked_ratio"] is not None else "–",
                ]
            )
        pts = [
            {
                "name": r["name"],
                "x": r["drivers_home"],
                "y": r["booked_share"],
                "tip": f"{r['name']}: {r['drivers_home']:.1f} drivers at home ({r['drivers_near']:.1f} within 30 km), "
                f"{pct(r['booked_share'], 0)} of {r['gigs_open']:,} gig-days booked"
                + (f" at {r['booked_ratio']:.2f} × typical fee" if r["booked_ratio"] is not None else ""),
            }
            for r in towns
            if (r["gigs_open"] or 0) >= 20 and r["booked_share"] is not None and (r["drivers_home"] or 0) > 0
        ]
        if len(pts) >= 3:
            rho = spearman([p["x"] for p in pts], [p["y"] for p in pts])
            low, high = min(pts, key=lambda p: p["y"]), max(pts, key=lambda p: p["y"])
            if rho is None or abs(rho) < 0.3:
                ttl = "More drivers in town does not mean more gigs booked"
            else:
                ttl = f"Towns with more drivers book {'more' if rho > 0 else 'fewer'} of their gigs"
            ttl += f": {low['name']} books {pct(low['y'], 0)} of gig-days, {high['name']} {pct(high['y'], 0)}"
            xs = [p["x"] for p in pts]
            ticks = [v for v in (0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500) if min(xs) / 2.5 < v < max(xs) * 2.5]
            chart = scatter_chart(
                pts,
                x_ticks=ticks,
                x_label=f"drivers living in the town, mean per day (log scale; n = {len(pts)} towns)",
                y_ticks=SHARE_TICKS,
                y_fmt=pct0,
                y_label="gig-days booked",
                labelled={low["name"], high["name"], pts[0]["name"]},
                aria=f"Level 8 towns: drivers at home against the booked share of gig-days, {len(pts)} towns; "
                f"rank correlation {rho:.2f}."
                if rho is not None
                else "Level 8 towns: drivers at home against the booked share of gig-days.",
                cls="s3",
            )
            cards.append(
                card(
                    ttl,
                    chart,
                    "",
                    [
                        "A gig-day is one gig open on one day. Level 8 moves drivers between towns in every world, so "
                        f"this is the average world over {weeks} weeks (business days); the spread is in the table. "
                        "Towns with fewer than 20 gig-days are not drawn."
                        + (f" Rank correlation {rho:.2f}." if rho is not None else "")
                    ],
                    table(
                        trs,
                        [
                            "Town",
                            "Drivers at home",
                            "Monday range",
                            "Within 30 km",
                            "Requests/wk",
                            "Gig-days",
                            "Bookings",
                            "Booked",
                            "Booked fee / typical",
                        ],
                    ),
                )
            )
    else:
        cards.append(card("Supply by town, level 8", muted("No level 8 weeks with gigs yet.")))
    return section("drivers", "4. Drivers: what fee books", grid(cards))


def pw(e: dict, key: str) -> float:
    """Per-week mean from an oracle experiment block, tolerant of how `per_week` names its keys."""
    p = e.get("per_week") or {}
    weeks = e.get("weeks") or 1
    for k in (key, f"{key}_cents", f"{key}_gain_cents"):
        v = p.get(k)
        if isinstance(v, (int, float)):
            return v
        if isinstance(v, dict) and isinstance(v.get("gain_cents"), (int, float)):
            return v["gain_cents"]
    wf = p.get("waterfall")
    if isinstance(wf, dict) and isinstance(wf.get(f"{key}_cents"), (int, float)):
        return wf[f"{key}_cents"]
    # fall back to the summed block
    if key in ("selection", "delivery", "fee", "quote"):
        return (e.get(key) or {}).get("gain_cents", 0) / weeks
    if key in ("margin", "oracle", "gap"):
        return e.get(f"{key}_cents", 0) / weeks
    return (e.get("waterfall") or {}).get(f"{key}_cents", 0) / weeks


ACCOUNT = [
    ("revenue", "Revenue"),
    ("driver_fee", "Driver fees"),
    ("late_refund", "Late refunds"),
    ("undelivered_penalty", "Undelivered penalties"),
    ("handling", "Failed visits, waiting, release, fines"),
]
LEVERS = [
    ("selection", "Perfect accept/decline", "accept/decline", "s1"),
    ("delivery", "All on time", "all on time", "s2"),
    ("fee", "Lowest comparable fees", "lowest fees", "s3"),
    ("quote", "Quoting at the flip", "quoting at the flip", "s4"),
]


def oracle_experiments(d: dict) -> dict:
    return {(e["experiment"], e["level"]): e for e in (d["oracle"] or {}).get("experiments", [])}


def biggest_lever(e: dict) -> tuple[str, float]:
    """(name, cents per week) of the largest of the oracle's four gains in one experiment."""
    _, name, _, _ = max(LEVERS, key=lambda lv: pw(e, lv[0]))
    return name, max(pw(e, lv[0]) for lv in LEVERS)


def section_economics(d: dict) -> str:
    o = d["oracle"]
    note = muted(d["oracle_note"]) if d["oracle_note"] else ""
    focus = focus_experiment(d)
    if not d["accounts"] or not focus:
        return section("economics", "5. Economics: where the margin goes", note + muted("No played weeks yet."))
    oexp = oracle_experiments(d)
    key = (focus["experiment"], focus["level"])
    name = exp_label(focus)
    e = oexp.get(key)
    a = next(a for a in d["accounts"] if (a["experiment"], a["level"]) == key)
    if e:
        vals = {k: pw(e, k) for k, _ in ACCOUNT if k != "handling"}
        vals["handling"] = sum(pw(e, k) for k in ("failed_visit", "waiting", "release_fee", "fine", "other"))
        vals["margin"] = pw(e, "margin")
    else:
        vals = {k: a[k] for k in ("revenue", "driver_fee", "late_refund", "undelivered_penalty", "handling", "margin")}
    cards = []
    # 5a where the money went
    steps = [{"label": "Revenue", "value": vals["revenue"], "kind": "abs", "cls": "s1"}]
    steps += [{"label": label, "value": vals[k], "kind": "delta", "cls": "s2"} for k, label in ACCOUNT[1:]]
    steps.append({"label": "Margin", "value": vals["margin"], "kind": "abs", "cls": "total"})
    fee_share = abs(vals["driver_fee"]) / vals["revenue"] if vals["revenue"] else None
    ttl = (
        f"In {name}, driver fees take {pct(fee_share, 0)} of the revenue: the mean week ends at {eur(vals['margin'])}"
        if fee_share is not None
        else f"{name}: the mean week ends at {eur(vals['margin'])}"
    )
    aria = f"{name}, mean week: revenue {eur(vals['revenue'])}, driver fees {eur(vals['driver_fee'])}, margin {eur(vals['margin'])}."
    acc_rows = [
        [
            x["experiment"],
            x["level"],
            x["weeks"],
            eur(x["revenue"]),
            eur(x["driver_fee"]),
            eur(x["late_refund"]),
            eur(x["undelivered_penalty"]),
            eur(x["handling"]),
            eur(x["margin"]),
        ]
        for x in d["accounts"]
    ]
    cards.append(
        card(
            ttl,
            waterfall_chart(steps, aria),
            legend([("s1", "revenue"), ("s2", "costs"), ("total", "margin")]),
            [f"The mean of {a['weeks']} weeks of {name}; the other experiments are in the table."],
            table(
                acc_rows,
                [
                    "Experiment",
                    "Level",
                    "Weeks",
                    "Revenue/wk",
                    "Driver fees",
                    "Late refunds",
                    "Undelivered",
                    "Failed visits, waiting, release, fines",
                    "Margin/wk",
                ],
            ),
        )
    )
    if not oexp:
        cards.append(
            card(
                "No oracle bounds yet",
                muted("Run uv run python -m analysis.oracle for the gap to a perfect dispatcher."),
            )
        )
        return section("economics", "5. Economics: where the margin goes", note + grid(cards))
    bound_note = (
        "Upper bounds, each under its own assumptions (under “Method and caveats” below); they add up without "
        "overlap, and they are not forecasts."
    )
    # 5b what a perfect dispatcher keeps, focus experiment
    if e:
        q = e.get("quote") or {}
        wp, wb = q.get("weeks_probe") or 0, q.get("weeks_brackets") or 0
        src = f"probe flips in {wp} of {e['weeks']} weeks" if wp else "an estimate from the win curve" if wb else "none"
        gains = [(lab, pw(e, k)) for k, lab, _, _ in LEVERS]
        steps = [{"label": "Margin", "value": pw(e, "margin"), "kind": "abs", "cls": "total"}]
        steps += [{"label": "+ " + lab, "value": v, "kind": "delta", "cls": "s1"} for lab, v in gains]
        steps.append({"label": "Oracle", "value": pw(e, "oracle"), "kind": "abs", "cls": "total"})
        big_name, big = biggest_lever(e)
        rest = sum(v for _, v in gains) - big
        ttl = f"{big_name} is worth up to {eur(big)} a week in {name}"
        if rest > 0:
            ttl += f", {big / rest:.1f}× the other three levers together"
        aria = f"{name}: margin {eur(pw(e, 'margin'))} per week, oracle {eur(pw(e, 'oracle'))}; " + ", ".join(
            f"{lab} {eur(v)}" for lab, v in gains
        )
        sp, cb, weeks = e.get("split") or {}, e.get("combining") or {}, e.get("weeks") or 1
        cards.append(
            card(
                ttl,
                waterfall_chart(steps, aria),
                legend([("total", "margin and oracle"), ("s1", "gain of one perfect decision")]),
                [
                    bound_note,
                    f"Quote side from {src}.",
                    (
                        f"Split as in the brief (mean week): quoting {eur((sp.get('quoting_cents') or 0) / weeks)}, driver "
                        f"fees {eur((sp.get('driver_fees_cents') or 0) / weeks)}, delivery "
                        f"{eur((sp.get('delivery_cents') or 0) / weeks)}; car combining not measurable (no gig with two "
                        f"orders yet; {cb.get('candidates', 0):,} candidate orders)."
                    ),
                ],
            )
        )
    # 5c the gap of every experiment, as shares
    srows, trs, tops = [], [], []
    for x in d["accounts"]:
        oe = oexp.get((x["experiment"], x["level"]))
        if not oe:
            continue
        gains = {k: max(pw(oe, k), 0) for k, _, _, _ in LEVERS}
        total = sum(gains.values()) or 1
        tops.append(biggest_lever(oe)[0])
        srows.append(
            {
                "label": x["experiment"],
                "sub": f"L{x['level']} · {short_eur(round(pw(oe, 'gap') / 100, -2))} €/wk",
                "parts": {
                    k: (gains[k], f"{lab}: {eur_signed(gains[k])} a week ({pct(gains[k] / total, 0)} of the gains)")
                    for k, lab, _, _ in LEVERS
                },
            }
        )
        q = oe.get("quote") or {}
        br = q.get("brackets") or {}
        lbs = br.get("lost_below_similar") or {}
        weeks = oe.get("weeks") or 1
        trs.append(
            [
                x["experiment"],
                x["level"],
                oe["weeks"],
                eur(pw(oe, "margin")),
                eur_signed(pw(oe, "selection")),
                eur_signed(pw(oe, "delivery")),
                eur_signed(pw(oe, "fee")),
                f"{eur_signed(pw(oe, 'quote'))} ({q.get('source') or 'none'})",
                eur(pw(oe, "oracle")),
                eur(pw(oe, "gap")),
                f"{num((br.get('lost_requests') or 0) / weeks)} ({eur((br.get('lost_ceiling_cents') or 0) / weeks)})",
                f"{num((lbs.get('requests') or 0) / weeks)} ({eur((lbs.get('revenue_cents') or 0) / weeks)})",
            ]
        )
    if srows:
        top = max(set(tops), key=tops.count)
        ttl = f"{top} is the biggest lever in {tops.count(top)} of {len(tops)} experiments"
        other = [(x, tp) for x, tp in zip(srows, tops, strict=True) if tp != top]
        if other:
            ttl += f"; in {other[0][0]['label']} it is {other[0][1].lower()}"
        cards.append(
            card(
                ttl,
                stacked_hbar(
                    srows,
                    [(k, short, cls) for k, _, short, cls in LEVERS],
                    "The gap to the oracle by experiment, split by lever: "
                    + "; ".join(f"{r['label']} {r['sub']}, biggest {tp}" for r, tp in zip(srows, tops, strict=True)),
                    "share of the gap to the oracle; under the name: the gap per week",
                ),
                legend([(cls, short) for _, _, short, cls in LEVERS]),
                [bound_note, "Shares, because the gaps differ by an order of magnitude; the euros are in the table."],
                table(
                    trs,
                    [
                        "Experiment",
                        "Level",
                        "Weeks",
                        "Margin/wk",
                        "+ Selection",
                        "+ Delivery",
                        "+ Fees",
                        "+ Quotes (source)",
                        "Oracle/wk",
                        "Gap/wk",
                        "Lost quotes/wk (ceiling €)",
                        "Lost below similar wins/wk (€)",
                    ],
                ),
            )
        )
    assumptions = (o or {}).get("assumptions", {})
    items = [
        f"{k}: {v}"
        for k, v in assumptions.items()
        if k in ("selection", "delivery", "fee", "quote_probe", "quote_brackets")
    ]
    extra = (
        method(["What each upper bound assumes (from analysis.oracle; see analysis/README.md):", *items])
        if items
        else ""
    )
    return section("economics", "5. Economics: where the margin goes", note + grid(cards) + extra)


BUCKETS = [
    ("on_time", "on time", "s1"),
    ("le_2h", "up to 2 h late", "s4"),
    ("le_24h", "2–24 h", "o1"),
    ("le_2bd", "to 2 business days", "o2"),
    ("gt_2bd", "longer", "o3"),
    ("undelivered", "undelivered", "total"),
]


# ---------------------------------------------------------------- page


def summary(d: dict) -> str:
    """The strip at the top: the five numbers that matter."""
    tot = d["totals"]
    focus = focus_experiment(d)
    tiles = [("Weeks scraped", f"{tot['weeks'] or 0:,}", f"{tot['played'] or 0} played, {tot['passive'] or 0} passive")]
    if focus:
        tiles.append(
            (
                f"Best level {focus['level']} margin",
                f"{eur(focus['margin'])}",
                f"a week · {focus['experiment']}, {focus['weeks']} weeks",
            )
        )
        tiles.append(
            (
                "On time",
                pct(focus["on_time_share"]),
                f"{focus['ranked']} of {focus['weeks']} weeks ranked (≥ 90%)",
            )
        )
    else:
        tiles += [("Best margin", "–", "no played weeks yet"), ("On time", "–", "no played weeks yet")]
    lvl = probe_level(d["probes"])
    med = probe_median(d["probes"], lvl)
    n = sum(1 for r in d["probes"] if r["first"] and r["level"] == lvl)
    tiles.append(
        ("Median probe flip", f"{med:.2f} × list", f"level {lvl}, {n} probed requests")
        if med
        else ("Median probe flip", "–", "no probe rows yet")
    )
    e = oracle_experiments(d).get((focus["experiment"], focus["level"])) if focus else None
    if e:
        name, big = biggest_lever(e)
        tiles.append(("Biggest gap to the oracle", eur_signed(big), f"a week, upper bound · {name.lower()}"))
    else:
        tiles.append(("Biggest gap to the oracle", "–", "no oracle data"))
    return (
        '<div class="tiles">'
        + "".join(
            f'<div class="tile"><span class="k">{E(k)}</span><b>{E(v)}</b><span>{E(s)}</span></div>'
            for k, v, s in tiles
        )
        + "</div>"
    )


CSS = """
:root{--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--q1:#86b6ef;--q2:#5598e7;--q3:#2a78d6;--q4:#1c5cab;--q5:#0d366b;
--o1:#f2a27f;--o2:#eb6834;--o3:#a84318;--total:#52514e}
@media (prefers-color-scheme: dark){:root{--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;
--muted:#898781;--grid:#2c2c2a;--axis:#383835;--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;
--q1:#cde2fb;--q2:#9ec5f4;--q3:#6da7ec;--q4:#3987e5;--q5:#184f95;--o1:#f2a27f;--o2:#d95926;--o3:#a84318;
--total:#c3c2b7}}
*{box-sizing:border-box}
html{color-scheme:light dark}
body{max-width:1200px;margin:0 auto;padding:16px;font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif;
background:var(--page);color:var(--ink);overflow-wrap:anywhere}
header{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 20px}
h1{font-size:22px;margin:0}h2{font-size:18px;margin:28px 0 0}
h3{font-size:15px;line-height:1.3;margin:0 0 8px;font-weight:600;text-wrap:balance}
h4{font-size:12px;margin:8px 0 0;color:var(--ink2);font-weight:600}
nav{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:14px}a{color:var(--s1)}
.built{color:var(--muted);font-size:13px;margin:2px 0 0}
.muted{color:var(--muted);font-size:13px;margin:8px 0}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:12px;margin:10px 0}
.card{background:var(--surface);border:1px solid var(--grid);border-radius:8px;padding:12px;min-width:0;
display:flex;flex-direction:column}
.card svg{max-width:440px;margin:0 auto}
.card>details{margin-top:auto;padding-top:6px}
.legend{display:flex;flex-wrap:wrap;gap:2px 12px;font-size:12px;color:var(--ink2);margin-top:6px}
.legend span{display:inline-flex;align-items:center;gap:5px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,150px),1fr));gap:12px;margin:12px 0 0}
.tile{background:var(--surface);border:1px solid var(--grid);border-radius:8px;padding:10px 12px}
.tile b{display:block;font-size:24px;line-height:1.25;font-weight:600}
.tile span{display:block;color:var(--ink2);font-size:12px}.tile .k{font-size:13px}
details{font-size:13px}summary{cursor:pointer;color:var(--muted)}
details p,details ul{color:var(--ink2);margin:6px 0}details ul{padding-left:18px}
section>details{margin:6px 0}
table{border-collapse:collapse;font-size:13px;background:var(--surface);margin:8px 0}
th{color:var(--ink2);font-weight:600;text-align:left;border-bottom:1px solid var(--axis);padding:4px 8px;white-space:nowrap}
td{padding:3px 8px;border-bottom:1px solid var(--grid);white-space:nowrap}
td.n{text-align:right;font-variant-numeric:tabular-nums}
svg{display:block;overflow:visible}
svg text{fill:var(--ink)}
.tl,.lab{font-size:12px;fill:var(--ink2)}.lab2{font-size:11px;fill:var(--ink2)}
.tk{font-size:11px;fill:var(--muted);font-variant-numeric:tabular-nums}.al{font-size:11px;fill:var(--muted)}
svg text.inbar{font-size:11px;fill:#fff;font-weight:600}svg text.inbar.dark{fill:#0b0b0b}
line.grid{stroke:var(--grid)}.axis{stroke:var(--axis);stroke-width:1}
.sep{stroke:var(--grid);stroke-width:1}
.ref{stroke:var(--axis);stroke-width:1.5;stroke-dasharray:4 3}
.medline{stroke:var(--ink2);stroke-width:1.5}
.mark{stroke:var(--ink);stroke-width:2}
.conn{stroke:var(--muted);stroke-width:1}
.s1{stroke:var(--s1);fill:var(--s1)}.s2{stroke:var(--s2);fill:var(--s2)}.s3{stroke:var(--s3);fill:var(--s3)}
.s4{stroke:var(--s4);fill:var(--s4)}.q1{stroke:var(--q1);fill:var(--q1)}.q2{stroke:var(--q2);fill:var(--q2)}
.q3{stroke:var(--q3);fill:var(--q3)}.q4{stroke:var(--q4);fill:var(--q4)}.q5{stroke:var(--q5);fill:var(--q5)}
.o1{stroke:var(--o1);fill:var(--o1)}.o2{stroke:var(--o2);fill:var(--o2)}.o3{stroke:var(--o3);fill:var(--o3)}
.total{stroke:var(--total);fill:var(--total)}
rect.s1,rect.s2,rect.s3,rect.s4,rect.q1,rect.q2,rect.q3,rect.q4,rect.q5,rect.o1,rect.o2,rect.o3,rect.total{stroke:none}
.line{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.pt{stroke:var(--surface);stroke-width:2}
.ring{fill:var(--surface);stroke-width:1.5}
.hit{fill:transparent;stroke:none;pointer-events:all}
"""

SECTIONS = [
    ("experiments", "Experiments"),
    ("dealers", "Dealers"),
    ("probe", "Probe"),
    ("drivers", "Drivers"),
    ("economics", "Economics"),
]


def page(sections: list[str], d: dict) -> str:
    tot = d["totals"]
    built = (
        f"Built {d['built']} from {os.path.basename(d['db'])}: {tot['requests'] or 0:,} requests, "
        f"{tot['quoted'] or 0:,} quotes, {tot['orders'] or 0:,} orders. Hover a mark for its values; the numbers and "
        "the method of each chart are under “Data and method”."
    )
    nav = "".join(f'<a href="#{sid}">{i}. {E(n)}</a>' for i, (sid, n) in enumerate(SECTIONS, 1))
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta name="color-scheme" content="light dark">'
        f"<title>Spread weeks: overview</title><style>{CSS}</style></head><body>"
        f"<header><h1>Spread weeks: overview</h1><nav>{nav}</nav></header>"
        f'<p class="built">{E(built)}</p>' + summary(d) + "".join(sections) + "</body></html>"
    )


def build(db: str, probe_dir: str, oracle_path: str) -> tuple[str, dict]:
    d = load(db, probe_dir, oracle_path)
    sections = [
        section_experiments(d),
        section_dealers(d),
        section_probe(d),
        section_drivers(d),
        section_economics(d),
    ]
    return page(sections, d), d


def serve(text: str, port: int) -> None:
    """Serves the page on localhost until Ctrl-C; a taken port falls back to a free one."""
    body = text.encode()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            ok = self.path.split("?")[0] in ("/", "/report.html")
            data = body if ok else b"Not found: the report is at /\n"
            self.send_response(200 if ok else 404)
            self.send_header("Content-Type", "text/html; charset=utf-8" if ok else "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        do_HEAD = do_GET

        def log_message(self, *args):
            pass

    try:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        print(f"Port {port} is taken, using a free one.")
    print(f"Serving the report at http://localhost:{server.server_address[1]}/ (Ctrl-C stops)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        description="Write one HTML page with the whole picture of the scraped weeks and serve it on localhost."
    )
    ap.add_argument("--db", default="out/spread.sqlite")
    ap.add_argument("--probe", default="out/probe")
    ap.add_argument("--oracle", default="out/oracle.json")
    ap.add_argument("--out", default="out/report.html")
    ap.add_argument("--no-serve", action="store_true", help="only write the file (for scripts)")
    ap.add_argument("--serve", action="store_true", help="serve the page on localhost (the default)")
    ap.add_argument("--port", type=int, default=8000, help="port to serve on; a free one is used if it is taken")
    args = ap.parse_args(argv)
    if not os.path.exists(args.db):
        sys.exit(f"No database at {args.db}.")
    text, d = build(args.db, args.probe, args.oracle)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(text)
    reqs = len({(r["level"], r["seed"], r["request"]) for r in d["probes"]})
    print(
        f"Wrote {args.out} ({len(text.encode()) // 1024} kB): {d['totals']['weeks'] or 0} weeks, "
        f"{len(d['experiments'])} experiments, {reqs} probed requests."
    )
    if not args.no_serve:
        serve(text, args.port)


if __name__ == "__main__":
    main()
