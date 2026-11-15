"""An orthogonal-array search of a TypeScript strategy's params on the server (issue #389).

`play` plays every setup of a JSON file ({name: {param: value}}) on every seed with `pnpm bench`, 12 weeks at once
on each key, and goes on where a stopped search ended. `--l27 <factors.json>` ({param: [low, middle, high]}, up to 13
params) makes the setups of the Taguchi L27 array, plus `default`. `report` prints each setup's mean against
`default` on the same seeds and, for an L27 search, each param's mean by level. Every week is saved by the bench.

    uv run python -m tools.orthogonal play --dir out/orth/screen --l27 factors.json --seeds orth-1..orth-12
    uv run python -m tools.orthogonal report --dir out/orth/screen
"""

import argparse
import csv
import itertools
import json
import os
import re
import statistics
import subprocess
import threading
import time
from pathlib import Path

SLOTS = 12  # weeks at once on one key
CHUNK_SECONDS = 40 * 60  # a bench call that takes longer is stopped and its missing weeks are played again
# The 13 columns of L27: every direction of a three-dimensional space over the numbers 0, 1, 2.
COLUMNS = [(1, 0, 0), (0, 1, 0), (1, 1, 0), (1, 2, 0), (0, 0, 1), (1, 0, 1), (1, 0, 2)]
COLUMNS += [(0, 1, 1), (0, 1, 2), (1, 1, 1), (1, 1, 2), (1, 2, 1), (1, 2, 2)]


def l27(factors: dict[str, list]) -> dict[str, dict]:
    """The 27 setups of the array for these params, named `r01` to `r27`, and `default` with no param changed."""
    if len(factors) > len(COLUMNS):
        raise SystemExit("L27 takes 13 params at most")
    setups: dict[str, dict] = {"default": {}}
    for row, point in enumerate(itertools.product(range(3), repeat=3), start=1):
        levels = [sum(a * b for a, b in zip(column, point, strict=True)) % 3 for column in COLUMNS]
        setups[f"r{row:02d}"] = {name: values[levels[i]] for i, (name, values) in enumerate(factors.items())}
    return setups


def spec(strategy: str, params: dict) -> str:
    """The bench's name of a setup: `lean:key=value,key=value`."""
    pairs = ",".join(f"{key}={json.dumps(value)}" for key, value in params.items())
    return f"{strategy}:{pairs}" if pairs else strategy


def seeds_of(text: str) -> list[str]:
    seeds: list[str] = []
    for item in text.split(","):
        if ".." not in item:
            seeds.append(item)
            continue
        first, last = item.split("..")
        head, start = re.fullmatch(r"(.*?)(\d+)", first).groups()
        end = re.fullmatch(r"(.*?)(\d+)", last).group(2)
        seeds += [f"{head}{n}" for n in range(int(start), int(end) + 1)]
    return seeds


def keys() -> list[str]:
    """Every Spread key of `.env`, the commented ones too."""
    found = re.findall(r"^\s*#?\s*SPREAD_KEY\w*\s*=\s*(\S+)", Path(".env").read_text(), flags=re.MULTILINE)
    return list(dict.fromkeys(key.strip("\"'") for key in found))


def weeks(folder: Path) -> list[dict]:
    """Every week in the folder's bench files, the latest play of a setup and seed."""
    rows: dict[tuple[str, str], dict] = {}
    for file in sorted(folder.glob("chunk-*.csv")):
        with file.open() as handle:
            for row in csv.DictReader(handle):
                if row["seed"] != "mean":
                    rows[(row["strategy"], row["seed"])] = row
    return list(rows.values())


def play(args: argparse.Namespace) -> None:
    folder = Path(args.dir)
    folder.mkdir(parents=True, exist_ok=True)
    setups_file = folder / "setups.json"
    if args.l27:
        setups = l27(json.loads(Path(args.l27).read_text()))
        (folder / "factors.json").write_text(Path(args.l27).read_text())
    elif args.setups:
        setups = json.loads(Path(args.setups).read_text())
    else:
        setups = json.loads(setups_file.read_text())
    setups_file.write_text(json.dumps(setups, indent=1))
    specs = [spec(args.strategy, params) for params in setups.values()]
    seeds = seeds_of(args.seeds)
    lock = threading.Lock()
    counter = itertools.count(len(list(folder.glob("chunk-*.csv"))))

    def pending() -> list[tuple[str, list[str]]]:
        done = {(row["strategy"], row["seed"]) for row in weeks(folder)}
        chunks = []
        for seed in seeds:
            left = [s for s in specs if (s, seed) not in done]
            chunks += [(seed, left[i : i + SLOTS]) for i in range(0, len(left), SLOTS)]
        return chunks

    for attempt in range(args.attempts):
        queue = pending()
        if not queue:
            break
        print(f"Round {attempt + 1}: {sum(len(c[1]) for c in queue)} weeks to play.", flush=True)

        def worker(index: int, key: str, queue: list = queue) -> None:
            env = {**os.environ, f"ORTH_KEY_{index}": key}
            running: list[tuple[subprocess.Popen, float, int]] = []
            while True:
                running = [r for r in running if r[0].poll() is None and not expired(r)]
                used = sum(size for _, _, size in running)
                with lock:
                    chunk = next((c for c in queue if len(c[1]) <= SLOTS - used), None)
                    if chunk:
                        queue.remove(chunk)
                if chunk:
                    seed, names = chunk
                    number = next(counter)
                    out = folder / f"chunk-{number:04d}.csv"
                    command = ["pnpm", "bench", *names, "--level", str(args.level), "--seeds", seed]
                    command += ["--jobs", str(len(names)), "--key-env", f"ORTH_KEY_{index}", "--csv", str(out)]
                    log = (folder / f"chunk-{number:04d}.log").open("w")
                    running.append(
                        (subprocess.Popen(command, env=env, stdout=log, stderr=log), time.time(), len(names))
                    )
                    print(f"{time.strftime('%H:%M:%S')} key {index}: {len(names)} setups on {seed}", flush=True)
                elif not running:
                    return
                else:
                    time.sleep(5)

        def expired(run: tuple[subprocess.Popen, float, int]) -> bool:
            if time.time() - run[1] < CHUNK_SECONDS:
                return False
            run[0].terminate()
            return True

        threads = [threading.Thread(target=worker, args=(i, key)) for i, key in enumerate(keys()[: args.keys])]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    print(f"{time.strftime('%H:%M:%S')} done: {len(weeks(folder))} weeks, {len(pending())} chunks left.", flush=True)


