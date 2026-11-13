/** Our half of the week: every action that the desk sent, with the world's answer, one JSON line each in
 * out/journal/<world id>.jsonl. The event log is the world's half. On a rebuild the desk feeds a new strategy both,
 * merged in order, so it ends in the same state as the one that played. SPREAD_JOURNAL_DIR changes the folder. */
import { appendFileSync, existsSync, mkdirSync, readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import type { Action, ActionResult } from '../../vendor/spread-typescript/spread.ts'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..')
const DIR = path.resolve(process.env.SPREAD_JOURNAL_DIR || path.join(ROOT, 'out', 'journal'))

/** One action and its answer, at the minute the strategy learned it and after the event `seq`, the last one seen. */
export type JournalLine = { seq: number; at: number; action: Action; result: ActionResult }

export class Journal {
  readonly file: string
  #broken = false // a journal that cannot be written warns once, and never stops the week

  constructor(worldId: string) {
    this.file = path.join(DIR, `${worldId}.jsonl`)
  }

  /** The lines written so far, in order; none when the file is not on this machine. A line cut off by a crash is
   * left out. */
  read(): JournalLine[] {
    if (!existsSync(this.file)) return []
    return readFileSync(this.file, 'utf-8')
      .split('\n')
      .flatMap((text) => {
        try {
          return text ? [JSON.parse(text) as JournalLine] : []
        } catch {
          return []
        }
      })
  }

  write(line: JournalLine): void {
    if (this.#broken) return
    try {
      mkdirSync(DIR, { recursive: true })
      appendFileSync(this.file, `${JSON.stringify(line)}\n`)
    } catch (error) {
      this.#broken = true
      console.error(
        `Could not write the journal ${this.file}: ${(error as Error).message}. A rebuild relearns the events only.`,
      )
    }
  }
}
