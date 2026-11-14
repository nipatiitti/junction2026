// Offline Spread world, level 8. A statistical stand-in for the server, not a copy of it:
// the rules are implemented as written, the request stream / roster / car facts are replayed from
// recorded seeds (sim/data), and the hidden values (dealer thresholds, driver costs and days) are
// drawn from distributions fitted to probes. Every tunable number is in PRM (override: sim/params.json).
import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { gunzipSync } from 'node:zlib'

const DIR = import.meta.dirname + '/data'
export const MAP = JSON.parse(readFileSync(DIR + '/map.json', 'utf8'))
const ROAD: Record<string, { km: number; minutes: number }> = {}
for (const r of MAP.roads) ROAD[r.from + '>' + r.to] = r
const PLACE: Record<string, any> = {}
for (const p of MAP.places) PLACE[p.id] = p
const road = (a: string, b: string) => ROAD[a + '>' + b]
const CROW: Record<string, number> = {}
function crow(a: string, b: string): number {
  const k = a + '>' + b
  if (CROW[k] !== undefined) return CROW[k]
  const A = PLACE[a],
    B = PLACE[b],
    R = Math.PI / 180
  const x = (B.lon - A.lon) * R * Math.cos(((A.lat + B.lat) / 2) * R),
    y = (B.lat - A.lat) * R
  return (CROW[k] = 6371 * Math.sqrt(x * x + y * y))
}

export const PRM = {
  // ---- dealers: accepted price = list x level x day x lane x dealer x noise x option x trust ...
  // fitted on 1,291 quote probes: base 1.24 x list at zero trust, +1% per on-time order, -2.1% per late order
  level: [1.26, 1.54],
  thrBase: 0.925,
  daySd: 0.1,
  laneSd: 0.14,
  dealerSd: 0.04,
  reqSd: 0.04,
  optSd: 0.14,
  distK: 0.1,
  optF: { same_day: 1.09, next_day: 1.0, within_3_days: 0.96 } as Record<string, number>,
  trustStep: 0.0115,
  latePenalty: 0.017,
  onTimeHeal: 0.002,
  unquotedPenalty: 0.002,
  compStep: 0.03,
  compMax: 2,
  compHi: 0.6,
  compLo: 0.25,
  war: 0.8,
  outage: 1.3,
  // ---- drivers: who works
  pWork: 0.5,
  pWorkSat: 0.18,
  dayJob: 0.25,
  notif: 0.7,
  knowsWeek: 0.3,
  flu: 0.3,
  snowHome: 0.3,
  // ---- drivers: what a gig costs them (cents)
  costFix: 700,
  wDrive: 20,
  wPt: 5,
  ptF: 1.4,
  ptFix: 20,
  ticketCheap: 5,
  ticketDear: 9,
  wLate: 12,
  night: 5000,
  exPrivate: 300,
  exTrade: 500,
  exPlates: 600,
  exCharge: 600,
  satF: 1.25,
  multSd: 0.15,
  epsSd: 0.22,
  // ---- drivers: looking at the app
  openWork: 1.2,
  openOff: 0.15,
  nearKm: 40,
  pNear: 0.5,
  pPay: 0.6,
  pFar: 0.02,
  payView: 0.85,
  reView: 0.35,
  notifRead: 0.9,
  notifReadOff: 0.25,
  // ---- drivers: waiting, drops, drive time
  belief0: 1.05,
  beliefMix: 0.25,
  waitK: 3,
  dropScale: 1,
  thinDrop: 0.2,
  driveSd: 0.07,
  slowP: 0.04,
  snowF: 1.3,
  cancelP: 0.012,
  pToday: 0.5,
  urgent: 0.3,
  urgentTau: 180,
  costScale: 1.15,
  maxGigs: 5,
  pNearOff: 0.03,
  bundleF: 0.9,
  dropLong: 0.0015,
}
const PFILE = process.env.SIM_PARAMS ?? import.meta.dirname + '/params.json'
if (existsSync(PFILE)) Object.assign(PRM, JSON.parse(readFileSync(PFILE, 'utf8')))

// ---------- randomness: hashes for anything that must not depend on the order of actions ----------
function h(s: string): number {
  let x = 2166136261
  for (let i = 0; i < s.length; i++) x = Math.imul(x ^ s.charCodeAt(i), 16777619)
  x ^= x >>> 13
  x = Math.imul(x, 0x5bd1e995)
  x ^= x >>> 15
  x = Math.imul(x, 0x2c1b3c6d)
  x ^= x >>> 12
  return ((x >>> 0) + 0.5) / 4294967296
}
const hn = (s: string) => Math.sqrt(-2 * Math.log(h(s + 'a'))) * Math.cos(2 * Math.PI * h(s + 'b'))
function rnd(W: any): number {
  let t = (W.rs = (W.rs + 0x6d2b79f5) | 0)
  t = Math.imul(t ^ (t >>> 15), t | 1)
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
  return (((t ^ (t >>> 14)) >>> 0) + 0.5) / 4294967296
}
const rexp = (W: any, mean: number) => -Math.log(rnd(W)) * mean
const rn = (W: any) => Math.sqrt(-2 * Math.log(rnd(W))) * Math.cos(2 * Math.PI * rnd(W))

// ---------- time and opening hours ----------
const day = (t: number) => Math.floor(t / 1440),
  tod = (t: number) => t % 1440
function span(hh: any, D: number): [number, number] | null {
  const wd = D % 7
  if (wd === 5) return hh.saturday ? [hh.saturday.opens, hh.saturday.closes] : null
  return wd < 5 && hh.weekdays.includes(wd) ? [hh.opens, hh.closes] : null
}
function isOpen(hh: any, t: number): boolean {
  if (!hh) return true
  const s = span(hh, day(t))
  return !!s && tod(t) >= s[0] && tod(t) <= s[1]
}
function nextOpen(hh: any, t: number): number {
  if (!hh || isOpen(hh, t)) return t
  for (let D = day(t); D < 12; D++) {
    const s = span(hh, D)
    if (s && D * 1440 + s[0] >= t) return D * 1440 + s[0]
  }
  return Infinity
}
const bizDays = (a: number, b: number) => {
  let n = 0
  for (let D = a + 1; D <= b; D++) if (D % 7 < 5) n++
  return n
}
const nextBiz = (D: number) => {
  do D++
  while (D % 7 >= 5)
  return D
}
const fmt = (t: number) =>
  `${['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][day(t) % 7]} ${String(Math.floor(tod(t) / 60)).padStart(2, '0')}:${String(tod(t) % 60).padStart(2, '0')}`

// ---------- data packs ----------
const PACKS: Record<string, any> = {}
let SEEDS: string[] | null = null
export function packFor(seed: string) {
  SEEDS ??= readdirSync(DIR + '/L8')
    .map((f) => f.replace('.json.gz', ''))
    .sort()
  const name = SEEDS.includes(seed) ? seed : SEEDS[Math.floor(h('pack' + seed) * SEEDS.length)] // unknown seed: a recorded week
  if (!PACKS[name]) {
    const p = JSON.parse(gunzipSync(readFileSync(`${DIR}/L8/${name}.json.gz`)).toString())
    p.near = {} // place -> drivers who live within 30 km (notifications)
    for (const pl of MAP.places)
      p.near[pl.id] = p.drivers
        .map((d: any, i: number) => (crow(d.homePlaceId, pl.id) <= 30 ? i : -1))
        .filter((i: number) => i >= 0)
    p.snow = p.forecasts.map((f: any) => ({ from: f.from, to: f.to, places: new Set(f.placeIds) }))
    PACKS[name] = p
  }
  return PACKS[name]
}
const snowAt = (P: any, place: string, t: number) =>
  P.snow.some((s: any) => t >= s.from && t < s.to && s.places.has(place))

