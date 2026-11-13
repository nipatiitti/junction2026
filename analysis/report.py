"""Overview report of the scraped weeks: one static HTML page (#67).

Reads the facts tables of `analysis.facts`, the probe rows of `probe.py` and, when present, the oracle JSON of
`analysis.oracle`, and writes `out/report.html`: one file, inline SVG, no JavaScript, no network.

    uv run python -m analysis.report [--db out/spread.sqlite] [--probe out/probe] [--oracle out/oracle.json]
                                     [--out out/report.html]
"""

from __future__ import annotations

import argparse
import datetime
import glob
import html
import json
import math
import os
import re
import sqlite3
import statistics
import sys
import zlib

E = html.escape
MINUS = "−"
W = 480
ML, MR, MT, MB = 44, 64, 12, 34
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
    height: int = 260,
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
            ends.append((last[0], last[1], s["name"]))
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
    height: int = 260,
) -> str:
    """Vertical bars: each bar has lo, hi (x), y (None = not drawn) and tip."""
    h = height
    x0, x1, y0, y1 = ML, W - MR, MT, h - MB

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
        out.append(t(px(v) + 3, y0 - 3, label, "tk" if kind == "ref" else "lab"))
    out.append("</svg>")
    return "".join(out)


LABEL_W = 132


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
            out.append(t(x1 + 6, cy + 4, r["end"], "lab"))
    out.append(f'<line x1="{x0}" x2="{x1}" y1="{bottom}" y2="{bottom}" class="axis"/>')
    out.append("</svg>")
    return "".join(out)


def hbar_chart(rows: list[dict], panels: list[dict], aria: str) -> str:
    """Rows shared by side-by-side panels, each with its own x axis: rows have name, tip and one value per panel."""
    h = 40 + 18 * len(rows)
    out = [svg_open(h, aria)]
    for p in panels:
        a, b = p["x"]
        out.append(t(a, 14, p["header"], "lab"))
        out.append(f'<line x1="{a}" x2="{a}" y1="22" y2="{h - 8}" class="axis"/>')
    for i, r in enumerate(rows):
        y = 26 + 18 * i
        out.append(f"<g>{title(r['tip'])}")
        out.append(t(110, y + 11, r["name"], "lab", "end"))
        for p, v in zip(panels, r["values"], strict=True):
            a, b = p["x"]
            if v is None:
                out.append(t(a + 4, y + 11, "–", "tk"))
                continue
            w = max(v / p["max"] * (b - a - 36), 1)
            out.append(f'<rect x="{a}" y="{y + 2}" width="{w:.1f}" height="12" rx="3" class="{p["cls"]}"/>')
            out.append(t(a + w + 4, y + 12, p["fmt"](v), "tk"))
        out.append(f'<rect x="0" y="{y}" width="{W}" height="18" class="hit"/></g>')
    out.append("</svg>")
    return "".join(out)


def waterfall_chart(steps: list[dict], aria: str) -> str:
    """Horizontal waterfall: steps have label, value (cents), kind 'abs' (from 0) or 'delta', cls."""
    h = 40 + 26 * len(steps)
    x0, x1 = 156, W - MR
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
        lines = wrap(s["label"], 11, 150)
        for j, line in enumerate(lines):
            out.append(t(150, y + 12 + 11 * j - 5.5 * (len(lines) - 1), line, "lab2", "end"))
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


def stacked_hbar(rows: list[dict], segments: list[tuple[str, str, str]], aria: str) -> str:
    """100% bars: rows have label, sub, parts {key: (n, cents)}; segments are (key, name, cls) in order."""
    h = 40 + 30 * len(rows)
    x0, x1 = 120, W - 8
    out = [svg_open(h, aria)]
    for v in (0, 0.25, 0.5, 0.75, 1):
        x = x0 + v * (x1 - x0)
        out.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="8" y2="{h - 30}" class="grid"/>')
        out.append(t(x, h - 16, pct(v, 0), "tk", "middle"))
    out.append(t((x0 + x1) / 2, h - 3, "share of counted orders", "al", "middle"))
    for i, r in enumerate(rows):
        y = 10 + 30 * i
        out.append(t(4, y + 9, r["label"], "lab"))
        out.append(t(4, y + 21, r["sub"], "tk"))
        total = sum(n for n, _ in r["parts"].values()) or 1
        x = x0
        for key, name, cls in segments:
            n, cents = r["parts"].get(key, (0, 0))
            if not n:
                continue
            w = n / total * (x1 - x0)
            tip = f"{name}: {n:,} orders ({pct(n / total)}), {eur(-abs(cents)) if cents else '0 €'}"
            out.append(
                f'<rect x="{x + 1:.1f}" y="{y + 2}" width="{max(w - 2, 0.8):.1f}" height="20" rx="3" '
                f'class="{cls}">{title(tip)}</rect>'
            )
            if w > 40:
                out.append(t(x + w / 2, y + 16, pct(n / total, 0), "inbar", "middle"))
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


def details(rows, columns, summary="Data") -> str:
    return f"<details><summary>{E(summary)}</summary>{table(rows, columns)}</details>"


def muted(s: str) -> str:
    return f'<p class="muted">{E(s)}</p>'


def legend(items: list[tuple[str, str]]) -> str:
    """items: (cls or 'ring:cls' / 'dash', name)."""
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


def card(h3: str, body: str, caption: str = "", legend_html: str = "", data: str = "", wide: bool = False) -> str:
    cap = f'<p class="cap">{E(caption)}</p>' if caption else ""
    cls = "card wide" if wide else "card"
    return f'<div class="{cls}"><h3>{E(h3)}</h3>{body}{legend_html}{cap}{data}</div>'


