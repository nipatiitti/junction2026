/** Reads a dealer's note (Finnish, Swedish or English) into facts: when the car is ready or released, the real
 * opening hours of both sites, a tighter deadline, and the car facts that decide who may drive it. A port of
 * strategies/notes/reader.py; RULES.md, "Notes and changes of plan", says how notes are written, and
 * strategies/notes/README.md lists the phrasings. */
import type { Note } from '../../vendor/spread-typescript/types.ts'
import { DAY, dayOf, HOUR, type Hours, weekday } from './calendar.ts'

/** What a note says. Times are world minutes; null when the note does not say. The note speaks of the first car:
 * in a trade-in, the new car. The world's notes state no other facts (the reveal's `LegTruth` lists exactly these). */
export type NoteFacts = {
  readyAt: number | null // the car is ready from then
  releasedAt: number | null // handed over after payment, from then; a `release` event comes then
  pickupHours: Hours | null // the pickup site's real weekday hours
  deliveryHours: Hours | null // the delivery site's real weekday hours
  deadline: number | null // a tighter deadline than the request's
  manual: boolean // manual gearbox: a driver with a manual licence
  plates: boolean // no plates: fetch transfer plates on the way
  summerTyres: boolean // cannot be collected while snow falls at either end
}

export const NO_FACTS: NoteFacts = Object.freeze({
  readyAt: null,
  releasedAt: null,
  pickupHours: null,
  deliveryHours: null,
  deadline: null,
  manual: false,
  plates: false,
  summerTyres: false,
})

/** The first minute the car can be collected by the note: ready and, if it waits for payment, released. */
export function earliestPickup(facts: NoteFacts): number | null {
  const times = [facts.readyAt, facts.releasedAt].filter((t) => t !== null)
  return times.length > 0 ? Math.max(...times) : null
}

/** The facts a note states, with days counted from the day the request arrived. A note it cannot read gives
 * `NO_FACTS`, never an error. */
export function readNote(note: Note | string | null | undefined, arrivedAt: number): NoteFacts {
  const text = typeof note === 'string' ? note : note?.text
  if (!text || !Number.isFinite(arrivedAt)) return NO_FACTS
  try {
    return read(text, arrivedAt)
  } catch {
    return NO_FACTS
  }
}

// ---------------------------------------------------------------------------------------------------------------
// Patterns. JavaScript's `\b` and `\w` know only ASCII letters, and notes are full of "ä", "å" and "ö", so every
// pattern goes through `rx`, which gives both their Unicode meaning, as in Python. The sources then read as in
// reader.py.

const W = String.raw`[\p{L}\p{N}_]`
const BOUNDARY = `(?:(?<=${W})(?!${W})|(?<!${W})(?=${W}))`

function rx(source: string, flags = ''): RegExp {
  return new RegExp(source.replaceAll(String.raw`\b`, BOUNDARY).replaceAll(String.raw`\w`, W), `${flags}u`)
}

/** A match at the start of the text only, as Python's `re.match`. */
const startsWith = (pattern: RegExp, text: string): RegExpExecArray | null => {
  const sticky = new RegExp(pattern.source, `${pattern.flags.replace('g', '')}y`)
  return sticky.exec(text)
}

const groups = (m: RegExpExecArray): Record<string, string | undefined> => m.groups ?? {}

const all = (pattern: RegExp, text: string): RegExpExecArray[] => [
  ...text.matchAll(new RegExp(pattern.source, pattern.flags.includes('g') ? pattern.flags : `${pattern.flags}g`)),
]

// ---------------------------------------------------------------------------------------------------------------
// Typos: notes drop, double and swap letters ("huomennna", "toomorrow", "akisin", "Pltaes"). A word one edit away
// from a word the reader knows is read as that word.

