"""Rehearses the final on a practice world. A second client moves the world's clock as the final's clock runs, sped
up, while the ladder plays it the way it plays the final: from the live event stream, rebuilding its books first.
`--restart-at` stops the desk at a world minute and starts a new one, which must rebuild from the world.

    uv run ladder/rehearse.py --seed spread-1                         # a whole week, 3 times the final's speed
    uv run ladder/rehearse.py --seed spread-1 --restart-at 3000       # and a restart on Tuesday 02:00

The week is saved like every other online run (record.py), under the policy `ladder`.
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:] = [str(HERE.parent)] + [p for p in sys.path if Path(p or ".").resolve() != HERE]

import argparse  # after the path above
import threading
import time

from ladder import main as ladder_main
from ladder.desk import Desk
from ladder.rides import TOP_RUNG
from record import Recorder
from spread_proxy import ProxyClient

DAY, HOUR = 24 * 60, 60
TICK = 0.5  # real seconds between two moves of the clock


def seconds_per_hour(now: int) -> float:
    """The final's clock (HANDBOOK.md): 18 real seconds a weekday hour from 06:00 to 22:00, 6 a Saturday hour, 9 an
    hour of the last Monday, and 3 an hour at night, on Sunday, and after the last Monday's 22:00."""
    day, hour = now // DAY, now % DAY // HOUR
    if day >= 8 or (day == 7 and hour >= 22) or day % 7 == 6 or not 6 <= hour < 22:
        return 3.0
    return 6.0 if day == 5 else 9.0 if day == 7 else 18.0


class Clock(threading.Thread):
    """Moves the world's clock as the final's runs, `speed` times faster, with a client of its own."""

    def __init__(self, world_id: str, ends_at: int, now: int, speed: float):
        super().__init__(daemon=True)
        self.world = ProxyClient().world(world_id)
        self.ends_at, self.now, self.speed = ends_at, now, speed
        self.error: BaseException | None = None

    def run(self) -> None:
        try:
            while self.now < self.ends_at:
                minutes = max(1, round(TICK * self.speed * HOUR / seconds_per_hour(self.now)))
                started = time.monotonic()
                self.now = self.world.advance(to=min(self.ends_at, self.now + minutes))["now"]
                time.sleep(max(0.0, TICK - (time.monotonic() - started)))
        except BaseException as error:  # noqa: BLE001  (reported by the main thread)
            self.error = error


class Restart(Exception):
    """Stops the desk, as a crash in the final would."""


def main() -> None:
    parser = argparse.ArgumentParser(description="Rehearses the final on a practice world with the ride ladder.")
    parser.add_argument("--level", type=int, choices=range(1, 9), default=8)
    parser.add_argument("--seed", help="any text; the same seed gives the same world")
    parser.add_argument("--rung", type=int, default=TOP_RUNG, help=f"the hardest rung to take (default {TOP_RUNG})")
    parser.add_argument("--speed", type=float, default=3.0, help="times the final's clock (default 3)")
    parser.add_argument("--restart-at", type=int, help="stop the desk at this world minute and start a new one")
    args = parser.parse_args()
    client = ProxyClient()
    world = ladder_main.create(client, args.level, args.seed, False)
    print(f"Practice world {world.id}, level {args.level}. Rehearsing the final at rung {args.rung}.", flush=True)
    snapshot = world.snapshot()
    clock = Clock(world.id, snapshot["endsAt"], snapshot["now"], args.speed)
    # The desk reads the final's clock when the stream is quiet: here it is the rehearsal clock.
    client.final = lambda: {"worldId": world.id, "startsAt": "", "now": clock.now}  # type: ignore[method-assign]
    if args.restart_at is not None:
        tick = Desk.tick

        def crashing_tick(desk: Desk) -> None:
            if desk.now >= args.restart_at and not getattr(Desk, "restarted", False):
                Desk.restarted = True  # type: ignore[attr-defined]
                raise Restart
            tick(desk)

        Desk.tick = crashing_tick  # type: ignore[method-assign]
    try:
        recorder = Recorder(world, args.level, args.seed, "practice", policy=ladder_main.POLICY)
        clock.start()
        while True:
            try:
                ladder_main.play_final(world, args.rung)
                break
            except Restart:
                print(f"Restart at minute {clock.now}: a new desk rebuilds its books from the world.", flush=True)
        clock.join()
        if clock.error is not None:
            raise clock.error
    except BaseException:
        world.delete()
        print(f"Stopped. Practice world {world.id} is deleted.", file=sys.stderr, flush=True)
        raise
    score = world.score()
    ladder_main.report("End", score)
    print("Ranked." if score["ranked"] else "Not ranked.", flush=True)
    recorder.save()


if __name__ == "__main__":
    main()
