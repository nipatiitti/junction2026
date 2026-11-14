/** Every strategy by name. Adding one is a folder under src/strategies/ and one line here. */
import type { StrategyKind } from '../strategy.ts'
import { bidprice } from './bidprice/index.ts'
import { flat } from './flat/index.ts'
import { recall } from './recall/index.ts'
import { starter } from './starter/index.ts'

import { squeeze } from './squeeze/index.ts'
import { isotone } from './isotone/index.ts'
import { surge } from './surge/index.ts'
import { tide } from './tide/index.ts'
import { atlas } from './atlas/index.ts'
import { groundhog } from './groundhog/index.ts'
import { gambit } from './gambit/index.ts'
import { menu } from './menu/index.ts'
export const STRATEGIES: Record<string, StrategyKind> = {
  starter,
  bidprice,
  flat,
  squeeze,
  isotone,
  surge,
  tide,
  atlas,
  groundhog,
  gambit,
  menu,
  recall,
}
