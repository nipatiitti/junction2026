"""Plays many practice weeks on different seeds and levels, and saves each week's raw data for an offline model
of the server. `stats.py` turns the saved weeks into distributions. README.md says how to run both.

    uv run scrape.py --policy passive --levels 6,7,8 --seeds 20

Each week goes to <out>/L<level>/<seed>/: events.jsonl.gz (every event), reveal.json.gz, snapshot.json.gz (the
orders and gigs at the end), drivers.json.gz, score.json and meta.json (every setting of the scrape), and what the
server keeps no record of: actions.jsonl.gz (each action we sent, with its minute and result), rosters.jsonl.gz (the
driver list at each midnight and at the end) and positions.jsonl.gz (our drivers' positions, with --sample-every).
A week that has meta.json is skipped, so a stopped scrape goes on where it was. Give each experiment its own --tag:
its weeks then go to their own folder, out/scrape/<policy>-<tag>, and are not skipped as saved before. Ctrl-C, SIGTERM and SIGHUP delete the worlds in play; a week folder with only
world.json names a world that a killed scrape left behind, and the next run saves it or deletes it.
"""

from __future__ import annotations

import argparse
import gzip
import json
import random
import re
import shutil
import signal
import subprocess
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
from dispatch import DAY, HOUR, WAKE_ON, Desk, pickups
from spread_proxy import ProxyClient, bypasses_proxy  # noqa: F401  (tests import bypasses_proxy from here)
from stats import load_week

POLICIES = ("passive", "starter", "explore")
PRACTICE_SLOTS = 8  # a team holds at most 8 practice worlds that have not ended
STOP = threading.Event()  # set on Ctrl-C or a kill: every week in play stops at its next request and deletes its world
WORLD = "world.json"  # in a week's folder from the world's creation until the week is saved: the world it plays
FEE_SHAPES = ("rising", "flat", "slow")
OFFER_KM = 30  # direct offers go to drivers whose home is this close to the pickup by road: the app's notice radius


class Stopped(Exception):
    """The scrape was stopped before the week ended."""


class Recorder:
    """What a week's reveal and events do not keep: every action that the desk sent, with its minute and result
    (the reveal keeps only the last quote, the snapshot only each gig's last fee schedule), the driver list at each
    midnight and at the end, and, when asked, the positions of our drivers. It wraps the world's `act` and
    `advance`, so every action is logged, also those that the desk sends at once."""

    def __init__(self, world: World, now: int):
        self.now = now
        self.actions: list[dict] = []
        self.rosters: list[dict] = []
        self.positions: list[dict] = []
        act, advance = world.act, world.advance
        inside = False  # advance sends its first actions through act: log them once, with advance

        def logged_act(actions):
            results = act(actions)
            if not inside:
                self.log(actions, results)
            return results

        def logged_advance(*args, actions=(), **kwargs):
            nonlocal inside
            inside, at = True, self.now
            try:
                step = advance(*args, actions=actions, **kwargs)
            finally:
                inside = False
            self.log(actions, step["results"], at)
            self.now = step["now"]
            return step

        world.act, world.advance = logged_act, logged_advance  # type: ignore[method-assign]

    def log(self, actions, results, at: int | None = None) -> None:
        for action, result in zip(actions, results):
            when = self.now if at is None else at
            self.actions.append({"seq": len(self.actions), "at": when, "action": action, "result": result})