def section(sid: str, h2: str, lead: str, body: str) -> str:
    return f'<section id="{sid}"><h2>{E(h2)}</h2><p class="lead">{E(lead)}</p>{body}</section>'


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
                if r.get("error") or r.get("ends") == "inverted" or r.get("monotone") is False:
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
                data = oracle.build(db_path, probe_dir)
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


def pct0(v):
    return pct(v, 0)


def win_series(data: list[dict], key: str, groups: list[tuple], width: float, minimum: int) -> list[dict]:
    """groups: (value, name, cls). Points at bin middles from 0.6 to 2.0."""
    out = []
    n_bins = round(1.4 / width)
    for g, name, cls in groups:
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
        out.append({"name": name, "cls": cls, "pts": pts, "rows": by_b})
    return out


def win_table(series: list[dict], width: float) -> str:
    out = []
    for s in series:
        for b, r in sorted(s["rows"].items()):
            out.append([s["name"], f"{b:.1f}–{b + width:.1f}", f"{r['n']:,}", pct(r["win"])])
    return details(out, ["Series", "Quote / list", "Quotes", "Won"])


def win_chart(series, aria, refs=((1.0, "list"),)) -> str:
    return line_chart(
        series,
        x_range=(0.6, 2.0),
        x_ticks=ratio_ticks(),
        x_label="quote / list price",
        y_max=1.0,
        y_ticks=SHARE_TICKS,
        y_fmt=pct0,
        y_label="won",
        refs=refs,
        aria=aria,
    )


def curve_finding(s: dict) -> str:
    drawn = [(x, y) for x, y, _ in s["pts"] if y is not None]
    if len(drawn) < 2:
        return f"{s['name']}: too few quotes to draw"
    (xa, ya), (xb, yb) = drawn[0], drawn[-1]
    return f"{s['name']}: {pct(ya, 0)} won at {xa:.2f} × list, {pct(yb, 0)} at {xb:.2f} × list"


def exp_label(e: dict) -> str:
    return f"{e['experiment']} L{e['level']}"


# ---------------------------------------------------------------- sections


def section_experiments(d: dict) -> str:
    exps = d["experiments"]
    passive = ", ".join(f"L{r['level']} {r['n']}" for r in d["passive"]) or "none"
    if not exps:
        body = muted("No played weeks yet.") + muted(f"Passive weeks (requests only): {passive}.")
        return section(
            "experiments", "1. Experiments: score and on-time share", "No experiment has won an order yet.", body
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
    tbl = table(
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
    # Chart 1a
    groups: dict = {}
    for w in d["weeks"]:
        groups.setdefault((w["experiment"], w["level"]), []).append(w)
    ms = [w["margin_cents"] / 100 for w in d["weeks"]]
    ticks = nice_ticks(min(min(ms), 0), max(max(ms), 0), 5)
    srows = []
    for (exp, lvl), ws in groups.items():
        mean = sum(w["margin_cents"] for w in ws) / len(ws) / 100
        ranked = sum((w["on_time_share"] or 0) >= 0.9 for w in ws)
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
                "mark_tip": f"{exp} L{lvl} mean: {eur(mean * 100)} ({ranked} of {len(ws)} ranked)",
                "end": eur(mean * 100),
            }
        )
    best = max(exps, key=lambda e: e["margin"])
    aria = f"Margin of each played week. Best mean: {exp_label(best)} at {eur(best['margin'])} per week; " + "; ".join(
        f"{exp_label(e)} {eur(e['margin'])}, {e['ranked']} of {e['weeks']} ranked" for e in exps
    )
    chart = strip_chart(
        srows,
        x_range=(ticks[0], ticks[-1]),
        x_ticks=[(v, short_eur(v)) for v in ticks],
        x_label="margin of the week (€); tick and right-hand figure = mean",
        refs=((0, "0", "axis"),),
        aria=aria,
    )
    lvls = sorted({lvl for _, lvl in groups})
    leg = legend(
        [("dot:pt " + LEVEL_CLS.get(lvl, "s4"), f"level {lvl}") for lvl in lvls]
        + [("dot:pt total", "ranked (≥ 90% on time)"), ("ring:total", "not ranked")]
    )
    data_rows = [
        [w["experiment"], w["level"], w["seed"], eur(w["margin_cents"]), pct(w["on_time_share"])] for w in d["weeks"]
    ]
    c = card(
        "Margin of each week",
        chart,
        "One dot per played week. Shape, not colour, says whether the week was ranked.",
        leg,
        details(data_rows, ["Experiment", "Level", "Seed", "Margin", "On time"]),
        wide=True,
    )
    body = tbl + muted(f"Passive weeks (requests only): {passive}.") + grid([c])
    return section(
        "experiments",
        "1. Experiments: score and on-time share",
        "Which experiment and level made or lost how much, and how many of its weeks would have been ranked.",
        body,
    )