// biome-ignore format: one list of words
const KNOWN_WORDS = [
  'tänään', 'huomenna', 'ylihuomenna', 'today', 'tomorrow', 'idag', 'imorgon', 'morgon', 'övermorgon', 'maanantai',
  'maanantaina', 'tiistai', 'tiistaina', 'keskiviikko', 'keskiviikkona', 'torstai', 'torstaina', 'perjantai',
  'perjantaina', 'lauantai', 'lauantaina', 'sunnuntai', 'sunnuntaina', 'monday', 'tuesday', 'wednesday', 'thursday',
  'friday', 'saturday', 'sunday', 'måndag', 'tisdag', 'onsdag', 'torsdag', 'fredag', 'lördag', 'söndag', 'perillä',
  'perille', 'mennessä', 'viimeistään', 'toimitus', 'vastaanotto', 'vastaanottava', 'vastaanotetaan', 'kohde',
  'kohteen', 'valmis', 'valmiina', 'vasta', 'noudettavissa', 'aikaisintaan', 'alkaen', 'jälkeen', 'ennen',
  'haettava', 'haettavissa', 'nouto', 'noutaa', 'kiinni', 'sulkee', 'aukioloajat', 'arkisin', 'arkipäivisin',
  'avoinna', 'liike', 'maksun', 'maksaa', 'maksettu', 'maksu', 'luovutus', 'luovutetaan', 'ostaja', 'asiakas',
  'korjaus', 'correction', 'rättelse', 'destination', 'receiving', 'arrive', 'arrival', 'earliest', 'released',
  'payment', 'before', 'pickup', 'collect', 'closes', 'weekdays', 'manuaali', 'manuaalivaihteinen',
  'manuaalivaihteet', 'manuaalivaihteisto', 'käsivaihteinen', 'automaatti', 'manual', 'transmission', 'automatic',
  'kilvet', 'kilpiä', 'rekisterikilvet', 'siirtokilvet', 'koekilvet', 'rekkareita', 'plates', 'unregistered',
  'skyltar', 'provskyltar', 'kesärenkaat', 'kesärenkailla', 'talvirenkaita', 'summer', 'tyres', 'sommardäck',
  'winters',
]
const KNOWN = new Set(KNOWN_WORDS)

/** One letter dropped, added, changed, or two neighbours swapped. */
function oneEdit(a: string, b: string): boolean {
  if (a === b || Math.abs(a.length - b.length) > 1) return a === b
  if (a.length === b.length) {
    const diff: number[] = []
    for (let k = 0; k < a.length; k++) if (a[k] !== b[k]) diff.push(k)
    const [i = 0, j = 0] = diff
    return diff.length === 1 || (diff.length === 2 && j === i + 1 && a[i] === b[j] && a[j] === b[i])
  }
  const [short, long] = a.length < b.length ? [a, b] : [b, a]
  let i = 0
  while (i < short.length && short[i] === long[i]) i++
  return short.slice(i) === long.slice(i + 1)
}

const fixWord = (word: string): string =>
  word.length < 5 || KNOWN.has(word) ? word : (KNOWN_WORDS.find((known) => oneEdit(word, known)) ?? word)

const normalise = (text: string): string =>
  text
    .toLowerCase()
    .replace(/[–—]/gu, '-')
    .replace(/[a-zåäö]+/gu, fixWord)

// ---------------------------------------------------------------------------------------------------------------
// Car facts.

const MANUAL = rx(
  String.raw`manuaal|manuell|\bmanual\b|ei automaatti|no automatic|inte automat|stick shift|käsivaiht|växlad för hand`,
)
/** "Automaatti, ei manuaali": a denied gearbox. */
const NOT_MANUAL = rx(String.raw`(?:not|ei|inte|no)\s+(?:a\s+|en\s+)?(?:manual|manuaal|manuell)`, 'g')
const PLATES = rx(
  String.raw`kilv|kilpi|rekkari|rekisteristä|\bplates? removed|no plates|without plates|unregistered|trade plates|transfer plates|skylt|avregistrer`,
)
/** Summer tyres on the car, not a spare set in the boot. */
const SUMMER_TYRES = rx(
  'kesärenkaat alla|kesärenkailla|kesärenkaille|talvirenkaita ei|ei talvirenkaita|talvirenkaat puuttu|on summer tyres|summer tyres on|still on summer|no winter|sommardäck på|sommardäcken på|på sommardäck|inga vinterdäck',
)

