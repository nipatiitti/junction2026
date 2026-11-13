/** Reads the clock times in a request's note, as the organisers' starter does. */
import type { Note, TimeWindow } from '../../../vendor/spread-typescript/spread.ts'
import { DAY, HOUR } from '../../time.ts'

/** "Not before", "at the earliest" and a ready time all mean from then on; read them before BEFORE. */
const AFTER =
  /jälkeen|alkaen|aikaisintaan|\bafter\b|\bfrom\b|earliest|not before|ei ennen|valmis|\bready\b|efter|tidigast|inte före|klar/
const BEFORE = /ennen|mennessä|viim|\bbefore\b|\bby\b|latest|före|senast/
const DELIVERY =
  /toimit|perillä|perille|vastaanot|kohde|deliver|arrive|destination|receiv|leverera|leverans|framme|mottag/
const CLOCK = /(?:klo|kl\.?)\s*(\d{1,2})(?:[.:](\d{2}))?|\b(\d{1,2})[.:](\d{2})\b/g
/** Opening hours as a range: "9-16", "klo 9.00-14.30", "kl 10-14". */
const RANGE = /\b(\d{1,2})(?:[.:](\d{2}))?\s*[-–]\s*(\d{1,2})(?:[.:](\d{2}))?\b/g

/** Narrows a stop's window by clock times in the note, found by keywords: "nouto ennen 15.30",
 * "klo 12 jälkeen", "deliver by 19:00", "efter kl. 12", "aikaisintaan klo 13.30", "not before
 * 16:00", and opening hours as a range, "arkisin 9-16". The time is on the window's own day. */
export function windowFromNote(note: Note | null, window: TimeWindow, stop: 'pickup' | 'delivery'): TimeWindow {
  if (!note) return window
  let text = note.text.toLowerCase()
  if (DELIVERY.test(text) !== (stop === 'delivery')) return window
  const minutes = (hour: number, minute: number): number | null =>
    hour > 24 || minute > 59 ? null : hour * HOUR + minute
  const dayStart = (t: number) => Math.floor(t / DAY) * DAY
  let { from, to } = window
  // Opening hours hold every day: they move the window's start to the first day's opening and its end to the last day's closing.
  for (const match of text.matchAll(RANGE)) {
    const opens = minutes(Number(match[1]), Number(match[2] ?? 0))
    const closes = minutes(Number(match[3]), Number(match[4] ?? 0))
    if (opens === null || closes === null || opens >= closes) continue
    from = Math.max(from, dayStart(from) + opens)
    to = Math.min(to, dayStart(to) + closes)
  }
  text = text.replace(RANGE, ' ')
  for (const match of text.matchAll(CLOCK)) {
    const m = minutes(Number(match[1] ?? match[3]), Number(match[2] ?? match[4] ?? 0))
    if (m === null) continue
    const time = dayStart(window.from) + m
    const around = text.slice(Math.max(0, match.index - 16), match.index + match[0].length + 16)
    if (AFTER.test(around)) from = Math.max(from, time)
    else if (BEFORE.test(around)) to = Math.min(to, time)
  }
  return from <= to ? { from, to } : window
}