class ExploreDesk(Desk):
    """The starter's desk with random prices, so the data shows how dealers and drivers answer them.

    - Quotes: each option of a request at its own random multiple of its list price. With a quote share below 1, only
      that share of requests; the others are declined (quoted at 10 times the list price), so the week does not win
      more cars than drivers can move, which would spoil the dealers' satisfaction and the delivery data.
    - Fees: one random multiple an order (reposts and steep fees keep it), on a fee shape that holds for the whole
      week, because drivers learn our fees: `rising` (the starter's), `flat` (the opening fee only) or `slow` (a
      linear rise from the opening fee to the cap times the typical fee, planned to end 3 hours before the order's
      lastPickupAt, when the deadline warning would come). After a deadline warning every shape goes steep.
    - Direct offers: each order's first gig goes, in the minute it is posted, as a direct offer to up to `offers` drivers who live near the
      pickup and fit the audience, each at its own random multiple of the typical fee.

    The same seed and level draw the same multiples."""

    def __init__(
        self,
        world: World,
        level: int,
        now: int,
        rng: random.Random,
        args: argparse.Namespace,
        roster: list[dict],
        world_map: dict,
    ):
        super().__init__(world, level, now)
        self.rng, self.args = rng, args
        self.fee_factor: dict[str, float] = {}  # order id -> its fee multiple
        self.offered: set[str] = set()  # the orders whose first gig went as direct offers
        self.offers_today: dict[tuple[str, int], int] = {}  # (driver, day) -> offers sent: at most 3 a day
        homes: dict[str, list[dict]] = {}
        for driver in roster:
            homes.setdefault(driver["homePlaceId"], []).append(driver)
        self.near: dict[str, list[dict]] = {}  # place -> the drivers who live near it
        for road in world_map["roads"]:
            if road["km"] <= OFFER_KM:
                self.near.setdefault(road["from"], []).extend(homes.get(road["to"], []))

    def quote(self, request: PriceRequest) -> None:
        self.requests[request["id"]] = request
        if self.args.quote_share < 1 and self.rng.random() >= self.args.quote_share:
            if self.level > 3:  # up to level 3 every quote wins: decline by not quoting
                first = request["options"][0]
                prices = {first["kind"]: 10 * first["listPriceCents"]}
                self.outbox.append({"type": "quote", "requestId": request["id"], "prices": prices})
            return
        prices = {
            o["kind"]: max(1, round(o["listPriceCents"] * self.rng.uniform(*self.args.quote_range)))
            for o in request["options"]
        }
        self.outbox.append({"type": "quote", "requestId": request["id"], "prices": prices})

    def fees_for(self, order: Order, cars: int):
        factor = self.fee_factor.setdefault(order["id"], self.rng.uniform(*self.args.fee_range))
        starter = [{**s, "feeCents": max(1, round(s["feeCents"] * factor))} for s in super().fees_for(order, cars)]
        shape = self.args.fee_shape
        if order["id"] in self.urgent or shape == "rising" or self.level == 1:
            return starter
        if shape == "flat":
            return starter[:1]
        # slow: a linear rise from the opening fee to the cap, ending when the deadline warning would come
        fee = self.requests[order["id"]]["referenceFeeCents"] * cars / len(order["legs"])
        opening, end_at = starter[0]["feeCents"], order["lastPickupAt"] - 3 * HOUR
        cap = max(opening, round(fee * self.args.fee_cap))
        if end_at - self.now < HOUR:
            return starter
        steps = min(48, (end_at - self.now) // 30 + 1)
        return [
            {
                "at": self.now + round(k * (end_at - self.now) / (steps - 1)),
                "feeCents": max(1, round(opening + (cap - opening) * k / (steps - 1))),
            }
            for k in range(steps)
        ]

    def read_results(self, actions, results) -> None:
        super().read_results(actions, results)
        if self.args.offers <= 0 or self.level < 3:  # direct offers come at level 3
            return
        for action, result in zip(actions, results):
            if action["type"] != "post" or result["ok"] is not True:
                continue
            order_id = action["stops"][0]["orderId"]
            if order_id in self.offered or order_id not in self.orders:
                continue
            self.offered.add(order_id)
            self.offer(self.orders[order_id], action, result["id"])

    def offer(self, order: Order, action: dict, gig_id: str) -> None:
        """Sends the gig to up to `offers` drivers near its first pickup, each at a random multiple of the typical fee."""
        pickup = order["legs"][action["stops"][0]["leg"]]["pickup"]["placeId"]
        audience, day = action["audience"], self.now // DAY
        fits = [
            d
            for d in self.near.get(pickup, [])
            if self.offers_today.get((d["id"], day), 0) < 3
            and (not audience["experienced"] or (d["rating"] >= 4.8 and d["completedGigs"] >= 50))
            and (not audience["manualLicence"] or d["licence"] == "manual")
        ]
        fee = self.requests[order["id"]]["referenceFeeCents"] * pickups(action) / len(order["legs"])
        for driver in self.rng.sample(fits, min(self.args.offers, 3, len(fits))):
            self.offers_today[(driver["id"], day)] = self.offers_today.get((driver["id"], day), 0) + 1
            cents = max(1, round(fee * self.rng.uniform(*self.args.offer_range)))
            self.outbox.append({"type": "offer", "gigId": gig_id, "driverId": driver["id"], "feeCents": cents})


def play_week(world: World, desk: Desk | None, recorder: Recorder, sample_every: int) -> None:
    """Plays to the end: without a desk (passive) with no actions, else from one event that needs an answer to the
    next, as dispatch.play_practice without the daily reports. Stops at each midnight for the driver list, and every
    `sample_every` minutes (0: never) for the positions of our drivers."""
    ends_at = world.snapshot()["endsAt"]
    midnight = (recorder.now // DAY + 1) * DAY
    sample_at = recorder.now + sample_every if sample_every and desk is not None else ends_at + 1
    while recorder.now < ends_at:
        if STOP.is_set():
            raise Stopped()
        stop = min(ends_at, midnight, sample_at)
        if desk is None:
            world.advance(to=stop)
        else:
            if isinstance(desk, ExploreDesk) and desk.args.offers and any(a["type"] == "post" for a in desk.outbox):
                # Posts first, so their direct offers go in the same minute, before an app driver books the gig.
                desk.send()
            actions, desk.outbox = desk.outbox, []
            step = world.advance(until=WAKE_ON, max=stop, actions=actions)
            desk.read_results(actions, step["results"])
            desk.now = step["now"]
            for event in step["events"]:
                desk.handle(event)
        if recorder.now >= midnight:
            recorder.rosters.append({"at": recorder.now, "drivers": world.roster()})
            midnight += DAY
        if recorder.now >= sample_at:
            recorder.positions.append({"at": recorder.now, "positions": world.snapshot()["driverPositions"]})
            sample_at = recorder.now + sample_every
    recorder.rosters.append({"at": recorder.now, "drivers": world.roster()})


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


def write_lines(path: Path, rows: list[dict]) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, separators=(",", ":")) + "\n")


