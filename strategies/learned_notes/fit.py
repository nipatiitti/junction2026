"""Proposes reviewed note phrases from reveal JSON already committed under data/scrape/runs, without network access.

    uv run python -m strategies.learned_notes.fit

Only won cars' first legs carry note truth. A candidate is a normalised whole-note literal for which the base reader
returned NO_FACTS but the reveal differs from the request's stated facts. Conflicting literals are left for manual
review rather than written. The output replaces phrases.json; inspect every candidate before using it.
"""

from __future__ import annotations

import argparse
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path

from strategies.notes.reader import DAY, NO_FACTS, normalise, read_note

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "data/scrape/runs"
OUT = Path(__file__).with_name("phrases.json")


def relative_time(value: int, arrived_at: int) -> dict[str, int]:
    """A JSON time that the reader can resolve against another request's arrival day."""
    return {"days": value // DAY - arrived_at // DAY, "minute": value % DAY}


def changed_hours(stated: dict | None, truth: dict | None) -> dict[str, int] | None:
    """The revealed weekday hours when they add a note fact, rather than repeat the request."""
    if truth is None:
        return None
    hours = {"opens": truth["opens"], "closes": truth["closes"]}
    return None if stated and all(stated.get(k) == v for k, v in hours.items()) else hours


def reveal_facts(request: dict, order: dict) -> dict[str, object]:
    """Facts on the first leg that the request alone did not already state."""
    if not order.get("legs"):
        return {}
    stated, truth = request["legs"][0], order["legs"][0]
    arrived_at = request["arrivedAt"]
    stated_from = stated["pickup"]["window"]["from"]
    facts: dict[str, object] = {}
    for name, key in (("ready_at", "readyAt"), ("released_at", "releasedAt")):
        value = truth.get(key)
        if value is not None and value > stated_from:
            facts[name] = relative_time(value, arrived_at)
    for name, side, key in (
        ("pickup_hours", "pickup", "pickupHours"),
        ("delivery_hours", "delivery", "deliveryHours"),
    ):
        hours = changed_hours(stated[side].get("hours"), truth.get(key))
        if hours is not None:
            facts[name] = hours
    latest = max(option["deadline"] for option in request["options"])
    if truth.get("noteDeadline") is not None and truth["noteDeadline"] < latest:
        facts["deadline"] = relative_time(truth["noteDeadline"], arrived_at)
    for name, key in (("manual", "manualGearbox"), ("plates", "needsPlates"), ("summer_tyres", "summerTyres")):
        if truth.get(key):
            facts[name] = True
    return facts


def fit(runs: Path) -> tuple[list[dict], int, int]:
    """Returns unambiguous candidates, the number of usable won noted cars, and ambiguous literal count."""
    observations: dict[str, Counter[str]] = defaultdict(Counter)
    encoded_facts: dict[str, dict[str, object]] = {}
    usable = 0
    seen: set[tuple[str, int, str]] = set()
    for path in sorted(runs.rglob("reveal.json.gz")):
        try:
            with gzip.open(path, "rt", encoding="utf-8") as file:
                reveal = json.load(file)
        except OSError, json.JSONDecodeError:
            continue
        orders = {order["orderId"]: order for order in reveal.get("orders", [])}
        for entry in reveal.get("requests", []):
            request = entry.get("request", entry)
            note = request.get("note")
            order = orders.get(request["id"])
            if entry.get("outcome", request.get("outcome")) != "won" or not note or order is None:
                continue
            key = (note["text"], request["arrivedAt"], request["dealerId"])
            if key in seen:
                continue
            seen.add(key)
            usable += 1
            if read_note(note["text"], request["arrivedAt"]) != NO_FACTS:
                continue
            facts = reveal_facts(request, order)
            if not facts:
                continue
            encoded = json.dumps(facts, sort_keys=True)
            observations[normalise(note["text"])][encoded] += 1
            encoded_facts[encoded] = facts
    phrases = []
    for literal, variants in sorted(observations.items()):
        if len(variants) != 1:
            continue
        encoded, support = next(iter(variants.items()))
        phrases.append({"literal": literal, "facts": encoded_facts[encoded], "support": support})
    return phrases, usable, sum(len(v) > 1 for v in observations.values())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--runs", type=Path, default=RUNS, help="local saved-week root; never fetched")
    parser.add_argument("--out", type=Path, default=OUT, help="candidate JSON to replace")
    args = parser.parse_args()
    phrases, usable, ambiguous = fit(args.runs)
    args.out.write_text(json.dumps({"phrases": phrases}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if usable == 0:
        print(f"No usable reveal data found; wrote an empty {args.out}")
        return
    print(
        f"Read {usable} won noted cars; wrote {len(phrases)} candidate phrases to {args.out} "
        f"({ambiguous} conflicting literals omitted). Review the data before use."
    )


if __name__ == "__main__":
    main()