// ---------- queue ----------
function push(W: any, it: any) {
  it.t = Math.max(Math.ceil(it.t), W.now)
  it.n = W.qn++
  const q = W.q
  let i = q.length
  q.push(it)
  while (i > 0) {
    const p = (i - 1) >> 1
    if (q[p].t < it.t || (q[p].t === it.t && q[p].n < it.n)) break
    q[i] = q[p]
    i = p
  }
  q[i] = it
}
function pop(W: any) {
  const q = W.q,
    top = q[0],
    last = q.pop()
  if (q.length) {
    let i = 0
    for (;;) {
      let c = 2 * i + 1
      if (c >= q.length) break
      if (c + 1 < q.length && (q[c + 1].t < q[c].t || (q[c + 1].t === q[c].t && q[c + 1].n < q[c].n))) c++
      if (last.t < q[c].t || (last.t === q[c].t && last.n < q[c].n)) break
      q[i] = q[c]
      i = c
    }
    q[i] = last
  }
  return top
}
const emit = (W: any, kind: string, f: any = {}) => W.events.push({ seq: W.events.length, at: W.now, kind, ...f })
function ledger(W: any, kind: string, cents: number, orderId: string | null, gigId: string | null, detail: string) {
  cents = Math.round(cents)
  W.margin += cents
  if (kind === 'revenue') W.revenue += cents
  emit(W, 'ledger', { line: { at: W.now, kind, cents, orderId, gigId, detail } })
}

// ---------- world ----------
let WN = 0
export let FULL_FORK_HISTORY = false
export const setFullForkHistory = (v: boolean) => (FULL_FORK_HISTORY = v)
export function createWorld(seed: string, level = 8): any {
  const P = packFor(seed)
  const W: any = {
    worldId: 'w' + (++WN).toString(36).padStart(4, '0') + Math.floor(h(seed + WN) * 1e9).toString(36),
    seed,
    pack: P.seed,
    level,
    now: 0,
    endsAt: 14280,
    ended: false,
    rs: Math.floor(h('rng' + seed) * 2 ** 32) | 0,
    q: [],
    qn: 0,
    events: [],
    cursor: 0,
    views: [],
    quotes: {},
    outcome: {},
    orders: {},
    gigs: {},
    gigN: 0,
    offerN: 0,
    open: [],
    dealers: {},
    margin: 0,
    revenue: 0,
    hid: {} as any,
    drivers: [] as any[],
  }
  // hidden market conditions
  const H = W.hid
  H.level = PRM.thrBase * (PRM.level[0] + (PRM.level[1] - PRM.level[0]) * h(seed + 'lvl'))
  H.dayF = [0, 1, 2, 3, 4].map((d) => Math.exp(PRM.daySd * hn(seed + 'day' + d)))
  H.outDay = Math.floor(h(seed + 'od') * 5)
  H.outTown = MAP.places[Math.floor(h(seed + 'ot') * MAP.places.length)].id
  H.warDay = (H.outDay + 1 + Math.floor(h(seed + 'wd') * 4)) % 5
  H.fluDay = Math.floor(h(seed + 'fd') * 5)
  // a recorded seed: the server's own level per weekday (it already holds that week's price war and outage)
  const mk = P.market
  if (mk && [0, 1, 2, 3, 4].every((d) => mk[d])) {
    H.dayF = [0, 1, 2, 3, 4].map((d) => mk[d] / H.level)
    H.recovered = true
    H.warDay = -1
    H.outDay = -1
  }
  // drivers and their days
  P.drivers.forEach((p: any, i: number) => {
    const dj = rnd(W) < PRM.dayJob,
      weekend = rnd(W) < 0.08
    const days = []
    for (let D = 0; D < 10; D++) {
      const wd = D % 7
      let works = wd === 6 ? false : wd === 5 ? weekend || rnd(W) < PRM.pWorkSat : !weekend && rnd(W) < PRM.pWork
      if (works && D === H.fluDay && rnd(W) < PRM.flu) works = false
      if (works && snowAt(P, p.homePlaceId, D * 1440 + 600) && rnd(W) < PRM.snowHome) works = false
      const from = dj && wd < 5 ? 960 + rnd(W) * 60 : 360 + rnd(W) * 240
      days.push({
        works,
        from: Math.round(from),
        to: Math.round(dj && wd < 5 ? 1320 + rnd(W) * 60 : 960 + rnd(W) * 330),
        max: 1 + Math.floor(PRM.maxGigs * rnd(W) ** 3),
      })
    }
    W.drivers.push({
      i,
      id: p.id,
      home: p.homePlaceId,
      rating: p.rating,
      licence: p.licence,
      completed: p.completedGigs,
      drops: 0,
      exp: p.rating >= 4.8 && p.completedGigs >= 50,
      notif: rnd(W) < PRM.notif,
      knows: rnd(W) < PRM.knowsWeek,
      mult: Math.exp(PRM.multSd * rn(W)),
      days,
      busy: [],
      loc: p.homePlaceId,
      freeAt: 0,
      locDay: -1,
      belief: PRM.belief0,
      offers: [-1, 0],
    })
    push(W, { t: nextLook(W, W.drivers[i], 300), k: 'open', d: i })
  })
  P.requests.forEach((r: any, i: number) => push(W, { t: r.arrivedAt, k: 'req', i }))
  P.forecasts.forEach((f: any, i: number) => push(W, { t: f.at, k: 'forecast', i }))
  for (let D = 1; D < 8; D++) push(W, { t: D * 1440 + 360, k: 'morning' })
  return W
}
export function fork(W: any): any {
  // events and views only grow and their items never change: share the items, copy the rest
  const { events, views, ...rest } = W
  const C = structuredClone(rest)
  C.events = events.slice()
  C.views = views.slice()
  C.worldId = 'w' + (++WN).toString(36).padStart(4, '0') + 'f'
  C.parent = W.worldId
  if (FULL_FORK_HISTORY) C.cursor = 0 // the server's first advance on a copy answers with the whole history
  return C
}
const dealer = (W: any, id: string) => (W.dealers[id] ??= { trust: 0, sat: 0, comp: 0, won: 0, n: 0 })

// ---------- orders ----------
const pubOrder = (o: any) => ({
  id: o.id,
  dealerId: o.dealerId,
  option: o.option,
  priceCents: o.priceCents,
  deadline: o.deadline,
  legs: structuredClone(o.legs),
  status: o.status,
  deliveredAt: [...o.deliveredAt],
  lastPickupAt: o.lastPickupAt,
})
const legDeadline = (o: any, i: number) =>
  o.legs[i].delivery.privateAddress ? o.legs[i].delivery.window.to + 30 : o.deadline
const needsCharge = (l: any) =>
  l.car.electric && (l.car.chargePercent ?? 100) < 30 && road(l.pickup.placeId, l.delivery.placeId).km > 200
const live = (o: any) => o && o.status !== 'cancelled' && o.status !== 'delivered'

// last minute to collect the first undelivered car and still deliver every car on time
function lastPickup(W: any, o: any): number {
  const todo = o.legs.map((_: any, i: number) => i).filter((i: number) => o.deliveredAt[i] === null && !o.picked[i])
  if (!todo.length) return o.lastPickupAt
  const f = o.legs[todo[0]]
  const fits = (t: number) => {
    if (!isOpen(f.pickup.hours, t) || t < f.pickup.window.from || (f.pickup.privateAddress && t > f.pickup.window.to))
      return false
    let prev = ''
    for (const i of todo) {
      const l = o.legs[i]
      if (prev) {
        t += road(prev, l.pickup.placeId).minutes
        if (l.pickup.hours && !isOpen(l.pickup.hours, t)) return false
      }
      t += road(l.pickup.placeId, l.delivery.placeId).minutes + (needsCharge(l) ? 40 : 0)
      if (t > legDeadline(o, i) || (l.delivery.hours && !isOpen(l.delivery.hours, t))) return false
      if (l.delivery.privateAddress) t = Math.max(t, l.delivery.window.from)
      prev = l.delivery.placeId
    }
    return true
  }
  const start = Math.min(legDeadline(o, todo[0]), f.pickup.privateAddress ? f.pickup.window.to : Infinity)
  for (let t = start, n = 0; t >= W.now && n < 8000; t--, n++)
    if (fits(t)) {
      o.late = false
      return t
    }
  o.late = true // no pickup can be on time any more: gigs for this order run to the end of the world
  return nextOpen(f.pickup.hours, Math.max(W.now, f.pickup.window.from))
}
function armWarn(W: any, o: any) {
  push(W, { t: o.lastPickupAt - 180, k: 'warn', o: o.id, v: ++o.warnV })
}
const hasDriver = (W: any, o: any) =>
  o.gigOf.some(
    (g: string | null, i: number) => g && o.deliveredAt[i] === null && ['booked', 'working'].includes(W.gigs[g].status),
  )
