"""The search of the ifs system: looks for values that give better weeks, by playing practice weeks.

It goes through the values of values.json that have a step, one at a time. For each it plays the same seeds with the
value one step up and one step down, and keeps the change when the mean margin of those weeks rises. A pass that keeps
nothing halves the steps; when the smallest steps keep nothing either, it tries changes of two or three values at
once. It runs until the mean margin of a week is over the target, and goes on from its state file after a stop.

    uv run python -m strategies.ifs.search                             # until a week earns over €20,000 on average
    uv run python -m strategies.ifs.search --seeds spread-1 --target 12000
    uv run python -m strategies.ifs.search --dry                       # what it would play, without the server
    uv run python -m strategies.ifs.search --adopt out/ifs/best.json   # make the best values those of values.json

It plays practice weeks only, never a ranking run or a final, through the seed bench (strategies/bench), and it is
one online run, whatever its --jobs. Every week is saved like any other online run (tools/record.py). README.md next
to this file has the options.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import signal
import sys
import time
from pathlib import Path

from spread.client import SpreadError

from strategies.bench.bench import Bench, Result, RunFailed, Version, euros, parse_seeds, table
from strategies.ifs.rules import VALUES, load_values, read_values
from tools.spread_proxy import ProxyClient

ROOT = Path(__file__).resolve().parents[2]
DISPATCH = Path(__file__).with_name("dispatch.py")
OUT = ROOT / "out" / "ifs"
DEFAULT_SEEDS = "spread-1,spread-2,spread-3"
# The code that plays a week of this system. A week that other code played is played again, not read from the file.
PLAYS = [
    "dispatch.py",
    "strategies/strategy.py",
    "strategies/admission",
    "strategies/pricing",
    "strategies/fees",
    "strategies/notes",
    "strategies/offers",
    "strategies/bundling",
    "strategies/ifs",
]
UNDER = 10**10  # cents: what a week under the on-time minimum takes off a score, so such values never win
MIN_SCALE = 0.25  # the smallest steps that a pass tries: a quarter of each value's step
TRIES, PAUSE = 3, 60  # a bench run that fails is played again, this many times in all, after this many seconds

Values = dict[str, float]


def search_space() -> dict[str, dict]:
    """The values that the search may change: those of values.json that have a step, with their range."""
    return {name: entry for name, entry in read_values(VALUES).items() if entry.get("step")}


def neighbours(value: float, entry: dict, scale: float) -> list[float]:
    """The value one step up and one step down, inside its range. `scale` shrinks the step; a whole number moves by
    at least 1."""
    step = entry["step"] * scale
    if entry.get("whole"):
        step = max(1, round(step))
    moved: list[float] = []
    for candidate in (value + step, value - step):
        candidate = min(entry["max"], max(entry["min"], candidate))
        candidate = float(round(candidate)) if entry.get("whole") else float(f"{candidate:.6g}")
        if candidate != value and candidate not in moved:
            moved.append(candidate)
    return moved


def fingerprint(values: Values) -> str:
    """A short name for a set of values: the same values always give the same name."""
    text = json.dumps({name: float(value) for name, value in values.items()}, sort_keys=True)
    return hashlib.sha1(text.encode()).hexdigest()[:16]


def code_version() -> str:
    """A fingerprint of the code that plays a week of this system (`PLAYS`), without this file."""
    digest = hashlib.sha1()
    for item in PLAYS:
        path = ROOT / item
        for file in sorted(path.rglob("*.py")) if path.is_dir() else [path]:
            if file != Path(__file__).resolve():
                digest.update(str(file.relative_to(ROOT)).encode())
                digest.update(file.read_bytes())
    return digest.hexdigest()[:12]


def write_json(path: Path, data: object) -> None:
    """Writes the file whole: to a temporary file first, so a stop never leaves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    partial.write_text(json.dumps(data, indent=2) + "\n")
    partial.replace(path)


def shown(path: Path) -> str:
    """The path from the working folder when it is below it, else in full."""
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


def is_under(week: dict, min_on_time: float) -> bool:
    """A week that does not count: not ranked, or under our own on-time minimum."""
    return not week["ranked"] or week["onTimeShare"] < min_on_time


def mean_margin(weeks: dict[str, dict]) -> int:
    return round(sum(week["marginCents"] for week in weeks.values()) / len(weeks))