// ---------------------------------------------------------------------------------------------------------------
// Days and clock times.

const FI_DAYS = ['maanantai', 'tiistai', 'keskiviikko', 'torstai', 'perjantai', 'lauantai', 'sunnuntai']
const SV_DAYS = ['måndag', 'tisdag', 'onsdag', 'torsdag', 'fredag', 'lördag', 'söndag']
const EN_DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
/** Short forms: a word only when a time follows, or as the whole of a correction ("korjaus: pe"). */
// biome-ignore format: a table
const SHORT_DAYS = new Map(Object.entries({
  ma: 0, ti: 1, ke: 2, to: 3, pe: 4, la: 5, su: 6,
  mån: 0, tis: 1, ons: 2, tors: 3, fre: 4, lör: 5, sön: 6,
  mon: 0, tue: 1, tues: 1, wed: 2, thu: 3, thur: 3, thurs: 3, fri: 4, sat: 5, sun: 6,
}))
const RELATIVE: [string, number][] = [
  [String.raw`ylihuomen\w*|i övermorgon|övermorgon|day after tomorrow`, 2],
  [String.raw`huomen\w*|i morgon|imorgon|tomorrow|tmrw|tmr|tomoz`, 1],
  ['tänään|idag|today|tonight', 0],
]

/** The working hour a word names, 9 to 17 (RULES.md): Finnish stems, then Swedish and English words. */
// biome-ignore format: a table
const FI_HOURS: [string, number][] = [
  ['yhdeks', 9], ['kahdeks', 8], ['seitsem', 7], ['kymmen', 10], ['yhde', 1], ['yhte', 1], ['yksi', 1],
  ['kahde', 2], ['kahte', 2], ['kaksi', 2], ['kolm', 3], ['nelj', 4], ['viid', 5], ['viit', 5], ['viisi', 5],
  ['kuud', 6], ['kuut', 6], ['kuusi', 6],
]
// biome-ignore format: a table
const WORD_HOURS = new Map(Object.entries({
  one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, nine: 9, ten: 10, eleven: 11, twelve: 12,
  ett: 1, två: 2, tre: 3, fyra: 4, fem: 5, sex: 6, nio: 9, tio: 10, elva: 11, tolv: 12,
}))
const NOON = rx(String.raw`\b(?:noon|midday|keskipäivä\w*|middag|lunchtid)\b`, 'g')

const workingHour = (number: number): number => (number < 9 ? number + 12 : number)

function fiWordHour(word: string): number | null {
  const found = FI_HOURS.find(([stem]) => word.startsWith(stem))
  if (!found) return null
  return word.includes('toista') || word.includes('toisat') ? found[1] + 10 : found[1]
}

/** A Finnish hour word in a time form: "viideltä" (at five), "kolmesta" (from three), "neljään" (by four), and the
 * genitive before "jälkeen" or "mennessä": "kahdentoista jälkeen". */