function relast(W: any, o: any) {
  const was = o.lastPickupAt
  o.lastPickupAt = lastPickup(W, o)
  if (o.lastPickupAt > was) armWarn(W, o)
}

// the highest price the dealer accepts for each option, as things stand now
function thresholds(W: any, req: any): Record<string, number> {
  const D = dealer(W, req.dealerId),
    H = W.hid
  const d = day(req.arrivedAt),
    m = tod(req.arrivedAt),
    pu = req.legs[0].pickup.placeId,
    de = req.legs[0].delivery.placeId
  let f =
    H.level *
    (H.dayF[d] ?? 1) *
    Math.exp(
      PRM.laneSd * hn(W.seed + 'ln' + pu + de) +
        PRM.dealerSd * hn(W.seed + 'dl' + req.dealerId) +
        PRM.reqSd * hn(W.seed + 'rq' + req.id),
    )
  f *= (1 + PRM.trustStep * D.trust) * (1 - D.sat) * (1 - PRM.compStep * D.comp)
  if (m >= 480 && m < 1080) {
    if (d === H.warDay) f *= PRM.war
    if (d === H.outDay && crow(pu, H.outTown) <= 80) f *= PRM.outage
  }
  const out: Record<string, number> = {}
  for (const o of req.options)
    out[o.kind] =
      o.listPriceCents *
      f *
      PRM.optF[o.kind] *
      Math.exp(PRM.distK * Math.max(-1, Math.min(0.6, Math.log(o.listPriceCents / 5500)))) *
      Math.exp(PRM.optSd * hn(W.seed + 'op' + req.id + o.kind))
  return out
}
function makeOrder(W: any, req: any, opt: any, price: number): any {
  const P = packFor(W.pack),
    rec = P.won[req.id]?.[opt.kind]
  const truth =
    P.truths[req.id] ??
    req.legs.map((l: any) => ({
      readyAt: l.pickup.window.from,
      releasedAt: null,
      pickupHours: l.pickup.hours,
      deliveryHours: l.delivery.hours,
      manualGearbox: false,
      needsPlates: false,
      summerTyres: false,
      noteDeadline: null,
    }))
  const legs = structuredClone(req.legs)
  let deadline = opt.deadline
  if (rec) {
    deadline = rec.deadline
    legs.forEach((l: any, i: number) => {
      l.pickup.window = { ...rec.windows[i][0] }
      l.delivery.window = { ...rec.windows[i][1] }
    })
  } else
    for (const l of legs) {
      if (!l.pickup.privateAddress) l.pickup.window.to = deadline
      if (!l.delivery.privateAddress) l.delivery.window.to = deadline
    }
  const o: any = (W.orders[req.id] = {
    id: req.id,
    dealerId: req.dealerId,
    option: opt.kind,
    priceCents: price,
    deadline,
    legs,
    status: 'waiting',
    deliveredAt: legs.map(() => null),
    lastPickupAt: 0,
    truth,
    ref: req.referenceFeeCents,
    picked: legs.map(() => false),
    gigOf: legs.map(() => null),
    warnV: 0,
    viewers: {},
    wonAt: W.now,
  })
  o.lastPickupAt = lastPickup(W, o)
  if (rec && rec.lastPickupAt >= W.now && !o.late) o.lastPickupAt = rec.lastPickupAt // the server's own value when we have it
  return o
}
const cancelAt = (W: any, o: any) => {
  const P = packFor(W.pack)
  return (
    P.cancels[o.id] ??
    (!P.truths[o.id] && h(W.seed + 'cx' + o.id) < PRM.cancelP
      ? W.now + 30 + h(W.seed + 'cy' + o.id) * Math.max(60, o.lastPickupAt - W.now)
      : null)
  )
}

function decide(W: any, req: any) {
  const q = W.quotes[req.id],
    D = dealer(W, req.dealerId)
  if (!q) {
    W.outcome[req.id] = { outcome: 'unquoted', option: null }
    D.sat = Math.min(0.4, D.sat + PRM.unquotedPenalty)
    return
  }
  const thr = thresholds(W, req)
  let best: any = null
  for (const o of req.options) {
    if (!q[o.kind]) continue
    const s = Math.log(thr[o.kind] / q[o.kind])
    if (s >= 0 && (!best || s > best.s)) best = { s, o }
  }
  D.n++
  if (!best) {
    W.outcome[req.id] = { outcome: 'lost', option: null }
    emit(W, 'order_lost', { requestId: req.id })
    return
  }
  D.won++
  win(W, req, best.o, q[best.o.kind])
}
// the dealer takes this option at this price (also used to replay a recorded week's orders)
export function win(W: any, req: any, opt: any, price: number) {
  W.outcome[req.id] = { outcome: 'won', option: opt.kind }
  const P = packFor(W.pack),
    o = makeOrder(W, req, opt, price),
    legs = o.legs
  emit(W, 'order_won', { order: pubOrder(o) })
  armWarn(W, o)
  o.truth.forEach((t: any, i: number) => {
    if (t.releasedAt && t.releasedAt > W.now) push(W, { t: t.releasedAt, k: 'release', o: o.id, leg: i })
  })
  legs.forEach((l: any, i: number) => {
    if (l.pickup.privateAddress && !(i === 1 && legs[0].delivery.placeId === l.pickup.placeId))
      push(W, { t: l.pickup.window.to + 1, k: 'slot', o: o.id, leg: i })
  })
  const cAt = cancelAt(W, o)
  if (cAt) push(W, { t: cAt, k: 'cancel', o: o.id })
  for (const c of P.changes[o.id] ?? [])
    if (c.places.some((p: string[], i: number) => p[1] !== req.legs[i].delivery.placeId))
      push(W, { t: c.at, k: 'change', o: o.id, places: c.places, message: c.message })
}

function delivered(W: any, o: any, leg: number, gigId: string, drv: any) {
  if (o.deliveredAt[leg] !== null || o.status === 'cancelled') return
  o.deliveredAt[leg] = W.now
  emit(W, 'delivered', { gigId, orderId: o.id, leg, placeId: o.legs[leg].delivery.placeId })
  if (o.legs[leg].car.premium && drv && !drv.exp)
    ledger(W, 'fine', -15000, o.id, gigId, `A premium car needs an experienced driver: ${o.id} leg ${leg}`)
  if (o.deliveredAt.some((x: any) => x === null)) return relast(W, o)
  o.status = 'delivered'
  ledger(W, 'revenue', o.priceCents, o.id, null, 'Delivered')
  let late = 0,
    dl = 0
  o.legs.forEach((_: any, i: number) => {
    const d = Math.min(legDeadline(o, i), o.truth[i].noteDeadline ?? Infinity)
    if (o.deliveredAt[i] - d > late) {
      late = o.deliveredAt[i] - d
      dl = d
    }
  })
  const D = dealer(W, o.dealerId)
  if (late <= 0) {
    o.onTime = true
    D.trust = Math.min(25, D.trust + 1)
    D.sat = Math.max(0, D.sat - PRM.onTimeHeal)
    return
  }
  const share = late <= 120 ? 0.1 : late <= 1440 ? 0.25 : bizDays(day(dl), day(W.now)) <= 2 ? 0.5 : 1
  ledger(W, 'late_refund', -o.priceCents * share, o.id, null, `Late by ${late} minutes, ${share * 100}% back`)
  D.trust = Math.floor(D.trust / 2)
  D.sat = Math.min(0.4, D.sat + PRM.latePenalty)
}

