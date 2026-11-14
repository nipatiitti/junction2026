/** Chains: several of our open cars as one gig for one driver. The cars are the nodes of a graph, and an edge goes
 * from one car to the next when the next is collected near where the first is delivered. A path through it is a day
 * of work: the driver pays one trip to the first car and one trip home from the last, where the same cars as single
 * gigs pay a trip out and a trip home each. A path that ends where it started pays no trip home at all. The search
 * walks the paths of up to `maxCars` cars inside `maxDrive` hours of driving, keeps the ones a driver can do inside
 * every window, and takes the paths that save the most, each car once. */
import { readFileSync } from 'node:fs'
import type { Audience, OpeningHours, StopRef, WorldMap } from '../../../vendor/spread-typescript/spread.ts'
import { nextOpen } from '../../ops/calendar.ts'
import { DAY, HOUR, minutes } from '../../ops/index.ts'

/** The measured typical fee of one car: 15.72 euros and 0.387 a road minute. We split the minute into the drive and
 * the trip home by public transport, which costs a driver much less than the wheel. */
const FIXED = 1572
const PER_MINUTE = 38.7
const HOME_SHARE = 0.3
/** A driver takes this long at a stop, and a delivery must arrive this long before it is due. Neither is measured. */
const HANDLING = 15
const SPARE = 45
/** Real drives take up to this × the road minutes, and a later car is reached this long before its last pickup. */
const DRIVE = 1.2
const SLACK = 30
/** A chain's driver starts no sooner than this from now, waits at most this long in all, and works at most this
 * long. None of the three is measured, and the last cannot bind with four cars and 8 hours of driving. */
const LEAD = 2 * HOUR
const MAX_WAIT = 2 * HOUR
const MAX_DAY = 14 * HOUR

/** One open car of ours: a single gig that no driver holds, or a car that waits for a partner. */
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
  chance: number // its chance to book: from where the drivers live (`bookChance`), or from the model at `level`
  level: number // its fees × `typical`: 1, or the level that the model says earns the most
  worth: number // with the model: what posting it earns over its cars as single gigs, in cents
}

/** The chain model (chain.json): the chance that a chain books within an hour, fitted on 26,151 chains of 295
 * server weeks (the fit is in the README). `level` is the weight of the log of the fee level, measured by ten weeks
 * that drew each chain's level from 0.78 to 1.12: 12%, 31%, 46% and 66% of them booked. */
export type ChainModel = { intercept: number; weights: Record<string, number> }
export const loadChains = (): ChainModel =>
  JSON.parse(readFileSync(new URL('./chain.json', import.meta.url), 'utf-8')) as ChainModel

/** What the model needs of the week: place id -> the drivers who live there, the bookings so far per driver, and
 * the opening fee × a chain's worth (`open`). Without `model` a chain keeps level 1. */
export type Scene = {
  homes: ReadonlyMap<string, number>
  load: number
  open: number
  alone?: number // × what the cars pay as single gigs: over 1 pays chains more to book more of them
  model?: ChainModel | undefined
}

/** What a chain's cars pay as single gigs × their typical fees when chains are off (ten server weeks: 0.94 for
 * cars won on the Monday, 0.99 from Tuesday to Thursday), and what a failed chain costs its cars on top (1.04
 * against 0.99). */
const [ALONE_MONDAY, ALONE] = [0.94, 0.99]
const FAILED = 0.05
/** The fee levels that the model chooses from. */
const LEVELS = [0.85, 0.9, 0.95, 1, 1.05, 1.1, 1.15, 1.2, 1.25, 1.3]
/** The model's units: a fee of 19 euros an hour of driving, 900 drivers, 30 km as the app's notification reach. */
const [PAY, DRIVERS, REACH, LOAD_MOST, HOME_MOST, LONG, LATE, EARLY] = [1900, 900, 30, 0.6, 360, 5, 12, 7]

/** Kilometres between two places in a straight line, on a flat map at 61 degrees north. */
function apart(map: WorldMap, a: string, b: string): number {
  const [p, q] = [map.places.find((place) => place.id === a), map.places.find((place) => place.id === b)]
  if (!p || !q) return Infinity
  return Math.hypot((p.lon - q.lon) * 111 * Math.cos((61 * Math.PI) / 180), (p.lat - q.lat) * 111)
}