def section_dealers(d: dict) -> str:
    sample = ", ".join(f"{r['n']:,} rows at level {r['level']}" for r in d["win_sample"]) or "no rows"
    lead = (
        "How the chance to win falls with the price over the list price; level 8 pays well above list; the week "
        "drifts (trust, the competitor's answer) and one day a week is a price war; what trust is worth."
    )
    note = muted(
        "Only requests where we priced one option: with several priced options the dealer also chooses between them, "
        f"and each option's win share reads about half as high. Sample: {sample}. Points with fewer than 20 quotes "
        "(15 by trust) are not drawn."
    )
    cards = []
    # 2a
    s = win_series(d["win_level"], "level", [(6, "level 6", "s2"), (7, "level 7", "s3"), (8, "level 8", "s1")], 0.1, 20)
    if s:
        aria = "Win share by price over list, by level. " + "; ".join(curve_finding(x) for x in s)
        cards.append(
            card("By level", win_chart(s, aria), "", legend([(x["cls"], x["name"]) for x in s]), win_table(s, 0.1))
        )
    else:
        cards.append(card("By level", muted(NO_DATA)))
    # 2b
    s = win_series(d["win_day"], "day", [(i, DAYS[i], f"q{i + 1}") for i in range(5)], 0.1, 20)
    d["monday_curve"] = next((x for x in s if x["name"] == "Mon"), None)
    if s:
        aria = "Level 8 win share by weekday. " + "; ".join(curve_finding(x) for x in s)
        cards.append(
            card(
                "By weekday, level 8",
                win_chart(s, aria),
                "Later days win at higher prices: dealers trust us more, and the competitor raises its prices for "
                "dealers it keeps winning.",
                legend([(x["cls"], x["name"]) for x in s]),
                win_table(s, 0.1),
            )
        )
    else:
        cards.append(card("By weekday, level 8", muted(NO_DATA)))
    # 2c
    s = win_series(d["win_war"], "g", [(1, "war day (guess)", "s2"), (0, "other days", "s1")], 0.1, 20)
    found = sum(r["n"] for r in d["war_days"] if r["war_day"] is not None)
    total = sum(r["n"] for r in d["war_days"])
    per = ", ".join(f"{DAYS[i]} {next((r['n'] for r in d['war_days'] if r['war_day'] == i), 0)}" for i in range(5))
    war_line = f"War day found in {found} of {total} level 8 weeks: {per}."
    if s:
        aria = "Win share on the guessed price-war day against other days. " + "; ".join(curve_finding(x) for x in s)
        cards.append(
            card(
                "The price-war day, level 8",
                win_chart(s, aria) + muted(war_line),
                "On one day a week the competitor quotes 20% lower. The day is guessed from the win share at "
                "1.0–1.25 × list, so the gap is partly by construction.",
                legend([(x["cls"], x["name"]) for x in s]),
                win_table(s, 0.1),
            )
        )
    else:
        cards.append(card("The price-war day, level 8", muted(NO_DATA) + muted(war_line)))
    # 2d
    s = win_series(
        d["win_trust"],
        "g",
        [(0, "trust 0–2", "q2"), (1, "trust 3–6", "q3"), (2, "trust 7–11", "q4"), (3, "trust 12+", "q5")],
        0.2,
        15,
    )
    if s:
        aria = "Level 8 win share by dealer trust. " + "; ".join(curve_finding(x) for x in s)
        cards.append(
            card(
                "By dealer trust, level 8",
                win_chart(s, aria),
                "Each on-time order raises what its dealer accepts by 1%, up to 25; a late order halves the count. "
                "Bins of 0.2 here.",
                legend([(x["cls"], x["name"]) for x in s]),
                win_table(s, 0.2),
            )
        )
    else:
        cards.append(card("By dealer trust, level 8", muted(NO_DATA)))
    return section("dealers", "2. Dealers: the win curve", lead, note + grid(cards))


