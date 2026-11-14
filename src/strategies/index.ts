/** Every strategy by name. Adding one is a folder under src/strategies/ and one line here. */
import type { StrategyKind } from '../strategy.ts'
import { bidprice } from './bidprice/index.ts'
import { flat } from './flat/index.ts'
import { starter } from './starter/index.ts'
import { surge } from './surge/index.ts'

export const STRATEGIES: Record<string, StrategyKind> = {
  starter,
  bidprice,
  flat,
  surge,
}
