"""The seed bench: plays the same practice weeks with one or more versions of the system and prints one table.

Each version is a Python file that plays one practice week, as `dispatch.py` does: the bench runs
`python <file> --level <level> --seed <seed>` and reads the world id from its first line, then reads the
world's score from the server. A version can be a file, or a git ref checked out into a temporary worktree.
It never plays a ranking run or a final. See strategies/bench/README.md.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from concurrent.futures import FIRST_EXCEPTION, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from spread.client import SpreadError
from spread.types import Score

from tools.record import DATABASE, RUNS
from tools.spread_proxy import ProxyClient

SLOTS = 8  # a team holds at most 8 practice worlds that have not ended
DEFAULT_SEEDS = "spread-1..spread-5"
# The first line of dispatch.py and of the starter: "Practice world <id>, level 8. ..."
WORLD_LINE = re.compile(r"[Pp]ractice world (\S+), level")
SLOT_WAIT = 15  # seconds to wait for a free practice slot before trying again
SLOT_TRIES = 40  # then give up: 10 minutes


# Seeds


def parse_seeds(text: str) -> list[str]:
    """Seeds from a comma-separated list. An item is a seed, or a range of seeds that end in a number:
    "spread-1..spread-5" or "spread-1..5"."""
    seeds: list[str] = []
    for item in (part.strip() for part in text.split(",")):
        if not item:
            raise ValueError(f'"{text}" has an empty seed')
        if ".." not in item:
            seeds.append(item)
            continue
        first, last = item.split("..", 1)
        start = re.fullmatch(r"(.*?)(\d+)", first)
        end = re.fullmatch(r"(.*?)(\d+)", last)
        if start is None or end is None:
            raise ValueError(f'"{item}" is not a range: both ends must end in a number, as in spread-1..spread-5')
        prefix = start[1]
        if end[1] not in ("", prefix):
            raise ValueError(f'"{item}" is not a range: both ends must have the same text before the number')
        low, high = int(start[2]), int(end[2])
        if high < low:
            raise ValueError(f'"{item}" counts down: put the lower number first')
        seeds += [f"{prefix}{n}" for n in range(low, high + 1)]
    repeated = sorted({seed for seed in seeds if seeds.count(seed) > 1})
    if repeated:
        raise ValueError(f"seeds named more than once: {', '.join(repeated)}")
    return seeds


# Results, totals, table and CSV


class Result(NamedTuple):
    """One version's practice week on one seed."""

    version: str
    seed: str
    world_id: str
    score: Score


class Totals(NamedTuple):
    """One version's results on all seeds. The shares are over all orders of all weeks, not an average of shares."""

    margin_cents: int
    revenue_cents: int
    won_orders: int
    on_time_share: float
    undelivered_share: float
    ranked: int
    weeks: int


def totals(scores: list[Score]) -> Totals:
    orders = sum(score["wonOrders"] for score in scores)

    def share(key: str) -> float:
        return sum(score[key] * score["wonOrders"] for score in scores) / orders if orders else 0.0

    return Totals(
        margin_cents=sum(score["marginCents"] for score in scores),
        revenue_cents=sum(score["revenueCents"] for score in scores),
        won_orders=orders,
        on_time_share=share("onTimeShare"),
        undelivered_share=share("undeliveredShare"),
        ranked=sum(1 for score in scores if score["ranked"]),
        weeks=len(scores),
    )


def euros(cents: int, sign: bool = False) -> str:
    """-€72,612.51; with `sign`, +€1.00 for a gain."""
    prefix = "-" if cents < 0 else "+" if sign else ""
    return f"{prefix}€{abs(cents) / 100:,.2f}"


def by_version(results: list[Result], versions: list[str]) -> dict[str, list[Result]]:
    return {version: [r for r in results if r.version == version] for version in versions}


