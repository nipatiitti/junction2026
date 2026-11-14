"""Play the models that active-models.md lists as worth a practice week, on fresh random seeds, round after round,
until stopped. Each round is one bench run (strategies.bench), and every week it plays is saved to
data/scrape/runs and out/spread.sqlite (record.py), so a long run grows the saved-weeks database while nobody is
watching. tools/README.md says what it does.

Run it from the repository root, with SPREAD_URL and SPREAD_KEY set (add `--env-file .env` after `uv run` to read
them from .env):

    uv run python -m tools.sweep                     # the active models, eight fresh seeds a round, level 8
    uv run python -m tools.sweep --seeds-per-round 4 --jobs 4
    uv run python -m tools.sweep --once              # one round, to check the setup

Stop it with Ctrl-C, or by creating the stop file (out/sweep.stop). Ctrl-C stops the round in play at once: the
bench deletes every world that has not ended, so no practice slot is left held. The stop file is read between
rounds, so the round in play ends first. One round's output goes to out/sweep-<time>-round-<n>.log and .csv.
"""

from __future__ import annotations

import argparse
import os
import secrets
import signal
import subprocess
import sys
import time
from pathlib import Path

# active-models.md, "The list": the leading five by margin, the root dispatch.py among them as the week's reference,
# plus scarcity_urgency, which the page says is new and goes with the leaders. One entry is one file the bench plays.
ACTIVE = [
    "dispatch.py",
    "strategies/ceiling/dispatch.py",
    "strategies/scarcity_cost/dispatch.py",
    "strategies/delivery_urgency/dispatch.py",
    "strategies/price_ladder/dispatch.py",
    "strategies/scarcity_urgency/dispatch.py",
]
# The models the same page calls the rest of the comparison: behind the active list. Play these too with --all.
REST = [
    "strategies/bundling_cheaper/dispatch.py",
    "strategies/bundling_more/dispatch.py",
    "strategies/ratchet/dispatch.py",
    "strategies/baseline/baseline.py",
]
SEED_PREFIX = "sweep"
FAILS_BEFORE_STOP = 3  # rounds that fail in a row before the sweep gives up, so a bad key does not spin all night

child: subprocess.Popen | None = None  # the round's bench run, so a signal can be forwarded to it
stopping = False


def stop(signum: int, frame: object) -> None:
    """Ctrl-C or a termination signal: stop the sweep, and stop the round in play so the bench cleans up its worlds."""
    global stopping
    stopping = True
    print(f"\nSignal {signum}: stopping after the round in play.", flush=True)
    if child is not None and child.poll() is None:
        child.send_signal(signal.SIGINT)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m tools.sweep",
        description="Plays the models of active-models.md on fresh random seeds, round after round, until stopped. "
        "Set SPREAD_URL and SPREAD_KEY first.",
    )
    parser.add_argument("--level", type=int, choices=range(1, 9), default=8, help="the practice level (default 8)")
    parser.add_argument(
        "--seeds-per-round", type=int, default=8, metavar="N", help="fresh seeds in each round (default 8)"
    )
    parser.add_argument("--jobs", type=int, choices=range(1, 9), default=8, help="weeks at once, 1 to 8 (default 8)")
    parser.add_argument(
        "--models",
        metavar="FILES",
        help="the files to play, comma-separated (default: the six active models of active-models.md)",
    )
    parser.add_argument("--all", action="store_true", help="also play the models the page lists behind the active five")
    parser.add_argument("--prefix", default=SEED_PREFIX, help=f"the fresh seeds' prefix (default {SEED_PREFIX})")
    parser.add_argument(
        "--rounds", type=int, default=0, metavar="N", help="stop after N rounds (default 0: never, until stopped)"
    )
    parser.add_argument("--once", action="store_true", help="one round, to check the setup (same as --rounds 1)")
    parser.add_argument(
        "--stop-file",
        type=Path,
        default=Path("out") / "sweep.stop",
        help="the sweep stops when this file exists, read between rounds (default out/sweep.stop)",
    )
    parser.add_argument(
        "--log-dir", type=Path, default=Path("out"), help="where each round's log and CSV go (default out)"
    )
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="the checkout to play and save in (default .)")
    args = parser.parse_args()
    if args.seeds_per_round < 1:
        parser.error("--seeds-per-round must be at least 1")
    if args.once:
        args.rounds = 1
    return args


