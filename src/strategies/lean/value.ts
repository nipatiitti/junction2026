/** The value table (value.json), fitted on the saved lean weeks by analysis/lean_value.py: what one more order
 * takes from the rest of the week, as the value of the state the desk is in less the value of that state with
 * the order. The state is the minute of the week, the orders won so far per driver and the late share so far.
 *
 * Two parts. Crowding: every car booked after this order pays a higher fee and more refunds (`charge`, for an
 * order of the mean typical fee, × `level`, which gives it the mean of the `taxLoad` charge that it replaces).
 * The 90% rule: a week under 90% on time scores nothing, so an order costs `cliff` for each late order that it
 * adds over the share that the week is heading for: its own chance to be late (`late`, by option and day) and
 * the late cars it causes (`spill`), less the final share to expect (`share`). A safe order near the limit
 * dilutes the late share, and its charge falls; the charge is never under zero. */
import { readFileSync } from 'node:fs'
import { DAY } from '../../ops/index.ts'

type Kind = 'same_day' | 'next_day' | 'within_3_days'
export type ValueTable = {
  slotMinutes: number
  loadStep: number
  lateStep: number
  typicalCents: number
  level: number
  /** [slot of the week][load]: cents, and late cars caused. */
  charge: number[][]
  spill: number[][]
  /** [day][late share so far]: cents for a late order more, and the final late share to expect. */
  cliff: number[][]
  share: number[][]
  /** The share of late orders by option, [day won]. */
  late: Record<Kind, number[]>
}

let table: ValueTable | undefined
const load = (): ValueTable => {
  table ??= JSON.parse(readFileSync(new URL('./value.json', import.meta.url), 'utf-8')) as ValueTable
  return table
}

/** The table between its rows and columns; outside it, its edge. */
function between(rows: number[][], row: number, column: number): number {
  const width = rows[0]?.length ?? 0
  if (rows.length < 2 || width < 2) return rows[0]?.[0] ?? 0
  const r = Math.min(rows.length - 1, Math.max(0, row))
  const c = Math.min(width - 1, Math.max(0, column))
  const r0 = Math.min(rows.length - 2, Math.floor(r))
  const c0 = Math.min(width - 2, Math.floor(c))
  const at = (i: number, j: number): number => rows[i]?.[j] ?? 0
  const top = at(r0, c0) + (at(r0, c0 + 1) - at(r0, c0)) * (c - c0)
  const bottom = at(r0 + 1, c0) + (at(r0 + 1, c0 + 1) - at(r0 + 1, c0)) * (c - c0)
  return top + (bottom - top) * (r - r0)
}

/** What an order won now takes from the rest of the week, in cents: `now` is the minute of the week, `won` the
 * orders won so far per driver, `lateShare` the late share so far, `kind` the option and `typicalCents` the
 * request's typical fee. */
export function valueCharge(now: number, won: number, lateShare: number, kind: Kind, typicalCents: number): number {
  const t = load()
  const slot = now / t.slotMinutes
  const column = won / t.loadStep
  const crowding = t.level * between(t.charge, slot, column) * (typicalCents / t.typicalCents)
  const day = Math.min(t.cliff.length - 1, Math.max(0, Math.floor(now / DAY)))
  const late = lateShare / t.lateStep
  const added = (t.late[kind]?.[day] ?? 0) + between(t.spill, slot, column) - between(t.share, day, late)
  return Math.max(0, crowding + between(t.cliff, day, late) * added)
}
