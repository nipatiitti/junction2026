/** Chains: several of our open cars as one gig for one driver. The cars are the nodes of a graph, and an edge goes
 * from one car to the next when the next is collected near where the first is delivered. A path through it is a day
 * of work: the driver pays one trip to the first car and one trip home from the last, where the same cars as single
 * gigs pay a trip out and a trip home each. A path that ends where it started pays no trip home at all. The search
 * walks every path of up to `maxCars` cars inside the 12 hours of driving that a gig of several cars may plan, keeps
 * the ones a driver can do inside every window, and takes the paths that save the most, each car once. */
import type { Audience, OpeningHours, StopRef, WorldMap } from '../../../vendor/spread-typescript/spread.ts'
import { nextOpen } from '../../ops/calendar.ts'
import { HOUR, minutes } from '../../ops/index.ts'

/** A gig of several cars may plan 12 hours of driving (RULES.md). We plan 8: chains with more book rarely (50%
 * from 8 hours, 25% from 10), and their drivers finish them the next day, after a car's deadline. */
const MAX_DRIVE = 8 * HOUR
/** The measured typical fee of one car: 15.72 euros and 0.387 a road minute. We split the minute into the drive and
 * the trip home by public transport, which costs a driver much less than the wheel. */
const FIXED = 1572
const PER_MINUTE = 38.7
const HOME_SHARE = 0.3
/** A driver takes this long at a stop, and a delivery must arrive this long before it is due. */
const HANDLING = 15
const SPARE = 45
/** Real drives take up to this × the road minutes, and a later car is reached this long before its last pickup. */
const DRIVE = 1.2
const SLACK = 30
/** A chain's driver starts no sooner than this from now, waits at most this long in all, and works at most this long. */
const LEAD = 2 * HOUR
const MAX_WAIT = 2 * HOUR
const MAX_DAY = 14 * HOUR

/** One open car of ours: a single gig that no driver holds. */
export type Car = {
  gigId: string | undefined // its own gig in the app; none while the car waits for a partner
  orderId: string
  from: string
  to: string
  ready: number // the first minute it can be collected
  collectBy: number // the last
  due: number // the last minute it may arrive
  drive: number // road minutes
  typical: number // its typical fee as a single gig, in cents
  pickupHours: OpeningHours | null
  deliveryHours: OpeningHours | null
  stops: StopRef[] // its pickup and its delivery, as posted
  audience: Audience
}

export type Chain = {
  cars: Car[]
  drive: number // road minutes with the hops between the cars
  startBy: number // the last minute a driver can start it and meet every window
  typical: number // what the chain is worth to a driver, in cents: the fee schedule's unit
  singles: number // the cars' typical fees as single gigs, summed
}

export type ChainParams = { maxHop: number; maxCars: number; minSaving: number }

/** The chains worth posting among `cars`, best saving first, each car in one chain at most. */
export function findChains(cars: Car[], map: WorldMap, now: number, p: ChainParams): Chain[] {
  const found: Chain[] = []
  const next = new Map<Car, Car[]>()
  for (const a of cars)
    next.set(
      a,
      cars.filter((b) => b !== a && minutes(map, a.to, b.from) <= p.maxHop && b.due > a.ready),
    )
  const walk = (path: Car[], drive: number): void => {
    if (path.length >= 2) {
      const chain = judge(path, drive, map, now)
      if (chain && chain.typical <= (1 - p.minSaving) * chain.singles) found.push(chain)
    }
    if (path.length >= p.maxCars) return
    const last = path.at(-1) as Car
    for (const b of next.get(last) ?? []) {
      if (path.includes(b)) continue
      const more = drive + minutes(map, last.to, b.from) + b.drive
      if (more <= MAX_DRIVE) walk([...path, b], more)
    }
  }
  for (const car of cars) walk([car], car.drive)
  found.sort((a, b) => b.singles - b.typical - (a.singles - a.typical))
  const used = new Set<Car>()
  return found.filter((chain) => {
    if (chain.cars.some((car) => used.has(car))) return false
    for (const car of chain.cars) used.add(car)
    return true
  })
}

/** The chain of a path, or null when no driver can do it inside every window. */
function judge(path: Car[], drive: number, map: WorldMap, now: number): Chain | null {
  const first = path[0] as Car
  const last = path.at(-1) as Car
  const earliest = Math.max(now + LEAD, first.ready)
  if (!feasible(path, earliest, map)) return null
  let startBy = earliest
  for (let start = earliest + 30; start <= earliest + 48 * HOUR; start += 30) {
    if (feasible(path, start, map)) startBy = start
    else if (start > startBy + 16 * HOUR) break // a night between two days that work
  }
  const singles = path.reduce((sum, car) => sum + car.typical, 0)
  const modelled = path.reduce((sum, car) => sum + FIXED + PER_MINUTE * car.drive, 0)
  const home = minutes(map, last.to, first.from)
  const cost = FIXED + PER_MINUTE * ((1 - HOME_SHARE) * drive + HOME_SHARE * (Number.isFinite(home) ? home : drive))
  // The cars' own typical fees carry the world's noise for their lanes: the chain keeps it.
  return { cars: path, drive, startBy, singles, typical: Math.round((cost * singles) / modelled) }
}

/** Whether a driver who collects the first car at `start` meets every window, without long waits. */
function feasible(path: Car[], start: number, map: WorldMap): boolean {
  let at = start
  let waited = 0
  let here: string | undefined
  for (const car of path) {
    if (here !== undefined) at += minutes(map, here, car.from)
    const open = nextOpen(Math.max(at, car.ready), car.pickupHours)
    if (here !== undefined) waited += open - at
    at = open
    if (!(at <= car.collectBy - (here === undefined ? 0 : SLACK)) || waited > MAX_WAIT) return false
    at += HANDLING + DRIVE * car.drive
    if (!(nextOpen(at, car.deliveryHours) <= car.due - SPARE)) return false
    at += HANDLING
    here = car.to
  }
  return at - start <= MAX_DAY
}