// ---------- gigs ----------
const pubGig = (g: any) => ({
  id: g.id,
  stops: g.stops.map(({ skip, ...s }: any) => s),
  audience: g.audience,
  schedule: g.schedule,
  status: g.status,
  postedAt: g.postedAt,
  feeCents: g.feeCents,
  driverId: g.driverId,
})
function curFee(g: any, now: number): number {
  let f = g.schedule[0].feeCents
  for (const s of g.schedule) if (s.at <= now) f = s.feeCents
  return f
}
const place = (W: any, s: any) => W.orders[s.orderId].legs[s.leg][s.kind].placeId
const cars = (g: any) => g.stops.filter((s: any) => s.kind === 'pickup')
function shareOf(W: any, g: any, s: any): number {
  const m = (x: any) => {
    const l = W.orders[x.orderId].legs[x.leg]
    return road(l.pickup.placeId, l.delivery.placeId).minutes + 20
  }
  return m(s) / cars(g).reduce((a: number, x: any) => a + m(x), 0)
}
function windows(W: any, g: any) {
  const late = g.stops.some((s: any) => W.orders[s.orderId].late || W.now > W.orders[s.orderId].lastPickupAt)
  g.win = g.stops.map((s: any, k: number) => {
    const o = W.orders[s.orderId],
      l = o.legs[s.leg],
      site = l[s.kind],
      prev = g.stops[k - 1]
    if (
      s.kind === 'pickup' &&
      prev &&
      prev.kind === 'delivery' &&
      prev.orderId === s.orderId &&
      place(W, prev) === site.placeId
    )
      return { from: 0, to: W.endsAt } // trade-in: same visit
    if (s.window) return s.window
    if (s.kind === 'pickup' && site.privateAddress) return site.window
    const to = s.kind === 'delivery' && site.privateAddress ? site.window.to + 30 : site.window.to
    return late || to < W.now
      ? { from: s.kind === 'delivery' && site.privateAddress ? 0 : site.window.from, to: W.endsAt }
      : { from: s.kind === 'delivery' && site.privateAddress ? 0 : site.window.from, to }
  })
  g.expireAt = Math.min(...g.win.map((w: any) => w.to)) + 1
}
function reopen(W: any, g: any) {
  g.status = 'open'
  g.driverId = null
  g.drv = -1
  g.ver++
  if (g.expireAt <= W.now) {
    g.status = 'withdrawn'
    freeLegs(W, g)
    emit(W, 'gig_expired', { gigId: g.id })
    return
  }
  W.open.push(g.id)
  notify(W, g)
  for (const id of g.orderIds) {
    const o = W.orders[id]
    if (live(o)) {
      o.status = 'waiting'
      armWarn(W, o)
    }
  }
}
function freeLegs(W: any, g: any) {
  W.open = W.open.filter((x: string) => x !== g.id)
  for (const s of cars(g)) {
    const o = W.orders[s.orderId]
    if (o.gigOf[s.leg] === g.id) {
      o.gigOf[s.leg] = null
      if (live(o) && !hasDriver(W, o)) {
        if (o.status !== 'working') o.status = 'waiting'
        armWarn(W, o)
      }
    }
  }
}
function unbusy(W: any, g: any) {
  if (g.drv >= 0) {
    const d = W.drivers[g.drv]
    d.busy = d.busy.filter((b: any) => b.g !== g.id)
  }
}
function notify(W: any, g: any) {
  const pd = Math.min(9, day(Math.max(W.now, g.win[0].from)))
  const P = packFor(W.pack),
    m = tod(W.now),
    at = m < 420 ? day(W.now) * 1440 + 420 : m >= 1380 ? (day(W.now) + 1) * 1440 + 420 : W.now
  for (const i of P.near[place(W, g.stops[0])]) {
    const d = W.drivers[i]
    if (!d.notif) continue
    if (rnd(W) < (d.days[day(at)]?.works || d.days[pd]?.works ? PRM.notifRead : PRM.notifReadOff))
      push(W, { t: at + 1 + rexp(W, 4), k: 'look', d: i, g: g.id, src: 'notif' })
  }
}

function doPost(W: any, a: any) {
  if (!Array.isArray(a.stops) || a.stops.length < 2) return 'A gig needs at least two stops'
  const seen: Record<string, number> = {}
  for (const s of a.stops) {
    const o = W.orders[s.orderId],
      key = s.orderId + ':' + s.leg
    if (!o) return `No order ${s.orderId}`
    if (o.status === 'cancelled') return `${s.orderId} was cancelled`
    if (!o.legs[s.leg]) return `${s.orderId} has no leg ${s.leg}`
    if (o.deliveredAt[s.leg] !== null || o.picked[s.leg]) return `${s.orderId} leg ${s.leg} is already collected`
    if (s.kind === 'pickup') {
      if (seen[key]) return `${s.orderId} leg ${s.leg} appears twice`
      if (o.gigOf[s.leg]) return `${s.orderId} leg ${s.leg} is already in a live gig`
      seen[key] = 1
    } else {
      if (seen[key] !== 1) return `The delivery of ${s.orderId} leg ${s.leg} comes before its pickup`
      seen[key] = 2
    }
    const site = o.legs[s.leg][s.kind]
    if (s.window) {
      if (s.window.from < site.window.from)
        return `The ${s.kind} window of ${s.orderId} leg ${s.leg} starts before the order's window`
      if (s.kind === 'pickup' && site.privateAddress && s.window.to > site.window.to)
        return `The pickup window of ${s.orderId} leg ${s.leg} ends after the seller's slot`
    }
  }
  if (Object.values(seen).some((v) => v !== 2)) return 'Each car needs a pickup and a delivery'
  const bad = schedErr(a.schedule)
  if (bad) return bad
  const g: any = {
    id: 'g' + ++W.gigN,
    stops: a.stops.map((s: any) => ({
      orderId: s.orderId,
      leg: s.leg,
      kind: s.kind,
      ...(s.window ? { window: s.window } : {}),
      ...(s.kind === 'pickup' ? { withPlates: !!s.withPlates, withCharging: !!s.withCharging } : {}),
    })),
    audience: { experienced: !!a.audience?.experienced, manualLicence: !!a.audience?.manualLicence },
    schedule: a.schedule,
    status: 'open',
    postedAt: W.now,
    feeCents: null,
    driverId: null,
    drv: -1,
    ver: 0,
    viewers: {},
    minFee: {},
    looks: {},
    offers: [],
    failed: 0,
  }
  g.orderIds = [...new Set(g.stops.map((s: any) => s.orderId))]
  if (cars(g).length > 1) {
    let m = 0
    for (let k = 1; k < g.stops.length; k++) m += road(place(W, g.stops[k - 1]), place(W, g.stops[k])).minutes
    if (m > 720) return `The gig plans ${m} minutes of driving: a gig with more than one car may plan at most 720`
  }
  windows(W, g)
  for (let k = 0; k < g.stops.length; k++)
    if (g.win[k].to < W.now) {
      const s = g.stops[k]
      return `The ${s.kind} window of ${s.orderId} leg ${s.leg} ended at ${fmt(g.win[k].to)}: no driver can ${s.kind === 'pickup' ? 'collect' : 'deliver'} the car in it`
    }
  g.drive = 0
  for (let k = 1; k < g.stops.length; k++) g.drive += road(place(W, g.stops[k - 1]), place(W, g.stops[k])).minutes
  W.gigs[g.id] = g
  W.open.push(g.id)
  let fresh = false
  for (const s of cars(g)) {
    const o = W.orders[s.orderId]
    o.gigOf[s.leg] = g.id
    if (!o.posted) {
      o.posted = W.now
      fresh = true
    }
  }
  push(W, { t: g.expireAt, k: 'expire', g: g.id })
  if (fresh) notify(W, g)
  return g
}
function schedErr(s: any): string | null {
  if (!Array.isArray(s) || s.length < 1 || s.length > 48) return 'A fee schedule has 1 to 48 steps'
  for (let i = 0; i < s.length; i++) {
    if (!Number.isInteger(s[i].at) || !Number.isInteger(s[i].feeCents) || s[i].feeCents <= 0)
      return 'Times are whole minutes and fees whole cents'
    if (i && (s[i].at < s[i - 1].at || s[i].feeCents < s[i - 1].feeCents))
      return 'The steps of a fee schedule are in time order, and no fee is lower than the one before'
  }
  return null
}