def section_probe(d: dict) -> str:
    lead = (
        "The exact price at which a request flips from won to lost in one world (competitor and dealer value as one "
        "number), how that spreads around the list price, and that it agrees with the win curve from our quotes."
    )
    p = d["probes"]
    if not p:
        return section("probe", "3. Probe: where a quote flips", lead, muted(f"No probe rows yet in {d['probe_dir']}."))
    reqs = {(r["level"], r["seed"], r["request"]) for r in p}
    worlds = {(r["level"], r["seed"]) for r in p}
    first = [r for r in p if r["first"]]
    first_flips = sorted(r["flip"] for r in first if r["flip"] is not None)
    med = statistics.median(first_flips) if first_flips else None
    below = sum(1 for r in first if r["ends"] == "false" or (r["flip"] is not None and r["flip"] < 1.0))
    unwinnable = sum(1 for r in p if r["ends"] == "false")
    days = sorted({r["day"] for r in p if r["day"] is not None})
    tiles = [
        (f"{len(reqs):,}", f"probed requests in {len(worlds)} worlds"),
        (f"{med:.2f} × list" if med else "–", "median flip of the first option"),
        (pct(below / len(first), 0) if first else "–", "first options that flip below the list price"),
        (pct(unwinnable / len(p), 0), "options that no price in the range wins"),
    ]
    tiles_html = (
        '<div class="tiles">'
        + "".join(f'<div class="tile"><b>{E(a)}</b><span>{E(b)}</span></div>' for a, b in tiles)
        + "</div>"
    )
    note = muted(
        "The probe's world wins and delivers nothing: these are a world's first answers, with no trust and no "
        f"competitor reaction. Mostly Monday and Tuesday. Days present: {', '.join(DAYS[x] for x in days)}."
    )
    cards = []
    # 3a histogram
    bins = [0] * 24
    outside = 0
    for f in first_flips:
        i = math.floor((f - 0.6) / 0.05 + 1e-9)
        if 0 <= i < 24:
            bins[i] += 1
        else:
            outside += 1
    no_flip = len(first) - len(first_flips)
    ymax_ticks = nice_ticks(0, max(bins) or 1, 4)
    bars = [
        {
            "lo": 0.6 + i * 0.05,
            "hi": 0.65 + i * 0.05,
            "y": n,
            "tip": f"{0.6 + i * 0.05:.2f}–{0.65 + i * 0.05:.2f} × list: {n} requests",
        }
        for i, n in enumerate(bins)
    ]
    refs = [(1.0, "list", "ref")] + ([(med, f"median {med:.2f}", "medline")] if med else [])
    chart = histogram(
        bars,
        x_range=(0.6, 1.8),
        x_ticks=ratio_ticks(0.6, 1.8, 0.2),
        x_label="flip price / list price",
        y_max=ymax_ticks[-1],
        y_ticks=ymax_ticks,
        y_fmt=lambda v: f"{v:g}",
        y_label="requests",
        refs=refs,
        aria=f"Flip price of {len(first_flips)} first options; median {med:.2f} × list." if med else "No flips.",
    )
    cards.append(
        card(
            "Flip price of the first option",
            chart,
            f"{len(first_flips)} first options with a flip. Left out: {no_flip} that no price wins and {outside} "
            "outside 0.6–1.8 × list.",
            "",
            details([[f"{b['lo']:.2f}–{b['hi']:.2f}", b["y"]] for b in bars], ["Flip / list", "Requests"]),
        )
    )
    # 3b strip by option
    srows, trs = [], []
    for k, opt in enumerate(["same_day", "next_day", "within_3_days"]):
        fl = [r["flip"] for r in p if r["option"] == opt and r["flip"] is not None]
        if not fl:
            continue
        m = statistics.median(fl)
        trs.append([opt, len(fl), f2(m), f2(sum(fl) / len(fl)), sum(1 for f in fl if f < 0.6 or f > 1.8)])
        srows.append(
            {
                "label": opt,
                "sub": f"median {m:.2f}",
                "dots": [
                    (f, True, "s3", zlib.crc32(f"{opt}{i}".encode()) % 13 - 6, f"{opt}: flip at {f:.2f} × list")
                    for i, f in enumerate(fl)
                ],
                "mark": m,
                "mark_tip": f"{opt} median {m:.2f} × list",
                "end": f"n = {len(fl)}",
            }
        )
    if srows:
        chart = strip_chart(
            srows,
            x_range=(0.6, 1.8),
            x_ticks=ratio_ticks(0.6, 1.8, 0.2),
            x_label="flip price / list price (values outside are drawn at the edge)",
            refs=((1.0, "list", "ref"),),
            aria="Flip price by delivery option; medians "
            + ", ".join(f"{r['label']} {r['mark']:.2f}" for r in srows)
            + " × list.",
            height=60 + 36 * len(srows),
        )
        cards.append(
            card(
                "Flip by delivery option",
                chart,
                "Each option against its own list price. Slower options flip lower: the dealer pays for speed. "
                "The tick is the median.",
                "",
                details(trs, ["Option", "Options with a flip", "Median", "Mean", "Outside 0.6–1.8"]),
            )
        )
    # 3c probe against Monday quotes
    mon = [r for r in first if r["level"] == 8 and r["day"] == 0]
    if mon:
        pts = []
        for i in range(14):
            x = 0.65 + i * 0.1
            won = sum(1 for r in mon if r["ends"] == "true" or (r["flip"] is not None and r["flip"] >= x))
            pts.append(
                (x, won / len(mon), f"probe, {x:.2f} × list: {pct(won / len(mon), 0)} would win ({len(mon)} requests)")
            )
        series = [{"name": "probe", "cls": "s3", "pts": pts}]
        if d.get("monday_curve"):
            series.append({**d["monday_curve"], "name": "our quotes", "cls": "s1"})
        aria = "Probe flips against the Monday win curve at level 8. " + "; ".join(curve_finding(x) for x in series)
        cards.append(
            card(
                "Probe against our quotes, level 8 Mondays",
                win_chart(series, aria),
                f"The same curve from two sources: exact flips in a few worlds ({len(mon)} Monday first options), "
                "and one-option quotes in all Monday data.",
                legend([(x["cls"], x["name"]) for x in series]),
                details(
                    [[f2(x), pct(y)] for x, y, _ in pts],
                    ["Quote / list", "Probe: share that wins"],
                ),
            )
        )
    return section("probe", "3. Probe: where a quote flips", lead, tiles_html + note + grid(cards))


def rate(r) -> float | None:
    return 60.0 * r["booked"] / r["minutes"] if r and r["minutes"] else None