const FI_TIME_WORD = String.raw`(?:yh|ka|ko|ne|vi|ku|se|ky)\w*?(?:lta|ltä|sta|stä|toista|toisat)\b`
const FI_HOUR_WORD = rx(
  String.raw`\b(?:puoli\s+)?(${FI_TIME_WORD})` +
    String.raw`|\b(?:puoli\s+)?((?:yh|ka|ko|ne|vi|ku|se|ky)\w*?(?:en|än|ään|aan|n))(?=\s+(?:mennessä|asti|saakka|jälkeen))`,
  'g',
)
const CLOCK = rx(
  String.raw`(?<pre>\b(?:klo|kl|kello|klockan|at)\.?\s*)?` +
    String.raw`(?:(?<h>\d{1,2})(?:[:.](?<m>\d{2}))?\s*(?<ampm>[ap]\.?m\.?)\b` +
    String.raw`|(?<h2>\d{1,2})[:.](?<m2>\d{2})(?![\d.:])` +
    String.raw`|(?<h3>\d{1,2}):?(?:stä|sta|een|ään|aan|lta|ltä)\b)`,
  'g',
)
const KLO = rx(String.raw`\b(?:klo|kl|kello|klockan)\.?\s*(?<h>\d{1,2})(?<m>\d{2})?\b(?![:.]\d)`, 'g')
const BARE = rx(
  String.raw`\b(?<h>\d{1,2})\b(?![:.]\d|\s*(?:min|h\b|tun|tim|hour|km|tkm|%|e\b|€|kpl|sarja|set|rengas|tyre|däck))`,
  'g',
)
const WORD_CUE = rx(
  String.raw`\b(?:klo|kello|kl|klockan|at|by|from|until|till|before|after|around|från|före|efter)\s+$`,
)

/** A day, a time of day, or both, found in a note. */
type Expr = {
  start: number
  end: number
  day?: number // days after the request arrives
  weekday?: number // 0 = Monday; read against the arrival day
  minute?: number // minutes from midnight
}

function dayMatches(text: string): Expr[] {
  const found: Expr[] = []
  for (const [pattern, offset] of RELATIVE)
    for (const m of all(rx(String.raw`\b(?:${pattern})\b`), text))
      found.push({ start: m.index, end: m.index + m[0].length, day: offset })
  for (const names of [FI_DAYS, SV_DAYS, EN_DAYS])
    names.forEach((name, number) => {
      const stem = name.endsWith('i') ? name.slice(0, -1) : name // "maanantaina", "keskiviikkona"
      for (const m of all(rx(String.raw`\b(?:på\s+)?${stem}\w*`), text))
        found.push({ start: m.index, end: m.index + m[0].length, weekday: number })
    })
  // A short form before a time ("pe klo 15", "ke 12 mennessä", "fri 13:30", "ma viideltä") or alone at the end of a
  // correction. The hour in words is new against reader.py: it read "ma viideltä" as today.
  const short = rx(
    String.raw`\b(${[...SHORT_DAYS.keys()].join('|')})\b\.?(?=\s*(?:klo|kl|kello|at)?\s*\d|\s+(?:puoli\s+)?${FI_TIME_WORD}|\s*[.!,]?\s*$)`,
  )
  for (const m of all(short, text))
    found.push({ start: m.index, end: m.index + m[0].length, weekday: SHORT_DAYS.get(m[1] ?? '') })
  // Not when one day overlaps another (a weekday inside "i morgon"), and not "ma-pe" or "mon-fri".
  const dash = /\s*-\s*[a-zåäö]/u
  const days = found
    .filter((e) => !startsWith(dash, text.slice(e.end)))
    .sort((a, b) => a.start - b.start || b.end - b.start - (a.end - a.start))
  const kept: Expr[] = []
  for (const e of days) if (kept.length === 0 || e.start >= (kept.at(-1)?.end ?? 0)) kept.push(e)
  return kept
}