/** The model's score of a path at fee level 1: the log odds that it books within an hour. */
function score(path: Car[], drive: number, typical: number, map: WorldMap, now: number, scene: Scene): number {
  const model = scene.model as ChainModel
  const [first, last] = [path[0] as Car, path.at(-1) as Car]
  let [all, s60, s180, first30, last30] = [0, 0, 0, 0, 0]
  for (const [home, drivers] of scene.homes) {
    all += drivers
    const round = minutes(map, home, first.from) + minutes(map, last.to, home)
    if (round <= 60) s60 += drivers
    if (round <= 180) s180 += drivers
    if (apart(map, home, first.from) <= REACH) first30 += drivers
    if (apart(map, home, last.to) <= REACH) last30 += drivers
  }
  const share = (count: number): number => (all > 0 ? count / all : 0)
  const hours = drive / HOUR
  const load = Math.min(scene.load, LOAD_MOST)
  const start = (Math.max(now + LEAD, first.ready) % DAY) / HOUR
  const home = minutes(map, last.to, first.from)
  const x: Record<string, number> = {
    drive: hours,
    long: Math.max(0, hours - LONG),
    cars: path.length,
    empty: (drive - path.reduce((sum, car) => sum + car.drive, 0)) / drive,
    home: Math.min(Number.isFinite(home) ? home : HOME_MOST, HOME_MOST) / HOUR,
    pay: Math.log((scene.open * typical) / hours / PAY),
    s180: share(s180),
    s60: share(s60),
    last30: share(last30),
    first30: share(first30),
    load,
    loadDrive: load * hours,
    monday: Math.floor(now / DAY) === 0 ? 1 : 0,
    fresh: path.filter((car) => !car.gigId).length / path.length,
    late: start >= LATE ? 1 : 0,
    night: start < EARLY ? 1 : 0,
    drivers: all / DRIVERS,
  }
  let sum = model.intercept
  for (const [key, value] of Object.entries(x)) sum += (model.weights[key] ?? 0) * value
  return sum
}

/** The fee level that earns the most, with its chance to book and what it earns over the cars as single gigs:
 * chance × (what the cars pay alone − the chain's fee) − (1 − chance) × what a failed chain costs them. */
function priced(odds: number, singles: number, typical: number, now: number, scene: Scene) {
  const alone = (Math.floor(now / DAY) === 0 ? ALONE_MONDAY : ALONE) * (scene.alone ?? 1) * singles
  const slope = scene.model?.weights.level ?? 0
  let best = { level: 1, chance: 0, worth: -Infinity }
  for (const level of LEVELS) {
    const chance = 1 / (1 + Math.exp(-(odds + slope * Math.log(level))))
    const worth = chance * (alone - scene.open * level * typical) - (1 - chance) * FAILED * singles
    if (worth > best.worth) best = { level, chance, worth }
  }
  return best
}

export type ChainParams = { maxHop: number; maxCars: number; minSaving: number; maxDrive: number; chainFit: number }

/** A chain's chance to book, from 1,414 chains of 15 server weeks. What decides it is how many drivers can do the
 * chain as a round from home: with home to the first pickup and the last delivery to home inside `ROUND` road
 * minutes for half of the drivers or more, 76% booked, and with no such driver 43 to 51%. A chain that ends over
 * `FAR` road minutes from where it starts booked 36%. The fee did not decide it. */
const ROUND = 120
const FAR = 180
const FULL_SHARE = 0.5
const [CHANCE_FAR, CHANCE_NONE, CHANCE_FULL] = [0.36, 0.45, 0.8]

/** The chance that a chain from `first` to `last` books; `homes` is place id -> the drivers who live there. */
export function bookChance(map: WorldMap, homes: ReadonlyMap<string, number>, first: string, last: string): number {
  if (!(minutes(map, last, first) <= FAR)) return CHANCE_FAR
  let [all, near] = [0, 0]
  for (const [home, drivers] of homes) {
    all += drivers
    if (minutes(map, home, first) + minutes(map, last, home) <= ROUND) near += drivers
  }
  const share = all > 0 ? Math.min(1, near / all / FULL_SHARE) : 0
  return CHANCE_NONE + (CHANCE_FULL - CHANCE_NONE) * share
}

/** The search stops after this many paths, so that one tick stays far inside its 3 seconds: 20 cars near each other
 * make 116,000 paths of four. The cars are walked in the order of their ids, so the same cars give the same chains. */