def save_week(target: Path, world: World, drivers: list, meta: dict, recorder: Recorder | None) -> dict:
    """Writes the week to a temporary folder, then renames it, so a folder with meta.json is always complete.
    `drivers` is the driver list from the start of the week, as a system sees it. A week that a killed scrape left
    behind has no recorder: its actions, rosters and positions are lost, and meta.json says so (`recorded`)."""
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
    write_lines(partial / "events.jsonl.gz", events)
    if recorder is not None:
        write_lines(partial / "actions.jsonl.gz", recorder.actions)
        write_lines(partial / "rosters.jsonl.gz", recorder.rosters)
        if recorder.positions:
            write_lines(partial / "positions.jsonl.gz", recorder.positions)
    for name, data in files.items():
        write_json(partial / name, data)
    meta = {**meta, "events": len(events), "recorded": recorder is not None, "score": files["score.json"]}
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


def safe_name(seed: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", seed)


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
    recorder = None
    try:
        if found:
            drivers = found[1]
        else:
            # Noted before the week is played, so a run that is killed can be cleaned up by the next one.
            target.mkdir(parents=True, exist_ok=True)
            write_json(target / WORLD, {"worldId": world.id, "drivers": []})
            drivers = world.roster()
            write_json(target / WORLD, {"worldId": world.id, "drivers": drivers})
            recorder = play(world, level, seed, policy, args, drivers)
            ended = True
        explore = policy == "explore"
        meta = {
            "seed": seed,
            "level": level,
            "policy": policy,
            "tag": args.tag,
            "worldId": world.id,
            "quoteRange": list(args.quote_range) if explore else None,
            "feeRange": list(args.fee_range) if explore else None,
            "settings": {
                "quoteShare": args.quote_share if explore else None,
                "feeShape": args.fee_shape if explore else None,
                "feeCap": args.fee_cap if explore and args.fee_shape == "slow" else None,
                "offers": args.offers if explore else 0,
                "offerRange": list(args.offer_range) if explore and args.offers else None,
                "sampleEvery": args.sample_every if policy != "passive" else 0,
                "commit": COMMIT,
            },
        }
        meta = save_week(target, world, drivers, meta, recorder)
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


def play(world: World, level: int, seed: str, policy: str, args: argparse.Namespace, roster: list) -> Recorder:
    now = world.snapshot()["now"]
    recorder = Recorder(world, now)
    desk: Desk | None = None
    if policy == "starter":
        desk = Desk(world, level, now)
    elif policy == "explore":
        rng = random.Random(f"{seed}:{level}")
        desk = ExploreDesk(world, level, now, rng, args, roster, world.client.map())
    play_week(world, desk, recorder, args.sample_every)
    return recorder


def git_commit() -> str | None:
    """The commit of the scraper, so a week says which code played it."""

    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], check=False, capture_output=True, text=True, cwd=Path(__file__).parent)

    try:
        head, dirty = git("rev-parse", "HEAD"), git("status", "--porcelain")
    except OSError:
        return None
    return head.stdout.strip() + ("-dirty" if dirty.stdout.strip() else "") if head.returncode == 0 else None


