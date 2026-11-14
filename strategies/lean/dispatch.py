"""The lean system in Python: the TypeScript `lean` strategy (src/strategies/lean/) and the harness it plays in
(src/harness/), ported. See README.md next to this file.

Run it from the repository root: uv run strategies/lean/dispatch.py --level 8 --seed spread-1
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import asdict
from pathlib import Path

# Run as a file, Python looks for modules next to it; tools/ and strategies/ are at the root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spread.client import SpreadError, World

from strategies.lean.harness import play
from strategies.lean.strategy import Lean, Params, with_overrides
from tools.record import Recorder
from tools.spread_proxy import ProxyClient

POLICY = "lean"  # its saved weeks form their own group in out/spread.sqlite; the TypeScript weeks are `ts-lean`


def next_final(client: ProxyClient) -> World:
    """Our copy of the final that is set or runs now. Waits while none is set and while the last one has ended."""
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
            print("No final is set. Waiting for it.", flush=True)
            said = True
        time.sleep(10)


def main() -> None:
    parser = argparse.ArgumentParser(description="Plays a Spread world with lean. Set SPREAD_URL and SPREAD_KEY first.")
    parser.add_argument("--level", type=int, choices=range(1, 9), default=8, help="the practice level (default 8)")
    parser.add_argument("--seed", help="any text; the same seed gives the same world")
    parser.add_argument("--board", action="store_true", help="play your next ranking run at the level")
    parser.add_argument("--final", action="store_true", help="play your copy of the final from the live stream")
    parser.add_argument(
        "--set", action="append", default=[], metavar="KEY=VALUE", help="override one param, as in index.ts"
    )
    args = parser.parse_args()
    params = with_overrides(Params(), args.set)
    settings = {"strategy": "lean", "params": asdict(params)}
    try:
        client = ProxyClient()
        if args.final:
            world = next_final(client)
            level = next((w["level"] for w in client.worlds() if w["worldId"] == world.id), 8)
            print(f"Final world {world.id}.", flush=True)
            recorder = Recorder(world, level, None, "final", POLICY, settings)
            play(world, lambda roster, world_map: Lean(roster, world_map, level, params), level, live=True)
            recorder.save()
            return
        world = client.create(level=args.level, seed=args.seed, board=args.board)
        name = f"{'Ranking run' if args.board else 'Practice world'} {world.id}"
        stops = (
            "Ctrl-C or an error stops your system: the run then plays to its end without it, and counts."
            if args.board
            else "Ctrl-C or an error stops the run and deletes the world."
        )
        print(f"{name}, level {args.level}. {stops}", flush=True)
        recorder = Recorder(world, args.level, args.seed, "board" if args.board else "practice", POLICY, settings)
        try:
            play(world, lambda roster, world_map: Lean(roster, world_map, args.level, params), args.level, live=False)
        except BaseException as error:  # a world left behind holds one of the team's eight practice slots
            try:
                world.delete()
                after = f"{name} is deleted."
            except SpreadError:
                after = f"{name} is not deleted: it holds one of your eight practice slots."
            if args.board:
                after = f"{name} plays to its end without your system, and counts."
            if isinstance(error, KeyboardInterrupt):
                sys.exit(f"Stopped. {after}")
            print(f"Stopped by the error below. {after}", file=sys.stderr)
            raise
        recorder.save()
    except SpreadError as error:
        sys.exit(f"spread: {error}")
    except KeyboardInterrupt:
        sys.exit("Stopped. The final world keeps running without your system; start it again with --final.")


if __name__ == "__main__":
    main()