def report(args: argparse.Namespace) -> None:
    folder = Path(args.dir)
    setups = json.loads((folder / "setups.json").read_text())
    names = {spec(args.strategy, params): name for name, params in setups.items()}
    margin: dict[str, dict[str, float]] = {name: {} for name in setups}
    on_time: dict[str, dict[str, float]] = {name: {} for name in setups}
    unranked: dict[str, int] = dict.fromkeys(setups, 0)
    for row in weeks(folder):
        name = names.get(row["strategy"])
        if name is None:
            continue
        margin[name][row["seed"]] = float(row["margin_eur"])
        on_time[name][row["seed"]] = float(row["on_time_share"])
        unranked[name] += row["ranked"] != "yes"
    seeds = sorted({seed for values in margin.values() for seed in values})
    # Each week less its seed's mean over the setups: what the setup adds on that seed.
    seed_mean = {s: statistics.mean(v[s] for v in margin.values() if s in v) for s in seeds}
    centred = {name: {s: m - seed_mean[s] for s, m in values.items()} for name, values in margin.items()}
    cells = [value for values in centred.values() for value in values.values()]
    played = [name for name in setups if margin[name]]
    freedom = max(1, len(cells) - len(played) - len(seeds) + 1)
    sigma = (
        sum(value**2 for value in cells)
        - sum(len(centred[n]) * statistics.mean(centred[n].values()) ** 2 for n in played)
    ) ** 0.5 / freedom**0.5
    print(f"{len(cells)} weeks, {len(seeds)} seeds, {len(played)} setups. Residual SD of a week: €{sigma:,.0f}.\n")

    base = margin.get("default", {})
    print(
        f"{'setup':<12}{'weeks':>6}{'mean':>9}{'vs default':>12}{'± SE':>7}{'t':>6}{'min on time':>13}{'unranked':>10}"
    )
    lines = []
    for name in played:
        diffs = [margin[name][s] - base[s] for s in margin[name] if s in base]
        gain = statistics.mean(diffs) if diffs else float("nan")
        error = statistics.stdev(diffs) / len(diffs) ** 0.5 if len(diffs) > 1 else float("nan")
        lines.append((gain, name, len(margin[name]), statistics.mean(margin[name].values()), error))
    for gain, name, count, mean, error in sorted(lines, key=lambda line: -line[3]):
        t = gain / error if error and error == error else float("nan")
        low = min(on_time[name].values())
        print(f"{name:<12}{count:>6}{mean:>9,.0f}{gain:>12,.0f}{error:>7,.0f}{t:>6.1f}{low:>13.1%}{unranked[name]:>10}")

    factors_file = folder / "factors.json"
    if not factors_file.exists():
        return
    factors = json.loads(factors_file.read_text())
    rows = [name for name in played if name != "default"]
    print(
        f"\n{'param':<14}"
        + "".join(f"{label:>22}" for label in ("low", "middle", "high"))
        + f"{'range':>8}{'SE':>6}{'t':>6}"
    )
    best: dict[str, object] = {}
    for param, values in factors.items():
        means, texts, counts = [], [], []
        for value in values:
            group = [v for name in rows if setups[name][param] == value for v in centred[name].values()]
            late = min(min(on_time[name].values()) for name in rows if setups[name][param] == value)
            means.append(statistics.mean(group))
            counts.append(len(group))
            texts.append(f"{value}: {means[-1]:+,.0f} ({late:.0%})")
        error = sigma * (2 / statistics.mean(counts)) ** 0.5
        spread = max(means) - min(means)
        best[param] = values[means.index(max(means))]
        print(
            f"{param:<14}"
            + "".join(f"{text:>22}" for text in texts)
            + f"{spread:>8,.0f}{error:>6,.0f}{spread / error:>6.1f}"
        )
    print("\nEach cell: the level, its mean margin against the seed's mean, and the lowest on-time share of its weeks.")
    print(f"Best level of each param: {json.dumps(best)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["play", "report"])
    parser.add_argument("--dir", required=True, help="the search's folder, e.g. out/orth/screen")
    parser.add_argument("--strategy", default="lean")
    parser.add_argument("--l27", help="a JSON file {param: [low, middle, high]}")
    parser.add_argument("--setups", help="a JSON file {name: {param: value}}")
    parser.add_argument("--seeds", default="")
    parser.add_argument("--level", type=int, default=8)
    parser.add_argument("--keys", type=int, default=3, help="how many of the keys of .env to play on")
    parser.add_argument("--attempts", type=int, default=3, help="rounds that play the weeks still missing")
    args = parser.parse_args()
    (play if args.command == "play" else report)(args)


if __name__ == "__main__":
    main()
