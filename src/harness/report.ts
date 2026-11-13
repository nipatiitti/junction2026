/** The lines that a week prints. */
import type { Score } from '../../vendor/spread-typescript/spread.ts'

export const euros = (cents: number): string =>
  (cents / 100).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export const percent = (share: number): string => `${(100 * share).toFixed(1)}%`

/** One line of the score: at each midnight, and at the end. */
export function report(label: string, score: Score): void {
  const orders = `${String(score.wonOrders).padStart(4)} orders  ${percent(score.onTimeShare).padStart(6)} on time  ${percent(score.undeliveredShare).padStart(5)} not delivered`
  console.log(
    `${label.padEnd(9)}  margin €${euros(score.marginCents).padStart(11)}  revenue €${euros(score.revenueCents).padStart(11)}  ${orders}`,
  )
}

/** "a 3, b 1" from counts. */
export const counts = (tally: Map<string, number>): string =>
  [...tally].map(([kind, count]) => `${kind} ${count}`).join(', ')