def models_for(args: argparse.Namespace, repo: Path) -> list[str]:
    models = args.models.split(",") if args.models else list(ACTIVE)
    if args.all:
        models += [model for model in REST if model not in models]
    missing = [model for model in models if not (repo / model).is_file()]
    if missing:
        sys.exit(f"sweep: no such file: {', '.join(missing)}")
    return models


def fresh_seeds(count: int, prefix: str, seen: set[str]) -> list[str]:
    """`count` seed names that this sweep has not used. A new name is a new world: the same seed gives the same week."""
    seeds: list[str] = []
    while len(seeds) < count:
        seed = f"{prefix}-{secrets.token_hex(4)}"
        if seed not in seen:
            seen.add(seed)
            seeds.append(seed)
    return seeds


def saved_weeks(repo: Path, level: int) -> int:
    """How many weeks are saved at the level, over all policies and seeds: the growth of a long run."""
    return sum(1 for _ in (repo / "data" / "scrape" / "runs" / f"L{level}").rglob("meta.json"))


def play_round(models: list[str], seeds: list[str], args: argparse.Namespace, log: Path, csv: Path) -> int:
    """One bench run: the models on the seeds, at most `jobs` weeks at once. Its output goes to the log and the
    terminal. Returns its exit code. The bench deletes every world that has not ended on an error or Ctrl-C."""
    global child
    command = [
        sys.executable,
        "-m",
        "strategies.bench",
        *models,
        "--level",
        str(args.level),
        "--seeds",
        ",".join(seeds),
        "--jobs",
        str(args.jobs),
        "--csv",
        str(csv),
    ]
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf-8") as file:
        child = subprocess.Popen(
            command,
            cwd=args.repo,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
            start_new_session=True,  # Ctrl-C reaches this process only; `stop` forwards it to the bench
        )
        assert child.stdout is not None
        for line in child.stdout:  # the bench's own lines: one per week that ends, then its table
            file.write(line)
            file.flush()
            print(line, end="", flush=True)
        return child.wait()


def main() -> None:
    args = parse_args()
    if not os.environ.get("SPREAD_KEY"):
        sys.exit("sweep: SPREAD_KEY is not set. Set it, or add --env-file .env after uv run.")
    models = models_for(args, args.repo)
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    print(
        f"Sweep: {len(models)} models, {args.seeds_per_round} fresh seeds a round, level {args.level}, "
        f"{args.jobs} weeks at once. Stop file {args.stop_file}. Logs in {args.log_dir}.",
        flush=True,
    )
    seen: set[str] = set()
    rounds, failures = 0, 0
    while not stopping:
        if args.rounds and rounds >= args.rounds:
            break
        if args.stop_file.exists():
            print(f"Stop file {args.stop_file} found: stopping.", flush=True)
            break
        rounds += 1
        seeds = fresh_seeds(args.seeds_per_round, args.prefix, seen)
        log = args.log_dir / f"sweep-{stamp}-round-{rounds:03d}.log"
        print(f"Round {rounds}: {args.seeds_per_round} fresh seeds: {', '.join(seeds)}", flush=True)
        code = play_round(models, seeds, args, log, log.with_suffix(".csv"))
        if stopping:
            break
        if code == 0:
            failures = 0
        else:
            failures += 1
            print(f"Round {rounds} ended with exit code {code}; see {log}.", file=sys.stderr, flush=True)
            if failures >= FAILS_BEFORE_STOP:
                sys.exit(f"sweep: {failures} rounds in a row failed; stopping.")
        print(
            f"Round {rounds} done: {saved_weeks(args.repo, args.level)} weeks saved at level {args.level}.", flush=True
        )
    print(f"Sweep stopped after {rounds} round{'s' if rounds != 1 else ''}.", flush=True)


if __name__ == "__main__":
    main()
