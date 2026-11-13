"""Measures the note reader on reveals: how often it agrees with what was true of each won car, per fact,
next to the starter's reader. Reads folders written by `uv run spread-reveal-csv <world id>`.

    uv run python -m strategies.notes.check reveal-<world id> [reveal-<world id> ...] [--misses <fact>]
"""

from __future__ import annotations

import argparse
import csv
import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from spread.starter import window_from_note

from strategies.notes.reader import DAY, NO_FACTS, read_note

OPTIONS = ["same_day", "next_day", "within_3_days"]
FACTS = ["earliest pickup", "pickup hours", "delivery hours", "deadline", "manual gearbox", "no plates", "summer tyres"]


@dataclass
class Leg:
    """One won car with a note: what the request stated, and what was true."""

    note: str
    language: str
    leg: int  # a note speaks of the first car: in a trade-in, the new car
    arrived_at: int
    deadline: int  # of the won option
    latest: int  # the latest option's deadline: a note's deadline counts only before it
    stated_from: int
    stated_to: int
    delivery_from: int
    pickup_hours: tuple[int, int] | None
    delivery_hours: tuple[int, int] | None
    truth: dict[str, object]


def _int(value: str) -> int | None:
    return int(value) if value not in ("", None) else None


def _hours(row: dict[str, str], prefix: str) -> tuple[int, int] | None:
    opens, closes = _int(row.get(f"{prefix}.opens", "")), _int(row.get(f"{prefix}.closes", ""))
    return None if opens is None or closes is None else (opens, closes)


def load(folders: Iterable[str]) -> list[Leg]:
    """The won legs with a note in the folders. A week played twice on one seed counts once."""
    legs: list[Leg] = []
    seen: set[tuple[str, str, str, str]] = set()
    for folder in folders:
        with open(os.path.join(folder, "requests.csv"), encoding="utf-8") as file:
            requests = {r["id"]: r for r in csv.DictReader(file)}
        with open(os.path.join(folder, "legs.csv"), encoding="utf-8") as file:
            rows = list(csv.DictReader(file))
        for row in rows:
            request = requests[row["requestId"]]
            if request["outcome"] != "won" or not request["note"]:
                continue
            key = (request["note"], request["arrivedAt"], request["dealerId"], row["leg"])
            if key in seen:
                continue
            seen.add(key)
            ready, released = int(row["truth.readyAt"]), _int(row["truth.releasedAt"])
            truth = {
                "earliest pickup": max(ready, released or 0),
                "pickup hours": _hours(row, "truth.pickupHours"),
                "delivery hours": _hours(row, "truth.deliveryHours"),
                "deadline": _int(row["truth.noteDeadline"]),
                "manual gearbox": row["truth.manualGearbox"] == "true",
                "no plates": row["truth.needsPlates"] == "true",
                "summer tyres": row["truth.summerTyres"] == "true",
            }
            legs.append(
                Leg(
                    note=request["note"],
                    language=request["language"],
                    leg=int(row["leg"]),
                    arrived_at=int(request["arrivedAt"]),
                    deadline=int(request[f"{request['option']}.deadline"]),
                    latest=max(int(request[f"{k}.deadline"]) for k in OPTIONS if request.get(f"{k}.deadline")),
                    stated_from=int(row["pickup.window.from"]),
                    stated_to=int(row["pickup.window.to"]),
                    delivery_from=int(row["delivery.window.from"]),
                    pickup_hours=_hours(row, "pickup.hours"),
                    delivery_hours=_hours(row, "delivery.hours"),
                    truth=truth,
                )
            )
    return legs


def _with(stated: tuple[int, int] | None, opens: int | None, closes: int | None) -> tuple[int, int] | None:
    if stated is None:
        return None
    return (stated[0] if opens is None else opens, stated[1] if closes is None else closes)


def ours(leg: Leg) -> dict[str, object]:
    facts = read_note(leg.note, leg.arrived_at) if leg.leg == 0 else NO_FACTS
    ph, dh = facts.pickup_hours, facts.delivery_hours
    return {
        "earliest pickup": max(leg.stated_from, facts.earliest_pickup or 0),
        "pickup hours": _with(leg.pickup_hours, ph and ph.opens, ph and ph.closes),
        "delivery hours": _with(leg.delivery_hours, dh and dh.opens, dh and dh.closes),
        "deadline": facts.deadline if facts.deadline is not None and facts.deadline < leg.latest else None,
        "manual gearbox": facts.manual,
        "no plates": facts.plates,
        "summer tyres": facts.summer_tyres,
    }


