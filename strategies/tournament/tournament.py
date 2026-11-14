"""The tournament: plays the ceiling system and the changes built on it on the same practice weeks, round after
round, and stacks the changes that win into one system. See README.md next to this file. Issue #209.

A line-up is the ceiling system with a set of layers (mix.py). Round 1 plays `ceiling` and each layer alone. The
best line-up that beats the champion becomes the champion; each later round adds each layer still in to it, and a
layer whose line-up does not beat the champion is out. Every line-up plays the same seeds, so the standings at the
end compare all of them. Other systems can play the same seeds beside them, as a reference.

A week is a child process, played by the bench's player (strategies/bench). A saved week under data/scrape/runs is
read instead of played when the code that the line-up runs has not changed since. It never plays a ranking run or a
final.
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import math
import re
import statistics
import subprocess
import sys
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import NamedTuple

from spread.client import SpreadError
from spread.types import Score

from strategies.bench.bench import SLOTS, Bench, Result, RunFailed, Version, euros, parse_seeds
from strategies.tournament import mix
from tools.record import ROOT, RUNS
from tools.spread_proxy import ProxyClient

DEFAULT_SEEDS = "spread-1..spread-3"  # the seeds that every system built on ceiling has a saved week on
DEFAULT_JOBS = 6  # two of the team's eight practice slots stay free for teammates
MIX = Path(mix.__file__).resolve()
POLICY_LINE = re.compile(r'^(?:record\.)?POLICY = "([^"]+)"', re.MULTILINE)


# Line-ups


@dataclass(frozen=True)
class Entrant:
    """What plays in the tournament: a line-up of layers, or another system that plays beside them as it is."""

    label: str
    layers: tuple[str, ...] | None  # None: another system, never stacked
    file: Path  # the file that plays one week
    args: tuple[str, ...] = ()  # its arguments after --level and --seed
    policy: str | None = None  # the policy of its saved weeks, when known: without one, every week is played

    @property
    def played_by(self) -> str:
        return " ".join([shown(self.file), *self.args])


def shown(path: Path) -> str:
    """The path from the repository root when it is below it, else in full."""
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def policy_of(file: Path) -> str | None:
    """The policy a system saves its weeks under: the `POLICY` that its file sets. None for a file that sets none,
    as the root dispatch.py: its weeks are saved as `dispatch`, and so are the baseline's and older weeks of other
    systems, so a saved one cannot be told from theirs."""
    found = POLICY_LINE.search(file.read_text(encoding="utf-8"))
    return found[1] if found else None


def lineup(layers: Sequence[str]) -> Entrant:
    """The line-up of the ceiling system with the layers. A line-up that is one of the systems in strategies/ is
    played by that system's own file, so its weeks keep their policy; any other by the mixed system."""
    layers = tuple(name for name in mix.LAYERS if name in layers)
    own = ROOT / "strategies" / (layers[0] if layers else "ceiling") / "dispatch.py"
    if not layers or (len(layers) == 1 and mix.LAYERS[layers[0]].system):
        return Entrant(mix.label(layers), layers, own, policy=policy_of(own))
    return Entrant(mix.label(layers), layers, MIX, ("--layers", ",".join(layers)), mix.policy(layers))


def other(spec: str) -> Entrant:
    """Another system: a Python file that plays one week, as the bench's versions do."""
    file = Path(spec).resolve()
    if not file.is_file():
        raise ValueError(f'"{spec}" is not a file')
    return Entrant(spec, None, file, policy=policy_of(file))


# The saved weeks


class Week(NamedTuple):
    """One entrant's practice week on one seed: played now, or read from the saved weeks."""

    label: str
    seed: str
    world_id: str
    score: Score
    saved: bool


