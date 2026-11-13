"""Reads a dealer's note (Finnish, Swedish or English) into facts: when the car is ready or released,
the real opening hours of both sites, a tighter deadline, and the car facts that decide who may drive it.

RULES.md, "Notes and changes of plan", says how notes are written. README.md next to this file lists
the phrasings the reader knows and how to measure it on reveals.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

HOUR, DAY = 60, 24 * 60


@dataclass(frozen=True)
class Hours:
    """A site's weekday hours from a note, in minutes from midnight. None keeps the stated value."""

    opens: int | None = None
    closes: int | None = None


@dataclass(frozen=True)
class NoteFacts:
    """What a note says. Times are world minutes; None when the note does not say."""

    ready_at: int | None = None  # the car is ready from then
    released_at: int | None = None  # handed over after payment, from then; a `release` event comes then
    pickup_hours: Hours | None = None
    delivery_hours: Hours | None = None
    deadline: int | None = None  # a tighter deadline than the request's
    manual: bool = False  # manual gearbox: a driver with a manual licence
    plates: bool = False  # no plates: fetch transfer plates on the way
    summer_tyres: bool = False  # cannot be collected while snow falls at either end

    @property
    def earliest_pickup(self) -> int | None:
        """The first minute the car can be collected: ready and, if it waits for payment, released."""
        times = [t for t in (self.ready_at, self.released_at) if t is not None]
        return max(times) if times else None

    def __bool__(self) -> bool:
        return self != NoteFacts()


NO_FACTS = NoteFacts()

# ---------------------------------------------------------------------------------------------------------------
# Typos: notes drop, double and swap letters ("huomennna", "toomorrow", "akisin", "Pltaes"). A word one edit away
# from a word the reader knows is read as that word.

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
_KNOWN = set(KNOWN_WORDS)


def _one_edit(a: str, b: str) -> bool:
    """One letter dropped, added, changed, or two neighbours swapped."""
    if a == b or abs(len(a) - len(b)) > 1:
        return a == b
    if len(a) == len(b):
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        return len(diff) == 1 or (
            len(diff) == 2 and diff[1] == diff[0] + 1 and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]]
        )
    short, long = (a, b) if len(a) < len(b) else (b, a)
    i = 0
    while i < len(short) and short[i] == long[i]:
        i += 1
    return short[i:] == long[i + 1 :]


def _fix_word(match: re.Match[str]) -> str:
    word = match[0]
    if len(word) < 5 or word in _KNOWN:
        return word
    return next((known for known in KNOWN_WORDS if _one_edit(word, known)), word)


def normalise(text: str) -> str:
    text = text.lower().replace("–", "-").replace("—", "-")
    return re.sub(r"[a-zåäö]+", _fix_word, text)


# ---------------------------------------------------------------------------------------------------------------
# Car facts.

MANUAL = re.compile(
    r"manuaal|manuell|\bmanual\b|ei automaatti|no automatic|inte automat|stick shift|käsivaiht|växlad för hand"
)
# "Automaatti, ei manuaali": a denied gearbox.
NOT_MANUAL = re.compile(r"(?:not|ei|inte|no)\s+(?:a\s+|en\s+)?(?:manual|manuaal|manuell)")
PLATES = re.compile(
    r"kilv|kilpi|rekkari|rekisteristä|\bplates? removed|no plates|without plates|unregistered|trade plates|transfer plates"
    r"|skylt|avregistrer"
)
# Summer tyres on the car, not a spare set in the boot.
SUMMER_TYRES = re.compile(
    r"kesärenkaat alla|kesärenkailla|kesärenkaille|talvirenkaita ei|ei talvirenkaita|talvirenkaat puuttu"
    r"|on summer tyres|summer tyres on|still on summer|no winter|sommardäck på|sommardäcken på|på sommardäck|inga vinterdäck"
)

# ---------------------------------------------------------------------------------------------------------------
# Days and clock times.

FI_DAYS = ["maanantai", "tiistai", "keskiviikko", "torstai", "perjantai", "lauantai", "sunnuntai"]
SV_DAYS = ["måndag", "tisdag", "onsdag", "torsdag", "fredag", "lördag", "söndag"]
EN_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
# Short forms: a word only when a time follows, or as the whole of a correction ("korjaus: pe").
SHORT_DAYS = {
    "ma": 0, "ti": 1, "ke": 2, "to": 3, "pe": 4, "la": 5, "su": 6,
    "mån": 0, "tis": 1, "ons": 2, "tors": 3, "fre": 4, "lör": 5, "sön": 6,
    "mon": 0, "tue": 1, "tues": 1, "wed": 2, "thu": 3, "thur": 3, "thurs": 3, "fri": 4, "sat": 5, "sun": 6,
}  # fmt: skip
RELATIVE = [
    (r"ylihuomen\w*|i övermorgon|övermorgon|day after tomorrow", 2),
    (r"huomen\w*|i morgon|imorgon|tomorrow|tmrw|tmr|tomoz", 1),
    (r"tänään|idag|today|tonight", 0),
]

