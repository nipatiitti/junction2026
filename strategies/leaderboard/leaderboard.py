"""The leaderboard: plays every strategy as a live practice week on the server and draws one bar chart of the margins.

Every result comes from the server: the tool never reads the saved weeks of out/spread.sqlite. It keeps its own
online results in strategies/leaderboard/results/, each with a fingerprint of the strategy's code (the entry file and
every file of this repository that it imports). A strategy is played again only when it is new or its fingerprint has
changed, so adding or changing one strategy does not replay the others. See strategies/leaderboard/README.md.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import html
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from spread.client import SpreadError

from strategies.bench.bench import Bench, RunFailed, Stopped, Version, euros
from tools.spread_proxy import ProxyClient

ROOT = Path(__file__).resolve().parents[2]
RESULTS = Path(__file__).resolve().parent / "results"
DEFAULT_SEED = "spread-1"
DEFAULT_JOBS = 4  # the team shares 8 practice slots: leave half for teammates
# Entry files that are not called dispatch.py. Every strategies/<folder>/dispatch.py is found on its own.
OTHER_ENTRIES = [
    "strategies/baseline/baseline.py",
    "strategies/baseline_ladder/baseline_ladder.py",
    "strategies/baseline_tiers/baseline_tiers.py",
    "strategies/admission_scenarios/capacity.py",
    "strategies/admission_scenarios/cost.py",
    "strategies/admission_scenarios/both.py",
]
# Strategies and their fingerprints

TS_DISPATCH = ROOT / "src" / "dispatch.ts"
TS_REGISTRY = ROOT / "src" / "strategies" / "index.ts"
CODE_SUFFIXES = {".py", ".ts"}
LANGUAGES = ("python", "typescript")
SKIP_SUFFIXES = {".md", ".pyc"}
TS_IMPORT = re.compile(r"""(?:\bfrom|\bimport)\s*\(?\s*['"](\.{1,2}/[^'"]+)['"]""")
TS_URL = re.compile(r"""new URL\(\s*['"](\.{1,2}/[^'"]+)['"]""")


@dataclass
class Entry:
    """One strategy: how to play a week of it (`version`), and where the scan of its code starts (`roots`)."""

    version: Version
    roots: list[Path]
    language: str  # python or typescript
    hashed: list[Path] = field(default_factory=list)  # files hashed as they are, without following their imports

    def command_line(self) -> str:
        return " ".join([str(self.version.file.relative_to(ROOT)), *self.version.args])


def python_entries() -> dict[str, Entry]:
    found = {"dispatch.py": ROOT / "dispatch.py"}
    for file in sorted(ROOT.glob("strategies/*/dispatch.py")):
        found[file.parent.name] = file
    for name in OTHER_ENTRIES:
        file = ROOT / name
        if file.is_file():
            label = file.parent.name if file.stem == file.parent.name or file.stem == "baseline" else name[11:-3]
            found[label] = file
    return {label: Entry(Version(label, file), [file], "python") for label, file in found.items()}


def typescript_entries() -> dict[str, Entry]:
    """Every strategy of the TypeScript registry, src/strategies/index.ts, as ts:<name>. A week is
    `node src/dispatch.ts --strategy <name>`. A strategy's code is the harness (src/dispatch.ts and what it imports)
    and its own folder with what that imports, but not the other strategies that the registry imports, so a change
    to one TypeScript strategy does not replay the others."""
    if not TS_REGISTRY.is_file() or not TS_DISPATCH.is_file():
        return {}
    text = TS_REGISTRY.read_text()
    block = re.search(r"STRATEGIES[^=]*=\s*\{(.*?)\n\}", text, re.DOTALL)
    if block is None:
        return {}
    names = re.findall(r"^\s*(\w+)\s*[,:]", block[1], re.MULTILINE)
    folders = {name: folder for name, folder in re.findall(r"import \{ (\w+) \} from '\./(\w+)/index\.ts'", text)}
    found = {}
    for name in names:
        if name in folders:
            roots, hashed = [TS_REGISTRY.parent / folders[name] / "index.ts"], []
        else:  # a variant defined in the registry, such as bidboard: the strategies it names, and the registry itself
            line = re.search(rf"^const {name}\b.*$", text, re.MULTILINE)
            used = set(re.findall(r"\w+", line[0])) if line else set()
            roots = [TS_REGISTRY.parent / folders[other] / "index.ts" for other in sorted(used & folders.keys())]
            hashed = [TS_REGISTRY]
        label = f"ts:{name}"
        version = Version(label, TS_DISPATCH, args=("--strategy", name))
        found[label] = Entry(version, [TS_DISPATCH, *roots], "typescript", hashed)
    return found


def entries() -> dict[str, Entry]:
    """Every strategy, Python and TypeScript: its label, and how to play it."""
    return dict(sorted({**python_entries(), **typescript_entries()}.items()))


def module_file(name: str, near: Path) -> Path | None:
    """The file of this repository that holds a module, or None for the standard library and the packages."""
    parts = name.split(".")
    for base in (ROOT, near):
        stem = base.joinpath(*parts)
        for candidate in (stem.with_suffix(".py"), stem / "__init__.py"):
            if not candidate.is_file() or ".venv" in candidate.parts or "vendor" in candidate.parts:
                continue
            if exact(candidate):
                return candidate
    return None


def exact(file: Path) -> bool:
    """Whether the path's last two names are spelled as on disk, also on a case-insensitive disk (macOS), so every
    machine gets the same fingerprint."""
    return all(part.name in os.listdir(part.parent) for part in (file, file.parent))


def python_imports(file: Path) -> set[Path]:
    """The files of this repository that one Python file imports directly."""
    try:
        tree = ast.parse(file.read_text(), filename=str(file))
    except SyntaxError:
        return set()
    package = file.parent
    found: set[Path] = set()
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative: from . import x, from .fees import y
                base = package
                for _ in range(node.level - 1):
                    base = base.parent
                prefix = ".".join(base.relative_to(ROOT).parts)
                module = f"{prefix}.{node.module}" if node.module else prefix
            else:
                module = node.module or ""
            names = [module, *(f"{module}.{alias.name}" for alias in node.names)]
        for name in names:
            # Each package on the way in runs its __init__.py too.
            parts = name.split(".")
            for end in range(1, len(parts) + 1):
                target = module_file(".".join(parts[:end]), package)
                if target is not None:
                    found.add(target)
    return found


def typescript_imports(file: Path) -> set[Path]:
    """The files of this repository that one TypeScript file imports by a relative path, or reads with
    `new URL('./x.json', import.meta.url)`. The vendored kit and the strategy registry are not followed."""
    text = file.read_text()
    found: set[Path] = set()
    for spec in TS_IMPORT.findall(text) + TS_URL.findall(text):
        target = (file.parent / spec).resolve()
        if not target.is_file() or "vendor" in target.parts or target == TS_REGISTRY or not exact(target):
            continue
        found.add(target)
    return found


def code_files(entry: Entry) -> list[Path]:
    """The entry's files and every file of this repository that they import, directly or not, with the data files
    (anything but code and .md) in the folders of those modules under strategies/."""
    seen: set[Path] = set()
    todo = list(entry.roots)
    while todo:
        file = todo.pop()
        if file in seen:
            continue
        seen.add(file)
        if file.suffix == ".py":
            todo += python_imports(file) - seen
        elif file.suffix == ".ts":
            todo += typescript_imports(file) - seen
    data: set[Path] = set()
    for file in seen:
        if file.suffix in CODE_SUFFIXES and "strategies" in file.relative_to(ROOT).parts:
            data |= {
                other
                for other in file.parent.iterdir()
                if other.is_file() and other.suffix not in CODE_SUFFIXES and other.suffix not in SKIP_SUFFIXES
            }
    return sorted(seen | data | set(entry.hashed))


def fingerprint(entry: Entry) -> str:
    digest = hashlib.sha256()
    for file in code_files(entry):
        digest.update(str(file.relative_to(ROOT)).encode())
        digest.update(b"\0")
        digest.update(file.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:16]


# Results


def results_path(level: int, seed: str) -> Path:
    return RESULTS / f"L{level}-{seed}.json"


def load(level: int, seed: str) -> dict[str, dict]:
    path = results_path(level, seed)
    if not path.is_file():
        return {}
    return json.loads(path.read_text())["strategies"]


def save(level: int, seed: str, results: dict[str, dict]) -> None:
    path = results_path(level, seed)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"level": level, "seed": seed, "strategies": dict(sorted(results.items()))}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(body, indent=2) + "\n")
    tmp.replace(path)


# Playing


def play(todo: dict[str, tuple[Entry, str]], results: dict[str, dict], level: int, seed: str, jobs: int) -> list[str]:
    """Plays one week of each strategy in `todo`, at most `jobs` at once, and saves each result as it ends.
    Returns the strategies that failed; a failure does not stop the others."""
    bench = Bench([], [seed], level, jobs)
    lock = threading.Lock()
    failed: list[str] = []
    print(f"Playing {len(todo)} practice weeks at level {level}, seed {seed}, {jobs} at a time.", flush=True)

    def one(label: str, entry: Entry, print_: str) -> None:
        result = bench.play_one(entry.version, seed)
        with lock:
            results[label] = {
                "file": entry.command_line(),
                "fingerprint": print_,
                "world_id": result.world_id,
                "played_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "score": dict(result.score),
            }
            save(level, seed, results)

    pool = ThreadPoolExecutor(max_workers=jobs)
    futures = {pool.submit(one, label, entry, print_): label for label, (entry, print_) in todo.items()}
    try:
        for future in as_completed(futures):
            label = futures[future]
            error = future.exception()
            if error is None or isinstance(error, Stopped):
                continue
            failed.append(label)
            print(f"{seed:<12} {label}: FAILED. {error}", file=sys.stderr, flush=True)
    except KeyboardInterrupt:
        bench.stop(pool, interrupted=True)
        raise
    pool.shutdown()
    return sorted(failed)


# The chart


def rows(results: dict[str, dict], current: dict[str, str]) -> list[dict]:
    """One row per strategy that still exists, best margin first. `stale`: its code changed since it was played."""
    out = []
    for label, entry in results.items():
        if label not in current:
            continue
        score = entry["score"]
        out.append(
            {
                "label": label,
                "margin": score["marginCents"],
                "orders": score["wonOrders"],
                "on_time": score["onTimeShare"],
                "undelivered": score["undeliveredShare"],
                "ranked": bool(score["ranked"]),
                "world": entry["world_id"],
                "played": entry["played_at"],
                "stale": entry["fingerprint"] != current[label],
            }
        )
    return sorted(out, key=lambda row: -row["margin"])


def table(chart_rows: list[dict]) -> str:
    header = f"{'#':>3}  {'Strategy':<28} {'Margin':>14} {'Orders':>7} {'On time':>8}  Ranked"
    lines = [header]
    for n, row in enumerate(chart_rows, 1):
        note = "  (code changed since)" if row["stale"] else ""
        lines.append(
            f"{n:>3}  {row['label']:<28} {euros(row['margin']):>14} {row['orders']:>7,} {row['on_time']:>8.1%}  "
            f"{'yes' if row['ranked'] else 'no'}{note}"
        )
    return "\n".join(lines)


STYLE = """
:root { color-scheme: light; --surface:#fcfcfb; --surface-2:#f3f2ef; --text:#0b0b0b; --text-2:#52514e;
  --muted:#8a8984; --grid:#e4e3df; --ranked:#2a78d6; --unranked:#b9b8b2; --ref:#eb6834; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { color-scheme: dark; --surface:#1a1a19;
  --surface-2:#242423; --text:#f0efec; --text-2:#c3c2b7; --muted:#8f8e86; --grid:#333331; --ranked:#3987e5;
  --unranked:#5a5955; --ref:#d95926; } }
:root[data-theme="dark"] { color-scheme: dark; --surface:#1a1a19; --surface-2:#242423; --text:#f0efec;
  --text-2:#c3c2b7; --muted:#8f8e86; --grid:#333331; --ranked:#3987e5; --unranked:#5a5955; --ref:#d95926; }
* { box-sizing: border-box; }
body { margin:0; background:var(--surface); color:var(--text);
  font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif; }
main { max-width:1040px; margin:0 auto; padding:24px 16px 48px; }
h1 { font-size:22px; margin:0 0 4px; } p.sub { color:var(--text-2); margin:0 0 16px; }
.legend { display:flex; flex-wrap:wrap; gap:16px; color:var(--text-2); font-size:13px; margin:0 0 12px; }
.legend span { display:inline-flex; align-items:center; gap:6px; }
.sw { width:14px; height:10px; border-radius:2px; display:inline-block; }
.hatch { background:repeating-linear-gradient(45deg, var(--unranked) 0 2px, transparent 2px 4px); }
.chart { overflow-x:auto; } svg { display:block; width:100%; height:auto; min-width:560px; }
svg text { fill:var(--text-2); font-size:12px; } svg .name { fill:var(--text); }
svg .val { fill:var(--text-2); font-variant-numeric:tabular-nums; }
svg .bar:hover rect.mark { opacity:.8; }
#tip { position:fixed; pointer-events:none; background:var(--surface-2); color:var(--text); border:1px solid var(--grid);
  border-radius:6px; padding:8px 10px; font-size:12px; line-height:1.5; display:none; box-shadow:0 2px 8px #0002; }
table { border-collapse:collapse; width:100%; margin-top:28px; font-variant-numeric:tabular-nums; font-size:13px; }
th,td { text-align:left; padding:5px 8px; border-bottom:1px solid var(--grid); }
th { color:var(--text-2); font-weight:600; } td.n { text-align:right; }
details summary { cursor:pointer; color:var(--text-2); margin-top:24px; }
"""

TIP_SCRIPT = """
const tip = document.getElementById('tip');
document.querySelectorAll('.bar').forEach(bar => {
  bar.addEventListener('mousemove', e => {
    tip.innerHTML = bar.dataset.tip; tip.style.display = 'block';
    const x = Math.min(e.clientX + 14, innerWidth - tip.offsetWidth - 8);
    tip.style.left = x + 'px'; tip.style.top = (e.clientY + 14) + 'px';
  });
  bar.addEventListener('mouseleave', () => { tip.style.display = 'none'; });
});
"""


def chart_html(chart_rows: list[dict], level: int, seed: str) -> str:
    """A self-contained page: a horizontal bar chart of every strategy's margin, and the table under it."""
    bar_h, gap, top, name_w, value_w, width = 18, 4, 24, 200, 96, 1000
    plot_w = width - name_w - value_w - 16
    # The axis spans the ranked weeks: an unranked week's loss (the starter loses €72k) would squash every other bar.
    # A loss beyond the axis is drawn to its left edge, cut, and labelled with its full value.
    counted = [row["margin"] for row in chart_rows if row["ranked"]] or [row["margin"] for row in chart_rows]
    high = max([1, *counted])
    low = min([0, *counted])
    if any(row["margin"] < low for row in chart_rows):
        low = min(low, -high // 4)  # room for the cut bars
    span = high - low or 1

    def x(cents: int) -> float:
        return name_w + (max(cents, low) - low) / span * plot_w

    zero = x(0)
    height = top + len(chart_rows) * (bar_h + gap) + 8
    step = nice_step(span / 100 / 6)
    ticks, lines = [], []
    tick = (low // 100 // step) * step
    while tick * 100 <= high:
        tx = x(int(tick * 100))
        if tx >= name_w - 0.5:
            lines.append(f'<line x1="{tx:.1f}" x2="{tx:.1f}" y1="{top - 4}" y2="{height - 8}" stroke="var(--grid)"/>')
            ticks.append(f'<text x="{tx:.1f}" y="{top - 10}" text-anchor="middle">{short_euros(tick)}</text>')
        tick += step
    bars = []
    for n, row in enumerate(chart_rows):
        y = top + n * (bar_h + gap)
        x0, x1 = sorted((zero, x(row["margin"])))
        w = max(x1 - x0, 1.5)
        fill = "var(--ref)" if row["label"] == "dispatch.py" else "var(--ranked)" if row["ranked"] else "url(#hatch)"
        dash = ' stroke="var(--text-2)" stroke-dasharray="3 2"' if row["stale"] else ""
        # The data end is rounded, the baseline end is square.
        r = min(4, w / 2)
        if row["margin"] >= 0:
            path = f"M{x0:.1f},{y} H{x1 - r:.1f} Q{x1:.1f},{y} {x1:.1f},{y + r} V{y + bar_h - r} "
            path += f"Q{x1:.1f},{y + bar_h} {x1 - r:.1f},{y + bar_h} H{x0:.1f} Z"
            vx, anchor = x1 + 6, "start"
        else:
            path = f"M{x1:.1f},{y} H{x0 + r:.1f} Q{x0:.1f},{y} {x0:.1f},{y + r} V{y + bar_h - r} "
            path += f"Q{x0:.1f},{y + bar_h} {x0 + r:.1f},{y + bar_h} H{x1:.1f} Z"
            vx, anchor = x1 + 6, "start"
            if row["margin"] < low:  # cut at the axis' edge: a zigzag shows the bar goes on
                path = f"M{x1:.1f},{y} H{x0:.1f} L{x0 + 5:.1f},{y + bar_h / 4:.1f} L{x0:.1f},{y + bar_h / 2:.1f} "
                path += f"L{x0 + 5:.1f},{y + bar_h * 0.75:.1f} L{x0:.1f},{y + bar_h} H{x1:.1f} Z"
        note = "" if row["ranked"] else " · unranked"
        note += " · code changed since" if row["stale"] else ""
        tip = (
            f"<b>{html.escape(row['label'])}</b><br>Margin {euros(row['margin'])}<br>"
            f"{row['orders']:,} orders · {row['on_time']:.1%} on time · {row['undelivered']:.1%} not delivered<br>"
            f"{'Ranked' if row['ranked'] else 'Not ranked (under 90% on time)'}<br>"
            f"World {html.escape(row['world'])}<br>Played {html.escape(row['played'])}"
            + ("<br><i>Code changed since: run the tool to replay.</i>" if row["stale"] else "")
        )
        bars.append(
            f'<g class="bar" data-tip="{html.escape(tip, quote=True)}">'
            f'<rect x="0" y="{y - gap / 2}" width="{width}" height="{bar_h + gap}" fill="transparent"/>'
            f'<text class="name" x="{name_w - 8}" y="{y + bar_h - 5}" text-anchor="end">'
            f"{n + 1}. {html.escape(row['label'])}</text>"
            f'<path class="mark" d="{path}" fill="{fill}"{dash}/>'
            f'<text class="val" x="{vx:.1f}" y="{y + bar_h - 5}" text-anchor="{anchor}">'
            f"{euros(row['margin'])}{'' if row['ranked'] else ' ·  unranked'}</text></g>"
        )
    zero_line = f'<line x1="{zero:.1f}" x2="{zero:.1f}" y1="{top - 4}" y2="{height - 8}" stroke="var(--muted)"/>'
    svg = (
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Margin of every strategy, level {level}, '
        f'seed {html.escape(seed)}"><defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" '
        f'patternTransform="rotate(45)"><rect width="6" height="6" fill="var(--unranked)" opacity=".45"/>'
        f'<line x1="0" y1="0" x2="0" y2="6" stroke="var(--unranked)" stroke-width="3"/></pattern></defs>'
        f"{''.join(lines)}{''.join(ticks)}{zero_line}{''.join(bars)}</svg>"
    )
    table_rows = "".join(
        f"<tr><td class='n'>{n}</td><td>{html.escape(row['label'])}</td><td class='n'>{euros(row['margin'])}</td>"
        f"<td class='n'>{row['orders']:,}</td><td class='n'>{row['on_time']:.1%}</td>"
        f"<td>{'yes' if row['ranked'] else 'no'}</td><td>{'changed' if row['stale'] else ''}</td>"
        f"<td>{html.escape(row['world'])}</td></tr>"
        for n, row in enumerate(chart_rows, 1)
    )
    ranked = sum(1 for row in chart_rows if row["ranked"])
    stale = sum(1 for row in chart_rows if row["stale"])
    sub = f"Level {level}, seed {html.escape(seed)}: {len(chart_rows)} strategies, {ranked} ranked, played online."
    if stale:
        sub += f" {stale} have changed since they were played."
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Strategy leaderboard</title><style>{STYLE}</style></head>
<body><main>
<h1>Margin of every strategy</h1>
<p class="sub">{sub} Made {time.strftime("%Y-%m-%d %H:%M")}.</p>
<div class="legend">
<span><i class="sw" style="background:var(--ranked)"></i>Ranked (90%+ on time)</span>
<span><i class="sw hatch"></i>Unranked: the week does not count</span>
<span><i class="sw" style="background:var(--ref)"></i>Root dispatch.py, the reference</span>
<span><i class="sw" style="border:1px dashed var(--text-2)"></i>Code changed since it was played</span>
</div>
<div class="chart">{svg}</div>
<details open><summary>Table</summary>
<div class="chart"><table><thead><tr><th>#</th><th>Strategy</th><th>Margin</th><th>Orders</th><th>On time</th><th>Ranked</th>
<th>Code</th><th>World</th></tr></thead><tbody>{table_rows}</tbody></table></div></details>
</main><div id="tip"></div><script>{TIP_SCRIPT}</script></body></html>
"""


def nice_step(raw: float) -> int:
    """A round tick step in euros: 1, 2 or 5 times a power of ten."""
    power = 1
    while power * 10 <= raw:
        power *= 10
    for factor in (1, 2, 5, 10):
        if power * factor >= raw:
            return power * factor
    return power * 10


def short_euros(value: int) -> str:
    if abs(value) >= 1000:
        thousands = value / 1000
        text = f"{thousands:,.0f}" if thousands == int(thousands) else f"{thousands:,.1f}"
        return f"€{text}k"
    return f"€{value:,}"


# Command line


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m strategies.leaderboard",
        description="Plays every strategy online on one seed and draws a bar chart of the margins. Plays only the "
        "strategies that are new or whose code changed since their last online week. Never plays a ranking run "
        "or a final. Set SPREAD_URL and SPREAD_KEY first.",
    )
    parser.add_argument("--seed", default=DEFAULT_SEED, help=f"the practice seed (default {DEFAULT_SEED})")
    parser.add_argument("--level", type=int, choices=range(1, 9), default=8, help="the practice level (default 8)")
    parser.add_argument(
        "--jobs", type=int, choices=range(1, 9), default=DEFAULT_JOBS, help=f"weeks at once (default {DEFAULT_JOBS})"
    )
    parser.add_argument("--only", help="play only these strategies, comma-separated, also when their code is unchanged")
    parser.add_argument("--fresh", action="store_true", help="play every strategy again")
    parser.add_argument(
        "--language",
        choices=("all", "python", "typescript"),
        default="all",
        help="play only the Python or only the TypeScript strategies (default all); the chart shows every one",
    )
    parser.add_argument("--plan", action="store_true", help="print what would be played, and play nothing")
    parser.add_argument("--no-play", action="store_true", help="only redraw the chart from the online results")
    parser.add_argument("--html", type=Path, default=Path("out/leaderboard.html"), help="where to write the chart")
    args = parser.parse_args()

    found = entries()
    current = {label: fingerprint(entry) for label, entry in found.items()}
    results = load(args.level, args.seed)
    if args.only:
        wanted = [name.strip() for name in args.only.split(",") if name.strip()]
        unknown = [name for name in wanted if name not in found]
        if unknown:
            parser.error(f"no strategy named {', '.join(unknown)}. Known: {', '.join(found)}")
        todo = {label: (found[label], current[label]) for label in wanted}
    else:
        todo = {
            label: (entry, current[label])
            for label, entry in found.items()
            if args.language in ("all", entry.language)
            and (args.fresh or label not in results or results[label]["fingerprint"] != current[label])
        }

    if args.plan or args.no_play:
        new = [label for label in todo if label not in results]
        changed = [label for label in todo if label in results]
        languages = {language: sum(1 for e in found.values() if e.language == language) for language in LANGUAGES}
        counts = ", ".join(f"{n} {language}" for language, n in languages.items())
        up_to_date = sum(1 for label in found if label in results and results[label]["fingerprint"] == current[label])
        print(f"{len(found)} strategies ({counts}); {up_to_date} have an online week for their current code.")
        print(f"To play: {len(new)} new: {', '.join(new) or 'none'}")
        print(f"         {len(changed)} changed: {', '.join(changed) or 'none'}")
        if args.plan:
            return
        todo = {}

    failed: list[str] = []
    if todo:
        try:
            ProxyClient()  # stops at once when SPREAD_KEY is not set
        except SpreadError as error:
            sys.exit(f"spread: {error}")
        try:
            failed = play(todo, results, args.level, args.seed, args.jobs)
        except (RunFailed, SpreadError) as error:
            sys.exit(f"leaderboard: {error}")
        except KeyboardInterrupt:
            print("Stopped. The weeks that ended are saved; run again to play the rest.", file=sys.stderr)
    else:
        print("Nothing to play: every strategy has an online week for its current code.")

    chart_rows = rows(results, current)
    print()
    print(table(chart_rows))
    args.html.parent.mkdir(parents=True, exist_ok=True)
    args.html.write_text(chart_html(chart_rows, args.level, args.seed))
    print(f"\nWrote {args.html}. Results: {results_path(args.level, args.seed).relative_to(ROOT)}.")
    if failed:
        print(f"Failed, not in the chart: {', '.join(failed)}. Run again to retry them.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