COMMIT = git_commit()


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


def parse_share(text: str) -> float:
    share = float(text)
    if not 0 < share <= 1:
        raise argparse.ArgumentTypeError("the share is above 0 and at most 1")
    return share


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
    parser.add_argument("--tag", help="names the experiment: its folder is out/scrape/<policy>-<tag>")
    parser.add_argument("--out", type=Path, help="output folder (default out/scrape/<policy>[-<tag>])")
    parser.add_argument("--workers", type=int, default=4, help="weeks played at once (default 4)")
    parser.add_argument("--keep-free", type=int, default=2, help="practice slots left for teammates (default 2)")
    parser.add_argument(
        "--quote-range", type=parse_range, default=(0.7, 1.8), help="explore: quote / list price, low,high"
    )
    parser.add_argument("--fee-range", type=parse_range, default=(0.6, 1.6), help="explore: fee / starter fee")
    parser.add_argument(
        "--quote-share", type=parse_share, default=1.0, help="explore: share of requests quoted; others declined"
    )
    parser.add_argument(
        "--fee-shape", choices=FEE_SHAPES, default="rising", help="explore: rising (starter), flat or slow"
    )
    parser.add_argument("--fee-cap", type=float, default=2.5, help="explore, slow: the last fee / typical fee")
    parser.add_argument("--offers", type=int, default=0, help="explore: direct offers per new order, 0 to 3")
    parser.add_argument(
        "--offer-range", type=parse_range, default=(0.4, 1.6), help="explore: offer fee / typical fee, low,high"
    )
    parser.add_argument(
        "--sample-every", type=int, default=0, help="minutes between samples of our drivers' positions (0: none)"
    )
    parser.add_argument(
        "--db", type=Path, default=Path("out/spread.sqlite"), help="SQLite database to add each week to (db.py)"
    )
    parser.add_argument("--no-db", action="store_true", help="save the week folders only")
    args = parser.parse_args(argv)
    if not 0 <= args.offers <= 3:
        parser.error("--offers is 0 to 3: a gig holds at most three open direct offers")
    if args.workers > PRACTICE_SLOTS - args.keep_free:
        parser.error(f"--workers can be at most {PRACTICE_SLOTS} - --keep-free")
    out: Path = args.out or Path("out/scrape") / (f"{args.policy}-{args.tag}" if args.tag else args.policy)
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