def score_of(weeks: dict[str, dict], min_on_time: float) -> int:
    """The mean margin of the weeks in cents, less `UNDER` for each week that does not count."""
    return mean_margin(weeks) - UNDER * sum(1 for week in weeks.values() if is_under(week, min_on_time))


def describe(weeks: dict[str, dict], min_on_time: float) -> str:
    orders = sum(week["wonOrders"] for week in weeks.values())
    on_time = sum(week["onTimeShare"] * week["wonOrders"] for week in weeks.values()) / orders if orders else 0.0
    under = sum(1 for week in weeks.values() if is_under(week, min_on_time))
    text = f"mean margin {euros(mean_margin(weeks))}, on time {on_time:.1%}"
    return text + (f", {under} of {len(weeks)} weeks under the on-time minimum" if under else "")


def play_weeks(versions: list[Version], seeds: list[str], level: int, jobs: int) -> list[Result]:
    """One bench run: every version on every seed. A run that fails, as when the server goes away, is played again
    after a pause; the bench has deleted the worlds of its unfinished weeks by then."""
    for attempt in range(1, TRIES + 1):
        try:
            return Bench(versions, seeds, level, jobs).play()
        except (RunFailed, SpreadError) as error:
            if attempt == TRIES:
                raise
            print(f"search: {error}", file=sys.stderr)
            print(f"Playing these weeks again in {PAUSE} seconds (try {attempt + 1} of {TRIES}).", flush=True)
            time.sleep(PAUSE)
    raise AssertionError("unreachable")


