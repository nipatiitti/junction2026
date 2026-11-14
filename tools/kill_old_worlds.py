"""Deletes the team's practice worlds that are still open and older than 15 minutes, so forgotten worlds stop holding
the team's 8 practice slots. tools/README.md says how to run it.

    uv run --env-file .env python -m tools.kill_old_worlds              # lists the matching worlds, changes nothing
    uv run --env-file .env python -m tools.kill_old_worlds --yes        # deletes them
    uv run --env-file .env python -m tools.kill_old_worlds --minutes 30

The server gives no creation time for a world: GET /v1/worlds has none, and the snapshot has only world minutes. So the
age of a world counts from the first time this tool saw it open, kept in out/world_ages.json. A world seen for the first
time has age 0, and the first run deletes nothing: run it again later. Teammates' worlds count the same way, from the
first time this machine saw them.

Ranking runs are skipped unless --include-board asks for them: each can be played only once, and a deleted run still
counts on the rankings with its score at its end. Finals are always skipped: the API answers 403 to DELETE on a final.

Each run costs one practice request for the list, one for each listed world's snapshot, and one for each deletion.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spread.client import SpreadError

from tools.probe import retrying
from tools.spread_proxy import ProxyClient

ROOT = Path(__file__).resolve().parent.parent
AGES = ROOT / "out" / "world_ages.json"
RUNS = ROOT / "data" / "scrape" / "runs"
HOUR, DAY = 60, 24 * 60
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def load_ages() -> dict[str, dict]:
    """worldId -> {"firstSeen": ISO time, "now": world minute at the last look or None}."""
    try:
        return json.loads(AGES.read_text())
    except FileNotFoundError, json.JSONDecodeError:
        return {}


def save_ages(ages: dict[str, dict]) -> None:
    AGES.parent.mkdir(parents=True, exist_ok=True)
    AGES.write_text(json.dumps(ages, indent=2, sort_keys=True) + "\n")


def known_seed(world: dict) -> str:
    """The seed from a saved week of this world, or of the world that it was copied from; else "?"."""
    for world_id in (world["worldId"], world.get("parent")):
        if world_id:
            for folder in RUNS.glob(f"L*/*/{world_id}"):
                return folder.parent.name
    return "?"


def clock(minute: int | None) -> str:
    """A world minute as weekday and time of the week, minute 0 being Monday 00:00."""
    if minute is None:
        return "?"
    day, rest = divmod(minute, DAY)
    name = DAYS[day % 7] if day < 7 else f"day {day}"
    return f"{name} {rest // HOUR:02d}:{rest % HOUR:02d}"


def what(world: dict) -> str:
    if world["kind"] == "final":
        return "final"
    if world.get("boardRun") is not None:
        return f"ranking run {world['boardRun']} of round {world.get('season')}"
    if world.get("parent"):
        return f"copy of {world['parent']}"
    return "practice"


def world_minute(client: ProxyClient, world_id: str) -> int | None:
    try:
        return retrying(lambda: client.world(world_id).snapshot())["now"]
    except SpreadError as error:
        print(f"  could not read {world_id}: {error}", file=sys.stderr)
        return None


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m tools.kill_old_worlds",
        description="Lists the team's open practice worlds older than --minutes, and deletes them with --yes. "
        "The server gives no creation time, so a world's age counts from the first time this tool saw it open "
        "(kept in out/world_ages.json): the first run finds nothing old. Ranking runs (--board) are skipped unless "
        "--include-board is given, because each can be played only once and a deleted run still counts with its "
        "score at its end. Finals are always skipped: the server does not delete them. Set SPREAD_URL and "
        "SPREAD_KEY first (add --env-file .env after uv run).",
    )
    parser.add_argument("--minutes", type=float, default=15, help="age limit in minutes (default: 15)")
    parser.add_argument("--yes", action="store_true", help="delete the listed worlds; without it nothing changes")
    parser.add_argument(
        "--include-board",
        action="store_true",
        help="also delete open ranking runs: each can be played only once, and the deleted run still counts on the "
        "rankings with its score at its end",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if not os.environ.get("SPREAD_KEY"):
        sys.exit("kill_old_worlds: SPREAD_KEY is not set. Set it, or add --env-file .env after uv run.")
    client = ProxyClient()
    now = datetime.now(UTC)
    worlds: list[Any] = [w for w in retrying(client.worlds) if not w["ended"]]

    # The age of each open world, from the first time it was seen; worlds that have ended or are gone are forgotten.
    seen = load_ages()
    ages = {w["worldId"]: seen.get(w["worldId"]) or {"firstSeen": now.isoformat(), "now": None} for w in worlds}
    new = sum(1 for w in worlds if w["worldId"] not in seen)

    def minutes_old(world: dict) -> float:
        return (now - datetime.fromisoformat(ages[world["worldId"]]["firstSeen"])).total_seconds() / 60

    old = sorted((w for w in worlds if minutes_old(w) >= args.minutes), key=minutes_old, reverse=True)
    print(f"{len(worlds)} open worlds, {len(old)} seen open for {args.minutes:g} minutes or more.")
    if new:
        print(f"{new} seen for the first time: their age counts from now.")

    doomed = []
    for world in old:
        world_id, kind = world["worldId"], what(world)
        skip = None
        if world["kind"] == "final":
            skip = "skipped: the server does not delete finals"
        elif world.get("boardRun") is not None and not args.include_board:
            skip = "skipped: a ranking run, add --include-board to delete it"
        minute = None if world["kind"] == "final" else world_minute(client, world_id)
        last = ages[world_id].get("now")
        moved = (
            "" if minute is None or last is None else (", clock moved since last look" if minute != last else ", idle")
        )
        ages[world_id]["now"] = minute
        print(
            f"  {world_id}  L{world['level']}  seed {known_seed(world)}  {minutes_old(world):.0f} min  {kind}, "
            f"at {clock(minute)}{moved}" + (f"  ({skip})" if skip else "")
        )
        if not skip:
            doomed.append(world_id)
    save_ages(ages)

    if not doomed:
        return
    if not args.yes:
        print(f"Nothing deleted. Add --yes to delete these {len(doomed)} worlds.")
        return
    failed = 0
    for world_id in doomed:
        try:
            retrying(client.world(world_id).delete)
            print(f"Deleted {world_id}.")
            ages.pop(world_id, None)
        except SpreadError as error:
            failed += 1
            print(f"Could not delete {world_id}: {error}", file=sys.stderr)
    save_ages(ages)
    print(f"Deleted {len(doomed) - failed} of {len(doomed)} worlds.")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
