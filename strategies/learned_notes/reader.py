"""A NoteReader extended by reviewed phrases from phrases.json. The rule reader still runs first; a learned phrase
only fills a fact the rules left empty. See README.md next to this file for the data format and offline fitting.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from spread.types import DriverProfile, PriceRequest, WorldMap

from strategies.notes import Hours, NoteFacts, NoteReader
from strategies.notes.reader import DAY, normalise
from strategies.strategy import NoParams

PHRASES = Path(__file__).with_name("phrases.json")
TIMES = {"ready_at", "released_at", "deadline"}
HOURS = {"pickup_hours", "delivery_hours"}
BOOLEANS = {"manual", "plates", "summer_tyres"}


@dataclass(frozen=True)
class Phrase:
    """One reviewed literal or regular expression and the fact values it supplies."""

    literal: str | None
    regex: re.Pattern[str] | None
    facts: dict[str, object]

    def matches(self, note: str) -> bool:
        return self.literal in note if self.literal is not None else bool(self.regex and self.regex.search(note))


def load_phrases(path: Path = PHRASES) -> list[Phrase]:
    """Loads reviewed data, not executable model weights. Each entry has exactly one of `literal` and `regex`."""
    data = json.loads(path.read_text(encoding="utf-8"))
    phrases = []
    for item in data.get("phrases", []):
        literal, regex = item.get("literal"), item.get("regex")
        if (literal is None) == (regex is None):
            raise ValueError("A learned phrase needs exactly one of 'literal' and 'regex'")
        phrases.append(
            Phrase(
                normalise(literal) if literal is not None else None,
                re.compile(regex, re.IGNORECASE) if regex is not None else None,
                item["facts"],
            )
        )
    return phrases


def merge_facts(first: NoteFacts, second: NoteFacts) -> NoteFacts:
    """Keeps every value already in `first`, including each half of its opening hours, and fills only the gaps."""
    values: dict[str, object] = {}
    for name in TIMES:
        values[name] = getattr(first, name) if getattr(first, name) is not None else getattr(second, name)
    for name in HOURS:
        a, b = getattr(first, name), getattr(second, name)
        values[name] = (
            None
            if a is None and b is None
            else Hours(
                a.opens if a is not None and a.opens is not None else b and b.opens,
                a.closes if a is not None and a.closes is not None else b and b.closes,
            )
        )
    for name in BOOLEANS:
        values[name] = getattr(first, name) or getattr(second, name)
    return NoteFacts(**values)  # type: ignore[arg-type]


class LearnedNoteReader(NoteReader):
    """The rule-based note reader with a second, data-filled layer that can never replace a rule-based fact."""

    def __init__(
        self, roster: list[DriverProfile], world_map: WorldMap, level: int = 8, params: NoParams | None = None
    ) -> None:
        super().__init__(roster, world_map, level, params)
        self.phrases = load_phrases()

    def _learned(self, text: str, arrived_at: int) -> NoteFacts:
        facts = NoteFacts()
        note = normalise(text)
        for phrase in self.phrases:
            if not phrase.matches(note):
                continue
            values: dict[str, object] = {}
            for name, value in phrase.facts.items():
                if name in TIMES:
                    if not isinstance(value, dict):
                        raise ValueError(f"Learned time fact {name} needs 'days' and 'minute'")
                    values[name] = (arrived_at // DAY + int(value["days"])) * DAY + int(value["minute"])
                elif name in HOURS:
                    if not isinstance(value, dict):
                        raise ValueError(f"Learned hours fact {name} needs 'opens' and 'closes'")
                    values[name] = Hours(value.get("opens"), value.get("closes"))
                elif name in BOOLEANS:
                    values[name] = bool(value)
                else:
                    raise ValueError(f"Unknown learned note fact: {name}")
            # Phrases are tried in file order. An earlier learned value wins too, making review order explicit.
            facts = merge_facts(facts, NoteFacts(**values))  # type: ignore[arg-type]
        return facts

    def read(self, request: PriceRequest) -> NoteFacts:
        """Reads with the base rules first, then adds matching phrase facts only where the base result has a gap."""
        if request["id"] not in self.facts:
            base = super().read(request)
            text = request["note"] and request["note"]["text"]
            learned = self._learned(text, request["arrivedAt"]) if text else NoteFacts()
            self.facts[request["id"]] = merge_facts(base, learned)
        return self.facts[request["id"]]
