"""Two charts of the weekend, drawn from the saved weeks: the best score, and the seeds and strategies explored.

    uv run python -m analysis.weekend

Reads every `meta.json` under `data/scrape/runs` and writes `best-score.svg` and `explored.svg` to
`docs/images/lean/`. It plays nothing online. A saved week has no clock time of its own, so each week is dated by
the commit that first saved it (`git log`); a week that is not committed yet is left out.
"""

import argparse
import json
import subprocess
from collections import defaultdict
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = "data/scrape/runs"
HELSINKI = timezone(timedelta(hours=2))  # November: no summer time
START = datetime(2026, 11, 13, 18, 0, tzinfo=HELSINKI)  # the opening ceremony
HOUR = 3600
# Systems that play a seed from what they remember of it: their best week says nothing of an unseen week.
REMEMBERS = {"ts-recall"}
# Folder names that stand in for a seed the server chose.
NOT_A_SEED = {"board", "final", "random"}
# The ranking rounds open at these hours (docs/judging.md); a round counts when all 5 of its weeks were played.
ROUND_HOURS = [(13, 19.5), (14, 0), (14, 9), (14, 12), (14, 15), (14, 18), (14, 21), (15, 0), (15, 3), (15, 6)]
ROUND_WEEKS = 5

W, H = 960, 500
LEFT, RIGHT, TOP, BOTTOM = 64, 190, 122, 58

STYLE = """
  .card { fill: #fcfcfb; stroke: #e4e3de; }
  .title { font: 650 20px system-ui, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif; fill: #0b0b0b; }
  .sub { font: 400 13.5px system-ui, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif; fill: #52514e; }
  .tick, .note { font: 400 11.5px system-ui, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif; fill: #76756f; }
  .key { font: 400 12.5px system-ui, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif; fill: #52514e; }
  .value { font: 650 14px system-ui, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif; fill: #0b0b0b; }
  .grid { stroke: #e9e8e3; stroke-width: 1; }
  .axis { stroke: #c9c8c2; stroke-width: 1; }
  .dot { fill: #8d8c85; fill-opacity: .32; }
  .s1 { stroke: #2a78d6; } .f1 { fill: #2a78d6; }
  .s2 { stroke: #eb6834; } .f2 { fill: #eb6834; }
  .line { fill: none; stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }
  .ring { stroke: #fcfcfb; stroke-width: 2; }
  @media (prefers-color-scheme: dark) {
    .card { fill: #1a1a19; stroke: #333330; }
    .title, .value { fill: #f0efec; }
    .sub, .key { fill: #c3c2b7; }
    .tick, .note { fill: #9a998f; }
    .grid { stroke: #2a2a28; }
    .axis { stroke: #4a4945; }
    .dot { fill: #a3a299; fill-opacity: .3; }
    .s1 { stroke: #3987e5; } .f1 { fill: #3987e5; }
    .s2 { stroke: #d95926; } .f2 { fill: #d95926; }
    .ring { stroke: #1a1a19; }
  }
"""