def imports(path: Path) -> list[Path]:
    """The files of the repository's deciding code that a Python file imports: the root dispatch.py, and the
    modules and packages under strategies/. tools/ decides nothing in a week, so it is left out."""
    found: list[Path] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names = [node.module, *(f"{node.module}.{alias.name}" for alias in node.names)]
        else:
            continue
        for parts in (name.split(".") for name in names):
            if parts[0] in ("dispatch", "strategies"):
                for depth in range(1, len(parts) + 1):
                    base = ROOT.joinpath(*parts[:depth])
                    found += [base.with_suffix(".py"), base / "__init__.py"]
    # By its exact name: on a disk that ignores case, the class `Admission` would pass for the file admission.py.
    return [file for file in found if file.is_file() and file.name in listing(file.parent)]


@cache
def listing(folder: Path) -> frozenset[str]:
    return frozenset(path.name for path in folder.iterdir())


def code_of(entrant: Entrant) -> tuple[str, ...]:
    """Every file that decides the entrant's week: its file, what it imports, on and on, and the files a mix loads
    by name. Data files next to that code count too, such as a table of priors."""
    todo = [entrant.file, *(mix.files(entrant.layers) if entrant.file == MIX and entrant.layers else [])]
    seen: set[Path] = set()
    while todo:
        path = todo.pop().resolve()
        if path not in seen and path.is_relative_to(ROOT):
            seen.add(path)
            todo += imports(path)
    folders = {path.parent for path in seen if path.parent != ROOT}
    data = {f for folder in folders for f in folder.iterdir() if f.is_file() and f.suffix not in (".py", ".md")}
    return tuple(sorted(str(path.relative_to(ROOT)) for path in seen | data))


class Saved:
    """The practice weeks saved under data/scrape/runs at one level, and whether one is still an entrant's week."""

    def __init__(self, level: int):
        self.weeks: dict[tuple[str, str], list[dict]] = {}  # (policy, seed) -> the meta.json of each saved week
        for path in sorted((RUNS / f"L{level}").glob("*/*/meta.json")):
            meta = json.loads(path.read_text(encoding="utf-8"))
            if meta.get("kind") == "practice" and meta.get("level") == level and meta.get("score"):
                self.weeks.setdefault((meta.get("policy"), meta.get("seed")), []).append(meta)
        self.code: dict[str, tuple[str, ...]] = {}  # entrant -> the files that decide its week
        self.same: dict[tuple[str, str], bool] = {}  # (entrant, version) -> its code is the same now
        self.conflicts: list[str] = []

    def unchanged(self, entrant: Entrant, version: str | None) -> bool:
        """Whether the entrant's code is the same now as at the commit that played a saved week. A week played
        with changes that were not committed says nothing of its code, so it never counts."""
        if not version or version.endswith("-dirty") or not entrant.file.is_relative_to(ROOT):
            return False
        key = (entrant.label, version)
        if key not in self.same:
            if entrant.label not in self.code:
                files = code_of(entrant)
                new = git("ls-files", "--others", "--exclude-standard", "--", *files)
                self.code[entrant.label] = () if new.stdout.strip() else files  # a file git does not know: no week
            files = self.code[entrant.label]
            self.same[key] = bool(files) and git("diff", "--quiet", version, "--", *files).returncode == 0
        return self.same[key]

    def find(self, entrant: Entrant, seed: str) -> Week | None:
        """The entrant's saved week on the seed, or None. The same code on the same seed plays the same week, so
        saved weeks that disagree are not trusted, and the week is played."""
        if entrant.policy is None:
            return None
        metas = [m for m in self.weeks.get((entrant.policy, seed), []) if self.unchanged(entrant, m.get("version"))]
        if len({meta["score"]["marginCents"] for meta in metas}) > 1:
            self.conflicts.append(f"{entrant.label} on {seed}")
            return None
        return Week(entrant.label, seed, metas[0]["worldId"], metas[0]["score"], True) if metas else None

    def seconds(self) -> float | None:
        """How long a saved week took to play, in the middle of them all."""
        took = [meta["seconds"] for metas in self.weeks.values() for meta in metas if meta.get("seconds")]
        return statistics.median(took) if took else None


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)


# Playing