# The working hour a word names, 9 to 17 (RULES.md): Finnish stems, then Swedish and English words.
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


def _working_hour(number: int) -> int:
    return number + 12 if number < 9 else number


def _fi_word_hour(word: str) -> int | None:
    for stem, number in FI_HOURS:
        if word.startswith(stem):
            return number + 10 if "toista" in word or "toisat" in word else number
    return None


# A Finnish hour word in a time form: "viideltä" (at five), "kolmesta" (from three), "neljään" (by four), and the
# genitive before "jälkeen" or "mennessä": "kahdentoista jälkeen".
FI_HOUR_WORD = re.compile(
    r"\b(?:puoli\s+)?((?:yh|ka|ko|ne|vi|ku|se|ky)\w*?(?:lta|ltä|sta|stä|toista|toisat))\b"
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
WORD_CUE = re.compile(r"\b(?:klo|kello|kl|klockan|at|by|from|until|till|before|after|around|från|före|efter)\s+$")


@dataclass
class Expr:
    """A day, a time of day, or both, found in a note."""

    start: int
    end: int
    day: int | None = None  # days after the request arrives
    weekday: int | None = None  # 0 = Monday; read against the arrival day
    minute: int | None = None  # minutes from midnight


def _day_matches(text: str) -> list[Expr]:
    found: list[Expr] = []
    for pattern, offset in RELATIVE:
        for m in re.finditer(rf"\b(?:{pattern})\b", text):
            found.append(Expr(m.start(), m.end(), day=offset))
    for names in (FI_DAYS, SV_DAYS, EN_DAYS):
        for number, name in enumerate(names):
            stem = name.removesuffix("i")  # "maanantaina", "keskiviikkona"
            for m in re.finditer(rf"\b(?:på\s+)?{stem}\w*", text):
                found.append(Expr(m.start(), m.end(), weekday=number))
    # A short form before a time ("pe klo 15", "ke 12 mennessä", "fri 13:30") or alone at the end of a correction.
    for m in re.finditer(r"\b(" + "|".join(SHORT_DAYS) + r")\b\.?(?=\s*(?:klo|kl|kello|at)?\s*\d|\s*[.!,]?\s*$)", text):
        found.append(Expr(m.start(), m.end(), weekday=SHORT_DAYS[m[1]]))
    # Not when one day overlaps another (a weekday inside "i morgon"), and not "ma-pe" or "mon-fri".
    found = [e for e in found if not re.match(r"\s*-\s*[a-zåäö]", text[e.end :])]
    found.sort(key=lambda e: (e.start, -(e.end - e.start)))
    kept: list[Expr] = []
    for e in found:
        if not kept or e.start >= kept[-1].end:
            kept.append(e)
    return kept


def _time_matches(text: str, days: list[Expr]) -> list[Expr]:
    found: list[Expr] = []
    taken: list[tuple[int, int]] = []

    def add(start: int, end: int, minute: int) -> None:
        if minute <= 24 * HOUR and not any(s < end and start < e for s, e in taken):
            found.append(Expr(start, end, minute=minute))
            taken.append((start, end))

    for m in CLOCK.finditer(text):
        if m["ampm"]:
            hour = int(m["h"]) % 12 + (12 if m["ampm"].startswith("p") else 0)
            add(m.start(), m.end(), hour * HOUR + int(m["m"] or 0))
        elif m["h2"]:
            if int(m["m2"]) < 60:
                add(m.start(), m.end(), int(m["h2"]) * HOUR + int(m["m2"]))
        else:
            add(m.start(), m.end(), int(m["h3"]) * HOUR)
    for m in KLO.finditer(text):
        add(m.start(), m.end(), int(m["h"]) * HOUR + int(m["m"] or 0))
    for m in NOON.finditer(text):
        add(m.start(), m.end(), 12 * HOUR)
    for m in FI_HOUR_WORD.finditer(text):
        number = _fi_word_hour(m[1] or m[2])
        if number is not None:
            half = text[m.start() : m.end()].startswith("puoli")
            add(m.start(), m.end(), _working_hour(number) * HOUR - (30 if half else 0))
    for m in re.finditer(r"\b(?:(half|halv|puoli)\s+)?([a-zåäö]+)\b", text):
        word = m[2]
        if word not in WORD_HOURS and not (m[1] == "puoli" and _fi_word_hour(word) is not None):
            continue
        cued = m[1] or WORD_CUE.search(text[: m.start()]) or re.match(r"\s*o'?clock", text[m.end() :])
        if cued:
            number = WORD_HOURS.get(word) or _fi_word_hour(word)
            add(m.start(), m.end(), _working_hour(number) * HOUR - (30 if m[1] else 0))
    # A bare number is an hour right after a day ("ke 12 mennessä", "huomenna 12 jälkeen") or before "asti".
    for m in BARE.finditer(text):
        after_day = any(0 <= m.start() - d.end <= 2 for d in days)
        before_word = re.match(
            r"\s*(?:asti|saakka|mennessä|jälkeen|alkaen|och framåt|latest|at the latest)\b", text[m.end() :]
        )
        if after_day or before_word:
            add(m.start(), m.end(), int(m["h"]) * HOUR)
    return found


def expressions(text: str) -> list[Expr]:
    """The days and times in a piece of note, a day joined with the time right next to it."""
    days = _day_matches(text)
    times = _time_matches(text, days)
    items = sorted(days + times, key=lambda e: e.start)
    joined: list[Expr] = []
    for e in items:
        last = joined[-1] if joined else None
        gap = text[last.end : e.start] if last else ""
        if (
            last is not None
            and re.fullmatch(r"[\s,]*(?:klo|kl|kello|klockan|at|on|från|from)?\.?\s*", gap)
            and (last.minute is None) != (e.minute is None)
        ):
            last.end = e.end
            last.minute = last.minute if last.minute is not None else e.minute
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


def _clock(hour: str, minute: str | None, ampm: str | None) -> int:
    h = int(hour)
    if ampm:
        h = h % 12 + (12 if ampm.startswith("p") else 0)
    return h * HOUR + int(minute or 0)


def opening_range(text: str) -> tuple[int, int] | None:
    """The last opening hours given as a range: "9-16", "klo 7.00 - 14.30", "8am - 7pm", "8:sta 20:een"."""
    best = None
    for m in RANGE.finditer(text):
        opens, closes = _clock(m["a"], m["am"], m["ap"]), _clock(m["b"], m["bm"], m["bp"])
        if 0 <= opens < closes <= 24 * HOUR:
            best = (opens, closes)
    return best


# ---------------------------------------------------------------------------------------------------------------
# Clauses and what each says.

# A full stop after these does not end a sentence. After a short weekday, only when a time follows ("pe. klo 15").
ABBREVIATIONS = {"viim", "klo", "kl", "n", "oik", "esim", "t", "ca", "nro", "no", "ref"}
CORRECTION = r"(?:ei kun|eikun|ei vaan|korjaus|correction|rättelse|sorry,? i mean|i mean|or rather|nej,? förlåt|förlåt|jag menar)"
CORRECTS = re.compile(rf"(?:^|[\s,(])(?:{CORRECTION})\s*[:,]?\s*$")
DENIES = re.compile(r"(?:^|[\s,(])(?:ei|not|inte)\s*\(?\s*$")

# What a clause is about, tried in this order.
SELLER = re.compile(r"myyjä|seller|säljare|omistaja|owner|ägare")
RELEASE = re.compile(
    r"maks|payment|paid|pays|betal|rahoitus|financ|kauppa kesken|luovut|handover|handed over|lämnas ut"
)
OPEN_WORDS = re.compile(
    r"auki|avoinna|aukiolo|open|öppet|arkisin|arkipäivisin|weekdays|vardagar|ma-pe|mon-fri|hours|receiving|"
    r"vastaanot|mottag|nouto|noudettavissa|pickup|pikup|collect|hämt|kiinni|close"
)
# "Kello 19 jälkeen ei enää luovutuksia": no handovers after 19 is a closing time, not a release.
NO_MORE = re.compile(r"ei enää|no more|inga fler|ingen utlämning|no handovers")
# "Ready now, we close at 16.30": a car that is ready now gives no ready time.
READY_NOW = re.compile(r"\b(?:ready|valmis|valmiina|klar)\s+(?:now|nyt|nu|heti|right away|direkt)\b")
SHUTS = re.compile(r"kiinni|sulkee|\bclose|stäng|asti|saakka|until|ei ketään|nobody|no one|ingen")
DEADLINE = re.compile(
    r"perillä|perille|framme|at (?:the )?destination|must be at|must arrive|arrive by|arrival|deliver(?:ed)? by"
    r"|mennessä|levererad|no later than|must be there|oltava silloin|på plats|ska vara|måste vara"
)
READY = re.compile(
    r"valmi|ready|klar|aikaisintaan|earliest|tidigast|alkaen|voi noutaa|saa hakea|saa noutaa|haettavissa|"
    r"pickup from|pick up from|och framåt|available"
)
BEFORE = re.compile(r"\bbefore\b|\bennen\b|före|viimeistään|haku viim|latest|by\b")
AFTER = re.compile(r"jälkeen|after|efter|from|från")
DELIVERY_SIDE = re.compile(
    r"kohde|kohteen|vastaanot|perillä|perille|destination|receiv|mottag|toimitus|leverans|deliver|framme"
)


def _role(clause: str) -> str | None:
    """release, hours, closes, deadline or ready: what the times in a clause mean."""
    if SELLER.search(clause):
        return None  # a private seller's slot is the booked window already
    clause = READY_NOW.sub(" ", clause)
    if NO_MORE.search(clause):
        return "closes"
    if RELEASE.search(clause):
        return "release"
    if opening_range(clause) and (OPEN_WORDS.search(clause) or not READY.search(clause)):
        return "hours"
    if SHUTS.search(clause) and not READY.search(clause):
        return "closes"
    if DEADLINE.search(clause):
        return "deadline"
    if READY.search(clause):
        return "ready"
    if BEFORE.search(clause):
        return "closes"
    if AFTER.search(clause):
        return "ready"
    return None


def _split(text: str) -> list[str]:
    """Sentences, and the halves of a two-language note ("... / ..."). A full stop after an abbreviation
    ("viim.") or inside a time ("15.30") does not end a sentence."""
    parts, start = [], 0
    for m in re.finditer(r"[.!?;\n]|\s/\s", text):
        if m[0] == ".":
            word = re.search(r"([a-zåäö]+|\d+)$", text[start : m.start()])
            follows = text[m.end() :]
            if follows[:1].isdigit() or (word and word[1] in ABBREVIATIONS):
                continue
            if word and word[1] in SHORT_DAYS and re.match(r"\s*(?:klo|kl|kello|\d)", follows):
                continue
        parts.append(text[start : m.start()])
        start = m.end()
    parts.append(text[start:])
    return [p.strip() for p in parts if p.strip()]


def _clauses(text: str) -> list[str]:
    clauses: list[str] = []
    for part in _split(text):
        # "Korjaus: klo 17" corrects the clause before it.
        if clauses and re.match(rf"(?:{CORRECTION})\b", part):
            clauses[-1] = f"{clauses[-1]}, {part}"
        else:
            clauses.append(part)
    return clauses


def _resolve(exprs: list[tuple[Expr, str]]) -> Expr | None:
    """The time a clause settles on: a correction replaces what it names, and a denied time does not count."""
    current: Expr | None = None
    for expr, before in exprs:
        if DENIES.search(before):
            continue
        if current is not None and CORRECTS.search(before):
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


def _absolute(expr: Expr, arrived_at: int) -> int | None:
    if expr.minute is None:
        return None
    today = arrived_at // DAY
    if expr.weekday is not None:
        ahead = (expr.weekday - today % 7) % 7
        days = ahead if ahead >= 2 else ahead + 7  # a weekday name is 2 to 6 days after the request
    else:
        days = expr.day or 0
    return (today + days) * DAY + expr.minute


def read_note(text: str | None, arrived_at: int) -> NoteFacts:
    """The facts a note states. `arrived_at` is the minute the request arrived: days count from its day."""
    if not text:
        return NO_FACTS
    note = normalise(text)
    facts: dict[str, object] = {
        "manual": bool(MANUAL.search(NOT_MANUAL.sub(" ", note))),
        "plates": bool(PLATES.search(note)),
        "summer_tyres": bool(SUMMER_TYRES.search(note)),
    }
    for clause in _clauses(note):
        role = _role(clause)
        side = "delivery_hours" if DELIVERY_SIDE.search(clause) else "pickup_hours"
        if role == "hours":
            facts[side] = Hours(*opening_range(clause))  # type: ignore[misc]
            continue
        if role is None:
            continue
        expr = _resolve([(e, clause[max(0, e.start - 24) : e.start]) for e in expressions(clause)])
        when = None if expr is None else _absolute(expr, arrived_at)
        if when is None:
            continue
        if role == "closes":
            facts[side] = Hours(closes=when % DAY)
        else:
            facts[{"release": "released_at", "deadline": "deadline", "ready": "ready_at"}[role]] = when
    return NoteFacts(**facts)  # type: ignore[arg-type]