def saved_at() -> dict[str, int]:
    """The time of the first commit that added each meta.json, by its path (`-m` also reads merge commits)."""
    out = subprocess.run(
        ["git", "log", "-m", "--diff-filter=AR", "--format=C %at", "--name-only", "--", RUNS],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    first: dict[str, int] = {}
    at = 0
    for line in out.splitlines():
        if line.startswith("C "):
            at = int(line[2:])
        elif line.endswith("/meta.json"):
            first[line] = min(first.get(line, at), at)
    return first


def load() -> list[dict]:
    """Every committed week: when it was saved, and what its meta.json says."""
    first = saved_at()
    weeks = []
    missing = 0
    for path in sorted((ROOT / RUNS).rglob("meta.json")):
        at = first.get(path.relative_to(ROOT).as_posix())
        if at is None:
            missing += 1
            continue
        meta = json.loads(path.read_text())
        score = meta.get("score") or {}
        weeks.append(
            {
                "at": at,
                "world": meta.get("worldId"),
                "seed": str(meta.get("seed")),
                "level": meta.get("level"),
                "policy": meta.get("policy"),
                "kind": meta.get("kind"),
                "margin": (score.get("marginCents") or 0) / 100,
                "ranked": bool(score.get("ranked")),
            }
        )
    if missing:
        print(f"Left out {missing} weeks that are not committed yet.")
    weeks.sort(key=lambda w: w["at"])
    return weeks


def name(policy: str) -> str:
    """`ts-lean` is `ts:lean` in the team's words."""
    return policy.replace("ts-", "ts:", 1) if policy.startswith("ts-") else policy


def euros(value: float) -> str:
    return f"€{value:,.0f}"


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Frame:
    """The plot area: maps a time and a value to a point, and draws the parts both charts share."""

    def __init__(self, end: int, top: float, step: float):
        self.t0 = int(START.timestamp())
        self.t1 = self.t0 + -(-(end - self.t0) // (6 * HOUR)) * 6 * HOUR
        self.top, self.step = top, step
        self.parts: list[str] = []

    def x(self, at: float) -> float:
        return LEFT + (at - self.t0) / (self.t1 - self.t0) * (W - LEFT - RIGHT)

    def y(self, value: float) -> float:
        return H - BOTTOM - value / self.top * (H - BOTTOM - TOP)

    def add(self, part: str) -> None:
        self.parts.append(part)

    def header(self, title: str, sub: str, keys: list[tuple[str, str]]) -> None:
        self.add(f'<rect class="card" x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="14"/>')
        self.add(f'<text class="title" x="32" y="46">{esc(title)}</text>')
        self.add(f'<text class="sub" x="32" y="70">{esc(sub)}</text>')
        x = 32.0
        for cls, label in keys:
            if cls == "dot":
                self.add(f'<circle class="dot" cx="{x + 8}" cy="94" r="3" style="fill-opacity:.7"/>')
            else:
                self.add(f'<path class="line s{cls}" d="M{x} 94h16"/>')
            self.add(f'<text class="key" x="{x + 23}" y="98">{esc(label)}</text>')
            x += 23 + len(label) * 6.6 + 22

    def axes(self, fmt) -> None:
        value = 0.0
        while value <= self.top + 1e-9:
            y = self.y(value)
            cls = "axis" if value == 0 else "grid"
            self.add(f'<path class="{cls}" d="M{LEFT} {y:.1f}H{W - RIGHT}"/>')
            self.add(f'<text class="tick" x="{LEFT - 10}" y="{y + 4:.1f}" text-anchor="end">{fmt(value)}</text>')
            value += self.step
        at = self.t0
        while at <= self.t1:
            when = datetime.fromtimestamp(at, HELSINKI)
            label = f"{when:%H:%M}"
            if at == self.t0 or when.hour == 0:
                label = f"{when:%a} {label}"
            x = self.x(at)
            self.add(f'<path class="axis" d="M{x:.1f} {H - BOTTOM}v5"/>')
            self.add(f'<text class="tick" x="{x:.1f}" y="{H - BOTTOM + 20}" text-anchor="middle">{label}</text>')
            at += 6 * HOUR

    def steps(self, cls: str, points: list[tuple[int, float]], end: int) -> None:
        """A line that holds each value until the next one."""
        d = f"M{self.x(points[0][0]):.1f} {self.y(points[0][1]):.1f}"
        for at, value in points[1:]:
            d += f"H{self.x(at):.1f}V{self.y(value):.1f}"
        d += f"H{self.x(end):.1f}"
        self.add(f'<path class="line s{cls}" d="{d}"/>')
        self.add(f'<circle class="f{cls} ring" cx="{self.x(end):.1f}" cy="{self.y(points[-1][1]):.1f}" r="5"/>')

    def end_labels(self, labels: list[tuple[float, str, str]], end: int) -> None:
        """A value at the right of each line's end, with a line of words under it when there is one."""
        gap = 36 if any(small for _, _, small in labels) else 20
        placed = sorted((self.y(value) + 4, big, small) for value, big, small in labels)
        for i in range(1, len(placed)):
            if placed[i][0] - placed[i - 1][0] < gap:
                placed[i] = (placed[i - 1][0] + gap, *placed[i][1:])
        x = self.x(end) + 12
        for y, big, small in placed:
            self.add(f'<text class="value" x="{x:.1f}" y="{y:.1f}">{esc(big)}</text>')
            if small:
                self.add(f'<text class="key" x="{x:.1f}" y="{y + 17:.1f}">{esc(small)}</text>')

    def svg(self, label: str, note: str) -> str:
        self.add(f'<text class="note" x="32" y="{H - 14}">{esc(note)}</text>')
        body = "\n".join(self.parts)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
            f'aria-label="{esc(label)}">\n<title>{esc(label)}</title>\n<style>{STYLE}</style>\n{body}\n</svg>\n'
        )


def rounds(weeks: list[dict]) -> list[tuple[int, float, str]]:
    """Our best system in each ranking round it played in full: when, its mean week, its name."""
    opens = [
        int(datetime(2026, 11, day, int(hour), int(hour % 1 * 60), tzinfo=HELSINKI).timestamp())
        for day, hour in ROUND_HOURS
    ]
    played: dict[tuple[int, str], dict[str, dict]] = defaultdict(dict)
    for week in weeks:
        if week["kind"] == "board" and week["level"] == 8:
            opened = max((o for o in opens if o <= week["at"]), default=None)
            if opened is not None:
                played[(opened, week["policy"])][week["world"]] = week
    best: dict[int, tuple[int, float, str]] = {}
    for (opened, policy), worlds in played.items():
        if len(worlds) < ROUND_WEEKS or not all(w["ranked"] for w in worlds.values()):
            continue
        mean = sum(w["margin"] for w in worlds.values()) / len(worlds)
        if opened not in best or mean > best[opened][1]:
            best[opened] = (max(w["at"] for w in worlds.values()), mean, policy)
    return [best[opened] for opened in sorted(best)]


def best_score(weeks: list[dict]) -> str:
    practice = [
        w for w in weeks if w["level"] == 8 and w["kind"] == "practice" and w["ranked"] and w["policy"] not in REMEMBERS
    ]
    end = weeks[-1]["at"]
    record: list[tuple[int, float]] = []
    holder = practice[0]
    for week in practice:
        if not record or week["margin"] > record[-1][1]:
            if record and record[-1][0] == week["at"]:
                record.pop()  # saved by the same commit: keep the better week only
            record.append((week["at"], week["margin"]))
            holder = week
    ranking = rounds(weeks)
    frame = Frame(end, 30000, 5000)
    first = record[0][1]
    title = f"The best level 8 week rose from {euros(first)} to {euros(record[-1][1])} over the weekend"
    sub = f"Gross margin of one simulated week, from {len(practice):,} ranked practice weeks"
    if ranking:
        sub += f" and {len(ranking)} ranking rounds of 5 unseen weeks"
    frame.header(
        title,
        sub,
        [("1", "best practice week so far"), ("2", "ranking round, mean week"), ("dot", "one practice week")],
    )
    frame.axes(lambda v: "0" if v == 0 else f"€{v / 1000:.0f}K")
    seen = set()
    for week in practice:
        point = (round(frame.x(week["at"])), round(frame.y(min(max(week["margin"], 0), frame.top))))
        if point not in seen:
            seen.add(point)
            frame.add(f'<circle class="dot" cx="{point[0]}" cy="{point[1]}" r="1.8"/>')
    frame.steps("1", record, end)
    labels = [(record[-1][1], euros(record[-1][1]), f"{name(holder['policy'])} on {holder['seed']}")]
    if ranking:
        d = "M" + "L".join(f"{frame.x(at):.1f} {frame.y(mean):.1f}" for at, mean, _ in ranking)
        frame.add(f'<path class="line s2" d="{d}"/>')
        for at, mean, _ in ranking:
            frame.add(f'<circle class="f2 ring" cx="{frame.x(at):.1f}" cy="{frame.y(mean):.1f}" r="5"/>')
        at, mean, policy = ranking[-1]
        x = frame.x(at)
        frame.add(f'<path class="line s2" d="M{x:.1f} {frame.y(mean):.1f}H{frame.x(end):.1f}" stroke-dasharray="1 5"/>')
        labels.append((mean, euros(mean), f"{name(policy)}, mean of {ROUND_WEEKS} unseen weeks"))
    frame.end_labels(labels, end)
    note = "Each week is dated by the commit that saved it, Helsinki time. Not counted: unranked weeks"
    note += ", and ts:recall, which replays seeds it remembers." if REMEMBERS else "."
    return frame.svg(title, note)


def explored(weeks: list[dict]) -> str:
    end = weeks[-1]["at"]
    seeds: list[tuple[int, float]] = []
    policies: list[tuple[int, float]] = []
    seen_seeds: set[str] = set()
    seen_policies: set[str] = set()
    for week in weeks:
        if week["seed"] not in NOT_A_SEED and week["seed"] not in seen_seeds:
            seen_seeds.add(week["seed"])
            seeds.append((week["at"], len(seen_seeds)))
        if week["policy"] not in seen_policies:
            seen_policies.add(week["policy"])
            policies.append((week["at"], len(seen_policies)))
    most = max(len(seen_seeds), len(seen_policies))
    step = 50 if most > 120 else 20
    frame = Frame(end, -(-most // step) * step, step)
    hours = round((end - weeks[0]["at"]) / HOUR)
    title = f"{len(seen_policies)} strategies on {len(seen_seeds)} seeds in {hours} hours"
    sub = f"Counted over the {len(weeks):,} weeks played on the server and saved in this repository"
    frame.header(title, sub, [("1", "strategies tried so far"), ("2", "seeds played so far")])
    frame.axes(lambda v: f"{v:.0f}")
    frame.steps("1", [(weeks[0]["at"], 0.0), *policies], end)
    frame.steps("2", [(weeks[0]["at"], 0.0), *seeds], end)
    frame.end_labels(
        [
            (len(seen_policies), f"{len(seen_policies)} strategies", ""),
            (len(seen_seeds), f"{len(seen_seeds)} seeds", ""),
        ],
        end,
    )
    note = "Each week is dated by the commit that saved it, Helsinki time. A seed is one week; a strategy is a name that weeks were saved under."
    return frame.svg(title, note)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "docs/images/lean", help="the folder for the two SVG files")
    args = parser.parse_args()
    weeks = load()
    if not weeks:
        raise SystemExit(f"No committed week under {RUNS}.")
    args.out.mkdir(parents=True, exist_ok=True)
    for file, chart in (("best-score.svg", best_score), ("explored.svg", explored)):
        (args.out / file).write_text(chart(weeks))
        print(f"Wrote {(args.out / file).relative_to(ROOT) if args.out.is_relative_to(ROOT) else args.out / file}")
    last = datetime.fromtimestamp(weeks[-1]["at"], UTC).astimezone(HELSINKI)
    print(f"{len(weeks):,} weeks, the last saved on {last:%a %d %b at %H:%M}.")


if __name__ == "__main__":
    main()
