"""Plays many practice weeks on different seeds and levels, and saves each week's raw data for an offline model
of the server. `stats.py` turns the saved weeks into distributions. README.md says how to run both.

    uv run scrape.py --policy passive --levels 6,7,8 --seeds 20

Each week goes to <out>/L<level>/<seed>/: events.jsonl.gz (every event), reveal.json.gz, snapshot.json.gz (the
orders and gigs at the end), drivers.json.gz, score.json and meta.json. A week that has meta.json is skipped, so a
stopped scrape goes on where it was. Ctrl-C, SIGTERM and SIGHUP delete the worlds in play; a week folder with only
world.json names a world that a killed scrape left behind, and the next run saves it or deletes it.
"""

from __future__ import annotations

import argparse
import json
import random
import signal
import sys
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from spread.client import Client, SpreadError, World
from spread.types import Order, PriceRequest

from db import add_week, connect, load_folders
from dispatch import WAKE_ON, Desk
from record import safe_name, save_week, write_json
from spread_proxy import ProxyClient, bypasses_proxy  # noqa: F401  (tests import bypasses_proxy from here)
from stats import load_week

POLICIES = ("passive", "starter", "explore")
PRACTICE_SLOTS = 8  # a team holds at most 8 practice worlds that have not ended
STOP = threading.Event()  # set on Ctrl-C or a kill: every week in play stops at its next request and deletes its world
WORLD = "world.json"  # in a week's folder from the world's creation until the week is saved: the world it plays


class Stopped(Exception):
    """The scrape was stopped before the week ended."""


class ExploreDesk(Desk):
    """The starter's desk with random prices, so the data shows how dealers and drivers answer them. It quotes every
    option at a random multiple of its list price, and pays each order's gigs a random multiple of the starter's fees
    (one multiple an order, so reposts and steep fees keep it). The same seed and level draw the same multiples."""

    def __init__(
        self,
        world: World,
        level: int,
        now: int,
        rng: random.Random,
        quote_range: tuple[float, float],
        fee_range: tuple[float, float],
    ):
        super().__init__(world, level, now)
        self.rng, self.quote_range, self.fee_range = rng, quote_range, fee_range
        self.fee_factor: dict[str, float] = {}  # order id -> its fee multiple

    def quote(self, request: PriceRequest) -> None:
        self.requests[request["id"]] = request
        prices = {
            o["kind"]: max(1, round(o["listPriceCents"] * self.rng.uniform(*self.quote_range)))
            for o in request["options"]
        }
        self.outbox.append({"type": "quote", "requestId": request["id"], "prices": prices})

    def fees_for(self, order: Order, cars: int):
        factor = self.fee_factor.setdefault(order["id"], self.rng.uniform(*self.fee_range))
        return [{**s, "feeCents": max(1, round(s["feeCents"] * factor))} for s in super().fees_for(order, cars)]


def play_passive(world: World) -> None:
    """No quotes and no gigs: one advance to the end. The week shows its requests, forecasts and drivers."""
    world.advance(to=world.snapshot()["endsAt"])


def play_desk(world: World, desk: Desk) -> None:
    """As dispatch.play_practice, without the daily reports: from one event that needs an answer to the next."""
    ends_at = world.snapshot()["endsAt"]
    while desk.now < ends_at:
        if STOP.is_set():
            raise Stopped()
        actions, desk.outbox = desk.outbox, []
        step = world.advance(until=WAKE_ON, max=ends_at, actions=actions)
        desk.read_results(actions, step["results"])
        desk.now = step["now"]
        for event in step["events"]:
            desk.handle(event)


class Slots:
    """Creates practice worlds without taking the team's last free slots, which teammates may need."""

    def __init__(self, keep_free: int):
        self.keep_free, self.lock = keep_free, threading.Lock()

    def create(self, client: Client, level: int, seed: str) -> World:
        while True:
            if STOP.is_set():
                raise Stopped()
            with self.lock:
                open_worlds = sum(1 for w in client.worlds() if not w["ended"])
                if open_worlds < PRACTICE_SLOTS - self.keep_free:
                    try:
                        return client.create(level=level, seed=seed)
                    except SpreadError as error:
                        if error.status != 409:
                            raise
            STOP.wait(5)