def table(results: list[Result], versions: list[str], seeds: list[str], level: int) -> str:
    """The table: one line per seed and version, then each version's totals, then how each other
    version compares with the first."""
    found = {(r.version, r.seed): r for r in results}
    header = ["Seed", "Version", "Margin", "Orders", "On time", "Not delivered", "Ranked"]
    rows: list[list[str] | None] = []  # None is a blank line
    for seed in seeds:
        for version in versions:
            score = found[(version, seed)].score
            rows.append(
                [
                    seed,
                    version,
                    euros(score["marginCents"]),
                    f"{score['wonOrders']:,}",
                    f"{score['onTimeShare']:.1%}",
                    f"{score['undeliveredShare']:.1%}",
                    "yes" if score["ranked"] else "no",
                ]
            )
        if len(versions) > 1:
            rows.append(None)
    if rows and rows[-1] is not None:
        rows.append(None)
    grouped = by_version(results, versions)
    for version in versions:
        total = totals([r.score for r in grouped[version]])
        rows.append(
            [
                "Total",
                version,
                euros(total.margin_cents),
                f"{total.won_orders:,}",
                f"{total.on_time_share:.1%}",
                f"{total.undelivered_share:.1%}",
                f"{total.ranked} of {total.weeks}",
            ]
        )
    full = [row for row in [header, *rows] if row is not None]
    widths = [max(len(row[i]) for row in full) for i in range(len(header))]
    right = {2, 3, 4, 5}  # numbers line up on the right

    def line(row: list[str]) -> str:
        cells = [cell.rjust(widths[i]) if i in right else cell.ljust(widths[i]) for i, cell in enumerate(row)]
        return "  ".join(cells).rstrip()

    lines = [f"Level {level}, {len(seeds)} seed{'s' if len(seeds) != 1 else ''}.", "", line(header)]
    lines += ["" if row is None else line(row) for row in rows]
    if len(versions) > 1:
        lines += ["", *(comparison(results, versions[0], other, seeds) for other in versions[1:])]
    return "\n".join(lines).rstrip() + "\n"


def comparison(results: list[Result], first: str, other: str, seeds: list[str]) -> str:
    """One line: the first version against another, on margin and on ranked weeks."""
    found = {(r.version, r.seed): r.score for r in results}
    gain = sum(found[(first, s)]["marginCents"] - found[(other, s)]["marginCents"] for s in seeds)
    higher = sum(1 for s in seeds if found[(first, s)]["marginCents"] > found[(other, s)]["marginCents"])
    ranked = [sum(1 for s in seeds if found[(v, s)]["ranked"]) for v in (first, other)]
    return (
        f"{first} against {other}: margin {euros(gain, sign=True)} in total, higher on {higher} of {len(seeds)} "
        f"seeds; ranked on {ranked[0]} against {ranked[1]}."
    )


CSV_COLUMNS = [
    "seed",
    "version",
    "level",
    "world_id",
    "margin_eur",
    "revenue_eur",
    "won_orders",
    "on_time_share",
    "undelivered_share",
    "ranked",
]


def csv_rows(results: list[Result], versions: list[str], seeds: list[str], level: int) -> list[dict[str, str]]:
    """The CSV rows: one per seed and version, in the table's order, then one total per version."""
    found = {(r.version, r.seed): r for r in results}
    rows = []
    for seed in seeds:
        for version in versions:
            result = found[(version, seed)]
            score = result.score
            rows.append(
                {
                    "seed": seed,
                    "version": version,
                    "level": str(level),
                    "world_id": result.world_id,
                    "margin_eur": f"{score['marginCents'] / 100:.2f}",
                    "revenue_eur": f"{score['revenueCents'] / 100:.2f}",
                    "won_orders": str(score["wonOrders"]),
                    "on_time_share": f"{score['onTimeShare']:.4f}",
                    "undelivered_share": f"{score['undeliveredShare']:.4f}",
                    "ranked": "yes" if score["ranked"] else "no",
                }
            )
    grouped = by_version(results, versions)
    for version in versions:
        total = totals([r.score for r in grouped[version]])
        rows.append(
            {
                "seed": "total",
                "version": version,
                "level": str(level),
                "world_id": "",
                "margin_eur": f"{total.margin_cents / 100:.2f}",
                "revenue_eur": f"{total.revenue_cents / 100:.2f}",
                "won_orders": str(total.won_orders),
                "on_time_share": f"{total.on_time_share:.4f}",
                "undelivered_share": f"{total.undelivered_share:.4f}",
                "ranked": f"{total.ranked} of {total.weeks}",
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


# Versions


@dataclass
class Version:
    """A version of the system: the label in the table, and the file that plays one week."""

    label: str
    file: Path
    worktree: Path | None = None  # the temporary worktree of a git ref, removed at the end


def split_ref(spec: str) -> tuple[str, str]:
    """A git version as "<ref>" or "<ref>:<path>": the ref, and the file in it (dispatch.py by default)."""
    ref, _, path = spec.partition(":")
    return ref, path or "dispatch.py"


def command(version: Version, seed: str, level: int) -> list[str]:
    """The command that plays one practice week. Never a ranking run or a final: those need the team's approval."""
    return [sys.executable, str(version.file), "--level", str(level), "--seed", seed]


def git(*args: str, cwd: Path | None = None) -> str:
    done = subprocess.run(["git", *args], check=False, cwd=cwd, capture_output=True, text=True)
    if done.returncode != 0:
        raise ValueError(done.stderr.strip() or f"git {' '.join(args)} failed")
    return done.stdout.strip()


def prepare(spec: str) -> Version:
    """A file that exists, else a git ref checked out into a temporary worktree."""
    if Path(spec).is_file():
        return Version(spec, Path(spec).resolve())
    ref, path = split_ref(spec)
    try:
        commit = git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    except ValueError:
        raise ValueError(f'"{spec}" is neither a file nor a git ref') from None
    root = Path(git("rev-parse", "--show-toplevel"))
    worktree = Path(tempfile.mkdtemp(prefix="bench-"))
    git("worktree", "add", "--detach", "--quiet", str(worktree), commit, cwd=root)
    version = Version(spec, worktree / path, worktree)
    if not version.file.is_file():
        remove(version)
        raise ValueError(f"{ref} has no file {path}")
    return version


def remove(version: Version) -> None:
    if version.worktree is not None:
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(version.worktree)], check=False, capture_output=True
        )
        shutil.rmtree(version.worktree, ignore_errors=True)