def section_drivers(d: dict) -> str:
    lead = (
        "How fast a gig books at a fee over the typical fee (in a shortage the typical fee does not find a driver "
        "quickly), and how the last hours before lastPickupAt change it."
    )
    note = muted(
        "A rate, not a share: bookings divided by the daytime hours (07–23) that gigs stood open at that fee. "
        "Only weeks with an action log."
    )
    cards = []
    # 4a
    groups = [(6, "level 6", "s2"), (7, "level 7", "s3"), (8, "level 8", "s1")]
    series, trs, ymax = [], [], 0.0
    for lvl, name, cls in groups:
        by = {round(r["b"], 2): r for r in d["book_fee"] if r["level"] == lvl}
        if not by:
            continue
        pts = []
        for i in range(12):
            b = round(0.2 + 0.2 * i, 2)
            r = by.get(b)
            ok = r and r["minutes"] >= 3000
            v = rate(r) if ok else None
            if v is not None:
                ymax = max(ymax, v)
            tip = (
                f"{name}, {b:.1f}–{b + 0.2:.1f} × typical: {v:.2f} bookings per open hour "
                f"({r['booked']} in {r['minutes'] / 60:,.0f} h)"
                if ok
                else ""
            )
            pts.append((b + 0.1, v, tip))
            if r:
                trs.append(
                    [name, f"{b:.1f}–{b + 0.2:.1f}", r["spells"], r["booked"], num(r["minutes"] / 60), f2(rate(r))]
                )
        series.append({"name": name, "cls": cls, "pts": pts})
    if series and ymax > 0:
        yt = nice_ticks(0, ymax, 4)
        chart = line_chart(
            series,
            x_range=(0.2, 2.6),
            x_ticks=ratio_ticks(0.2, 2.6, 0.4),
            x_label="fee / typical fee",
            y_max=yt[-1],
            y_ticks=yt,
            y_fmt=lambda v: f"{v:g}",
            y_label="bookings per open hour",
            refs=((1.0, "typical fee"),),
            aria="Bookings per open daytime hour by fee over the typical fee. "
            + "; ".join(
                f"{s['name']}: highest {max(y for _, y, _ in s['pts'] if y is not None):.2f} per hour"
                for s in series
                if any(y is not None for _, y, _ in s["pts"])
            ),
        )
        cards.append(
            card(
                "By fee over the typical fee",
                chart,
                "Points with less than 50 open hours are not drawn.",
                legend([(s["cls"], s["name"]) for s in series]),
                details(trs, ["Series", "Fee / typical", "Spells", "Booked", "Open hours", "Per hour"]),
            )
        )
    else:
        cards.append(card("By fee over the typical fee", muted("No gigs with an action log at this level yet.")))
    # 4b
    labels = ["48 h+", "24–48 h", "12–24 h", "6–12 h", "3–6 h", "0–3 h", "late"]  # left to right: k 6 … 0
    bands = [(0, "below 0.9", "q2"), (1, "0.9–1.3", "q3"), (2, "1.3 and up", "q5")]
    series, trs, ymax = [], [], 0.0
    for band, name, cls in bands:
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
                f"fee {name}, {labels[pos]} left: {v:.2f} bookings per open hour ({r['minutes'] / 60:,.0f} h)"
                if ok
                else ""
            )
            pts.append((pos, v, tip))
            if r:
                trs.append([name, labels[pos], r["spells"], r["booked"], num(r["minutes"] / 60), f2(rate(r))])
        series.append({"name": name, "cls": cls, "pts": pts})
    if series and ymax > 0:
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
                "By hours to the last pickup time, level 8",
                chart,
                "The deadline warning comes at 3 hours; after that only a higher fee finds a driver. Lines are fee "
                "bands (fee / typical fee); points with less than 25 open hours are not drawn.",
                legend([(s["cls"], "fee " + s["name"]) for s in series]),
                details(trs, ["Fee band", "Time left", "Spells", "Booked", "Open hours", "Per hour"]),
            )
        )
    else:
        cards.append(
            card("By hours to the last pickup time, level 8", muted("No level 8 gigs with an action log yet."))
        )
    # 4c
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
        bars.append({"lo": lo, "hi": lo + 0.2, "y": share if len(ms) >= 20 else None, "tip": tip})
        trs.append([f"{lo:.1f}–{lo + 0.2:.1f}", len(ms), within, pct(share), med_s])
    if bars:
        chart = histogram(
            bars,
            x_range=(0.2, 1.8),
            x_ticks=ratio_ticks(0.2, 1.8, 0.2),
            x_label="opening fee / typical fee",
            y_max=1.0,
            y_ticks=SHARE_TICKS,
            y_fmt=pct0,
            y_label="booked within a day",
            refs=((1.0, "typical fee", "ref"),),
            aria="Share of level 8 gigs booked within a day of posting, by opening fee: "
            + ", ".join(f"{b['lo']:.1f} {pct(b['y'], 0)}" for b in bars if b["y"] is not None),
            cls="s1",
        )
        cards.append(
            card(
                "Share of gigs booked within a day of posting, by opening fee",
                chart,
                "Level 8, gigs with an action log; bars with fewer than 20 gigs are not drawn. The plain reading that "
                "the rate does not give.",
                "",
                details(
                    trs, ["Opening fee / typical", "Gigs", "Booked within a day", "Share", "Median time to booking"]
                ),
            )
        )
    else:
        cards.append(
            card("Share of gigs booked within a day of posting, by opening fee", muted("No level 8 gigs yet."))
        )
    return section("drivers", "4. Drivers: the booking curve", lead, note + grid(cards))


