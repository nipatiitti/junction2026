"""Plays many practice weeks on different seeds and levels, and saves each week's raw data for an offline model
of the server. `stats.py` turns the saved weeks into distributions. README.md says how to run both.

    uv run scrape.py --policy passive --levels 6,7,8 --seeds 20

Each week goes to <out>/L<level>/<seed>/: events.jsonl.gz (every event), reveal.json.gz, snapshot.json.gz (the
orders and gigs at the end), drivers.json.gz, score.json and meta.json. A week that has meta.json is skipped, so a
stopped scrape goes on where it was.
"""

from __future__ import annotations

import argparse
import gzip
import http.client
import json
import os
import random
import re
import shutil
import ssl
import sys
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from spread.client import Client, SpreadError, Unreachable, World
from spread.types import Order, PriceRequest

from db import add_week, connect, load_folders
from dispatch import WAKE_ON, Desk
from stats import load_week

POLICIES = ("passive", "starter", "explore")
PRACTICE_SLOTS = 8  # a team holds at most 8 practice worlds that have not ended


def bypasses_proxy(host: str, no_proxy: str) -> bool:
    """True when NO_PROXY names the host, or a domain it belongs to."""
    for entry in (e.strip().lstrip("*").lower() for e in no_proxy.split(",")):
        if entry and (host == entry.lstrip(".") or host.endswith(entry if entry.startswith(".") else "." + entry)):
            return True
    return False


class ProxyClient(Client):
    """The kit's client, sent through HTTPS_PROXY when one is set, and counting its requests. In a Claude Code cloud
    session the proxy adds the team key, so SPREAD_KEY can be a placeholder there."""

    def __init__(self, url: str | None = None, key: str | None = None):
        super().__init__(url, key)
        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        no_proxy = os.environ.get("NO_PROXY") or os.environ.get("no_proxy") or ""
        host = self._parts.hostname or ""
        use = proxy and self._parts.scheme == "https" and not bypasses_proxy(host, no_proxy)
        self.proxy = urlsplit(proxy) if use else None
        self.requests = 0

    def call(self, method: str, path: str, body: Any = None, actions: int = 0) -> Any:
        self.requests += 1
        return super().call(method, path, body, actions)

    def _send(self, method: str, path: str, payload: bytes | None, headers: dict):
        # The kit's _send, with the connection opened through the proxy. Retries a kept-alive connection that the
        # server closed while it was idle: that request never arrived.
        while True:
            reused = self._connection is not None
            if self._connection is None:
                self._connection = self._connect()
            try:
                self._connection.request(method, self._parts.path + path, payload, headers)
                response = self._connection.getresponse()
                return response.status, response.headers, response.read()
            except BaseException as error:
                self._connection.close()
                self._connection = None
                if reused and isinstance(error, (ConnectionResetError, BrokenPipeError)):
                    continue
                if isinstance(error, (OSError, http.client.HTTPException)):
                    raise Unreachable(0, f"Cannot reach {self.url}: {error}") from error
                raise

    def _connect(self) -> http.client.HTTPConnection:
        if self.proxy is None:
            kind = http.client.HTTPSConnection if self._parts.scheme == "https" else http.client.HTTPConnection
            return kind(self._parts.netloc, timeout=20)
        connection = http.client.HTTPSConnection(
            self.proxy.hostname, self.proxy.port or 80, timeout=20, context=ssl.create_default_context()
        )
        connection.set_tunnel(self._parts.hostname, self._parts.port or 443)
        return connection


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
        actions, desk.outbox = desk.outbox, []
        step = world.advance(until=WAKE_ON, max=ends_at, actions=actions)
        desk.read_results(actions, step["results"])
        desk.now = step["now"]
        for event in step["events"]:
            desk.handle(event)


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


def save_week(target: Path, world: World, drivers: list, meta: dict) -> dict:
    """Writes the week to a temporary folder, then renames it, so a folder with meta.json is always complete.
    `drivers` is the driver list from the start of the week, as a system sees it."""
    events = all_events(world)
    files = {
        "reveal.json.gz": world.reveal(),
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


class Slots:
    """Creates practice worlds without taking the team's last free slots, which teammates may need."""

    def __init__(self, keep_free: int):
        self.keep_free, self.lock = keep_free, threading.Lock()

    def create(self, client: Client, level: int, seed: str) -> World:
        while True:
            with self.lock:
                open_worlds = sum(1 for w in client.worlds() if not w["ended"])
                if open_worlds < PRACTICE_SLOTS - self.keep_free:
                    try:
                        return client.create(level=level, seed=seed)
                    except SpreadError as error:
                        if error.status != 409:
                            raise
            time.sleep(5)


def safe_name(seed: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", seed)


def scrape_week(
    client: ProxyClient, slots: Slots, out: Path, level: int, seed: str, policy: str, args: argparse.Namespace
) -> dict | None:
    """Plays and saves one week. None when it was saved before."""
    target = out / f"L{level}" / safe_name(seed)
    if (target / "meta.json").exists():
        return None
    started, requests_before = time.monotonic(), client.requests
    world = slots.create(client, level, seed)
    try:
        drivers = world.roster()
        if policy == "passive":
            play_passive(world)
        else:
            now = world.snapshot()["now"]
            desk = (
                Desk(world, level, now)
                if policy == "starter"
                else ExploreDesk(world, level, now, random.Random(f"{seed}:{level}"), args.quote_range, args.fee_range)
            )
            play_desk(world, desk)
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
        try:  # a world left behind holds one of the team's practice slots
            world.delete()
        except SpreadError:
            pass
        raise
    meta["seconds"] = round(time.monotonic() - started, 1)
    meta["requests"] = client.requests - requests_before
    write_json(target / "meta.json", meta)
    return meta


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
            pool.shutdown(wait=False, cancel_futures=True)
            sys.exit(
                "Stopping: the weeks in play finish and are saved, the rest are cancelled. A new run skips saved weeks."
            )
    if failed:
        sys.exit(f"{failed} weeks failed; run the same command again to retry them.")


if __name__ == "__main__":
    main()