def starters(leg: Leg) -> dict[str, object]:
    """The starter's reader gives only windows: a later pickup start is the earliest pickup, an earlier pickup
    end the site's closing time, and an earlier delivery end both the delivery site's closing time and the deadline."""
    note = {"text": leg.note, "language": leg.language}
    pickup = window_from_note(note, {"from": leg.stated_from, "to": leg.stated_to}, "pickup")
    base = {"from": leg.delivery_from, "to": max(leg.delivery_from, leg.deadline)}
    delivery = window_from_note(note, base, "delivery")
    pickup_close = pickup["to"] % DAY if pickup["to"] < leg.stated_to else None
    delivery_close = delivery["to"] % DAY if delivery["to"] < base["to"] else None
    return {
        "earliest pickup": pickup["from"],
        "pickup hours": _with(leg.pickup_hours, None, pickup_close),
        "delivery hours": _with(leg.delivery_hours, None, delivery_close),
        "deadline": delivery["to"] if delivery["to"] < min(base["to"], leg.latest) else None,
        "manual gearbox": False,
        "no plates": False,
        "summer tyres": False,
    }


def _stated(leg: Leg, fact: str) -> object:
    """What the request alone says: the default when a note says nothing."""
    return {
        "earliest pickup": leg.stated_from,
        "pickup hours": leg.pickup_hours,
        "delivery hours": leg.delivery_hours,
        "deadline": None,
    }.get(fact, False)


def score(legs: list[Leg], reader: Callable[[Leg], dict[str, object]]) -> dict[str, tuple[int, int, int, int]]:
    """Per fact: notes counted, notes it agrees on, notes where the note changed the fact, and those it read right."""
    result: dict[str, tuple[int, int, int, int]] = {}
    read = [reader(leg) for leg in legs]
    for fact in FACTS:
        counted = agree = changed = caught = 0
        for leg, guess in zip(legs, read):
            truth = leg.truth[fact]
            if fact.endswith("hours") and truth is None:
                continue  # a private address has no hours
            counted += 1
            agree += guess[fact] == truth
            if truth != _stated(leg, fact):
                changed += 1
                caught += guess[fact] == truth
        result[fact] = (counted, agree, changed, caught)
    return result


def table(legs: list[Leg]) -> str:
    new, old = score(legs, ours), score(legs, starters)
    lines = [
        "| Fact | Notes | Changed by the note | Starter agrees | Reader agrees | Starter reads the change | Reader reads the change |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for fact in FACTS:
        n, a, c, k = new[fact]
        _, a0, _, k0 = old[fact]
        lines.append(f"| {fact} | {n} | {c} | {a0 / n:.1%} | {a / n:.1%} | {k0}/{c} | {k}/{c} |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("folders", nargs="+", help="folders written by spread-reveal-csv")
    parser.add_argument("--misses", choices=FACTS, help="also list the notes where the reader gets this fact wrong")
    args = parser.parse_args()
    legs = load(args.folders)
    print(f"{len(legs)} won cars with a note, in {len(args.folders)} reveals.\n")
    print(table(legs))
    if args.misses:
        print(f"\nNotes where the reader gets {args.misses} wrong (reader → truth):")
        for leg in legs:
            guess, truth = ours(leg)[args.misses], leg.truth[args.misses]
            if guess != truth and not (args.misses.endswith("hours") and truth is None):
                print(f"  [{leg.language}] {fmt(leg.arrived_at)} {leg.note!r}: {show(guess)} → {show(truth)}")


def fmt(minute: int) -> str:
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    week = "" if minute < 7 * DAY else "+"
    return f"{days[minute // DAY % 7]}{week} {minute % DAY // 60:02d}:{minute % 60:02d}"


def show(value: object) -> str:
    if isinstance(value, bool) or value is None:
        return str(value)
    if isinstance(value, int):
        return fmt(value)
    if isinstance(value, tuple):
        return "-".join(f"{m // 60:02d}:{m % 60:02d}" for m in value)
    return str(value)


if __name__ == "__main__":
    main()