function timeMatches(text: string, days: Expr[]): Expr[] {
  const found: Expr[] = []
  const add = (start: number, end: number, minute: number): void => {
    if (minute <= 24 * HOUR && !found.some((e) => e.start < end && start < e.end)) found.push({ start, end, minute })
  }
  const span = (m: RegExpExecArray): [number, number] => [m.index, m.index + m[0].length]

  for (const m of all(CLOCK, text)) {
    const g = groups(m)
    if (g.ampm) {
      const hour = (Number(g.h) % 12) + (g.ampm.startsWith('p') ? 12 : 0)
      add(...span(m), hour * HOUR + Number(g.m ?? 0))
    } else if (g.h2) {
      if (Number(g.m2) < 60) add(...span(m), Number(g.h2) * HOUR + Number(g.m2))
    } else add(...span(m), Number(g.h3) * HOUR)
  }
  for (const m of all(KLO, text)) add(...span(m), Number(groups(m).h) * HOUR + Number(groups(m).m ?? 0))
  for (const m of all(NOON, text)) add(...span(m), 12 * HOUR)
  for (const m of all(FI_HOUR_WORD, text)) {
    const number = fiWordHour(m[1] ?? m[2] ?? '')
    if (number !== null) add(...span(m), workingHour(number) * HOUR - (m[0].startsWith('puoli') ? 30 : 0))
  }
  for (const m of all(rx(String.raw`\b(?:(half|halv|puoli)\s+)?([a-zåäö]+)\b`), text)) {
    const half = m[1]
    const word = m[2] ?? ''
    if (!WORD_HOURS.has(word) && !(half === 'puoli' && fiWordHour(word) !== null)) continue
    const cued =
      half || WORD_CUE.test(text.slice(0, m.index)) || startsWith(/\s*o'?clock/u, text.slice(m.index + m[0].length))
    const number = WORD_HOURS.get(word) ?? fiWordHour(word)
    if (cued && number !== null) add(...span(m), workingHour(number) * HOUR - (half ? 30 : 0))
  }
  // A bare number is an hour right after a day ("ke 12 mennessä", "huomenna 12 jälkeen") or before "asti".
  const word = rx(String.raw`\s*(?:asti|saakka|mennessä|jälkeen|alkaen|och framåt|latest|at the latest)\b`)
  for (const m of all(BARE, text)) {
    const afterDay = days.some((d) => m.index - d.end >= 0 && m.index - d.end <= 2)
    if (afterDay || startsWith(word, text.slice(m.index + m[0].length))) add(...span(m), Number(groups(m).h) * HOUR)
  }
  return found
}

const JOINS = rx(String.raw`^[\s,]*(?:klo|kl|kello|klockan|at|on|från|from)?\.?\s*$`)

/** The days and times in a piece of note, a day joined with the time right next to it. */
function expressions(text: string): Expr[] {
  const days = dayMatches(text)
  const items = [...days, ...timeMatches(text, days)].sort((a, b) => a.start - b.start)
  const joined: Expr[] = []
  for (const e of items) {
    const last = joined.at(-1)
    if (last && JOINS.test(text.slice(last.end, e.start)) && (last.minute === undefined) !== (e.minute === undefined)) {
      last.end = e.end
      last.minute ??= e.minute
      if (last.day === undefined && last.weekday === undefined) {
        last.day = e.day
        last.weekday = e.weekday
      }
    } else joined.push(e)
  }
  return joined
}

const RANGE = rx(
  String.raw`(?<a>\d{1,2})(?:[:.](?<am>\d{2}))?\s*(?<ap>[ap]\.?m\.?)?` +
    String.raw`(?:\s*(?:-|to|till|until)\s*|:?(?:sta|stä)\s+)` +
    String.raw`(?<b>\d{1,2})(?:[:.](?<bm>\d{2}))?\s*(?<bp>[ap]\.?m\.?)?(?::?(?:een|ään|aan))?(?![\d:.]\d)`,
  'g',
)

function clock(hour: string | undefined, minute: string | undefined, ampm: string | undefined): number {
  const h = ampm ? (Number(hour) % 12) + (ampm.startsWith('p') ? 12 : 0) : Number(hour)
  return h * HOUR + Number(minute ?? 0)
}

/** The last opening hours given as a range: "9-16", "klo 7.00 - 14.30", "8am - 7pm", "8:sta 20:een". */
function openingRange(text: string): [number, number] | null {
  let best: [number, number] | null = null
  for (const m of all(RANGE, text)) {
    const g = groups(m)
    const opens = clock(g.a, g.am, g.ap)
    const closes = clock(g.b, g.bm, g.bp)
    if (opens >= 0 && opens < closes && closes <= 24 * HOUR) best = [opens, closes]
  }
  return best
}

// ---------------------------------------------------------------------------------------------------------------
// Clauses and what each says.

/** A full stop after these does not end a sentence. After a short weekday, only when a time follows ("pe. klo 15"). */
const ABBREVIATIONS = new Set(['viim', 'klo', 'kl', 'n', 'oik', 'esim', 't', 'ca', 'nro', 'no', 'ref'])
const CORRECTION =
  '(?:ei kun|eikun|ei vaan|korjaus|correction|rättelse|sorry,? i mean|i mean|or rather|nej,? förlåt|förlåt|jag menar)'
const CORRECTS = rx(String.raw`(?:^|[\s,(])(?:${CORRECTION})\s*[:,]?\s*$`)
const DENIES = rx(String.raw`(?:^|[\s,(])(?:ei|not|inte)\s*\(?\s*$`)

// What a clause is about, tried in this order.
const SELLER = rx('myyjä|seller|säljare|omistaja|owner|ägare')
const RELEASE = rx('maks|payment|paid|pays|betal|rahoitus|financ|kauppa kesken|luovut|handover|handed over|lämnas ut')
const OPEN_WORDS = rx(
  'auki|avoinna|aukiolo|open|öppet|arkisin|arkipäivisin|weekdays|vardagar|ma-pe|mon-fri|hours|receiving|' +
    'vastaanot|mottag|nouto|noudettavissa|pickup|pikup|collect|hämt|kiinni|close',
)
/** "Kello 19 jälkeen ei enää luovutuksia": no handovers after 19 is a closing time, not a release. */
const NO_MORE = rx('ei enää|no more|inga fler|ingen utlämning|no handovers')
/** "Ready now, we close at 16.30": a car that is ready now gives no ready time. */
const READY_NOW = rx(String.raw`\b(?:ready|valmis|valmiina|klar)\s+(?:now|nyt|nu|heti|right away|direkt)\b`, 'g')
const SHUTS = rx(String.raw`kiinni|sulkee|\bclose|stäng|asti|saakka|until|ei ketään|nobody|no one|ingen`)
const DEADLINE = rx(
  'perillä|perille|framme|at (?:the )?destination|must be at|must arrive|arrive by|arrival|deliver(?:ed)? by' +
    '|mennessä|levererad|no later than|must be there|oltava silloin|på plats|ska vara|måste vara',
)
const READY = rx(
  'valmi|ready|klar|aikaisintaan|earliest|tidigast|alkaen|voi noutaa|saa hakea|saa noutaa|haettavissa|' +
    'pickup from|pick up from|och framåt|available',
)
const BEFORE = rx(String.raw`\bbefore\b|\bennen\b|före|viimeistään|haku viim|latest|by\b`)
const AFTER = rx('jälkeen|after|efter|from|från')
const DELIVERY_SIDE = rx(
  'kohde|kohteen|vastaanot|perillä|perille|destination|receiv|mottag|toimitus|leverans|deliver|framme',
)

type Role = 'release' | 'hours' | 'closes' | 'deadline' | 'ready'

/** What the times in a clause mean. */
function role(clause: string): Role | null {
  if (SELLER.test(clause)) return null // a private seller's slot is the booked window already
  const text = clause.replace(READY_NOW, ' ')
  if (NO_MORE.test(text)) return 'closes'
  if (RELEASE.test(text)) return 'release'
  if (openingRange(text) && (OPEN_WORDS.test(text) || !READY.test(text))) return 'hours'
  if (SHUTS.test(text) && !READY.test(text)) return 'closes'
  if (DEADLINE.test(text)) return 'deadline'
  if (READY.test(text)) return 'ready'
  if (BEFORE.test(text)) return 'closes'
  if (AFTER.test(text)) return 'ready'
  return null
}

/** Sentences, and the halves of a two-language note ("... / ..."). A full stop after an abbreviation ("viim.")
 * or inside a time ("15.30") does not end a sentence. */
function split(text: string): string[] {
  const parts: string[] = []
  let start = 0
  for (const m of all(/[.!?;\n]|\s\/\s/u, text)) {
    if (m[0] === '.') {
      const word = /([a-zåäö]+|\d+)$/u.exec(text.slice(start, m.index))?.[1]
      const follows = text.slice(m.index + 1)
      if (/^\d/u.test(follows) || (word !== undefined && ABBREVIATIONS.has(word))) continue
      if (word !== undefined && SHORT_DAYS.has(word) && /^\s*(?:klo|kl|kello|\d)/u.test(follows)) continue
    }
    parts.push(text.slice(start, m.index))
    start = m.index + m[0].length
  }
  parts.push(text.slice(start))
  return parts.map((p) => p.trim()).filter((p) => p.length > 0)
}

const CORRECTION_FIRST = rx(String.raw`^(?:${CORRECTION})\b`)

function clauses(text: string): string[] {
  const result: string[] = []
  for (const part of split(text)) {
    // "Korjaus: klo 17" corrects the clause before it.
    if (result.length > 0 && CORRECTION_FIRST.test(part)) result[result.length - 1] = `${result.at(-1)}, ${part}`
    else result.push(part)
  }
  return result
}

/** The time a clause settles on: a correction replaces what it names, and a denied time does not count. */
function resolve(exprs: [Expr, string][]): Expr | null {
  let current: Expr | null = null
  for (const [expr, before] of exprs) {
    if (DENIES.test(before)) continue
    if (current && CORRECTS.test(before)) {
      const namesDay = expr.day !== undefined || expr.weekday !== undefined
      current = {
        start: current.start,
        end: expr.end,
        day: namesDay ? expr.day : current.day,
        weekday: namesDay ? expr.weekday : current.weekday,
        minute: expr.minute ?? current.minute,
      }
    } else current = expr
  }
  return current
}

function absolute(expr: Expr, arrivedAt: number): number | null {
  if (expr.minute === undefined) return null
  const today = dayOf(arrivedAt)
  let days = expr.day ?? 0
  if (expr.weekday !== undefined) {
    const ahead = weekday(expr.weekday - today)
    days = ahead >= 2 ? ahead : ahead + 7 // a weekday name is 2 to 6 days after the request
  }
  return (today + days) * DAY + expr.minute
}

function read(text: string, arrivedAt: number): NoteFacts {
  const note = normalise(text)
  const facts: { -readonly [K in keyof NoteFacts]: NoteFacts[K] } = {
    ...NO_FACTS,
    manual: MANUAL.test(note.replace(NOT_MANUAL, ' ')),
    plates: PLATES.test(note),
    summerTyres: SUMMER_TYRES.test(note),
  }
  for (const clause of clauses(note)) {
    const meaning = role(clause)
    const side = DELIVERY_SIDE.test(clause) ? 'deliveryHours' : 'pickupHours'
    if (meaning === 'hours') {
      const range = openingRange(clause)
      if (range) facts[side] = { opens: range[0], closes: range[1] }
      continue
    }
    if (meaning === null) continue
    const expr = resolve(expressions(clause).map((e) => [e, clause.slice(Math.max(0, e.start - 24), e.start)]))
    const when = expr && absolute(expr, arrivedAt)
    if (when === null) continue
    if (meaning === 'closes') facts[side] = { closes: when % DAY }
    else if (meaning === 'release') facts.releasedAt = when
    else if (meaning === 'deadline') facts.deadline = when
    else facts.readyAt = when
  }
  return facts
}
