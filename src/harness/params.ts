/** A strategy and its params, from the command line. */
import { readFileSync } from 'node:fs'
import { STRATEGIES } from '../strategies/index.ts'
import type { Params } from '../strategy.ts'

/** A strategy or a param that the command line names wrongly. */
export class UsageError extends Error {}

/** A strategy by name, with its params: the defaults, overridden by the run. */
export type Run = { name: string; params: Params }

/** The run of a named strategy: its defaults, then the values of each JSON file, then each `key=value`. A key must be
 * one of the defaults, and its value of the same type. */
export function runOf(name: string, files: string[] = [], pairs: string[] = []): Run {
  const kind = Object.hasOwn(STRATEGIES, name) ? STRATEGIES[name] : undefined
  if (!kind) throw new UsageError(`no strategy "${name}". The strategies: ${Object.keys(STRATEGIES).join(', ')}`)
  const params: Params = { ...kind.defaults }
  const set = (key: string, value: unknown) => {
    if (!Object.hasOwn(kind.defaults, key))
      throw new UsageError(`${name} has no param "${key}": ${Object.keys(kind.defaults).join(', ')}`)
    if (typeof value !== typeof kind.defaults[key])
      throw new UsageError(`${name} param ${key} takes a ${typeof kind.defaults[key]}`)
    params[key] = value as Params[string]
  }
  for (const file of files)
    for (const [key, value] of Object.entries(JSON.parse(readFileSync(file, 'utf-8')))) set(key, value)
  for (const pair of pairs) {
    const [key, text] = pair.split(/=(.*)/s)
    if (text === undefined) throw new UsageError(`"${pair}" is not key=value`)
    set(key!, parse(text))
  }
  return { name, params }
}

/** A run from one bench argument: `<name>` or `<name>:<item>,<item>`, where an item is `key=value` or a JSON file. */
export function runFromSpec(spec: string): Run {
  const [name, rest = ''] = spec.split(/:(.*)/s)
  const items = rest.split(',').filter(Boolean)
  return runOf(
    name!,
    items.filter((item) => !item.includes('=')),
    items.filter((item) => item.includes('=')),
  )
}

/** A number, true, false or JSON; else the text itself. */
function parse(text: string): unknown {
  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}
