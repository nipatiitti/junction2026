"""Saves every week that dispatch.py plays on the server as a scraped week, so each online run adds to the team's
data: the week's folder under data/scrape/runs/L<level>/<seed>/<world id>/, in scrape.py's format, and its rows in the
SQLite database (db.py). Analysis then runs against the saved weeks instead of playing more weeks online. README.md
says what is saved.

SPREAD_RUNS_DIR and SPREAD_DB change where the weeks go; the bench sets both, so the versions that it checks out into
temporary worktrees save into the main checkout. SPREAD_RECORD=0 saves nothing.
"""

from __future__ import annotations

import gzip
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from spread.client import SpreadError, World

ROOT = Path(__file__).resolve().parent
RUNS = Path(os.environ.get("SPREAD_RUNS_DIR") or ROOT / "data" / "scrape" / "runs")
DATABASE = Path(os.environ.get("SPREAD_DB") or ROOT / "out" / "spread.sqlite")
ENABLED = os.environ.get("SPREAD_RECORD", "1") != "0"
POLICY = "dispatch"  # the policy of a saved run, next to scrape.py's passive, starter and explore
REVEAL_TRIES = 6  # the reveal of a final opens when the final has ended: try for half a minute


def safe_name(seed: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", seed)


def all_events(world: World) -> list[dict]:
    """Every event of the world, oldest first, in pages in case the server caps an answer."""
    events: list[dict] = []
    while True:
        page = world.events(after=events[-1]["seq"] if events else -1)
        if not page:
            return events
        events += page


def write_json(path: Path, data: Any) -> None:
    if path.suffix == ".gz":
        with gzip.open(path, "wt", encoding="utf-8") as f:
            json.dump(data, f, separators=(",", ":"))
    else:
        path.write_text(json.dumps(data, indent=2) + "\n")


def save_week(target: Path, world: World, drivers: list, meta: dict, reveal: dict | None = None) -> dict:
    """Writes the week to a temporary folder, then renames it, so a folder with meta.json is always complete.
    `drivers` is the driver list from the start of the week, as a system sees it. `reveal` defaults to the world's."""
    events = all_events(world)
    files = {
        "reveal.json.gz": world.reveal() if reveal is None else reveal,
        "snapshot.json.gz": world.snapshot(),
        "drivers.json.gz": drivers,
        "score.json": world.score(),
    }
    partial = target.with_name(target.name + ".partial")
    shutil.rmtree(partial, ignore_errors=True)
    partial.mkdir(parents=True)
    with gzip.open(partial / "events.jsonl.gz", "wt", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event, separators=(",", ":")) + "\n")
    for name, data in files.items():
        write_json(partial / name, data)
    meta = {**meta, "events": len(events), "score": files["score.json"]}
    write_json(partial / "meta.json", meta)
    shutil.rmtree(target, ignore_errors=True)
    partial.rename(target)
    return meta


def git_version() -> str | None:
    """The commit of this checkout, with "-dirty" when tracked files have changed; None outside git."""

    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()

    try:
        return git("rev-parse", "HEAD") + ("-dirty" if git("status", "--porcelain", "--untracked-files=no") else "")
    except OSError, subprocess.CalledProcessError:
        return None


def shown(path: Path) -> str:
    """The path from the working folder when it is below it, else in full."""
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


class Recorder:
    """Notes the start of a week played online, and saves the week once it has ended. `kind` is practice, board (a
    ranking run) or final. Saving never stops the run: a failure prints a warning."""

    def __init__(self, world: World, level: int, seed: str | None, kind: str):
        self.world, self.level, self.kind = world, level, kind
        self.seed = seed or ("random" if kind == "practice" else kind)
        self.version, self.started = git_version(), time.monotonic()
        self.requests_before = getattr(world.client, "requests", 0)
        self.drivers: list = []
        if ENABLED:
            try:
                self.drivers = list(world.roster())  # the driver list at the start, as scrape.py saves it
            except SpreadError as error:
                print(f"Could not read the driver list to save with the week: {error}", file=sys.stderr, flush=True)

    def reveal(self) -> dict | None:
        """The world's reveal, or None where the server gives none: never for a ranking run, and in a final only
        once the final has ended."""
        for _ in range(REVEAL_TRIES):
            try:
                return dict(self.world.reveal())
            except SpreadError as error:
                if error.status != 409:  # 403: a ranking run, or a final that has not ended
                    return None
            time.sleep(5)
        return None

    def save(self) -> None:
        """Saves the ended week to its folder under RUNS and adds it to DATABASE. A week saved before is skipped."""
        if not ENABLED:
            return
        target = RUNS / f"L{self.level}" / safe_name(self.seed) / self.world.id
        try:
            if (target / "meta.json").exists():
                return
            reveal = self.reveal()
            meta = {
                "seed": self.seed,
                "level": self.level,
                "policy": POLICY,
                "kind": self.kind,
                "worldId": self.world.id,
                "version": self.version,
                "revealed": reveal is not None,
                "recorded": False,  # no actions, rosters or positions, which scrape.py records
                "quoteRange": None,
                "feeRange": None,
            }
            meta = save_week(target, self.world, self.drivers, meta, reveal or {})
            meta["seconds"] = round(time.monotonic() - self.started, 1)
            meta["requests"] = getattr(self.world.client, "requests", 0) - self.requests_before
            write_json(target / "meta.json", meta)
            self.save_map()
            self.add_to_database(target)
        except Exception as error:  # noqa: BLE001  (the run has ended and scored: only the saving failed)
            print(f"Could not save the week to {shown(target)}: {error!r}", file=sys.stderr, flush=True)
            return
        print(f"Saved the week to {shown(target)} and {shown(DATABASE)}.", flush=True)

    def save_map(self) -> None:
        """The map, once for every run, as scrape.py saves it next to its weeks. Bench runs save at the same time,
        so each writes its own file and renames it."""
        path = RUNS / "map.json"
        if path.exists():
            return
        partial = path.with_name(f"map.json.{os.getpid()}")
        write_json(partial, self.world.client.map())
        partial.replace(path)

    def add_to_database(self, target: Path) -> None:
        from db import add_map, add_week, connect  # db.py and stats.py load only for the saving
        from stats import load_week

        database = connect(DATABASE)
        try:
            if database.execute("select count(*) from places").fetchone()[0] == 0:
                with database:
                    add_map(database, json.loads((RUNS / "map.json").read_text()))
            folder = target.resolve()
            add_week(
                database, load_week(target), str(folder.relative_to(ROOT) if folder.is_relative_to(ROOT) else folder)
            )
        finally:
            database.close()
