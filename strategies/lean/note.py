"""Reads a dealer's note (Finnish, Swedish or English) into facts: when the car is ready or released, the real opening
hours of both sites, a tighter deadline, and the car facts that decide who may drive it. A port of `src/ops/note.ts`,
which is itself a port of strategies/notes/reader.py with a few phrasings more ("ma viideltä"). Python's `re` gives
`\\b` and `\\w` their Unicode meaning already, so the patterns read as in note.ts without its `rx` helper; `$` at the
end of the input is `\\Z`, as JavaScript's `$` without the `m` flag."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

HOUR, DAY = 60, 24 * 60


@dataclass(frozen=True)
class NoteFacts:
    """What a note says. Times are world minutes; None when the note does not say."""

    ready_at: int | None = None
    released_at: int | None = None
    pickup_hours: dict | None = None  # {opens?, closes?}: the pickup site's real weekday hours
    delivery_hours: dict | None = None
    deadline: int | None = None
    manual: bool = False
    plates: bool = False
    summer_tyres: bool = False


NO_FACTS = NoteFacts()


def earliest_pickup(facts: NoteFacts) -> int | None:
    """The first minute the car can be collected by the note: ready and, if it waits for payment, released."""
    times = [t for t in (facts.ready_at, facts.released_at) if t is not None]
    return max(times) if times else None


def read_note(note: dict | str | None, arrived_at: float) -> NoteFacts:
    """The facts a note states, with days counted from the day the request arrived. A note it cannot read gives
    NO_FACTS, never an error."""
    text = note if isinstance(note, str) else (note or {}).get("text") if isinstance(note, dict | None) else None
    if not text or not isinstance(arrived_at, int | float):
        return NO_FACTS
    try:
        return read(text, int(arrived_at))
    except Exception:  # noqa: BLE001  (a note the reader cannot read is a note without facts)
        return NO_FACTS


# ----------------------------------------------------------------------------------------------------- typos

KNOWN_WORDS = [
    "tänään", "huomenna", "ylihuomenna", "today", "tomorrow", "idag", "imorgon", "morgon", "övermorgon", "maanantai",
    "maanantaina", "tiistai", "tiistaina", "keskiviikko", "keskiviikkona", "torstai", "torstaina", "perjantai",
    "perjantaina", "lauantai", "lauantaina", "sunnuntai", "sunnuntaina", "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday", "måndag", "tisdag", "onsdag", "torsdag", "fredag", "lördag", "söndag", "perillä",
    "perille", "mennessä", "viimeistään", "toimitus", "vastaanotto", "vastaanottava", "vastaanotetaan", "kohde",
    "kohteen", "valmis", "valmiina", "vasta", "noudettavissa", "aikaisintaan", "alkaen", "jälkeen", "ennen",
    "haettava", "haettavissa", "nouto", "noutaa", "kiinni", "sulkee", "aukioloajat", "arkisin", "arkipäivisin",
    "avoinna", "liike", "maksun", "maksaa", "maksettu", "maksu", "luovutus", "luovutetaan", "ostaja", "asiakas",
    "korjaus", "correction", "rättelse", "destination", "receiving", "arrive", "arrival", "earliest", "released",
    "payment", "before", "pickup", "collect", "closes", "weekdays", "manuaali", "manuaalivaihteinen",
    "manuaalivaihteet", "manuaalivaihteisto", "käsivaihteinen", "automaatti", "manual", "transmission", "automatic",
    "kilvet", "kilpiä", "rekisterikilvet", "siirtokilvet", "koekilvet", "rekkareita", "plates", "unregistered",
    "skyltar", "provskyltar", "kesärenkaat", "kesärenkailla", "talvirenkaita", "summer", "tyres", "sommardäck",
    "winters",
]  # fmt: skip
KNOWN = set(KNOWN_WORDS)


def one_edit(a: str, b: str) -> bool:
    """One letter dropped, added, changed, or two neighbours swapped."""
    if a == b or abs(len(a) - len(b)) > 1:
        return a == b
    if len(a) == len(b):
        diff = [k for k in range(len(a)) if a[k] != b[k]]
        i, j = (diff + [0, 0])[:2]
        return len(diff) == 1 or (len(diff) == 2 and j == i + 1 and a[i] == b[j] and a[j] == b[i])
    short, long = (a, b) if len(a) < len(b) else (b, a)
    i = 0
    while i < len(short) and short[i] == long[i]:
        i += 1
    return short[i:] == long[i + 1 :]


def fix_word(word: str) -> str:
    if len(word) < 5 or word in KNOWN:
        return word
    return next((known for known in KNOWN_WORDS if one_edit(word, known)), word)


def normalise(text: str) -> str:
    text = re.sub("[–—]", "-", text.lower())
    return re.sub("[a-zåäö]+", lambda m: fix_word(m.group(0)), text)


# ------------------------------------------------------------------------------------------------- car facts

MANUAL = re.compile(
    r"manuaal|manuell|\bmanual\b|ei automaatti|no automatic|inte automat|stick shift|käsivaiht|växlad för hand"
)
NOT_MANUAL = re.compile(r"(?:not|ei|inte|no)\s+(?:a\s+|en\s+)?(?:manual|manuaal|manuell)")
PLATES = re.compile(
    r"kilv|kilpi|rekkari|rekisteristä|\bplates? removed|no plates|without plates|unregistered|trade plates"
    r"|transfer plates|skylt|avregistrer"
)
SUMMER_TYRES = re.compile(
    "kesärenkaat alla|kesärenkailla|kesärenkaille|talvirenkaita ei|ei talvirenkaita|talvirenkaat puuttu|"
    "on summer tyres|summer tyres on|still on summer|no winter|sommardäck på|sommardäcken på|på sommardäck|"
    "inga vinterdäck"
)

# ------------------------------------------------------------------------------------- days and clock times

FI_DAYS = ["maanantai", "tiistai", "keskiviikko", "torstai", "perjantai", "lauantai", "sunnuntai"]
SV_DAYS = ["måndag", "tisdag", "onsdag", "torsdag", "fredag", "lördag", "söndag"]
EN_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
SHORT_DAYS = {
    "ma": 0, "ti": 1, "ke": 2, "to": 3, "pe": 4, "la": 5, "su": 6,
    "mån": 0, "tis": 1, "ons": 2, "tors": 3, "fre": 4, "lör": 5, "sön": 6,
    "mon": 0, "tue": 1, "tues": 1, "wed": 2, "thu": 3, "thur": 3, "thurs": 3, "fri": 4, "sat": 5, "sun": 6,
}  # fmt: skip
RELATIVE = [
    (r"ylihuomen\w*|i övermorgon|övermorgon|day after tomorrow", 2),
    (r"huomen\w*|i morgon|imorgon|tomorrow|tmrw|tmr|tomoz", 1),
    ("tänään|idag|today|tonight", 0),
]
FI_HOURS = [
    ("yhdeks", 9), ("kahdeks", 8), ("seitsem", 7), ("kymmen", 10), ("yhde", 1), ("yhte", 1), ("yksi", 1),
    ("kahde", 2), ("kahte", 2), ("kaksi", 2), ("kolm", 3), ("nelj", 4), ("viid", 5), ("viit", 5), ("viisi", 5),
    ("kuud", 6), ("kuut", 6), ("kuusi", 6),
]  # fmt: skip
WORD_HOURS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "ett": 1, "två": 2, "tre": 3, "fyra": 4, "fem": 5, "sex": 6, "nio": 9, "tio": 10, "elva": 11, "tolv": 12,
}  # fmt: skip
NOON = re.compile(r"\b(?:noon|midday|keskipäivä\w*|middag|lunchtid)\b")


def working_hour(number: int) -> int:
    return number + 12 if number < 9 else number


def fi_word_hour(word: str) -> int | None:
    found = next((hour for stem, hour in FI_HOURS if word.startswith(stem)), None)
    if found is None:
        return None
    return found + 10 if "toista" in word or "toisat" in word else found


FI_TIME_WORD = r"(?:yh|ka|ko|ne|vi|ku|se|ky)\w*?(?:lta|ltä|sta|stä|toista|toisat)\b"
FI_HOUR_WORD = re.compile(
    rf"\b(?:puoli\s+)?({FI_TIME_WORD})"
    r"|\b(?:puoli\s+)?((?:yh|ka|ko|ne|vi|ku|se|ky)\w*?(?:en|än|ään|aan|n))(?=\s+(?:mennessä|asti|saakka|jälkeen))"
)
CLOCK = re.compile(
    r"(?P<pre>\b(?:klo|kl|kello|klockan|at)\.?\s*)?"
    r"(?:(?P<h>\d{1,2})(?:[:.](?P<m>\d{2}))?\s*(?P<ampm>[ap]\.?m\.?)\b"
    r"|(?P<h2>\d{1,2})[:.](?P<m2>\d{2})(?![\d.:])"
    r"|(?P<h3>\d{1,2}):?(?:stä|sta|een|ään|aan|lta|ltä)\b)"
)
KLO = re.compile(r"\b(?:klo|kl|kello|klockan)\.?\s*(?P<h>\d{1,2})(?P<m>\d{2})?\b(?![:.]\d)")
BARE = re.compile(
    r"\b(?P<h>\d{1,2})\b(?![:.]\d|\s*(?:min|h\b|tun|tim|hour|km|tkm|%|e\b|€|kpl|sarja|set|rengas|tyre|däck))"
)
WORD_CUE = re.compile(r"\b(?:klo|kello|kl|klockan|at|by|from|until|till|before|after|around|från|före|efter)\s+\Z")
SHORT = re.compile(
    rf"\b({'|'.join(SHORT_DAYS)})\b\.?(?=\s*(?:klo|kl|kello|at)?\s*\d|\s+(?:puoli\s+)?{FI_TIME_WORD}|\s*[.!,]?\s*\Z)"
)
RELATIVE_PATTERNS = [(re.compile(rf"\b(?:{pattern})\b"), offset) for pattern, offset in RELATIVE]
NAME_PATTERNS = [
    (re.compile(rf"\b(?:på\s+)?{name.removesuffix('i')}\w*"), number)
    for names in (FI_DAYS, SV_DAYS, EN_DAYS)
    for number, name in enumerate(names)
]
DASH = re.compile(r"\s*-\s*[a-zåäö]")
WORD = re.compile(r"\b(?:(half|halv|puoli)\s+)?([a-zåäö]+)\b")
OCLOCK = re.compile(r"\s*o'?clock")
AFTER_BARE = re.compile(r"\s*(?:asti|saakka|mennessä|jälkeen|alkaen|och framåt|latest|at the latest)\b")


class Expr:
    """A day, a time of day, or both, found in a note."""

    __slots__ = ("day", "end", "minute", "start", "weekday")

    def __init__(self, start: int, end: int, day=None, weekday=None, minute=None) -> None:
        self.start, self.end, self.day, self.weekday, self.minute = start, end, day, weekday, minute


def day_matches(text: str) -> list[Expr]:
    found: list[Expr] = []
    for pattern, offset in RELATIVE_PATTERNS:
        found += [Expr(m.start(), m.end(), day=offset) for m in pattern.finditer(text)]
    for pattern, number in NAME_PATTERNS:
        found += [Expr(m.start(), m.end(), weekday=number) for m in pattern.finditer(text)]
    found += [Expr(m.start(), m.end(), weekday=SHORT_DAYS.get(m.group(1))) for m in SHORT.finditer(text)]
    days = sorted((e for e in found if not DASH.match(text, e.end)), key=lambda e: (e.start, -(e.end - e.start)))
    kept: list[Expr] = []
    for e in days:
        if not kept or e.start >= kept[-1].end:
            kept.append(e)
    return kept


def time_matches(text: str, days: list[Expr]) -> list[Expr]:
    found: list[Expr] = []

    def add(start: int, end: int, minute: int) -> None:
        if minute <= 24 * HOUR and not any(e.start < end and start < e.end for e in found):
            found.append(Expr(start, end, minute=minute))

    for m in CLOCK.finditer(text):
        g = m.groupdict()
        if g["ampm"]:
            hour = int(g["h"]) % 12 + (12 if g["ampm"].startswith("p") else 0)
            add(m.start(), m.end(), hour * HOUR + int(g["m"] or 0))
        elif g["h2"]:
            if int(g["m2"]) < 60:
                add(m.start(), m.end(), int(g["h2"]) * HOUR + int(g["m2"]))
        else:
            add(m.start(), m.end(), int(g["h3"]) * HOUR)
    for m in KLO.finditer(text):
        add(m.start(), m.end(), int(m.group("h")) * HOUR + int(m.group("m") or 0))
    for m in NOON.finditer(text):
        add(m.start(), m.end(), 12 * HOUR)
    for m in FI_HOUR_WORD.finditer(text):
        number = fi_word_hour(m.group(1) or m.group(2) or "")
        if number is not None:
            add(m.start(), m.end(), working_hour(number) * HOUR - (30 if m.group(0).startswith("puoli") else 0))
    for m in WORD.finditer(text):
        half, word = m.group(1), m.group(2) or ""
        if word not in WORD_HOURS and not (half == "puoli" and fi_word_hour(word) is not None):
            continue
        cued = half or WORD_CUE.search(text[: m.start()]) or OCLOCK.match(text, m.end())
        number = WORD_HOURS.get(word)
        if number is None:
            number = fi_word_hour(word)
        if cued and number is not None:
            add(m.start(), m.end(), working_hour(number) * HOUR - (30 if half else 0))
    for m in BARE.finditer(text):
        after_day = any(0 <= m.start() - d.end <= 2 for d in days)
        if after_day or AFTER_BARE.match(text, m.end()):
            add(m.start(), m.end(), int(m.group("h")) * HOUR)
    return found


JOINS = re.compile(r"^[\s,]*(?:klo|kl|kello|klockan|at|on|från|from)?\.?\s*\Z")


def expressions(text: str) -> list[Expr]:
    """The days and times in a piece of note, a day joined with the time right next to it."""
    days = day_matches(text)
    items = sorted([*days, *time_matches(text, days)], key=lambda e: e.start)
    joined: list[Expr] = []
    for e in items:
        last = joined[-1] if joined else None
        if last and JOINS.search(text[last.end : e.start]) and (last.minute is None) != (e.minute is None):
            last.end = e.end
            if last.minute is None:
                last.minute = e.minute
            if last.day is None and last.weekday is None:
                last.day, last.weekday = e.day, e.weekday
        else:
            joined.append(e)
    return joined


RANGE = re.compile(
    r"(?P<a>\d{1,2})(?:[:.](?P<am>\d{2}))?\s*(?P<ap>[ap]\.?m\.?)?"
    r"(?:\s*(?:-|to|till|until)\s*|:?(?:sta|stä)\s+)"
    r"(?P<b>\d{1,2})(?:[:.](?P<bm>\d{2}))?\s*(?P<bp>[ap]\.?m\.?)?(?::?(?:een|ään|aan))?(?![\d:.]\d)"
)


def clock(hour: str | None, minute: str | None, ampm: str | None) -> int:
    h = int(hour or 0) % 12 + (12 if ampm.startswith("p") else 0) if ampm else int(hour or 0)
    return h * HOUR + int(minute or 0)


def opening_range(text: str) -> tuple[int, int] | None:
    """The last opening hours given as a range: "9-16", "klo 7.00 - 14.30", "8am - 7pm", "8:sta 20:een"."""
    best = None
    for m in RANGE.finditer(text):
        opens = clock(m.group("a"), m.group("am"), m.group("ap"))
        closes = clock(m.group("b"), m.group("bm"), m.group("bp"))
        if 0 <= opens < closes <= 24 * HOUR:
            best = (opens, closes)
    return best


# ------------------------------------------------------------------------------- clauses and what each says

ABBREVIATIONS = {"viim", "klo", "kl", "n", "oik", "esim", "t", "ca", "nro", "no", "ref"}
CORRECTION = (
    "(?:ei kun|eikun|ei vaan|korjaus|correction|rättelse|sorry,? i mean|i mean|or rather|nej,? förlåt|förlåt|jag menar)"
)
CORRECTS = re.compile(rf"(?:^|[\s,(])(?:{CORRECTION})\s*[:,]?\s*\Z")
DENIES = re.compile(r"(?:^|[\s,(])(?:ei|not|inte)\s*\(?\s*\Z")
SELLER = re.compile("myyjä|seller|säljare|omistaja|owner|ägare")
RELEASE = re.compile("maks|payment|paid|pays|betal|rahoitus|financ|kauppa kesken|luovut|handover|handed over|lämnas ut")
OPEN_WORDS = re.compile(
    "auki|avoinna|aukiolo|open|öppet|arkisin|arkipäivisin|weekdays|vardagar|ma-pe|mon-fri|hours|receiving|"
    "vastaanot|mottag|nouto|noudettavissa|pickup|pikup|collect|hämt|kiinni|close"
)
NO_MORE = re.compile("ei enää|no more|inga fler|ingen utlämning|no handovers")
READY_NOW = re.compile(r"\b(?:ready|valmis|valmiina|klar)\s+(?:now|nyt|nu|heti|right away|direkt)\b")
SHUTS = re.compile(r"kiinni|sulkee|\bclose|stäng|asti|saakka|until|ei ketään|nobody|no one|ingen")
DEADLINE = re.compile(
    "perillä|perille|framme|at (?:the )?destination|must be at|must arrive|arrive by|arrival|deliver(?:ed)? by"
    "|mennessä|levererad|no later than|must be there|oltava silloin|på plats|ska vara|måste vara"
)
READY = re.compile(
    "valmi|ready|klar|aikaisintaan|earliest|tidigast|alkaen|voi noutaa|saa hakea|saa noutaa|haettavissa|"
    "pickup from|pick up from|och framåt|available"
)
BEFORE = re.compile(r"\bbefore\b|\bennen\b|före|viimeistään|haku viim|latest|by\b")
AFTER = re.compile("jälkeen|after|efter|from|från")
DELIVERY_SIDE = re.compile(
    "kohde|kohteen|vastaanot|perillä|perille|destination|receiv|mottag|toimitus|leverans|deliver|framme"
)


def role(clause: str) -> str | None:
    """What the times in a clause mean."""
    if SELLER.search(clause):
        return None
    text = READY_NOW.sub(" ", clause)
    if NO_MORE.search(text):
        return "closes"
    if RELEASE.search(text):
        return "release"
    if opening_range(text) and (OPEN_WORDS.search(text) or not READY.search(text)):
        return "hours"
    if SHUTS.search(text) and not READY.search(text):
        return "closes"
    if DEADLINE.search(text):
        return "deadline"
    if READY.search(text):
        return "ready"
    if BEFORE.search(text):
        return "closes"
    if AFTER.search(text):
        return "ready"
    return None


SPLITS = re.compile(r"[.!?;\n]|\s/\s")
LAST_WORD = re.compile(r"([a-zåäö]+|\d+)\Z")


def split(text: str) -> list[str]:
    """Sentences, and the halves of a two-language note. A full stop after an abbreviation or inside a time does
    not end a sentence."""
    parts: list[str] = []
    start = 0
    for m in SPLITS.finditer(text):
        if m.group(0) == ".":
            found = LAST_WORD.search(text[start : m.start()])
            word = found.group(1) if found else None
            follows = text[m.start() + 1 :]
            if re.match(r"\d", follows) or (word is not None and word in ABBREVIATIONS):
                continue
            if word is not None and word in SHORT_DAYS and re.match(r"\s*(?:klo|kl|kello|\d)", follows):
                continue
        parts.append(text[start : m.start()])
        start = m.end()
    parts.append(text[start:])
    return [p.strip() for p in parts if p.strip()]


CORRECTION_FIRST = re.compile(rf"^(?:{CORRECTION})\b")


def clauses(text: str) -> list[str]:
    result: list[str] = []
    for part in split(text):
        if result and CORRECTION_FIRST.search(part):
            result[-1] = f"{result[-1]}, {part}"
        else:
            result.append(part)
    return result


def resolve(exprs: list[tuple[Expr, str]]) -> Expr | None:
    """The time a clause settles on: a correction replaces what it names, and a denied time does not count."""
    current: Expr | None = None
    for expr, before in exprs:
        if DENIES.search(before):
            continue
        if current and CORRECTS.search(before):
            names_day = expr.day is not None or expr.weekday is not None
            current = Expr(
                current.start,
                expr.end,
                day=expr.day if names_day else current.day,
                weekday=expr.weekday if names_day else current.weekday,
                minute=expr.minute if expr.minute is not None else current.minute,
            )
        else:
            current = expr
    return current


def absolute(expr: Expr, arrived_at: int) -> int | None:
    if expr.minute is None:
        return None
    today = arrived_at // DAY
    days = expr.day or 0
    if expr.weekday is not None:
        ahead = (expr.weekday - today) % 7
        days = ahead if ahead >= 2 else ahead + 7  # a weekday name is 2 to 6 days after the request
    return (today + days) * DAY + expr.minute


def read(text: str, arrived_at: int) -> NoteFacts:
    note = normalise(text)
    facts = NoteFacts(
        manual=bool(MANUAL.search(NOT_MANUAL.sub(" ", note))),
        plates=bool(PLATES.search(note)),
        summer_tyres=bool(SUMMER_TYRES.search(note)),
    )
    for clause in clauses(note):
        meaning = role(clause)
        side = "delivery_hours" if DELIVERY_SIDE.search(clause) else "pickup_hours"
        if meaning == "hours":
            found = opening_range(clause)
            if found:
                facts = replace(facts, **{side: {"opens": found[0], "closes": found[1]}})
            continue
        if meaning is None:
            continue
        expr = resolve([(e, clause[max(0, e.start - 24) : e.start]) for e in expressions(clause)])
        when = absolute(expr, arrived_at) if expr else None
        if when is None:
            continue
        if meaning == "closes":
            facts = replace(facts, **{side: {"closes": when % DAY}})
        elif meaning == "release":
            facts = replace(facts, released_at=when)
        elif meaning == "deadline":
            facts = replace(facts, deadline=when)
        else:
            facts = replace(facts, ready_at=when)
    return facts
