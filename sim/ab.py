"""Compares strategies on the offline simulator, seed by seed.

    uv run python sim/ab.py lean lean:prior=true --seeds 120 [--offset 0] [--servers 6] [--jobs 4] [--out out/ab.csv]

Each arm is a bench spec (`<strategy>[:key=value,...]`); the first is the reference. `--seeds N` takes N of the
recorded level 8 seeds in `sim/data/L8`, evenly spread, `--offset` shifts the pick (another set of seeds), and a
comma list names seeds. It starts `--servers` simulators on `--port` and up, plays every arm on every seed (`pnpm
bench` on each; nothing is saved to `data/scrape`), and prints each arm's mean week and its paired difference to the
reference with a 95% interval. An unranked week scores nothing, as in the final: "scored" counts it as 0.

The simulator ranks strategies, it does not predict a server margin (sim/README.md): trust a difference only when it
is large, and never for fee levels or the on-time share.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def pick(count: int, offset: int) -> list[str]:
    seeds = sorted(p.name.removesuffix(".json.gz") for p in (ROOT / "sim" / "data" / "L8").glob("*.json.gz"))
    step = max(1, len(seeds) // count)
    return seeds[offset % step :: step][:count]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("arms", nargs="+")
    parser.add_argument("--seeds", default="60")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--servers", type=int, default=6)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--port", type=int, default=8840)
    parser.add_argument("--out")
    args = parser.parse_args()
    seeds = pick(int(args.seeds), args.offset) if args.seeds.isdigit() else args.seeds.split(",")
    servers = min(args.servers, len(seeds))
    env = {**os.environ, "SPREAD_RECORD": "0", "SPREAD_KEY": "sim", "NODE_NO_WARNINGS": "1"}
    start = time.time()
    sims = [
        subprocess.Popen(["node", "sim/server.ts", "--port", str(args.port + i)], cwd=ROOT, stdout=subprocess.DEVNULL)
        for i in range(servers)
    ]
    rows: list[dict] = []
    try:
        time.sleep(1.5)
        with tempfile.TemporaryDirectory() as tmp:
            runs = []
            for i in range(servers):
                out = Path(tmp) / f"{i}.csv"
                command = ["node", "src/bench.ts", *args.arms, "--level", "8", "--seeds", ",".join(seeds[i::servers])]
                command += ["--jobs", str(args.jobs), "--csv", str(out)]
                log = open(Path(tmp) / f"{i}.log", "w")
                url = f"http://localhost:{args.port + i}"
                run = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, env={**env, "SPREAD_URL": url})
                runs.append((out, log, run))
            for out, log, run in runs:
                if run.wait() != 0 or not out.exists():
                    print(Path(log.name).read_text()[-2000:], file=sys.stderr)
                    continue
                rows += [row for row in csv.DictReader(open(out)) if row["seed"] != "mean"]
    finally:
        for sim in sims:
            sim.terminate()
    if not rows:
        sys.exit("no week was played")
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    played = {row["strategy"] for row in rows}
    labels = [arm for arm in args.arms if arm in played] or sorted(played)
    by = {(row["strategy"], row["seed"]): row for row in rows}

    def scored(row: dict) -> float:
        return float(row["margin_eur"]) if row["ranked"] == "yes" else 0.0

    def mean(values: list[float]) -> float:
        return sum(values) / len(values) if values else float("nan")

    print(f"{len(seeds)} seeds, {len(rows)} weeks, {time.time() - start:.0f} s. Margins in euros a week.")
    print(f"{'arm':<44}{'margin':>9}{'scored':>9}{'orders':>8}{'on time':>9}{'ranked':>9}   vs reference (scored, 95%)")
    for label in labels:
        mine = [row for row in rows if row["strategy"] == label]
        line = f"{label[:43]:<44}{mean([float(r['margin_eur']) for r in mine]):>9.0f}{mean([scored(r) for r in mine]):>9.0f}"
        line += f"{mean([float(r['won_orders']) for r in mine]):>8.0f}"
        line += f"{100 * mean([float(r['on_time_share']) for r in mine]):>8.1f}%"
        line += f"{sum(r['ranked'] == 'yes' for r in mine):>5}/{len(mine):<3}"
        pairs = [scored(by[label, s]) - scored(by[labels[0], s]) for s in seeds if (label, s) in by and (labels[0], s) in by]
        if label != labels[0] and len(pairs) > 1:
            d = mean(pairs)
            se = math.sqrt(sum((p - d) ** 2 for p in pairs) / (len(pairs) - 1) / len(pairs))
            line += f"   {d:+.0f} ± {1.96 * se:.0f}, ahead on {sum(p > 0 for p in pairs)} of {len(pairs)}"
        print(line)


if __name__ == "__main__":
    main()