// ---------- drivers ----------
function nextLook(W: any, d: any, t: number): number {
  for (let n = 0; n < 50; n++) {
    const D = day(t)
    if (D > 9) return Infinity
    t += rexp(W, 60 / (d.days[D].works ? PRM.openWork : PRM.openOff))
    const m = tod(t)
    if (m < 390) t = day(t) * 1440 + 390 + rnd(W) * 90
    else if (m > 1350) t = (day(t) + 1) * 1440 + 390 + rnd(W) * 90
    else return t
  }
  return Infinity
}

// how driver d would do gig g: when they leave, when they collect, what it costs them. null: cannot.
function plan(W: any, d: any, g: any): any {
  const now = W.now,
    w0 = g.win[0],
    p0 = place(W, g.stops[0]),
    today = day(now)
  const h0 = W.orders[g.stops[0].orderId].legs[g.stops[0].leg].pickup.hours
  const first = Math.max(now, w0.from)
  for (let D = day(first); D <= Math.min(day(w0.to), day(first) + 3, 9); D++) {
    const dd = d.days[D]
    if (!dd.works || (D > today + 2 && !d.knows)) continue
    // today most drivers have already given their day to other work; ours (chained) are still around
    const ours = d.locDay === today || d.busy.some((x: any) => x.D === D)
    if (D === today && !ours && h(W.seed + d.id + 'td' + D) > PRM.pToday) continue
    let loc = d.home,
      free = Math.max(now, D * 1440 + dd.from),
      n = 0,
      chain = false
    if (D === today && d.locDay === today) {
      loc = d.loc
      free = Math.max(free, d.freeAt)
      chain = loc !== d.home
    }
    for (const b of d.busy)
      if (b.D === D) {
        n++
        if (b.end + 10 >= free) {
          loc = b.endPlace
          free = b.end + 10
          chain = true
        }
      }
    if (n >= dd.max) continue
    const ptTo = loc === p0 ? 10 : road(loc, p0).minutes * PRM.ptF + PRM.ptFix
    let tp = nextOpen(h0, Math.max(free + ptTo, first, D * 1440)),
      nightCost = 0
    if (tp > w0.to && D > today && n === 0) {
      tp = nextOpen(h0, Math.max(w0.from, D * 1440 + 360))
      nightCost = PRM.night
    } // travel the evening before
    if (tp > w0.to || day(tp) !== D) continue
    let end = 0,
      ok = false,
      extras = nightCost,
      fixed = false // fixed: the pickup cannot move later
    for (let pass = 0; pass < 4 && !ok; pass++) {
      let t = tp,
        shift = 0
      ok = true
      extras = nightCost
      for (let k = 1; k < g.stops.length; k++) {
        const s = g.stops[k],
          prev = g.stops[k - 1],
          l = W.orders[s.orderId].legs[s.leg],
          site = l[s.kind],
          w = g.win[k]
        t +=
          road(place(W, prev), site.placeId).minutes +
          (prev.kind === 'pickup' ? (prev.withPlates ? 30 : 0) + (prev.withCharging ? 40 : 0) : 0)
        if (t < w.from) {
          if (site.privateAddress) t = w.from
          else {
            shift = w.from - t
            ok = false
            break
          }
        }
        if (site.hours && !isOpen(site.hours, t)) {
          const o = nextOpen(site.hours, t)
          if (day(o) === day(t) && o - t < 600 && !fixed) {
            shift = o - t
            ok = false
            break
          } // leave later rather than wait
          if (s.kind === 'pickup') {
            ok = false
            break
          }
          // no start reaches the delivery site open: they go anyway and leave the car, it counts when the site opens
        }
        if (s.kind === 'delivery' && site.privateAddress) t = Math.max(t, site.window.from)
        if (t > w.to) {
          ok = false
          break
        }
        if (site.privateAddress) extras += PRM.exPrivate
      }
      if (!ok) {
        if (!shift) break
        if (tp + shift > w0.to || !isOpen(h0, tp + shift) || pass >= 2) fixed = true
        else tp += shift
      } else end = t
    }
    if (!ok) continue
    const last = place(W, g.stops[g.stops.length - 1])
    const ptHome = last === d.home ? 10 : road(last, d.home).minutes * PRM.ptF + PRM.ptFix
    if (end + ptHome > D * 1440 + 1500 && g.drive < 300) continue
    let cost =
      PRM.costFix +
      PRM.wDrive * g.drive +
      PRM.wPt * (ptTo + ptHome) +
      PRM.ticketCheap * road(loc, p0).km +
      PRM.ticketDear * road(last, d.home).km +
      PRM.wLate * Math.max(0, end + ptHome - (D * 1440 + dd.to)) +
      extras
    if (chain)
      cost -= PRM.wPt * (road(loc, d.home).minutes * PRM.ptF + PRM.ptFix) + PRM.ticketDear * road(loc, d.home).km
    for (const s of cars(g)) cost += (s.withPlates ? PRM.exPlates : 0) + (s.withCharging ? PRM.exCharge : 0)
    if (cars(g).length > 1) {
      if (g.orderIds.length === 1) cost += PRM.exTrade
      else cost *= PRM.bundleF
    }
    if (D % 7 === 5) cost *= PRM.satF
    cost *= PRM.costScale * (1 + PRM.urgent * Math.exp(-Math.max(0, w0.from - now) / PRM.urgentTau)) // a car that is ready now costs more than one for tomorrow
    cost = Math.max(300, cost * d.mult * Math.exp(PRM.epsSd * hn(W.seed + d.id + g.stops[0].orderId + D)))
    return { D, leave: Math.max(now, tp - ptTo), tp, end, endPlace: last, cost }
  }
  return null
}
const allowed = (d: any, g: any) =>
  (!g.audience.experienced || d.exp) && (!g.audience.manualLicence || d.licence === 'manual')

function view(W: any, d: any, g: any, fee: number) {
  emit(W, 'gig_viewed', { gigId: g.id, driverId: d.id })
  W.views.push([g.id, d.i, W.now, fee])
  g.viewers[d.i] ??= fee
  for (const id of g.orderIds) {
    const o = W.orders[id]
    o.firstFee ??= fee
    o.firstView ??= W.now
  }
}

// driver d looks at gig g: maybe views it, maybe books it
function consider(W: any, d: any, g: any, src: string) {
  if (g.status !== 'open' || g.expireAt <= W.now) return
  const fee = curFee(g, W.now),
    can = allowed(d, g),
    today = day(W.now)
  let pl: any
  if (src === 'app') {
    const p0 = place(W, g.stops[0]),
      near = crow(d.locDay === today ? d.loc : d.home, p0) <= PRM.nearKm || crow(d.home, p0) <= PRM.nearKm
    const on = !!d.days[today]?.works
    let pv = near ? (on ? PRM.pNear : PRM.pNearOff) : PRM.pFar
    if (!near && can && d.days[today]?.works && fee >= 0.5 * (PRM.costFix + PRM.wDrive * g.drive)) {
      pl = plan(W, d, g)
      if (pl && fee >= PRM.payView * pl.cost) pv = PRM.pPay
    }
    if (g.viewers[d.i] !== undefined) pv *= PRM.reView
    if (rnd(W) >= pv) return
  }
  view(W, d, g, fee)
  if (!can) return
  pl ??= plan(W, d, g)
  if (!pl) return
  for (const id of g.orderIds) W.orders[id].viewers[d.i] = 1
  if (fee >= pl.cost && fee > (g.minFee[d.i] ?? 0)) {
    const slack = (pl.tp - W.now) / 60,
      age = (W.now - (W.orders[g.orderIds[0]].firstView ?? W.now)) / 60
    const pw =
      Math.min(0.8, Math.max(0, (d.belief - 1) * PRM.waitK)) * Math.min(1, slack / 3) * Math.min(1.5, 0.6 + age / 4)
    if (src !== 'wait' && d.days[today]?.works && rnd(W) < pw)
      push(W, { t: W.now + 30 + rnd(W) * 60, k: 'look', d: d.i, g: g.id, src: 'wait' })
    else book(W, d, g, fee, pl)
  } else if (d.days[today]?.works && fee * Math.max(d.belief, 1.1) >= pl.cost && (g.looks[d.i] ?? 0) < 3) {
    g.looks[d.i] = (g.looks[d.i] ?? 0) + 1
    push(W, { t: W.now + 40 + rnd(W) * 60, k: 'look', d: d.i, g: g.id, src: 'again' })
  }
}