def section_supply(d: dict) -> str:
    lead = "Where the drivers live in a shortage world and where gigs actually get booked."
    towns = sorted(d["towns"], key=lambda r: -(r["drivers_home"] or 0))
    if not towns:
        return section("supply", "5. Supply by town", lead, muted("No level 8 weeks with gigs yet."))
    weeks = d["town_weeks"] or 1
    rws, trs = [], []
    for r in towns:
        share = r["booked_share"] if (r["gigs_open"] or 0) >= 20 else None
        ratio = f" at {r['booked_ratio']:.2f} × typical fee" if r["booked_ratio"] is not None else ""
        tip = (
            f"{r['name']}: {r['drivers_home']:.1f} drivers at home ({r['drivers_near']:.1f} within 30 km), "
            f"{r['requests']:,} requests, "
            + (f"{pct(share, 0)} of gig-days booked{ratio}" if share is not None else f"{r['gigs_open']} gig-days")
        )
        rws.append({"name": r["name"], "tip": tip, "values": [r["drivers_home"], share]})
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
    top = max(r["drivers_home"] or 0 for r in towns) or 1
    chart = hbar_chart(
        rws,
        [
            {
                "x": (115, 290),
                "header": "drivers at home (mean per day)",
                "cls": "s1",
                "max": top,
                "fmt": lambda v: f"{v:.1f}",
            },
            {"x": (310, 470), "header": "gig-days booked", "cls": "s3", "max": 1.0, "fmt": pct0},
        ],
        aria=f"Level 8 towns by drivers living there: most in {towns[0]['name']} ({towns[0]['drivers_home']:.1f}); "
        f"booked share of gig-days shown beside it for {sum(1 for r in rws if r['values'][1] is not None)} towns.",
    )
    c = card(
        "Drivers at home and booked share by town, level 8",
        chart,
        "A gig-day is one gig open on one day. Level 8 moves drivers between towns in every world, so this is the "
        f"average world over {weeks} weeks (business days); the spread is in the table. – = fewer than 20 gig-days.",
        legend([("s1", "drivers at home"), ("s3", "share of gig-days booked")]),
        details(
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
        wide=True,
    )
    return section("supply", "5. Supply by town", lead, grid([c]))


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


def account_chart(vals: dict, name: str) -> str:
    steps = [{"label": "Revenue", "value": vals["revenue"], "kind": "abs", "cls": "s1"}]
    for k, label in ACCOUNT[1:]:
        steps.append({"label": label, "value": vals[k], "kind": "delta", "cls": "s2"})
    steps.append({"label": "Margin", "value": vals["margin"], "kind": "abs", "cls": "total"})
    aria = f"{name}, mean week: revenue {eur(vals['revenue'])}, driver fees {eur(vals['driver_fee'])}, margin {eur(vals['margin'])}."
    return waterfall_chart(steps, aria)


def section_economics(d: dict) -> str:
    lead = (
        "Where a week's margin goes, and how much each perfect decision would have kept (mean week of each experiment)."
    )
    o = d["oracle"]
    note = ""
    if d["oracle_note"]:
        note += muted(d["oracle_note"])
    if not d["accounts"]:
        return section(
            "economics", "6. Order economics: the oracle's gap waterfall", lead, note + muted("No played weeks yet.")
        )
    cards = []
    oexp = {(e["experiment"], e["level"]): e for e in (o or {}).get("experiments", [])}
    oweeks = (o or {}).get("weeks", [])
    assumptions = (o or {}).get("assumptions", {})
    trs = []
    for a in d["accounts"]:
        name = f"{a['experiment']} L{a['level']}"
        e = oexp.get((a["experiment"], a["level"]))
        if e:
            vals = {k: pw(e, k) for k, _ in ACCOUNT if k != "handling"}
            vals["handling"] = sum(pw(e, k) for k in ("failed_visit", "waiting", "release_fee", "fine", "other"))
            vals["margin"] = pw(e, "margin")
        else:
            vals = {
                k: a[k] for k in ("revenue", "driver_fee", "late_refund", "undelivered_penalty", "handling", "margin")
            }
        body = f"<h4>Where the money went (mean week)</h4>{account_chart(vals, name)}"
        if e:
            q = e.get("quote") or {}
            wp, wb = q.get("weeks_probe") or 0, q.get("weeks_brackets") or 0
            src = f"(probe, {wp} of {e['weeks']} weeks)" if wp else "(estimate)" if wb else "(none)"
            gains = [
                ("+ Perfect accept/decline", pw(e, "selection")),
                ("+ All on time", pw(e, "delivery")),
                ("+ Lowest comparable fees", pw(e, "fee")),
                (f"+ Quotes at the flip {src}", pw(e, "quote")),
            ]
            steps = [{"label": "Margin", "value": pw(e, "margin"), "kind": "abs", "cls": "total"}]
            steps += [{"label": lab, "value": v, "kind": "delta", "cls": "s1"} for lab, v in gains]
            steps.append({"label": "Oracle", "value": pw(e, "oracle"), "kind": "abs", "cls": "total"})
            aria = f"{name}: margin {eur(pw(e, 'margin'))} per week, oracle {eur(pw(e, 'oracle'))}; " + ", ".join(
                f"{lab} {eur(v)}" for lab, v in gains
            )
            body += f"<h4>What a perfect dispatcher keeps (mean week, upper bounds)</h4>{waterfall_chart(steps, aria)}"
            items = "".join(
                f"<li><b>{E(k)}</b>: {E(str(v))}</li>"
                for k, v in assumptions.items()
                if k in ("selection", "delivery", "fee")
                or (k == "quote_probe" and wp)
                or (k == "quote_brackets" and wb)
            )
            body += muted(
                "Upper bounds, each under its assumptions; they add up without overlap. See analysis/README.md."
            )
            if items:
                body += f'<ul class="small">{items}</ul>'
            sp = e.get("split") or {}
            cb = e.get("combining") or {}
            weeks = e.get("weeks") or 1
            body += muted(
                f"Split as in the brief (mean week): quoting {eur((sp.get('quoting_cents') or 0) / weeks)}, driver fees "
                f"{eur((sp.get('driver_fees_cents') or 0) / weeks)}, delivery {eur((sp.get('delivery_cents') or 0) / weeks)}; "
                "car combining not measurable (no gig with two orders yet; "
                f"{cb.get('candidates', 0):,} candidate orders)."
            )
            ids = set(e.get("week_ids") or [])
            both = [
                w
                for w in oweeks
                if w.get("week_id") in ids
                and (w.get("quote") or {}).get("probe")
                and ((w.get("quote") or {}).get("brackets") or {}).get("estimate")
            ]
            if both:
                pr = sum(w["quote"]["probe"].get("week_gain_cents", 0) for w in both) / len(both)
                es = sum(w["quote"]["brackets"]["estimate"].get("week_gain_cents", 0) for w in both) / len(both)
                body += muted(
                    f"Quote side on probed weeks ({len(both)}): probe {eur(pr)}, estimate {eur(es)} per week."
                )
            br = q.get("brackets") or {}
            lbs = br.get("lost_below_similar") or {}
            trs.append(
                [
                    a["experiment"],
                    a["level"],
                    e["weeks"],
                    eur(pw(e, "margin")),
                    eur_signed(pw(e, "selection")),
                    eur_signed(pw(e, "delivery")),
                    eur_signed(pw(e, "fee")),
                    f"{eur_signed(pw(e, 'quote'))} ({q.get('source') or 'none'})",
                    eur(pw(e, "oracle")),
                    eur(pw(e, "gap")),
                    f"{num((br.get('lost_requests') or 0) / weeks)} ({eur((br.get('lost_ceiling_cents') or 0) / weeks)})",
                    f"{num((lbs.get('requests') or 0) / weeks)} ({eur((lbs.get('revenue_cents') or 0) / weeks)})",
                ]
            )
        else:
            body += muted("Run uv run python -m analysis.oracle for the gap bounds.")
        leg = legend([("s1", "revenue / gains"), ("s2", "costs"), ("total", "totals")])
        cards.append(f'<div class="card"><h3>{E(name)} · {a["weeks"]} weeks</h3>{body}{leg}</div>')
    tbl = ""
    if trs:
        tbl = "<h3>All experiments, per week</h3>" + table(
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
        )
    return section("economics", "6. Order economics: the oracle's gap waterfall", lead, note + grid(cards) + tbl)


BUCKETS = [
    ("on_time", "on time", "s1"),
    ("le_2h", "up to 2 h", "s4"),
    ("le_24h", "2–24 h", "o1"),
    ("le_2bd", "to 2 business days", "o2"),
    ("gt_2bd", "longer", "o3"),
    ("undelivered", "undelivered", "total"),
]


def section_on_time(d: dict) -> str:
    lead = "Which weeks clear the 90% delivery minimum and how the late orders split."
    if not d["weeks"]:
        return section("on-time", "7. On time", lead, muted("No played weeks yet."))
    groups: dict = {}
    for w in d["weeks"]:
        groups.setdefault((w["experiment"], w["level"]), []).append(w)
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
        srows.append({"label": exp, "sub": f"L{lvl} · ranked {ranked} of {len(ws)}", "dots": dots})
    ttl = "On-time share of each week" + (f" ({clamped} weeks below 60% drawn at 60%)" if clamped else "")
    chart = strip_chart(
        srows,
        x_range=(0.6, 1.0),
        x_ticks=[(v / 100, f"{v}%") for v in range(60, 101, 10)],
        x_label="on-time share of counted orders",
        refs=((0.9, "minimum", "ref"),),
        aria="On-time share of each played week against the 90% minimum. "
        + "; ".join(f"{r['label']} {r['sub']}" for r in srows),
    )
    lvls = sorted({lvl for _, lvl in groups})
    c1 = card(
        ttl,
        chart,
        "A week below 90% on time is not ranked, whatever its margin.",
        legend(
            [("dot:pt " + LEVEL_CLS.get(lvl, "s4"), f"level {lvl}") for lvl in lvls]
            + [("dot:pt total", "ranked (≥ 90% on time)"), ("ring:total", "not ranked")]
        ),
    )
    # 7b
    parts: dict = {}
    for r in d["late"]:
        parts.setdefault((r["experiment"], r["level"]), {})[r["late_bucket"]] = (r["n"], r["cents"] or 0)
    srows2, trs2 = [], []
    for (exp, lvl), pp in sorted(parts.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        tot = sum(n for n, _ in pp.values())
        srows2.append({"label": exp, "sub": f"L{lvl} · {tot:,} orders", "parts": pp})
        for key, name, _ in BUCKETS:
            n, cents = pp.get(key, (0, 0))
            trs2.append([f"{exp} L{lvl}", name, n, pct(n / tot if tot else 0), eur(cents)])
    if srows2:
        aria = "Counted orders by lateness: " + "; ".join(
            f"{r['label']} {r['sub']}, {pct(r['parts'].get('on_time', (0, 0))[0] / max(sum(n for n, _ in r['parts'].values()), 1))} on time"
            for r in srows2
        )
        c2 = card(
            "Counted orders by lateness",
            stacked_hbar(srows2, BUCKETS, aria),
            "Hover a segment for its orders and what the refunds and penalties cost.",
            legend(
                [
                    ("s1", "on time"),
                    ("s4", "up to 2 h (10% back)"),
                    ("o1", "2–24 h (25%)"),
                    ("o2", "to 2 business days (50%)"),
                    ("o3", "longer (100%)"),
                    ("total", "undelivered (penalty 2 × price)"),
                ]
            ),
            details(trs2, ["Experiment", "Lateness", "Orders", "Share", "Refund or penalty"]),
        )
    else:
        c2 = card("Counted orders by lateness", muted("No counted orders yet."))
    trs = [
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
    tbl = table(
        trs,
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
    )
    return section("on-time", "7. On time", lead, grid([c1, c2]) + tbl)


# ---------------------------------------------------------------- page

CSS = """
:root{--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--q1:#86b6ef;--q2:#5598e7;--q3:#2a78d6;--q4:#1c5cab;--q5:#0d366b;
--o1:#f2a27f;--o2:#eb6834;--o3:#a84318;--total:#52514e}
@media (prefers-color-scheme: dark){:root{--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;
--muted:#898781;--grid:#2c2c2a;--axis:#383835;--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;
--q1:#cde2fb;--q2:#9ec5f4;--q3:#6da7ec;--q4:#3987e5;--q5:#184f95;--total:#c3c2b7}}
*{box-sizing:border-box}
html{color-scheme:light dark}
body{max-width:1040px;margin:0 auto;padding:16px;font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;
background:var(--page);color:var(--ink);overflow-wrap:anywhere}
h1{font-size:26px;margin:8px 0}h2{font-size:21px;margin:40px 0 4px}h3{font-size:15px;margin:0 0 8px}
h4{font-size:13px;margin:12px 0 4px;color:var(--ink2)}
nav{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:14px}a{color:var(--s1)}
.lead{color:var(--ink2);margin:0 0 12px}.muted{color:var(--muted);font-size:14px;margin:8px 0}
.cap{color:var(--ink2);font-size:13px;margin:6px 0 0}.small{font-size:13px;color:var(--ink2);padding-left:18px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,330px),1fr));gap:16px;margin:12px 0}
.card{background:var(--surface);border:1px solid var(--grid);border-radius:8px;padding:12px;min-width:0}
.card.wide{grid-column:1/-1}
.card.wide svg{max-width:640px;margin:0 auto}
.legend{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:13px;color:var(--ink2);margin-top:6px}
.legend span{display:inline-flex;align-items:center;gap:5px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,200px),1fr));gap:16px;margin:12px 0}
.tile{background:var(--surface);border:1px solid var(--grid);border-radius:8px;padding:12px}
.tile b{display:block;font-size:28px;line-height:1.2;font-variant-numeric:tabular-nums}
.tile span{color:var(--ink2);font-size:14px}
details{margin-top:8px;font-size:14px}summary{cursor:pointer;color:var(--ink2)}
table{border-collapse:collapse;font-size:14px;background:var(--surface);margin:8px 0}
th{color:var(--ink2);font-weight:600;text-align:left;border-bottom:1px solid var(--axis);padding:4px 8px;white-space:nowrap}
td{padding:3px 8px;border-bottom:1px solid var(--grid);white-space:nowrap}
td.n{text-align:right;font-variant-numeric:tabular-nums}
svg{display:block;overflow:visible}
svg text{fill:var(--ink)}
.tl,.lab{font-size:12px;fill:var(--ink2)}.lab2{font-size:11px;fill:var(--ink2)}
.tk{font-size:11px;fill:var(--muted)}.al{font-size:12px;fill:var(--muted)}
.inbar{font-size:11px;fill:var(--surface);font-weight:600}

line.grid{stroke:var(--grid)}.axis{stroke:var(--axis);stroke-width:1}
.sep{stroke:var(--grid);stroke-width:1;stroke-dasharray:2 3}
.ref{stroke:var(--axis);stroke-width:1.5;stroke-dasharray:4 3}
.medline{stroke:var(--ink2);stroke-width:1.5}
.mark{stroke:var(--ink);stroke-width:2}
.conn{stroke:var(--muted);stroke-width:1;stroke-dasharray:2 2}
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
    ("supply", "Supply"),
    ("economics", "Economics"),
    ("on-time", "On time"),
]


def page(sections: list[str], d: dict | None = None) -> str:
    d = d or {}
    tot = d.get("totals", {})
    head = (
        f"Built {d.get('built', '')} from {os.path.basename(d.get('db', ''))}: {tot.get('played') or 0} played weeks, "
        f"{tot.get('passive') or 0} passive weeks, {tot.get('requests') or 0:,} requests, {tot.get('quoted') or 0:,} "
        f"quotes, {tot.get('orders') or 0:,} orders."
    )
    nav = "".join(f'<a href="#{sid}">{i}. {E(n)}</a>' for i, (sid, n) in enumerate(SECTIONS, 1))
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta name="color-scheme" content="light dark">'
        f"<title>Spread weeks: overview</title><style>{CSS}</style></head><body>"
        f'<header><h1>Spread weeks: overview</h1><p class="lead">{E(head)}</p><nav>{nav}</nav></header>'
        + "".join(sections)
        + "</body></html>"
    )


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Write one HTML page with the whole picture of the scraped weeks.")
    ap.add_argument("--db", default="out/spread.sqlite")
    ap.add_argument("--probe", default="out/probe")
    ap.add_argument("--oracle", default="out/oracle.json")
    ap.add_argument("--out", default="out/report.html")
    args = ap.parse_args(argv)
    if not os.path.exists(args.db):
        sys.exit(f"No database at {args.db}.")
    d = load(args.db, args.probe, args.oracle)
    sections = [
        section_experiments(d),
        section_dealers(d),
        section_probe(d),
        section_drivers(d),
        section_supply(d),
        section_economics(d),
        section_on_time(d),
    ]
    text = page(sections, d)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(text)
    reqs = len({(r["level"], r["seed"], r["request"]) for r in d["probes"]})
    print(
        f"Wrote {args.out} ({len(text.encode()) // 1024} kB): {d['totals']['weeks'] or 0} weeks, "
        f"{len(d['experiments'])} experiments, {reqs} probed requests."
    )


if __name__ == "__main__":
    main()