def left_behind(client: Client, target: Path) -> tuple[World, list] | None:
    """The world that a killed scrape left in this week's folder: the world and its starting driver list when it
    ended, so it only needs saving. A world that had not ended is deleted, to free its slot and play the week again."""
    marker = target / WORLD
    if not marker.exists():
        return None
    noted = json.loads(marker.read_text())
    world = client.world(noted["worldId"])
    summary = next((w for w in client.worlds() if w["worldId"] == world.id), None)
    if summary is not None and summary["ended"]:
        return world, noted["drivers"]
    if summary is not None:
        try:
            world.delete()
        except SpreadError:
            pass
    marker.unlink()
    return None


def scrape_week(
    client: ProxyClient, slots: Slots, out: Path, level: int, seed: str, policy: str, args: argparse.Namespace
) -> dict | None:
    """Plays and saves one week. None when it was saved before."""
    target = out / f"L{level}" / safe_name(seed)
    if (target / "meta.json").exists():
        return None
    started, requests_before = time.monotonic(), client.requests
    found = left_behind(client, target)
    world = found[0] if found else slots.create(client, level, seed)
    ended = found is not None
    try:
        if found:
            drivers = found[1]
        else:
            # Noted before the week is played, so a run that is killed can be cleaned up by the next one.
            target.mkdir(parents=True, exist_ok=True)
            write_json(target / WORLD, {"worldId": world.id, "drivers": []})
            drivers = world.roster()
            write_json(target / WORLD, {"worldId": world.id, "drivers": drivers})
            play(world, level, seed, policy, args)
            ended = True
        meta = {
            "seed": seed,
            "level": level,
            "policy": policy,
            "worldId": world.id,
            "quoteRange": list(args.quote_range) if policy == "explore" else None,
            "feeRange": list(args.fee_range) if policy == "explore" else None,
        }
        meta = save_week(target, world, drivers, meta)
    except BaseException:
        # A world that has not ended holds one of the team's practice slots. An ended one holds none: it stays, with
        # its world.json, and the next run saves it.
        if not ended:
            try:
                world.delete()
            except SpreadError:
                pass
            (target / WORLD).unlink(missing_ok=True)
        raise
    meta["seconds"] = round(time.monotonic() - started, 1)
    meta["requests"] = client.requests - requests_before
    write_json(target / "meta.json", meta)
    return meta


def play(world: World, level: int, seed: str, policy: str, args: argparse.Namespace) -> None:
    if policy == "passive":
        play_passive(world)
        return
    now = world.snapshot()["now"]
    desk = (
        Desk(world, level, now)
        if policy == "starter"
        else ExploreDesk(world, level, now, random.Random(f"{seed}:{level}"), args.quote_range, args.fee_range)
    )
    play_desk(world, desk)


stopping = False


def stop_on_signal(signum: int, frame: Any) -> None:
    """Stops the scrape on the first signal. Later ones are ignored, so they cannot cut the deletions short: timeout
    and uv can each send one."""
    global stopping
    if stopping:
        return
    stopping = True
    raise KeyboardInterrupt


def parse_range(text: str) -> tuple[float, float]:
    low, high = (float(x) for x in text.split(","))
    if not 0 < low <= high:
        raise argparse.ArgumentTypeError(f"{text}: give two numbers, low,high, with 0 < low <= high")
    return low, high