function book(W: any, d: any, g: any, fee: number, pl: any) {
  g.status = 'booked'
  g.feeCents = fee
  g.driverId = d.id
  g.drv = d.i
  g.plan = pl
  g.ver++
  g.lateFree = false
  W.open = W.open.filter((x: string) => x !== g.id)
  d.busy.push({ g: g.id, D: pl.D, start: pl.leave, end: pl.end, endPlace: pl.endPlace })
  emit(W, 'gig_booked', { gigId: g.id, driverId: d.id, feeCents: fee })
  for (const id of g.orderIds) {
    const o = W.orders[id]
    if (o.status === 'waiting') o.status = 'booked'
    const ratio = fee / (o.firstFee ?? fee)
    for (const i in o.viewers) {
      const v = W.drivers[i]
      v.belief = (1 - PRM.beliefMix) * v.belief + PRM.beliefMix * ratio
    }
  }
  push(W, { t: pl.leave, k: 'start', g: g.id, v: g.ver })
  // drops: something comes up (more likely the longer the booking is held), or the fee only just paid
  const hold = (pl.leave - W.now) / 60
  const H = (x: number) =>
    PRM.dropScale *
    (0.004 * Math.min(x, 1) +
      0.013 * Math.min(Math.max(x - 1, 0), 3) +
      0.0085 * Math.min(Math.max(x - 4, 0), 8) +
      PRM.dropLong * Math.max(x - 12, 0))
  if (rnd(W) < 1 - Math.exp(-H(hold))) {
    const u = rnd(W) * H(hold)
    let lo = 0,
      hi = hold
    for (let i = 0; i < 20; i++) {
      const m = (lo + hi) / 2
      if (H(m) < u) lo = m
      else hi = m
    }
    push(W, { t: W.now + lo * 60, k: 'drop', g: g.id, v: g.ver })
  } else if ((fee - pl.cost) / fee < 0.05 && hold > 0.3 && rnd(W) < PRM.thinDrop)
    push(W, { t: W.now + 10 + rnd(W) * Math.min(50, hold * 60 - 10), k: 'drop', g: g.id, v: g.ver })
}

function driveTime(W: any, a: string, b: string): number {
  const P = packFor(W.pack)
  let f = Math.exp(PRM.driveSd * rn(W))
  if (rnd(W) < PRM.slowP) f *= 1.15 + rnd(W) * 0.35
  if (snowAt(P, a, W.now) || snowAt(P, b, W.now)) f *= PRM.snowF
  return Math.max(1, Math.round(road(a, b).minutes * f))
}
function nextStop(W: any, g: any, k: number, from: string, extra: number) {
  for (let j = k + 1; j < g.stops.length; j++)
    if (!g.stops[j].skip)
      return push(W, { t: W.now + extra + driveTime(W, from, place(W, g.stops[j])), k: 'stop', g: g.id, i: j })
  const d = W.drivers[g.drv]
  g.status = 'done'
  if (g.failed < 1) ledger(W, 'driver_fee', -g.feeCents * (1 - g.failed), g.orderIds[0], g.id, 'Driver fee')
  d.completed++
  d.freeAt = W.now + extra
  d.loc = from
  d.locDay = day(W.now)
  unbusy(W, g)
}
function atStop(W: any, g: any, k: number) {
  const s = g.stops[k],
    o = W.orders[s.orderId],
    l = o.legs[s.leg],
    d = W.drivers[g.drv],
    t = W.now,
    here = l[s.kind].placeId
  if (o.status === 'cancelled') return nextStop(W, g, k, here, 0)
  if (s.kind === 'pickup') {
    const tr = o.truth[s.leg],
      P = packFor(W.pack)
    if (t < g.win[k].from && !l.pickup.privateAddress) return push(W, { t: g.win[k].from, k: 'stop', g: g.id, i: k })
    let why = ''
    if (t < Math.max(tr.readyAt, tr.releasedAt ?? 0)) why = 'not_ready'
    else if (tr.summerTyres && (snowAt(P, l.pickup.placeId, t) || snowAt(P, l.delivery.placeId, t))) why = 'not_ready'
    else if (
      l.pickup.privateAddress
        ? (t < l.pickup.window.from || t > l.pickup.window.to) && g.win[k].from !== 0
        : !isOpen(tr.pickupHours, t)
    )
      why = 'closed'
    else if (tr.manualGearbox && d.licence !== 'manual') why = 'licence'
    else if (tr.needsPlates && !s.withPlates) why = 'no_plates'
    if (why) {
      const sh = shareOf(W, g, s)
      g.failed += sh
      for (const x of g.stops) if (x.orderId === s.orderId && x.leg === s.leg) x.skip = true
      emit(W, 'visit_failed', { gigId: g.id, orderId: o.id, leg: s.leg, reason: why })
      ledger(
        W,
        'failed_visit',
        -Math.max(2500, 0.5 * sh * g.feeCents),
        o.id,
        g.id,
        `Failed visit at the pickup of ${o.id} leg ${s.leg} in ${PLACE[here].name}: ${why}`,
      )
      o.gigOf[s.leg] = null
      if (!hasDriver(W, o)) {
        o.status = 'waiting'
        armWarn(W, o)
      }
      return nextStop(W, g, k, here, 0)
    }
    o.picked[s.leg] = true
    emit(W, 'picked_up', { gigId: g.id, orderId: o.id, leg: s.leg, placeId: here })
    let extra = (s.withPlates ? 30 : 0) + (s.withCharging ? 40 : 0)
    if (needsCharge(l) && !s.withCharging) {
      extra += 90
      ledger(
        W,
        'fine',
        -10000,
        o.id,
        g.id,
        `An electric car below 30% on a route over 200 km needs a charging stop: ${o.id} leg ${s.leg}`,
      )
    }
    return nextStop(W, g, k, here, extra)
  }
  // delivery
  const tr = o.truth[s.leg]
  let leave = t,
    counts = t
  if (l.delivery.privateAddress) counts = leave = Math.max(t, l.delivery.window.from)
  else if (!isOpen(l.delivery.hours, t)) counts = nextOpen(tr.deliveryHours, t)
  else if (!isOpen(tr.deliveryHours, t)) {
    const op = nextOpen(tr.deliveryHours, t),
      wait = Math.min(120, op - t)
    ledger(
      W,
      'waiting',
      (-1500 * wait) / 60,
      o.id,
      g.id,
      `Waited ${wait} minutes at the delivery of ${o.id} leg ${s.leg} in ${PLACE[here].name}: the site was closed at a time its stated hours show open`,
    )
    leave = t + wait
    counts = op <= t + 120 ? op : nextOpen(tr.deliveryHours, leave)
  }
  if (counts <= t) delivered(W, o, s.leg, g.id, d)
  else push(W, { t: Math.min(counts, W.endsAt + 1), k: 'delivered', o: o.id, leg: s.leg, g: g.id, d: d.i })
  nextStop(W, g, k, here, leave - t)
}

function releaseFee(W: any, g: any, why: string) {
  const mins = g.plan.tp - W.now,
    share = g.lateFree ? 0 : mins > 1440 ? 0.25 : mins >= 120 ? 0.5 : 1
  if (share)
    ledger(
      W,
      'release_fee',
      -g.feeCents * share,
      g.orderIds[0],
      g.id,
      `${why}Driver released, ${share * 100}% of the fee`,
    )
  unbusy(W, g)
  g.status = 'withdrawn'
  g.ver++
  freeLegs(W, g)
}