class Search:
    """One search: its settings, its state, and every week it has played."""

    def __init__(self, args: argparse.Namespace, state: dict, space: dict[str, dict], names: list[str]):
        self.args, self.state, self.space, self.names = args, state, space, names
        self.target = round(args.target * 100)
        self.min_gain = round(args.min_gain * 100)
        self.folder: Path = args.state.resolve().parent  # in full: each week's process runs in another folder
        self.weeks_file = self.folder / "weeks.json"
        self.best_file = self.folder / "best.json"
        self.code = code_version()
        # Every week played, by code, level, seed and values: the same week is never played twice.
        self.played: dict[str, dict] = json.loads(self.weeks_file.read_text()) if self.weeks_file.exists() else {}

    def key(self, seed: str, values: Values) -> str:
        return f"{self.code}/{self.state['level']}/{seed}/{fingerprint(values)}"

    def save(self) -> None:
        write_json(self.args.state, self.state)

    def play(self, candidates: list[tuple[str, Values]], seeds: list[str] | None = None) -> list[dict]:
        """Plays the seeds with each candidate's values, all candidates in one bench run, and returns each one's
        label, values, weeks and score. A candidate is a label and its values."""
        seeds = self.state["seeds"] if seeds is None else seeds
        todo: dict[tuple[str, ...], list[tuple[str, Values]]] = {}  # the seeds to play -> the candidates to play them
        for label, values in candidates:
            need = tuple(seed for seed in seeds if self.key(seed, values) not in self.played)
            if need:
                todo.setdefault(need, []).append((label, values))
        for need, group in todo.items():
            versions = []
            for label, values in group:
                path = self.folder / "trials" / f"{fingerprint(values)}.json"
                write_json(path, values)
                versions.append(Version(label, DISPATCH, args=("--values", str(path))))
            by_label = dict(group)
            for result in play_weeks(versions, list(need), self.state["level"], self.args.jobs):
                week = {"worldId": result.world_id, **result.score}
                self.played[self.key(result.seed, by_label[result.version])] = week
            self.state["weeks"] += len(need) * len(group)
            write_json(self.weeks_file, self.played)
            self.save()
        results = []
        for label, values in candidates:
            weeks = {seed: self.played[self.key(seed, values)] for seed in seeds}
            score = score_of(weeks, self.args.min_on_time)
            results.append({"label": label, "values": values, "weeks": weeks, "score": score})
        return results

    def keep(self, results: list[dict]) -> dict | None:
        """Prints each result against the best values. The best of the results takes their place when its score is
        more than `--min-gain` above theirs; returns it then."""
        best = self.state["best"]
        winner = max(results, key=lambda result: result["score"], default=None)
        kept = winner if winner is not None and winner["score"] > best["score"] + self.min_gain else None
        for result in results:
            gain = mean_margin(result["weeks"]) - mean_margin(best["weeks"])
            text = describe(result["weeks"], self.args.min_on_time)
            mark = "kept" if result is kept else "no"
            print(f"  {result['label']}: {text}, {euros(gain, sign=True)}: {mark}", flush=True)
            self.state["trials"].append({"label": result["label"], "score": result["score"], "kept": result is kept})
        if kept is not None:
            self.state["best"] = kept
            write_json(self.best_file, kept["values"])
        return kept

    def step(self, name: str) -> None:
        """Tries one value a step up and a step down. A kept change stays on the value, so the next step goes on in
        the same direction (the way back is a week already played); else the pass moves to the next value."""
        state = self.state
        values = state["best"]["values"]
        moves = neighbours(values[name], self.space[name], state["scale"])
        results = self.play([(f"{name}={moved:g}", {**values, name: moved}) for moved in moves])
        if self.keep(results) is None:
            state["next"] += 1
        else:
            state["kept"] += 1

    def jump(self) -> None:
        """No single value gives a better week: tries changes of two or three values at once, each a full step. A
        kept jump starts the passes again from the full steps."""
        state = self.state
        best = state["best"]
        width = max(1, self.args.jobs // len(state["seeds"]))
        candidates: list[tuple[str, Values]] = []
        seen: set[str] = set()
        for n in range(state["jumps"], state["jumps"] + width):
            draw = random.Random(f"{fingerprint(best['values'])}/{n}")  # the same jump after a stop and a restart
            values, moved = dict(best["values"]), []
            for name in draw.sample(self.names, k=min(len(self.names), draw.choice((2, 2, 3)))):
                options = neighbours(values[name], self.space[name], 1.0)
                if options:
                    values[name] = draw.choice(options)
                    moved.append(f"{name}={values[name]:g}")
            if moved and fingerprint(values) not in seen:
                seen.add(fingerprint(values))
                candidates.append((" ".join(moved), values))
        state["jumps"] += width
        if self.keep(self.play(candidates)) is not None:
            state.update(scale=1.0, next=0, kept=0, jumps=0)

    def run(self) -> str:
        """Searches until the mean margin of the best values is over the target, and says why it stopped."""
        state, args = self.state, self.args
        start = state["best"]["values"] if state["best"] else state["start"]
        state["best"] = self.play([("best" if state["best"] else "start", start)])[0]
        write_json(self.best_file, state["best"]["values"])
        self.save()
        print(f"Starting from {describe(state['best']['weeks'], args.min_on_time)}.", flush=True)
        while True:
            if state["best"]["score"] > self.target:
                return "the mean margin is over the target"
            if args.stop_file.exists():
                return f"the stop file {shown(args.stop_file)} is there"
            if args.max_weeks and state["weeks"] >= args.max_weeks:
                return f"--max-weeks is {args.max_weeks}"
            if state["next"] < len(self.names):
                self.step(self.names[state["next"]])
            elif state["kept"]:
                print(f"The pass kept {state['kept']} changes. Going through the values again.", flush=True)
                state.update(next=0, kept=0)
            elif state["scale"] / 2 >= MIN_SCALE:
                state.update(next=0, scale=state["scale"] / 2)
                print(f"The pass kept nothing. Trying steps {state['scale']:g} times as large.", flush=True)
            elif state["jumps"] < args.jumps:
                if state["jumps"] == 0:
                    print("No single value gives a better week. Trying two or three values at once.", flush=True)
                self.jump()
            else:
                return "no single value and no jump gives a better week"
            self.save()

    def report(self, why: str) -> None:
        """What the search found, where the values are, and the commands that use them."""
        state, args = self.state, self.args
        best, seeds = state["best"], state["seeds"]
        results = [Result("best", seed, best["weeks"][seed]["worldId"], best["weeks"][seed]) for seed in seeds]
        print(f"\nThe search stopped: {why}. It has played {state['weeks']} weeks.\n")
        print(table(results, ["best"], seeds, state["level"]))
        defaults = load_values()
        changed = [
            f"{name} {defaults[name]:g} -> {value:g}"
            for name, value in best["values"].items()
            if value != defaults[name]
        ]
        print(f"The values that differ from {shown(VALUES)}: {', '.join(changed) or 'none'}.")
        print(f"All of them are in {shown(self.best_file)}. Play a week with them:")
        print(
            f"  uv run strategies/ifs/dispatch.py --level {state['level']} --seed {seeds[0]} --values {shown(self.best_file)}"
        )
        print(f"Make them the values of {shown(VALUES)}:")
        print(f"  uv run python -m strategies.ifs.search --adopt {shown(self.best_file)}")
        # A search stopped by its stop file plays nothing more.
        if args.holdout and best["values"] != state["start"] and not args.stop_file.exists():
            holdout = parse_seeds(args.holdout)
            print("\nThe best values and the starting values on the holdout seeds, which the search did not see:")
            played = self.play([("best", best["values"]), ("start", state["start"])], holdout)
            results = [
                Result(r["label"], seed, r["weeks"][seed]["worldId"], r["weeks"][seed])
                for r in played
                for seed in holdout
            ]
            print(table(results, ["best", "start"], holdout, state["level"]))


def load_state(args: argparse.Namespace) -> dict:
    """The state of the search in `--state`, or of a new search. A file that `--fresh` replaces is kept under
    another name."""
    seeds = parse_seeds(args.seeds) if args.seeds else None
    if args.state.exists() and not args.fresh:
        state = json.loads(args.state.read_text())
        if (seeds and seeds != state["seeds"]) or (args.level and args.level != state["level"]):
            raise ValueError(
                f"{shown(args.state)} holds a search at level {state['level']} on {', '.join(state['seeds'])}. "
                "Pass --fresh to start a new search, or --state to keep this one in another file."
            )
        print(f"Going on with the search in {shown(args.state)}: {state['weeks']} weeks played so far.", flush=True)
        return state
    if args.state.exists():
        kept = args.state.with_name(f"{args.state.stem}-{time.strftime('%Y%m%d-%H%M%S')}{args.state.suffix}")
        args.state.rename(kept)
        print(f"The search that was in {shown(args.state)} is now in {shown(kept)}.", flush=True)
    return {
        "level": args.level or 8,
        "seeds": seeds or parse_seeds(DEFAULT_SEEDS),
        "start": load_values(args.values),  # every value the search starts from
        "best": None,  # the best values so far, with their weeks and their score
        "scale": 1.0,  # the size of the steps of this pass
        "next": 0,  # the place in the pass: the value to try next
        "kept": 0,  # the changes this pass has kept
        "jumps": 0,  # the jumps tried since the last kept change
        "weeks": 0,  # the weeks played so far
        "trials": [],  # every set of values tried, with its score
    }


def describe_plan(args: argparse.Namespace, space: dict[str, dict], names: list[str]) -> None:
    """`--dry`: the values the search goes through and the weeks of one pass, without the server."""
    seeds = parse_seeds(args.seeds or DEFAULT_SEEDS)
    values = load_values(args.values)
    print(f"The search goes through {len(names)} values of {shown(VALUES)}, in this order:")
    width = max(len(name) for name in names)
    for name in names:
        entry = space[name]
        whole = ", whole numbers" if entry.get("whole") else ""
        print(
            f"  {name:<{width}}  {values[name]:<7g} from {entry['min']:g} to {entry['max']:g}, step {entry['step']:g}{whole}"
        )
    weeks = 2 * len(names) * len(seeds)
    print(
        f"A pass tries each value one step up and one step down on {len(seeds)} seed{'s' if len(seeds) != 1 else ''} "
        f"({', '.join(seeds)}): up to {weeks} practice weeks at level {args.level or 8}, {args.jobs} at a time."
    )
    print(f"It stops when the mean margin of a week is over {euros(round(args.target * 100))}.")


def adopt(path: Path) -> None:
    """Writes the values of the file at `path` into values.json, each on its own line there, so that they are the
    values of the system from now on."""
    values = load_values(path)
    lines = VALUES.read_text().splitlines()
    changed: list[str] = []
    for n, text in enumerate(lines):
        match = re.match(r'(\s*"(\w+)": \{ "value": )([^,} ]+)', text)
        if match is None or float(match[3]) == float(values[match[2]]):
            continue
        value = float(values[match[2]])
        new = str(int(value)) if value.is_integer() and "." not in match[3] else json.dumps(value)
        lines[n] = match[1] + new + text[match.end() :]
        changed.append(f"{match[2]} {match[3]} -> {new}")
    VALUES.write_text("\n".join(lines) + "\n")
    print(f"{shown(VALUES)}: {', '.join(changed) if changed else 'nothing to change'}.")


def interrupt(signum: int, frame: object) -> None:
    """A termination signal stops the search as Ctrl-C does, so the bench deletes the worlds in play."""
    raise KeyboardInterrupt


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m strategies.ifs.search",
        description="Looks for values of strategies/ifs/values.json that give better practice weeks: it tries each "
        "value one step up and one step down on the same seeds, and keeps the changes that raise the mean margin. "
        "It never plays a ranking run or a final. Set SPREAD_URL and SPREAD_KEY first.",
    )
    parser.add_argument(
        "--target",
        type=float,
        default=20000,
        metavar="EUROS",
        help="stop when the mean margin of a week is over this (default 20000)",
    )
    parser.add_argument(
        "--seeds", help=f"the seeds every set of values plays, comma-separated or a range (default {DEFAULT_SEEDS})"
    )
    parser.add_argument("--level", type=int, choices=range(1, 9), help="the practice level (default 8)")
    parser.add_argument(
        "--jobs",
        type=int,
        choices=range(1, 9),
        default=6,
        help="weeks played at once, 1 to 8 (default 6, which leaves two practice slots to teammates)",
    )
    parser.add_argument(
        "--values", type=Path, help="a file of values to start a new search from (default: those of values.json)"
    )
    parser.add_argument(
        "--only", help="search only these values, comma-separated (default: every value that has a step)"
    )
    parser.add_argument(
        "--min-on-time",
        type=float,
        default=0.93,
        metavar="SHARE",
        help="a week under this on-time share, or not ranked, never counts as better (default 0.93)",
    )
    parser.add_argument(
        "--min-gain",
        type=float,
        default=50,
        metavar="EUROS",
        help="keep a change only when it raises the mean margin by more than this (default 50)",
    )
    parser.add_argument(
        "--max-weeks", type=int, default=0, metavar="N", help="stop after playing N weeks (default 0: no limit)"
    )
    parser.add_argument(
        "--jumps",
        type=int,
        default=12,
        metavar="N",
        help="changes of several values to try when no single value helps (default 12)",
    )
    parser.add_argument(
        "--holdout",
        help="seeds to play the best and the starting values on at the end, to check them on weeks the search did not see",
    )
    parser.add_argument(
        "--state",
        type=Path,
        default=OUT / "search.json",
        help="the file that keeps the search, so that it goes on after a stop (default out/ifs/search.json)",
    )
    parser.add_argument("--fresh", action="store_true", help="start a new search, also when --state holds one")
    parser.add_argument(
        "--stop-file",
        type=Path,
        default=OUT / "stop",
        help="the search stops when this file exists, read between steps (default out/ifs/stop)",
    )
    parser.add_argument(
        "--dry", action="store_true", help="print the values and the weeks of one pass, and play nothing"
    )
    parser.add_argument(
        "--adopt", type=Path, metavar="FILE", help="write the values of this file into values.json, and play nothing"
    )
    args = parser.parse_args()
    try:
        if args.adopt:
            adopt(args.adopt)
            return
        space = search_space()
        only = [name.strip() for name in args.only.split(",")] if args.only else list(space)
        unknown = [name for name in only if name not in space]
        if unknown:
            parser.error(f"not a value with a step in {VALUES.name}: {', '.join(unknown)}")
        names = [name for name in space if name in only]
        if args.dry:
            describe_plan(args, space, names)
            return
        ProxyClient()  # stops at once when SPREAD_KEY is not set
        search = Search(args, load_state(args), space, names)
        signal.signal(signal.SIGTERM, interrupt)
        signal.signal(signal.SIGHUP, interrupt)
        state = search.state
        print(
            f"Searching {len(names)} of the values at level {state['level']} on {', '.join(state['seeds'])}, until the mean "
            f"margin of a week is over {euros(search.target)}. The best values go to {shown(search.best_file)}. "
            f"Stop it with Ctrl-C or by creating {shown(args.stop_file)}.",
            flush=True,
        )
        search.report(search.run())
    except KeyboardInterrupt:
        sys.exit(f"Stopped. The same command goes on from {shown(args.state)}.")
    except (OSError, ValueError, RunFailed, SpreadError) as error:
        sys.exit(f"search: {error}")


if __name__ == "__main__":
    main()