const MAX_PATHS = 20_000

/** The chains worth posting among `cars` that `keep` lets through, best first, each car in one chain at most. The
 * best chain saves the most × its chance to book to the power `chainFit`: 0 ranks by the saving alone. With the
 * model, the best chain earns the most a car, and only chains that earn something are kept. */
export function findChains(
  open: Car[],
  map: WorldMap,
  now: number,
  p: ChainParams,
  keep: (chain: Chain) => boolean = () => true,
  scene: Scene = { homes: new Map(), load: 0, open: 1 },
): Chain[] {
  const cars = [...open].sort((a, b) => a.orderId.localeCompare(b.orderId))
  const found: Chain[] = []
  const next = new Map<Car, Car[]>()
  for (const a of cars)
    next.set(
      a,
      cars.filter((b) => b !== a && minutes(map, a.to, b.from) <= p.maxHop && b.due > a.ready),
    )
  let paths = 0
  const walk = (path: Car[], drive: number): void => {
    if (paths >= MAX_PATHS) return
    if (path.length >= 2) {
      paths++
      const chain = judge(path, drive, map, now, p.minSaving, scene)
      if (chain && keep(chain)) found.push(chain)
    }
    if (path.length >= p.maxCars) return
    const last = path.at(-1) as Car
    for (const b of next.get(last) ?? []) {
      if (path.includes(b)) continue
      const more = drive + minutes(map, last.to, b.from) + b.drive
      if (more <= p.maxDrive * HOUR) walk([...path, b], more)
    }
  }
  for (const car of cars) walk([car], car.drive)
  const key = (chain: Chain): string => chain.cars.map((car) => car.orderId).join(' ')
  const worth = (chain: Chain): number =>
    scene.model ? chain.worth / chain.cars.length : (chain.singles - chain.typical) * chain.chance ** p.chainFit
  found.sort((a, b) => worth(b) - worth(a) || key(a).localeCompare(key(b)))
  const used = new Set<Car>()
  return found.filter((chain) => {
    if (chain.cars.some((car) => used.has(car))) return false
    for (const car of chain.cars) used.add(car)
    return true
  })
}

/** A chain's start is tried every `GRID` minutes of the clock, for `HORIZON` from the first minute a driver could
 * start; a gap of over `NIGHT` between two starts that work ends the search (a night between two days is shorter). */
const GRID = 30
const HORIZON = 48 * HOUR
const NIGHT = 16 * HOUR

/** The chain of a path, or null when it saves a driver less than `minSaving` of its cars' fees, or no driver can do
 * it inside every window. */
function judge(path: Car[], drive: number, map: WorldMap, now: number, minSaving: number, scene: Scene): Chain | null {
  const first = path[0] as Car
  const last = path.at(-1) as Car
  const singles = path.reduce((sum, car) => sum + car.typical, 0)
  const modelled = path.reduce((sum, car) => sum + FIXED + PER_MINUTE * car.drive, 0)
  const home = minutes(map, last.to, first.from)
  const cost = FIXED + PER_MINUTE * ((1 - HOME_SHARE) * drive + HOME_SHARE * (Number.isFinite(home) ? home : drive))
  // The cars' own typical fees carry the world's noise for their lanes: the chain keeps it.
  const typical = Math.round((cost * singles) / modelled)
  if (typical > (1 - minSaving) * singles) return null // before the search for its starts, which costs the most
  // The first start that works may be a later one: a start this afternoon can reach the second yard after it
  // closes, where one tomorrow morning does not.
  const earliest = Math.ceil(Math.max(now + LEAD, first.ready) / GRID) * GRID
  let startBy: number | undefined
  for (let start = earliest; start <= earliest + HORIZON; start += GRID) {
    if (feasible(path, start, map)) startBy = start
    else if (startBy !== undefined && start > startBy + NIGHT) break
  }
  if (startBy === undefined) return null
  if (scene.model) {
    const best = priced(score(path, drive, typical, map, now, scene), singles, typical, now, scene)
    return best.worth > 0 ? { cars: path, drive, startBy, singles, typical, ...best } : null
  }
  const chance = bookChance(map, scene.homes, first.from, last.to)
  return { cars: path, drive, startBy, singles, typical, chance, level: 1, worth: 0 }
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