def parse_levels(text: str) -> list[int]:
    levels = [int(x) for x in text.split(",")]
    if any(not 1 <= level <= 8 for level in levels):
        raise argparse.ArgumentTypeError("levels are 1 to 8")
    return levels


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Plays practice weeks on many seeds and saves their raw data.")
    parser.add_argument("--policy", choices=POLICIES, default="passive", help="how to play each week (default passive)")
    parser.add_argument("--levels", type=parse_levels, default=[8], help="comma-separated levels, e.g. 6,7,8")
    parser.add_argument("--seeds", type=int, default=10, help="weeks per level (default 10)")
    parser.add_argument("--seed-prefix", default="scrape", help="seeds are <prefix>-<n> (default scrape)")
    parser.add_argument("--seed-start", type=int, default=1, help="the first n (default 1)")
    parser.add_argument("--out", type=Path, help="output folder (default out/scrape/<policy>)")
    parser.add_argument("--workers", type=int, default=4, help="weeks played at once (default 4)")
    parser.add_argument("--keep-free", type=int, default=2, help="practice slots left for teammates (default 2)")
    parser.add_argument(
        "--quote-range", type=parse_range, default=(0.7, 1.8), help="explore: quote / list price, low,high"
    )
    parser.add_argument("--fee-range", type=parse_range, default=(0.6, 1.6), help="explore: fee / starter fee")
    parser.add_argument(
        "--db", type=Path, default=Path("out/spread.sqlite"), help="SQLite database to add each week to (db.py)"
    )
    parser.add_argument("--no-db", action="store_true", help="save the week folders only")
    args = parser.parse_args(argv)
    if args.workers > PRACTICE_SLOTS - args.keep_free:
        parser.error(f"--workers can be at most {PRACTICE_SLOTS} - --keep-free")
    out: Path = args.out or Path("out/scrape") / args.policy
    out.mkdir(parents=True, exist_ok=True)

    try:
        first = ProxyClient()
        if not (out / "map.json").exists():
            write_json(out / "map.json", first.map())
    except SpreadError as error:
        sys.exit(f"spread: {error}")
    database = None if args.no_db else connect(args.db)
    if database is not None:
        load_folders(database, [out])  # the map, and weeks saved before without the database
    slots, local = Slots(args.keep_free), threading.local()

    def job(level: int, seed: str) -> Callable[[], dict | None]:
        def run() -> dict | None:
            if not hasattr(local, "client"):  # one connection a thread: http.client is not thread-safe
                local.client = ProxyClient()
            return scrape_week(local.client, slots, out, level, seed, args.policy, args)

        return run

    # A kill (timeout, a closed terminal, a stopped session) stops the scrape as Ctrl-C does, so the weeks in play
    # delete their worlds and free the team's slots.
    for name in ("SIGINT", "SIGTERM", "SIGHUP"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), stop_on_signal)
    seeds = [f"{args.seed_prefix}-{n}" for n in range(args.seed_start, args.seed_start + args.seeds)]
    weeks = [(level, seed) for level in args.levels for seed in seeds]
    print(f"{len(weeks)} weeks, policy {args.policy}, {args.workers} at once, into {out}", flush=True)
    failed = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(job(level, seed)): (level, seed) for level, seed in weeks}
        try:
            for future in as_completed(futures):
                level, seed = futures[future]
                try:
                    meta = future.result()
                except SpreadError as error:
                    failed += 1
                    print(f"L{level} {seed}: failed: {error}", file=sys.stderr, flush=True)
                    continue
                if meta is None:
                    print(f"L{level} {seed}: saved before, skipped", flush=True)
                    continue
                if database is not None:
                    add_week(database, load_week(out / f"L{level}" / safe_name(seed)), str(out))
                score = meta["score"]
                print(
                    f"L{level} {seed}: {meta['events']:>6} events, {meta['requests']:>5} requests, "
                    f"{meta['seconds']:>6}s, margin €{score['marginCents'] / 100:>11,.2f}, "
                    f"{score['wonOrders']:>4} orders, {score['onTimeShare']:.1%} on time",
                    flush=True,
                )
        except KeyboardInterrupt:
            STOP.set()
            print("Stopping: deleting the worlds of the weeks in play.", file=sys.stderr, flush=True)
            pool.shutdown(wait=True, cancel_futures=True)
            sys.exit("Stopped. Saved weeks stay, and the same command again skips them.")
    if failed:
        sys.exit(f"{failed} weeks failed; run the same command again to retry them.")


if __name__ == "__main__":
    main()