class Arena(Bench):
    """The bench's player for the tournament's weeks. A week that fails puts its entrant out, and the other weeks
    go on: one mix that cannot play must not stop the rest."""

    def __init__(self, level: int, jobs: int):
        super().__init__([], [], level, jobs)
        self.failed: dict[str, str] = {}  # entrant -> why its week failed

    def play_one(self, version: Version, seed: str) -> Result | None:
        try:
            return super().play_one(version, seed)
        except RunFailed as error:
            with self.lock:
                self.failed.setdefault(version.label, str(error))
            print(f"{seed:<12} {version.label}: out. {error}", file=sys.stderr, flush=True)
            return None


class Tournament:
    """The weeks of every entrant so far, and the rounds."""

    def __init__(self, seeds: list[str], level: int, jobs: int, fresh: bool):
        self.seeds, self.level, self.fresh = seeds, level, fresh
        self.arena = Arena(level, jobs)
        self.saved = Saved(level)
        self.weeks: dict[tuple[str, str], Week] = {}  # (entrant, seed) -> its week
        self.round_of: dict[str, int] = {}  # entrant -> the round it first played in

    def missing(self, entrants: Iterable[Entrant]) -> list[tuple[Entrant, str]]:
        """Reads the saved weeks of the entrants, and returns the weeks that are still to play."""
        runs = []
        for seed in self.seeds:
            for entrant in entrants:
                if (entrant.label, seed) in self.weeks:
                    continue
                week = None if self.fresh else self.saved.find(entrant, seed)
                if week is None:
                    runs.append((entrant, seed))
                else:
                    self.weeks[(entrant.label, seed)] = week
        return runs

    def play(self, entrants: list[Entrant], number: int) -> None:
        """One round: every entrant on every seed, the saved weeks read and the others played."""
        for entrant in entrants:
            self.round_of.setdefault(entrant.label, number)
        runs = self.missing(entrants)
        total = len(entrants) * len(self.seeds)
        print(
            f"\nRound {number}: {count(len(entrants), 'line-up')} on {count(len(self.seeds), 'seed')}, "
            f"{total - len(runs)} of {count(total, 'week')} saved.",
            flush=True,
        )
        if not runs:
            return
        ProxyClient()  # stops at once when SPREAD_KEY is not set; a round of saved weeks needs no key
        versions = {entrant.label: Version(entrant.label, entrant.file, args=entrant.args) for entrant, _ in runs}
        for result in self.arena.play([(versions[entrant.label], seed) for entrant, seed in runs]):
            if result is not None:
                self.weeks[(result.version, result.seed)] = Week(*result, saved=False)
        self.arena.delete_unfinished()  # the world of a week that failed, when its own run did not delete it

    def of(self, entrant: Entrant) -> list[Week] | None:
        """The entrant's weeks in seed order, or None when one of them is missing: the entrant is out."""
        weeks = [self.weeks.get((entrant.label, seed)) for seed in self.seeds]
        return None if any(week is None for week in weeks) else weeks  # type: ignore[return-value]

    def beats(self, entrant: Entrant, champion: Entrant) -> bool:
        mine, theirs = self.of(entrant), self.of(champion)
        return mine is not None and theirs is not None and standing(mine) > standing(theirs)


def standing(weeks: list[Week]) -> tuple[bool, float]:
    """The order of the practice rankings and of the final: an entrant whose every week is ranked comes first,
    then the mean margin of a week."""
    return all(week.score["ranked"] for week in weeks), mean_margin(weeks)


def mean_margin(weeks: list[Week]) -> float:
    return sum(week.score["marginCents"] for week in weeks) / len(weeks)