# Playing


class Stopped(Exception):
    """The bench is stopping: a run that has not started does not start."""


class RunFailed(Exception):
    def __init__(self, version: str, seed: str, why: str, output: list[str]):
        tail = "\n".join(f"    {line}" for line in output)
        super().__init__(f"{seed} with {version} {why}." + (f" Its last lines:\n{tail}" if tail else ""))


class Bench:
    """Plays every seed with every version, at most `jobs` weeks at once. Each week is a child process."""

    def __init__(self, versions: list[Version], seeds: list[str], level: int, jobs: int):
        self.versions, self.seeds, self.level, self.jobs = versions, seeds, level, jobs
        self.stopping = threading.Event()
        self.lock = threading.Lock()
        self.running: set[subprocess.Popen] = set()
        self.unfinished: dict[tuple[str, str], str] = {}  # (version, seed) -> the world of a run that has not ended

    def play(self) -> list[Result]:
        runs = [(version, seed) for seed in self.seeds for version in self.versions]
        print(f"Playing {len(runs)} practice weeks at level {self.level}, {self.jobs} at a time.", flush=True)
        pool = ThreadPoolExecutor(max_workers=self.jobs)
        futures: list[Future[Result]] = [pool.submit(self.play_one, version, seed) for version, seed in runs]
        try:
            done, _ = wait(futures, return_when=FIRST_EXCEPTION)
            failed = next((f.exception() for f in done if f.exception() is not None), None)
            if failed is not None:
                raise failed
        except BaseException as error:
            self.stop(pool, interrupted=isinstance(error, KeyboardInterrupt))
            raise
        pool.shutdown()
        return [future.result() for future in futures]

    def play_one(self, version: Version, seed: str) -> Result:
        for _ in range(SLOT_TRIES):
            world_id, code, output = self.run(version, seed)
            if code == 0 and world_id is not None:
                score = ProxyClient().world(world_id).score()
                print(f"{seed:<12} {version.label}: margin {euros(score['marginCents'])}, world {world_id}", flush=True)
                return Result(version.label, seed, world_id, score)
            if self.stopping.is_set():
                raise Stopped()
            if world_id is None and any("HTTP 409" in line for line in output):
                print(f"{seed:<12} {version.label}: no free practice slot, trying again in {SLOT_WAIT} s", flush=True)
                if self.stopping.wait(SLOT_WAIT):
                    raise Stopped()
                continue
            why = f"stopped with exit code {code}" if code != 0 else "printed no practice world id"
            raise RunFailed(version.label, seed, why, list(output))
        raise RunFailed(
            version.label, seed, f"found no free practice slot in {SLOT_WAIT * SLOT_TRIES // 60} minutes", []
        )

    def run(self, version: Version, seed: str) -> tuple[str | None, int, deque[str]]:
        """One child process: returns the world it created, its exit code and its last lines."""
        key = (version.label, seed)
        with self.lock:
            if self.stopping.is_set():
                raise Stopped()
            child = subprocess.Popen(
                command(version, seed, self.level),
                cwd=version.file.parent,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                # Every version saves its week into this checkout's data/scrape/runs and database (record.py), also
                # one checked out into a temporary worktree.
                env={**os.environ, "PYTHONUNBUFFERED": "1", "SPREAD_RUNS_DIR": str(RUNS), "SPREAD_DB": str(DATABASE)},
            )
            self.running.add(child)
        world_id, output = None, deque(maxlen=20)
        assert child.stdout is not None
        for line in child.stdout:
            output.append(line.rstrip())
            match = WORLD_LINE.search(line) if world_id is None else None
            if match:
                world_id = match[1]
                with self.lock:
                    self.unfinished[key] = world_id
        code = child.wait()
        with self.lock:
            self.running.discard(child)
            if code == 0:  # the week has ended: its world holds no slot, and stays to be read and revealed
                self.unfinished.pop(key, None)
        return world_id, code, output

    def stop(self, pool: ThreadPoolExecutor, interrupted: bool) -> None:
        """Stops every run, then deletes each world of a week that has not ended, so no practice slot is left held."""
        previous = signal.signal(signal.SIGINT, signal.SIG_IGN)  # a second Ctrl-C would leave worlds behind
        try:
            print("Stopping: the bench deletes the worlds of the weeks that have not ended.", file=sys.stderr)
            self.stopping.set()
            pool.shutdown(wait=False, cancel_futures=True)
            with self.lock:
                children = list(self.running)
            # After Ctrl-C the children have it too: each deletes its own world. Give them the time.
            deadline = time.monotonic() + (10 if interrupted else 0)
            for child in children:
                try:
                    child.wait(timeout=max(0.0, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    child.send_signal(signal.SIGINT)
            for child in children:
                try:
                    child.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    child.kill()
            pool.shutdown(wait=True)
            self.delete_unfinished()
        finally:
            signal.signal(signal.SIGINT, previous)

    def delete_unfinished(self) -> None:
        with self.lock:
            worlds = set(self.unfinished.values())
        if not worlds:
            return
        client = ProxyClient()
        try:
            listed = {world["worldId"]: world for world in client.worlds()}
        except SpreadError as error:
            print(f"Cannot list the team's worlds ({error}). Check these: {', '.join(sorted(worlds))}", file=sys.stderr)
            return
        for world_id in sorted(worlds):
            world = listed.get(world_id)
            if world is None or world["ended"]:
                continue  # its own run deleted it, or it ended
            try:
                client.world(world_id).delete()
                print(f"Deleted practice world {world_id}.", file=sys.stderr)
            except SpreadError as error:
                print(f"Practice world {world_id} is not deleted: {error}", file=sys.stderr)


# Command line


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m strategies.bench",
        description="Plays the same practice weeks with one or more versions of the system and prints one table. "
        "Never plays a ranking run or a final. Set SPREAD_URL and SPREAD_KEY first.",
    )
    parser.add_argument(
        "versions",
        nargs="*",
        metavar="VERSION",
        help="a Python file that plays one week (default dispatch.py), or a git ref such as origin/main, "
        "or <ref>:<file>. Compare two: dispatch.py origin/main",
    )
    parser.add_argument("--level", type=int, choices=range(1, 9), default=8, help="the practice level (default 8)")
    parser.add_argument(
        "--seeds", default=DEFAULT_SEEDS, help=f"seeds or ranges, comma-separated (default {DEFAULT_SEEDS})"
    )
    parser.add_argument(
        "--jobs", type=int, choices=range(1, SLOTS + 1), default=SLOTS, help="weeks at once, 1 to 8 (default 8)"
    )
    parser.add_argument("--csv", type=Path, help="where to write the CSV (default out/bench-<date>-<time>.csv)")
    args = parser.parse_args()
    specs = args.versions or ["dispatch.py"]
    if len(set(specs)) != len(specs):
        parser.error("a version is named twice")
    try:
        seeds = parse_seeds(args.seeds)
    except ValueError as error:
        parser.error(str(error))
    try:
        ProxyClient()  # stops at once when SPREAD_KEY is not set
    except SpreadError as error:
        sys.exit(f"spread: {error}")
    versions: list[Version] = []
    try:
        for spec in specs:
            versions.append(prepare(spec))
        results = Bench(versions, seeds, args.level, args.jobs).play()
    except (ValueError, RunFailed, SpreadError) as error:
        sys.exit(f"bench: {error}")
    except KeyboardInterrupt:
        sys.exit("Stopped.")
    finally:
        for version in versions:
            remove(version)
    labels = [version.label for version in versions]
    print()
    print(table(results, labels, seeds, args.level), end="")
    path = args.csv or Path("out") / f"bench-{time.strftime('%Y%m%d-%H%M%S')}.csv"
    write_csv(path, csv_rows(results, labels, seeds, args.level))
    print(f"\nWrote {path}.")


if __name__ == "__main__":
    main()
