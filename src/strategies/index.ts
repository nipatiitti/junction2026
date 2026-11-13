/** Every strategy by name. Adding one is a folder under src/strategies/ and one line here. */
import type { StrategyKind } from '../strategy.ts'
import { starter } from './starter/index.ts'

export const STRATEGIES: Record<string, StrategyKind> = {
  starter,
}