// ---------- the event loop ----------
function handle(W: any, it: any) {
  const P = packFor(W.pack)
  switch (it.k) {
    case 'req': {
      const r = P.requests[it.i]
      emit(W, 'price_request', { ri: it.i })
      push(W, { t: r.respondBy, k: 'decide', i: it.i })
      break
    }
    case 'decide':
      decide(W, P.requests[it.i])
      break
    case 'forecast': {
      const { seq, at, kind, ...f } = P.forecasts[it.i]
      emit(W, 'forecast', f)
      break
    }
    case 'release':
      if (live(W.orders[it.o])) emit(W, 'release', { orderId: it.o, leg: it.leg })
      break
    case 'morning':
      morning(W)
      break
    case 'open': {
      const d = W.drivers[it.d]
      for (const id of [...W.open]) consider(W, d, W.gigs[id], 'app')
      const t = nextLook(W, d, W.now)
      if (t < W.endsAt) push(W, { t, k: 'open', d: it.d })
      break
    }
    case 'look': {
      const g = W.gigs[it.g]
      if (g) consider(W, W.drivers[it.d], g, it.src)
      break
    }
    case 'expire': {
      const g = W.gigs[it.g]
      if (g.status === 'open' && g.expireAt <= W.now) {
        g.status = 'withdrawn'
        freeLegs(W, g)
        emit(W, 'gig_expired', { gigId: g.id })
      }
      break
    }
    case 'warn': {
      const o = W.orders[it.o]
      if (it.v === o.warnV && live(o) && !hasDriver(W, o))
        emit(W, 'deadline_close', { orderId: o.id, lastPickupAt: o.lastPickupAt })
      break
    }
    case 'drop': {
      const g = W.gigs[it.g]
      if (g.ver !== it.v || g.status !== 'booked') break
      const d = W.drivers[g.drv]
      d.drops++
      unbusy(W, g)
      g.minFee[d.i] = Math.round(g.feeCents * 1.05)
      emit(W, 'gig_dropped', { gigId: g.id, driverId: d.id })
      reopen(W, g)
      break
    }
    case 'start': {
      const g = W.gigs[it.g]
      if (g.ver !== it.v || g.status !== 'booked') break
      const d = W.drivers[g.drv]
      const busyTill = Math.max(
        d.freeAt,
        ...d.busy
          .filter((b: any) => b.g !== g.id && b.start < g.plan.leave && W.gigs[b.g].status === 'working')
          .map((b: any) => b.end),
      )
      if (busyTill > W.now) {
        // an earlier gig runs late
        const tp = g.plan.tp + (busyTill - W.now),
          l = W.orders[g.stops[0].orderId].legs[g.stops[0].leg]
        if (tp > g.win[0].to && !g.lateFree) {
          if (!l.pickup.privateAddress && isOpen(l.pickup.hours, tp)) {
            g.lateFree = true
            emit(W, 'driver_late', { gigId: g.id, driverId: d.id, pickupAt: tp })
          } else {
            unbusy(W, g)
            emit(W, 'no_show', { gigId: g.id, driverId: d.id })
            reopen(W, g)
            break
          }
        }
        g.plan.tp = tp
        g.plan.leave = busyTill
        push(W, { t: busyTill, k: 'start', g: g.id, v: g.ver })
        break
      }
      g.status = 'working'
      for (const id of g.orderIds) if (live(W.orders[id])) W.orders[id].status = 'working'
      emit(W, 'gig_started', { gigId: g.id, driverId: d.id })
      push(W, { t: Math.max(g.plan.tp, W.now), k: 'stop', g: g.id, i: 0 })
      break
    }
    case 'stop':
      atStop(W, W.gigs[it.g], it.i)
      break
    case 'delivered':
      delivered(W, W.orders[it.o], it.leg, it.g, W.drivers[it.d])
      break
    case 'offer': {
      const g = W.gigs[it.g],
        d = W.drivers[it.d]
      if (g.status !== 'open' || !allowed(d, g)) break
      view(W, d, g, it.fee)
      const pl = plan(W, d, g)
      if (pl && it.fee >= pl.cost && it.fee > (g.minFee[d.i] ?? 0)) {
        g.offers = g.offers.filter((x: any) => x.id !== it.id)
        emit(W, 'offer_answered', { gigId: g.id, driverId: d.id, answer: 'accepted' })
        book(W, d, g, it.fee, pl)
        it.done = true
      }
      break
    }
    case 'offerEnd': {
      const g = W.gigs[it.g],
        off = g.offers.find((x: any) => x.id === it.id)
      if (!off) break
      g.offers = g.offers.filter((x: any) => x.id !== it.id)
      emit(W, 'offer_answered', {
        gigId: g.id,
        driverId: W.drivers[it.d].id,
        answer: it.read && g.status === 'open' ? 'declined' : 'expired',
      })
      break
    }
    case 'slot': {
      // a private seller's slot ended with the car still there
      const o = W.orders[it.o],
        l = o?.legs[it.leg]
      if (!live(o) || o.picked[it.leg]) break
      const g = o.gigOf[it.leg] && W.gigs[o.gigOf[it.leg]]
      if (g && g.status === 'working') break
      const shift = (nextBiz(day(l.pickup.window.from)) - day(l.pickup.window.from)) * 1440
      l.pickup.window = { from: l.pickup.window.from + shift, to: l.pickup.window.to + shift }
      o.lastPickupAt = lastPickup(W, o)
      emit(W, 'order_changed', {
        order: pubOrder(o),
        message: {
          text: "The car was not collected in the seller's slot. The dealer booked the same hours on the next business day.",
          language: 'en',
        },
      })
      armWarn(W, o)
      push(W, { t: l.pickup.window.to + 1, k: 'slot', o: o.id, leg: it.leg })
      break
    }
    case 'change': {
      const o = W.orders[it.o]
      if (!live(o)) break
      let any = false
      o.legs.forEach((l: any, i: number) => {
        if (o.deliveredAt[i] === null && it.places[i] && l.delivery.placeId !== it.places[i][1]) {
          l.delivery.placeId = it.places[i][1]
          any = true
        }
      })
      if (!any) break
      o.lastPickupAt = lastPickup(W, o)
      emit(W, 'order_changed', { order: pubOrder(o), message: it.message })
      break
    }
    case 'cancel': {
      const o = W.orders[it.o]
      if (!live(o)) break
      o.status = 'cancelled'
      const out: any[] = []
      for (const id of new Set(o.gigOf.filter(Boolean)) as Set<string>) {
        const g = W.gigs[id]
        if (g.status === 'open') {
          g.status = 'withdrawn'
          freeLegs(W, g)
          out.push({ gigId: id, outcome: 'withdrawn' })
        } else if (g.status === 'booked' && g.orderIds.length === 1) {
          releaseFee(W, g, 'The dealer cancelled the order. ')
          out.push({ gigId: id, outcome: 'released' })
        } else if (g.status === 'booked') {
          g.stops = g.stops.filter((s: any) => s.orderId !== o.id)
          g.orderIds = g.orderIds.filter((x: string) => x !== o.id)
          windows(W, g)
          out.push({ gigId: id, outcome: 'shortened' })
        } else if (g.status === 'working') out.push({ gigId: id, outcome: 'continues' })
      }
      emit(W, 'order_cancelled', { orderId: o.id, gigs: out })
      break
    }
  }
}

// each morning the competitor answers what we won from each dealer
function morning(W: any) {
  for (const D of Object.values(W.dealers) as any[]) {
    if (D.n >= 3) {
      const s = D.won / D.n
      if (s > PRM.compHi) D.comp = Math.min(PRM.compMax, D.comp + 1)
      else if (s < PRM.compLo) D.comp = Math.max(-PRM.compMax, D.comp - 1)
    }
    D.won *= 0.5
    D.n *= 0.5
  }
}

