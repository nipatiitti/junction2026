"""The loop: plays a practice week or the final with the desk, prints the starter's lines, and saves the week.

A practice world stands still until we advance it. Each step sends the desk's actions with the advance, which moves
the clock to the next event the desk must answer, or to the next minute the desk wants to look. In the final the
clock runs by itself: the desk answers each event of the live stream as it comes.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections import Counter

from spread.client import Client, SpreadError, Unreachable, World
from spread.types import Score

from ladder.desk import Desk
from ladder.rides import RUNGS, TOP_RUNG
from record import Recorder
from spread_proxy import ProxyClient

DAY = 24 * 60
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
POLICY = "ladder"  # the policy of the saved weeks, so the database tells them from dispatch.py's
SLOT_WAIT, SLOT_TRIES = 15, 120  # seconds between tries for a free practice slot, and how many tries: 30 minutes


def play_practice(world: World, level: int, rung: int) -> Counter[str]:
    """Steps the world from one stop of the clock to the next, and stops at each midnight for a report. Returns
    the reason for each stop: the kind of event that stopped it, "look" (the desk asked to look), "midnight"
    or "end"."""
    snapshot = world.snapshot()
    desk, ends_at = Desk(world, level, snapshot["now"], rung), snapshot["endsAt"]
    desk.rejoin(snapshot, [])
    stops: Counter[str] = Counter()
    while desk.now < ends_at:
        day, midnight = desk.now // DAY, (desk.now // DAY + 1) * DAY
        until, look_at = desk.waking()
        # One request a step: the advance applies the outbox at the current minute, then moves the clock.
        actions, desk.outbox = desk.outbox, []
        target = max(desk.now + 1, min(ends_at, midnight, look_at))
        step = world.advance(until=until, max=target, actions=actions)
        desk.now = step["now"]  # what the results add to the outbox goes out at this minute
        desk.read_results(actions, step["results"])
        woke = next((e["kind"] for e in step["events"] if e["kind"] in until and e["at"] == desk.now), None)
        stops[woke or ("end" if desk.now >= ends_at else "midnight" if desk.now == midnight else "look")] += 1
        for event in step["events"]:
            desk.handle(event)
        desk.tick()
        if desk.now // DAY > day:
            report(WEEKDAYS[day % 7], world.score())
    print(desk.summary(), flush=True)
    return stops


def play_final(world: World, rung: int) -> None:
    """Rebuilds the books from the world, then answers events as they come. After a second without an event,
    it reads the clock, so the desk's own timers still run."""
    history = world.events()
    snapshot = world.snapshot()
    if snapshot["now"] >= snapshot["endsAt"]:
        return
    level = next((w["level"] for w in world.client.worlds() if w["worldId"] == world.id), 8)
    desk = Desk(world, level, snapshot["now"], rung)
    desk.rejoin(snapshot, history)
    desk.tick()
    desk.send()
    for event in world.stream(after=history[-1]["seq"] if history else -1, idle=1.0):
        day = desk.now // DAY
        desk.now = world.client.final()["now"] if event is None else max(desk.now, event["at"])
        if event is not None:
            desk.handle(event)
        desk.tick()
        desk.send()
        if desk.now // DAY > day:
            report(WEEKDAYS[day % 7], world.score())
        if desk.now >= snapshot["endsAt"]:
            print(desk.summary(), flush=True)
            return


def report(label: str, score: Score) -> None:
    """The starter's line for a day or for the end of the week."""
    orders = (
        f"{score['wonOrders']:>4} orders  {score['onTimeShare']:6.1%} on time  "
        f"{score['undeliveredShare']:5.1%} not delivered"
    )
    print(
        f"{label:<9}  margin €{score['marginCents'] / 100:>11,.2f}  revenue €{score['revenueCents'] / 100:>11,.2f}  "
        f"{orders}",
        flush=True,
    )


def create(client: Client, level: int, seed: str | None, board: bool) -> World:
    """A new practice world. While the team's eight practice slots are all taken, for example by teammates' runs,
    waits for one to free, as the bench does: their worlds are not ours to delete."""
    for _ in range(SLOT_TRIES):
        try:
            return client.create(level=level, seed=seed, board=board)
        except SpreadError as error:
            if error.status != 409 or "practice worlds" not in str(error):
                raise
            print(f"All practice slots are taken. Trying again in {SLOT_WAIT} seconds.", file=sys.stderr, flush=True)
            time.sleep(SLOT_WAIT)
    return client.create(level=level, seed=seed, board=board)