def count(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


def names(items: Sequence[str]) -> str:
    """a, b and c."""
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


# The table and the CSV


def table(tournament: Tournament, entrants: list[Entrant], reference: Entrant) -> str:
    """The standings: one line for each entrant with a week on every seed, the best first. `vs` and `Ahead` compare
    an entrant with the reference, the plain ceiling system, on the same seeds."""
    rows = sorted(((standing(weeks), e, weeks) for e in entrants if (weeks := tournament.of(e))), key=lambda r: r[0])
    base = tournament.of(reference)
    header = ["#", "Line-up", "Round", "Margin a week", f"vs {reference.label}", "Ahead", "Ranked", "Lowest on time"]
    header.append("Best week")
    lines: list[list[str]] = []
    for place, (_, entrant, weeks) in enumerate(reversed(rows), start=1):
        versus, ahead = "", ""
        if base is not None and entrant != reference:
            versus = euros(round(mean_margin(weeks) - mean_margin(base)), sign=True)
            won = sum(1 for mine, theirs in zip(weeks, base) if mine.score["marginCents"] > theirs.score["marginCents"])
            ahead = f"{won} of {len(weeks)}"
        lines.append(
            [
                str(place),
                entrant.label,
                str(tournament.round_of.get(entrant.label, "")),
                euros(round(mean_margin(weeks))),
                versus,
                ahead,
                f"{sum(1 for week in weeks if week.score['ranked'])} of {len(weeks)}",
                f"{min(week.score['onTimeShare'] for week in weeks):.1%}",
                euros(max(week.score["marginCents"] for week in weeks)),
            ]
        )
    widths = [max(len(row[i]) for row in [header, *lines]) for i in range(len(header))]
    right = {0, 2, 3, 4, 5, 6, 7, 8}  # numbers line up on the right

    def line(row: list[str]) -> str:
        cells = [cell.rjust(widths[i]) if i in right else cell.ljust(widths[i]) for i, cell in enumerate(row)]
        return "  ".join(cells).rstrip()

    return "\n".join([line(header), *(line(row) for row in lines)]) + "\n"


CSV_COLUMNS = [
    "lineup",
    "round",
    "seed",
    "level",
    "world_id",
    "margin_eur",
    "revenue_eur",
    "won_orders",
    "on_time_share",
    "undelivered_share",
    "ranked",
    "source",
]


def write_csv(path: Path, tournament: Tournament, entrants: list[Entrant]) -> None:
    """One row for each week of each entrant: its score, and whether it was played now or read from a saved week."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for entrant in entrants:
            for seed in tournament.seeds:
                week = tournament.weeks.get((entrant.label, seed))
                if week is None:
                    continue
                score = week.score
                writer.writerow(
                    {
                        "lineup": entrant.label,
                        "round": tournament.round_of.get(entrant.label, ""),
                        "seed": seed,
                        "level": tournament.level,
                        "world_id": week.world_id,
                        "margin_eur": f"{score['marginCents'] / 100:.2f}",
                        "revenue_eur": f"{score['revenueCents'] / 100:.2f}",
                        "won_orders": score["wonOrders"],
                        "on_time_share": f"{score['onTimeShare']:.4f}",
                        "undelivered_share": f"{score['undeliveredShare']:.4f}",
                        "ranked": "yes" if score["ranked"] else "no",
                        "source": "saved" if week.saved else "played",
                    }
                )


# The rounds


def challengers(champion: Entrant, layers: list[str]) -> tuple[list[Entrant], dict[str, str]]:
    """The champion with each layer added, and why each layer that cannot join it is left out."""
    joined, refused = [], {}
    for name in layers:
        together = (*(champion.layers or ()), name)
        if why := mix.problem([layer for layer in mix.LAYERS if layer in together]):
            refused[name] = why
        else:
            joined.append(lineup(together))
    return joined, refused


def added(entrant: Entrant, champion: Entrant) -> str:
    """The layer that a challenger adds to the champion."""
    return next(name for name in entrant.layers or () if name not in (champion.layers or ()))


def plan(tournament: Tournament, entrants: list[Entrant], layers: list[str], rounds: int) -> None:
    """Prints round 1 without playing it: who plays each line-up, and which of its weeks are saved."""
    runs = {(entrant.label, seed) for entrant, seed in tournament.missing(entrants)}
    total = len(entrants) * len(tournament.seeds)
    print(f"Level {tournament.level}, {count(len(tournament.seeds), 'seed')}: {', '.join(tournament.seeds)}.")
    print(f"Round 1: {count(len(entrants), 'line-up')}, {count(total, 'week')}: {total - len(runs)} saved, ", end="")
    print(f"{len(runs)} to play.\n")
    header = ["Line-up", "Played by", *tournament.seeds]
    rows = [
        [e.label, e.played_by, *("play" if (e.label, seed) in runs else "saved" for seed in tournament.seeds)]
        for e in entrants
    ]
    widths = [max(len(row[i]) for row in [header, *rows]) for i in range(len(header))]
    for row in [header, *rows]:
        print("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip())
    took = tournament.saved.seconds()
    if runs and took:
        minutes = math.ceil(len(runs) / tournament.arena.jobs) * took / 60
        print(f"\nRound 1 takes about {minutes:.0f} minutes: a saved week took {took:.0f} seconds to play.")
    most = len(layers) * (len(layers) - 1) // 2 if rounds != 1 else 0
    if most:
        print(
            f"\nLater rounds add each layer that beat the champion to it: at most {count(most, 'more line-up')}, "
            f"{count(len(tournament.seeds), 'week')} each. No mix has a saved week before its first tournament."
        )
    report_conflicts(tournament)


def report_conflicts(tournament: Tournament) -> None:
    if tournament.saved.conflicts:
        print(
            f"\nSaved weeks disagree for {names(sorted(set(tournament.saved.conflicts)))}: the same code on the same "
            "seed plays the same week, so none of them is trusted and the week is played."
        )


def run(tournament: Tournament, others: list[Entrant], layers: list[str], rounds: int) -> tuple[Entrant, list[Entrant]]:
    """Plays the rounds. Returns the champion and every entrant, in the order they joined."""
    champion = lineup(())
    entrants = [champion, *others]
    left = list(layers)  # the layers still in
    number = 0
    while left and (not rounds or number < rounds):
        number += 1
        joined, refused = challengers(champion, left)
        for name, why in refused.items():
            print(f"\nOut: {name} cannot join {champion.label}: {why}.")
        if not joined:
            break
        entrants += joined
        first = [champion, *others] if number == 1 else []  # they play once: every round has the same seeds
        tournament.play([*first, *joined], number)
        if tournament.of(champion) is None:
            raise ValueError(f"{champion.label}, the system every line-up is measured against, has no week")
        print()
        print(table(tournament, [champion, *first[1:], *joined], lineup(())), end="")
        ahead = sorted((e for e in joined if tournament.beats(e, champion)), key=lambda e: standing(tournament.of(e)))
        failed = [added(e, champion) for e in joined if tournament.of(e) is None]
        lost = [added(e, champion) for e in joined if e not in ahead and tournament.of(e) is not None]
        if failed:
            print(f"\nOut: {names(failed)}, with a week that failed.")
        if lost:
            print(f"\nOut: {names(lost)} did not beat {champion.label}.")
        if not ahead:
            break
        winner = ahead[-1]
        still = {added(e, champion) for e in ahead[:-1]}
        left = [name for name in left if name in still]
        print(f"\n{winner.label} beat {champion.label}: it is the champion.", end="")
        print(f" Still in: {names(left)}." if left else " No layer is left to add.")
        champion = winner
    return champion, entrants


def finish(tournament: Tournament, champion: Entrant, entrants: list[Entrant], csv_path: Path) -> None:
    """The standings of every line-up, the champion, the best week, and the CSV."""
    reference = lineup(())
    print(f"\nStandings: level {tournament.level}, {count(len(tournament.seeds), 'seed')}.\n")
    print(table(tournament, entrants, reference), end="")
    weeks, base = tournament.of(champion), tournament.of(reference)
    if weeks and base:
        line = f"\nChampion: {champion.label}, {euros(round(mean_margin(weeks)))} a week over {len(weeks)} seeds"
        if champion != reference:
            gain = euros(round(mean_margin(weeks) - mean_margin(base)), sign=True)
            won = sum(1 for mine, theirs in zip(weeks, base) if mine.score["marginCents"] > theirs.score["marginCents"])
            line += f", {gain} over {reference.label}, ahead on {won} of {len(weeks)}"
        print(f"{line}. Play it: uv run {champion.played_by} --level {tournament.level} --seed <seed>")
    ranked = [week for week in tournament.weeks.values() if week.score["ranked"]]
    if ranked:
        best = max(ranked, key=lambda week: week.score["marginCents"])
        print(
            f"Best week: {best.label} on {best.seed}, {euros(best.score['marginCents'])}, "
            f"{best.score['onTimeShare']:.1%} on time, world {best.world_id}."
        )
    for label, why in tournament.arena.failed.items():
        print(f"\n{label} is out: {why}", file=sys.stderr)
    report_conflicts(tournament)
    write_csv(csv_path, tournament, entrants)
    played = sum(1 for week in tournament.weeks.values() if not week.saved)
    print(f"\nWrote {csv_path}. Played {count(played, 'week')}, read {len(tournament.weeks) - played} saved.")
    if played:
        print("Commit the new weeks with your PR: git add data/scrape/runs")


# Command line


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m strategies.tournament",
        description="Plays the ceiling system and the changes built on it on the same practice weeks, and stacks "
        "the changes that win into one system. Never plays a ranking run or a final. Set SPREAD_URL and SPREAD_KEY "
        "first; --plan needs neither.",
    )
    parser.add_argument("--level", type=int, choices=range(1, 9), default=8, help="the practice level (default 8)")
    parser.add_argument(
        "--seeds", default=DEFAULT_SEEDS, help=f"seeds or ranges, comma-separated (default {DEFAULT_SEEDS})"
    )
    parser.add_argument(
        "--layers", default=",".join(mix.LAYERS), help=f"the layers that take part (default: {', '.join(mix.LAYERS)})"
    )
    parser.add_argument(
        "--also",
        nargs="*",
        default=["dispatch.py"],
        metavar="FILE",
        help="other systems that play the same seeds as they are (default dispatch.py; --also alone for none)",
    )
    parser.add_argument("--rounds", type=int, default=0, metavar="N", help="stop after N rounds (default: no limit)")
    parser.add_argument(
        "--jobs",
        type=int,
        choices=range(1, SLOTS + 1),
        default=DEFAULT_JOBS,
        help=f"weeks at once, 1 to {SLOTS} (default {DEFAULT_JOBS})",
    )
    parser.add_argument("--fresh", action="store_true", help="play every week, also those with a saved week")
    parser.add_argument("--plan", action="store_true", help="print round 1 and its saved weeks, and play nothing")
    parser.add_argument("--csv", type=Path, help="where to write the CSV (default out/tournament-<date>-<time>.csv)")
    args = parser.parse_args()
    try:
        seeds = parse_seeds(args.seeds)
        layers = mix.parse_layers(args.layers)
        others = [other(spec) for spec in args.also]
    except ValueError as error:
        parser.error(str(error))
    if len({entrant.label for entrant in others}) != len(others):
        parser.error("a system is named twice")
    tournament = Tournament(seeds, args.level, args.jobs, args.fresh)
    if args.plan:
        plan(tournament, [lineup(()), *others, *challengers(lineup(()), layers)[0]], layers, args.rounds)
        return
    try:
        champion, entrants = run(tournament, others, layers, args.rounds)
    except (ValueError, SpreadError) as error:
        sys.exit(f"tournament: {error}")
    except KeyboardInterrupt:
        sys.exit("Stopped. The weeks that ended are saved under data/scrape/runs.")
    path = args.csv or Path("out") / f"tournament-{time.strftime('%Y%m%d-%H%M%S')}.csv"
    finish(tournament, champion, entrants, path)


if __name__ == "__main__":
    main()