function run(W: any, target: number, kinds?: Set<string>) {
  target = Math.min(target, W.endsAt)
  for (;;) {
    const top = W.q[0]
    if (!top || top.t > target) {
      W.now = Math.max(W.now, target)
      break
    }
    W.now = top.t
    const mark = W.events.length
    while (W.q.length && W.q[0].t === W.now) handle(W, pop(W))
    if (kinds) {
      let hit = false
      for (let i = mark; i < W.events.length; i++)
        if (kinds.has(W.events[i].kind)) {
          hit = true
          break
        }
      if (hit) break
    }
  }
  if (W.now >= W.endsAt && !W.ended) {
    W.ended = true
    for (const o of Object.values(W.orders) as any[])
      if (live(o)) ledger(W, 'undelivered_penalty', -2 * o.priceCents, o.id, null, 'Not delivered when the world ended')
  }
}

// ---------- the API ----------
export const requestOf = (W: any, id: string) => packFor(W.pack).requests.find((r: any) => r.id === id)
export function act(W: any, actions: any[]): any[] {
  return actions.map((a) => {
    const no = (reason: string) => ({ ok: false, reason })
    if (W.ended) return no('The world has ended')
    const P = packFor(W.pack)
    if (a.type === 'quote') {
      const r =
        P.byId?.[a.requestId] ?? (P.byId = Object.fromEntries(P.requests.map((x: any) => [x.id, x])))[a.requestId]
      if (!r || r.arrivedAt > W.now) return no(`No request ${a.requestId}`)
      if (W.now >= r.respondBy) return no(`The response deadline of ${a.requestId} has passed`)
      const prices: any = {}
      for (const [k, v] of Object.entries(a.prices ?? {})) {
        if (!r.options.some((o: any) => o.kind === k)) return no(`${a.requestId} has no option ${k}`)
        prices[k] = v
      }
      if (!Object.keys(prices).length) return no('A quote needs at least one price')
      W.quotes[r.id] = prices
      return { ok: true, id: r.id }
    }
    if (a.type === 'post') {
      const g = doPost(W, a)
      if (typeof g === 'string' && process.env.SIM_DEBUG) console.error(W.now, 'post refused:', g)
      return typeof g === 'string' ? no(g) : { ok: true, id: g.id }
    }
    const g = W.gigs[a.gigId]
    if (!g) return no(`No gig ${a.gigId}`)
    if (a.type === 'reprice') {
      if (g.status !== 'open') return no(`Gig ${g.id} is ${g.status}: only an open gig can be repriced`)
      const bad = schedErr(a.schedule)
      if (bad) return no(bad)
      g.schedule = a.schedule
      return { ok: true, id: g.id }
    }
    if (a.type === 'withdraw') {
      if (g.status !== 'open') return no(`Gig ${g.id} is ${g.status}: only an open gig can be withdrawn`)
      g.status = 'withdrawn'
      freeLegs(W, g)
      return { ok: true, id: g.id }
    }
    if (a.type === 'release') {
      if (g.status !== 'booked')
        return no(
          g.status === 'working' || g.status === 'done'
            ? `Gig ${g.id} has started: a driver can be released only before they leave`
            : `Gig ${g.id} has no driver`,
        )
      releaseFee(W, g, '')
      return { ok: true, id: g.id }
    }
    if (a.type === 'offer') {
      const d = W.drivers.find((x: any) => x.id === a.driverId)
      if (!d) return no(`No driver ${a.driverId}`)
      if (g.status !== 'open') return no(`Gig ${g.id} is ${g.status}: only an open gig can be offered`)
      if (d.offers[0] !== day(W.now)) d.offers = [day(W.now), 0]
      if (d.offers[1] >= 3) return no(`Driver ${d.id} already has three direct offers today`)
      if (g.offers.length >= 3) return no(`Gig ${g.id} already has three open direct offers`)
      d.offers[1]++
      const id = 'o' + ++W.offerN,
        dd = d.days[day(W.now)],
        m = tod(W.now)
      g.offers.push({ id, d: d.i })
      let pr = m >= 1380 || m < 420 ? 0 : !dd.works ? 0.12 : m >= dd.from && m <= dd.to ? 0.85 : 0.45
      if (!d.notif) pr *= 0.3
      const read = rnd(W) < pr
      if (read) push(W, { t: W.now + 1 + rnd(W) * 7, k: 'offer', g: g.id, d: d.i, fee: a.feeCents, id })
      push(W, { t: W.now + 10, k: 'offerEnd', g: g.id, d: d.i, id, read })
      return { ok: true, id }
    }
    return no(`Unknown action ${a.type}`)
  })
}

const outEvent = (W: any, e: any) =>
  e.kind === 'price_request' ? { seq: e.seq, at: e.at, kind: e.kind, request: packFor(W.pack).requests[e.ri] } : e
export function advance(W: any, body: any) {
  const results = body.actions?.length ? act(W, body.actions) : undefined
  if (body.untilEvent) run(W, body.max ?? W.endsAt, new Set(body.untilEvent))
  else run(W, body.to ?? W.now + (body.by ?? 0))
  const events = W.events.slice(W.cursor).map((e: any) => outEvent(W, e))
  W.cursor = W.events.length
  return { ...(results ? { results } : {}), now: W.now, events }
}
export const events = (W: any, after = -1, limit?: number) =>
  W.events.slice(after + 1, limit ? after + 1 + limit : undefined).map((e: any) => outEvent(W, e))
export function score(W: any) {
  const os = (Object.values(W.orders) as any[]).filter((o) => o.status !== 'cancelled')
  const won = os.length,
    onTime = os.filter((o) => o.onTime).length,
    undel = W.ended ? os.filter((o) => o.status !== 'delivered').length : 0
  return {
    marginCents: W.margin,
    revenueCents: W.revenue,
    marginShare: W.revenue ? W.margin / W.revenue : 0,
    wonOrders: won,
    onTimeShare: won ? onTime / won : 1,
    undeliveredShare: won ? undel / won : 0,
    ranked: won > 0 && onTime / won >= 0.9,
  }
}
export function snapshot(W: any) {
  const P = packFor(W.pack)
  return {
    worldId: W.worldId,
    now: W.now,
    endsAt: W.endsAt,
    openRequests: P.requests.filter((r: any) => r.arrivedAt <= W.now && r.respondBy > W.now),
    orders: Object.values(W.orders).map(pubOrder),
    gigs: Object.values(W.gigs).map(pubGig),
    driverPositions: (Object.values(W.gigs) as any[])
      .filter((g) => g.status === 'working')
      .map((g) => ({ driverId: g.driverId, gigId: g.id })),
    score: score(W),
  }
}
export const roster = (W: any) =>
  W.drivers.map((d: any) => ({
    id: d.id,
    homePlaceId: d.home,
    rating: d.rating,
    licence: d.licence,
    completedGigs: d.completed,
    drops: d.drops,
  }))
export function reveal(W: any) {
  const P = packFor(W.pack)
  return {
    requests: P.requests
      .filter((r: any) => r.arrivedAt <= W.now)
      .map((r: any) => ({
        request: r,
        quote: W.quotes[r.id] ?? null,
        ...(W.outcome[r.id] ?? { outcome: 'unquoted', option: null }),
      })),
    orders: (Object.values(W.orders) as any[]).map((o) => ({
      orderId: o.id,
      legs: o.truth.map((t: any, i: number) => ({ ...t, pickedUpAt: null, deliveredAt: o.deliveredAt[i] })),
    })),
    views: W.views.map(([gigId, i, at, feeCents]: any) => ({ gigId, driverId: W.drivers[i].id, at, feeCents })),
  }
}

// the pieces the oracle and other tools build on
export const internals = {
  thresholds,
  makeOrder,
  cancelAt,
  windows,
  plan,
  allowed,
  cars,
  place,
  needsCharge,
  nextOpen,
  isOpen,
  crow,
  road,
  dealer,
  morning,
  day,
  tod,
  lastPickup,
  legDeadline,
}