def next_final(client: Client) -> World:
    """Our copy of the final that is set or runs now. Waits while none is set and while the last one has ended: the
    organisers set a test final 15 minutes before its start, and the final 30 minutes before."""
    said = False
    while True:
        try:
            world: World | None = client.world(client.final()["worldId"])
        except SpreadError as error:
            if error.status != 404:
                raise
            world = None
        if world is not None:
            snapshot = world.snapshot()
            if snapshot["now"] < snapshot["endsAt"]:
                return world
        if not said:
            print("No final is set. Waiting for it: the organisers set a test final 15 minutes before its start.")
            said = True
        time.sleep(10)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plays a Spread world with the ride ladder. Set SPREAD_URL and SPREAD_KEY first."
    )
    parser.add_argument("--level", type=int, choices=range(1, 9), default=8, help="the practice level (default 8)")
    parser.add_argument("--seed", help="any text; the same seed gives the same world")
    parser.add_argument("--board", action="store_true", help="play our next ranking run; it counts in the rankings")
    parser.add_argument("--final", action="store_true", help="play our copy of the final from the live stream")
    parser.add_argument(
        "--rung",
        type=int,
        choices=range(1, len(RUNGS) + 1),
        default=int(os.environ.get("LADDER_RUNG", TOP_RUNG)),  # the bench passes only --level and --seed
        help=f"the hardest rung of rides to take (default $LADDER_RUNG, else {TOP_RUNG}): "
        + "; ".join(f"{n} {name}" for n, name in enumerate(RUNGS, start=1)),
    )
    args = parser.parse_args()
    try:
        client = ProxyClient()
        score, stops, recorder = None, None, None
        if args.final:
            world = None
            # A server restart drops every connection: the desk then rebuilds its books, as after its own restart.
            while True:
                try:
                    if world is None:
                        world = next_final(client)
                        print(f"Final world {world.id}, rung {args.rung}.", flush=True)
                        level = next((w["level"] for w in client.worlds() if w["worldId"] == world.id), 8)
                        recorder = Recorder(world, level, None, "final", policy=POLICY)
                    play_final(world, args.rung)
                    score = world.score()
                    break
                except Unreachable as error:
                    print(f"spread: {error}. Trying again in 5 seconds.", file=sys.stderr, flush=True)
                    time.sleep(5)
        else:
            world = create(client, args.level, args.seed, args.board)
            name = f"{'Ranking run' if args.board else 'Practice world'} {world.id}"
            after_stop = (
                "Ctrl-C or an error stops the system: the run then plays to its end without it, and counts."
                if args.board
                else "Ctrl-C or an error stops the run and deletes the world."
            )
            # The bench reads the world id from this first line.
            print(f"{name}, level {args.level}. Rung {args.rung}. {after_stop}", flush=True)
            try:
                recorder = Recorder(world, args.level, args.seed, "board" if args.board else "practice", policy=POLICY)
                stops = play_practice(world, args.level, args.rung)
            except BaseException as error:  # a world left behind holds one of the team's eight practice slots
                try:
                    world.delete()
                    deleted = True
                except SpreadError:
                    deleted = False
                left = (
                    f"{name} plays to its end without the system, and counts."
                    if args.board
                    else f"{name} is deleted."
                    if deleted
                    else f"{name} is not deleted: it holds one of the team's eight practice slots."
                )
                if isinstance(error, KeyboardInterrupt):
                    sys.exit(f"Stopped. {left}")
                print(f"Stopped by the error below. {left}", file=sys.stderr)
                raise
        score = score or world.score()
        report("End", score)
        if stops is not None:
            print(
                f"Requests  {client.requests:,}. Stops {stops.total():,}: "
                + ", ".join(f"{reason} {n:,}" for reason, n in stops.most_common())
            )
        print(
            "Ranked."
            if score["ranked"]
            else "Not ranked: no order won."
            if score["wonOrders"] == 0
            else "Not ranked: the delivery minimum is 90% of the orders on time."
        )
        if recorder is not None:
            recorder.save()
    except SpreadError as error:
        sys.exit(f"spread: {error}")
    except KeyboardInterrupt:
        sys.exit("Stopped. The final world keeps running without the system; start it again with --final.")
