// Spread prober: plays practice worlds with a small randomised desk and measures the hidden
// values by forking. Written against https://spread.bahnexpress.com/openapi.json only.
//
//   pnpm prober --mode fee    --seeds p1,p2      min fee that books each won order
//   pnpm prober --mode quote  --seeds p1,p2      max price a dealer accepts, per option
//   pnpm prober --mode branch --seeds p1 --at 1920,3360   policy variants from a minute to the end
//   pnpm prober --mode play   --seeds p1         just play and record
//
// Against the Spread server this is an online run: only on the user's explicit request.
// Against the simulator: SPREAD_URL=http://localhost:8787 SPREAD_KEY=sim node sim/prober.ts ...
//
// Keys: SPREAD_KEY1, SPREAD_KEY2, ... (or SPREAD_KEY) from the environment / .env. Server: SPREAD_URL.
// Each key runs one parent world and up to 7 forks at a time.

import { appendFileSync, mkdirSync, writeFileSync } from 'node:fs'
import { gzipSync } from 'node:zlib'

const BASE = process.env.SPREAD_URL ?? 'https://spread.bahnexpress.com'
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

// ---------- options ----------
const argv = process.argv.slice(2)
const opt = (name: string, dflt?: string) => {
  const i = argv.indexOf('--' + name)
  return i >= 0 ? (argv[i + 1] ?? 'true') : dflt
}
const num = (name: string, dflt: number) => Number(opt(name, String(dflt)))
const MODE = opt('mode', 'play')!
const LEVEL = num('level', 8)
const SEEDS = (opt('seeds', 'probe-1') as string).split(',')
const OUT = opt('out', 'probe2')!
const SHARE = num('share', 1) // share of targets that get probed
const WINDOW = num('window', 180) // minutes a fee probe waits for a booking
const AT = (opt('at', '') as string).split(',').filter(Boolean).map(Number)
const KEYS = Object.entries(process.env)
  .filter(([k, v]) => /^SPREAD_KEY\d*$/.test(k) && v)
  .sort(([a], [b]) => a.localeCompare(b))
  .map(([, v]) => v as string)

type Params = {
  qLo: number
  qHi: number // quote = list price x U(qLo, qHi), drawn per request
  qScale: number // extra factor on every quote
  townScale: Record<string, number> // extra factor by pickup place
  dealerSplit: boolean // dealers in three groups: x0.85, x1, x1.2 (competitor reaction study)
  fOpen: number
  fStep: number
  fCap: number // fee schedule in typical fees: open, +step an hour, cap
}
const BASEP: Params = {
  qLo: num('qLo', 1.0),
  qHi: num('qHi', 1.7),
  qScale: num('qScale', 1),
  townScale: {},
  dealerSplit: opt('dealerSplit') === 'true',
  fOpen: num('fOpen', 0.9),
  fStep: num('fStep', 0.1),
  fCap: num('fCap', 1.6),
}

// ---------- API ----------
class Api {
  requests = 0
  readonly key: string
  readonly name: string
  constructor(key: string, name: string) {
    this.key = key
    this.name = name
  }
  async req(method: string, path: string, body?: unknown): Promise<any> {
    for (let i = 0; ; i++) {
      let res: Response
      try {
        res = await fetch(BASE + path, {
          method,
          headers: {
            authorization: `Bearer ${this.key}`,
            ...(body !== undefined ? { 'content-type': 'application/json' } : {}),
          },
          body: body !== undefined ? JSON.stringify(body) : undefined,
          signal: AbortSignal.timeout(120_000),
        })
      } catch (e) {
        if (i >= 6) throw e
        await sleep(500 * (i + 1))
        continue
      }
      this.requests++
      const busy = res.status === 409 && (path.endsWith('/fork') || path === '/v1/worlds') // 8 worlds: wait for a slot
      if (res.status === 429 || res.status >= 502 || busy) {
        if (i >= 40) throw new Error(`${method} ${path} ${res.status} after ${i} tries`)
        const wait = Number(res.headers.get('retry-after') ?? res.headers.get('ratelimit-reset') ?? 0)
        await res.text()
        await sleep(Math.max(busy ? 300 : 50, Math.min(wait, 5000)))
        continue
      }
      if (res.status === 204) return null
      const text = await res.text()
      if (!res.ok) throw new Error(`${method} ${path} ${res.status} ${text.slice(0, 300)}`)
      return JSON.parse(text)
    }
  }
}

class Slots {
  private waiting: (() => void)[] = []
  private free: number
  constructor(free: number) {
    this.free = free
  }
  async take() {
    if (this.free > 0) return void this.free--
    await new Promise<void>((r) => this.waiting.push(r))
  }
  give() {
    const next = this.waiting.shift()
    if (next) next()
    else this.free++
  }
}

// ---------- map ----------
const ROAD: Record<string, { km: number; minutes: number }> = {}
const road = (a: string, b: string) => ROAD[a + '>' + b] ?? { km: 0, minutes: 0 }

// deterministic uniform [0,1) from a string
function h(s: string): number {
  let x = 2166136261
  for (let i = 0; i < s.length; i++) x = Math.imul(x ^ s.charCodeAt(i), 16777619)
  x ^= x >>> 13
  x = Math.imul(x, 0x5bd1e995)
  x ^= x >>> 15
  return (x >>> 0) / 4294967296
}

// ---------- the desk: a small randomised dispatcher, plain data so a fork can clone it ----------
type Car = { orderId: string; leg: number }
type Pending = { a: any; hold?: string; cars?: Car[]; retry?: any }
type Desk = {
  p: Params
  seed: string
  now: number
  reqs: Record<string, { dealer: string; ref: number; note: string; pickup: string; mult: number }>
  orders: Record<
    string,
    {
      o: any
      ref: number
      note: string
      cancelled: boolean
      done: boolean[]
      manual: boolean
      plates: boolean
      delay: number
    }
  >
  gigs: Record<string, { cars: Car[]; status: 'open' | 'booked' | 'gone' }>
  dealers: Record<string, { won: number; lost: number; onTime: number; late: number }>
  pending: Pending[]
  refused: number
}
const newDesk = (p: Params, seed: string): Desk => ({
  p,
  seed,
  now: 0,
  reqs: {},
  orders: {},
  gigs: {},
  dealers: {},
  pending: [],
  refused: 0,
})
const dealer = (d: Desk, id: string) => (d.dealers[id] ??= { won: 0, lost: 0, onTime: 0, late: 0 })

function quoteMult(d: Desk, req: any): number {
  const p = d.p
  let m =
    (p.qLo + (p.qHi - p.qLo) * h(d.seed + req.id + 'q')) * p.qScale * (p.townScale[req.legs[0].pickup.placeId] ?? 1)
  if (p.dealerSplit) m *= [0.85, 1, 1.2][Math.floor(h(d.seed + req.dealerId + 'g') * 3)]
  return m
}

function schedule(d: Desk, ref: number, urgent: boolean) {
  const { fOpen, fStep, fCap } = d.p
  const steps: { at: number; feeCents: number }[] = []
  if (urgent)
    for (let k = 0; k <= 4; k++) steps.push({ at: d.now + 30 * k, feeCents: Math.round(ref * (1.5 + 0.25 * k)) })
  else
    for (let k = 0, f = fOpen; k < 48 && f <= fCap + 1e-9; k++, f += fStep)
      steps.push({ at: d.now + 60 * k, feeCents: Math.round(ref * f) })
  return steps
}

// share of the order's typical fee that belongs to these cars
function refOf(d: Desk, cars: Car[]): number {
  let sum = 0
  for (const c of cars) {
    const r = d.orders[c.orderId]
    const mins = r.o.legs.map((l: any) => road(l.pickup.placeId, l.delivery.placeId).minutes + 20)
    sum += (r.ref * mins[c.leg]) / mins.reduce((a: number, b: number) => a + b, 0)
  }
  return Math.max(500, sum)
}

function postAction(d: Desk, cars: Car[], urgent: boolean, flat?: number) {
  const stops: any[] = []
  let experienced = false,
    manualLicence = false
  for (const c of cars) {
    const r = d.orders[c.orderId],
      leg = r.o.legs[c.leg]
    const far = road(leg.pickup.placeId, leg.delivery.placeId).km > 200
    const pickup: any = {
      orderId: c.orderId,
      leg: c.leg,
      kind: 'pickup',
      withPlates: r.plates || /plates|kilvet|kilpi|kilvi|skylt/i.test(r.note),
      withCharging: !!leg.car.electric && (leg.car.chargePercent ?? 100) < 30 && far,
    }
    if (r.delay > d.now && !leg.pickup.privateAddress)
      pickup.window = { from: r.delay, to: Math.max(r.delay + 600, leg.pickup.window.to) }
    stops.push(pickup, { orderId: c.orderId, leg: c.leg, kind: 'delivery' })
    experienced ||= !!leg.car.premium
    manualLicence ||= r.manual || /manua|manuell/i.test(r.note)
  }
  const ref = refOf(d, cars)
  return {
    type: 'post',
    stops,
    audience: { experienced, manualLicence },
    schedule: flat ? [{ at: d.now, feeCents: flat }] : schedule(d, ref, urgent),
  }
}

// one gig per order, unless a trade-in plans more than 12 hours of driving
function gigsOf(o: any): Car[][] {
  const cars = o.legs.map((_: any, i: number) => ({ orderId: o.id, leg: i }))
  if (cars.length < 2) return [cars]
  const [a, b] = o.legs
  const mins =
    road(a.pickup.placeId, a.delivery.placeId).minutes +
    road(a.delivery.placeId, b.pickup.placeId).minutes +
    road(b.pickup.placeId, b.delivery.placeId).minutes
  return mins <= 700 ? [cars] : [[cars[0]], [cars[1]]]
}

const alive = (d: Desk, c: Car) =>
  d.orders[c.orderId] && !d.orders[c.orderId].cancelled && !d.orders[c.orderId].done[c.leg]
function repost(d: Desk, cars: Car[], urgent: boolean) {
  cars = cars.filter((c) => alive(d, c))
  if (cars.length) d.pending.push({ a: postAction(d, cars, urgent), cars })
}

function onEvent(d: Desk, e: any, hold: (e: any) => boolean) {
  d.now = Math.max(d.now, e.at)
  switch (e.kind) {
    case 'price_request': {
      const q = e.request,
        mult = quoteMult(d, q)
      d.reqs[q.id] = {
        dealer: q.dealerId,
        ref: q.referenceFeeCents,
        note: q.note?.text ?? '',
        pickup: q.legs[0].pickup.placeId,
        mult,
      }
      const prices: Record<string, number> = {}
      for (const o of q.options) prices[o.kind] = Math.round(o.listPriceCents * mult)
      d.pending.push({ a: { type: 'quote', requestId: q.id, prices }, hold: hold(e) ? q.id : undefined })
      break
    }
    case 'order_lost':
      if (d.reqs[e.requestId]) dealer(d, d.reqs[e.requestId].dealer).lost++
      break
    case 'order_won': {
      const o = e.order,
        q = d.reqs[o.id]
      d.orders[o.id] = {
        o,
        ref: q?.ref ?? 5000,
        note: q?.note ?? '',
        cancelled: false,
        done: o.legs.map(() => false),
        manual: false,
        plates: false,
        delay: 0,
      }
      dealer(d, o.dealerId).won++
      const held = hold(e) ? o.id : undefined
      for (const cars of gigsOf(o)) d.pending.push({ a: postAction(d, cars, false), cars, hold: held })
      break
    }
    case 'order_changed':
      if (d.orders[e.order.id]) d.orders[e.order.id].o = e.order
      break
    case 'order_cancelled': {
      const r = d.orders[e.orderId]
      if (r) r.cancelled = true
      for (const g of e.gigs ?? [])
        if (g.outcome === 'withdrawn' && d.gigs[g.gigId]) {
          d.gigs[g.gigId].status = 'gone'
          repost(d, d.gigs[g.gigId].cars, false)
        }
      break
    }
    case 'gig_booked':
      if (d.gigs[e.gigId]) d.gigs[e.gigId].status = 'booked'
      break
    case 'gig_dropped':
    case 'no_show':
      if (d.gigs[e.gigId]) d.gigs[e.gigId].status = 'open'
      break
    case 'gig_expired':
      if (d.gigs[e.gigId]) {
        d.gigs[e.gigId].status = 'gone'
        repost(d, d.gigs[e.gigId].cars, true)
      }
      break
    case 'visit_failed': {
      const r = d.orders[e.orderId]
      if (!r) break
      if (e.reason === 'licence') r.manual = true
      else if (e.reason === 'no_plates') r.plates = true
      else r.delay = d.now + 240 // not ready or closed: try again later
      repost(d, [{ orderId: e.orderId, leg: e.leg }], false)
      break
    }
    case 'delivered': {
      const r = d.orders[e.orderId]
      if (!r) break
      r.done[e.leg] = true
      if (r.done.every(Boolean)) {
        const s = dealer(d, r.o.dealerId)
        if (e.at <= r.o.deadline) s.onTime++
        else {
          s.late++
          s.onTime = Math.floor(s.onTime / 2)
        }
      }
      break
    }
    case 'deadline_close': {
      let any = false
      for (const [id, g] of Object.entries(d.gigs))
        if (g.status === 'open' && g.cars.some((c) => c.orderId === e.orderId)) {
          any = true
          d.pending.push({ a: { type: 'reprice', gigId: id, schedule: schedule(d, refOf(d, g.cars), true) } })
        }
      const r = d.orders[e.orderId]
      // a post that has not gone out yet (a win and its warning in the same minute): make it urgent
      for (const x of d.pending)
        if (x.a.type === 'post' && x.cars?.some((c) => c.orderId === e.orderId)) {
          any = true
          x.a.schedule = schedule(d, refOf(d, x.cars), true)
        }
      const posted = Object.values(d.gigs).some(
        (g) => g.status !== 'gone' && g.cars.some((c) => c.orderId === e.orderId),
      )
      if (!any && !posted && r)
        repost(
          d,
          r.o.legs.map((_: any, i: number) => ({ orderId: e.orderId, leg: i })),
          true,
        )
      break
    }
  }
}

function onResults(d: Desk, sent: Pending[], results: any[] | undefined) {
  sent.forEach((s, i) => {
    const r = results?.[i]
    if (!r) return
    if (r.ok && s.a.type === 'post' && s.cars) d.gigs[r.id] = { cars: s.cars, status: 'open' }
    if (!r.ok && s.a.type === 'post' && s.cars) {
      d.refused++
      if (s.a.stops.some((x: any) => x.window) && !s.retry) {
        // our own window was refused: post without it
        for (const c of s.cars) if (d.orders[c.orderId]) d.orders[c.orderId].delay = 0
        d.pending.push({
          a: postAction(
            d,
            s.cars.filter((c) => alive(d, c)),
            false,
          ),
          cars: s.cars,
          retry: true,
        })
      }
    }
  })
}

// ---------- playing a world ----------
const STOP = ['price_request', 'order_won', 'order_cancelled', 'gig_expired', 'visit_failed', 'deadline_close']
type Run = { api: Api; wid: string; desk: Desk; lastSeq: number; endsAt: number; events?: any[] }

async function flush(run: Run, except?: string) {
  for (;;) {
    const send = run.desk.pending.filter((x) => !x.hold || x.hold !== except).slice(0, 50)
    if (!send.length) return
    run.desk.pending = run.desk.pending.filter((x) => !send.includes(x))
    const res = await run.api.req(
      'POST',
      `/v1/worlds/${run.wid}/actions`,
      send.map((x) => x.a),
    )
    onResults(run.desk, send, res)
  }
}

// advance to `until`, calling `probe` for each held target as it comes up
async function play(
  run: Run,
  until: number,
  isTarget: (e: any) => boolean = () => false,
  probe?: (e: any) => Promise<void>,
) {
  const d = run.desk
  while (d.now < until) {
    while (d.pending.length > 50) await flush(run)
    const send = d.pending.splice(0, 50)
    const body: any = { untilEvent: STOP, max: until }
    if (send.length) body.actions = send.map((x) => x.a)
    const r = await run.api.req('POST', `/v1/worlds/${run.wid}/advance`, body)
    onResults(d, send, r.results)
    const targets: any[] = []
    for (const e of r.events) {
      if (e.seq <= run.lastSeq) continue
      run.lastSeq = e.seq
      run.events?.push(e)
      onEvent(d, e, (x) => (isTarget(x) ? (targets.push(x), true) : false))
    }
    d.now = Math.max(d.now, r.now)
    for (const t of targets) {
      const id = t.kind === 'price_request' ? t.request.id : t.order.id
      await flush(run, id) // everything but the target's own action is in the world before we fork
      await probe!(t)
      for (const x of d.pending) if (x.hold === id) x.hold = undefined
    }
    if (r.now >= run.endsAt) break
  }
}

// ---------- forks ----------
async function trial(run: Run, slots: Slots, actions: any[], to: number) {
  await slots.take()
  let id: string | undefined
  try {
    id = (await run.api.req('POST', `/v1/worlds/${run.wid}/fork`)).worldId
    const r = await run.api.req('POST', `/v1/worlds/${id}/advance`, { to: Math.min(to, run.endsAt), actions })
    return { results: r.results as any[], events: (r.events as any[]).filter((e) => e.seq > run.lastSeq) }
  } finally {
    if (id) await run.api.req('DELETE', `/v1/worlds/${id}`).catch(() => {})
    slots.give()
  }
}

// Two rounds of a 7-point grid. `high(x)` is true on the upper side of the threshold
// (a fee that books, a price that loses). Returns the bracket around the flip.
async function search<T extends { high: boolean }>(
  lo: number,
  hi: number,
  test: (x: number) => Promise<T>,
  rounds = 2,
  n = 7,
) {
  const trials: (T & { x: number })[] = []
  let a = lo,
    b = hi,
    ends: string | null = null
  for (let round = 0; round < rounds; round++) {
    const xs = Array.from({ length: n }, (_, i) =>
      round === 0 ? a * (b / a) ** (i / (n - 1)) : a * (b / a) ** ((i + 1) / (n + 1)),
    )
    const got = await Promise.all(xs.map(async (x) => ({ x, ...(await test(x)) })))
    trials.push(...got)
    trials.sort((p, q) => p.x - q.x)
    const firstHigh = trials.find((t) => t.high)
    const below = trials.filter((t) => !t.high && (!firstHigh || t.x < firstHigh.x))
    if (!firstHigh) {
      a = hi
      b = hi * 1.6
      ends = 'above'
    } else if (!below.length) {
      a = lo * 0.5
      b = firstHigh.x
      ends = 'below'
    } else {
      a = below[below.length - 1].x
      b = firstHigh.x
      ends = null
    }
  }
  const monotone = trials.every((t, i) => i === 0 || !trials[i - 1].high || t.high)
  return { bracket: [a, b], flip: ends ? null : Math.sqrt(a * b), ends, monotone, trials }
}

const lane = (legs: any[]) => legs.map((l) => [l.pickup.placeId, l.delivery.placeId])
function load(d: Desk) {
  const c = { open: 0, booked: 0 }
  for (const g of Object.values(d.gigs)) if (g.status !== 'gone') c[g.status]++
  return { ...c, orders: Object.keys(d.orders).length }
}

async function feeProbe(run: Run, slots: Slots, e: any, file: string) {
  const d = run.desk,
    o = e.order,
    r = d.orders[o.id]
  const cars: Car[] = o.legs.map((_: any, i: number) => ({ orderId: o.id, leg: i }))
  const ref = r.ref
  const res = await search(0.45, 1.8, async (x) => {
    const t = await trial(run, slots, [postAction(d, cars, false, Math.round(ref * x))], d.now + WINDOW)
    const gig = t.results?.[0]
    const booked = gig?.ok ? t.events.find((v) => v.kind === 'gig_booked' && v.gigId === gig.id) : undefined
    return {
      high: !!booked,
      feeCents: Math.round(ref * x),
      minutes: booked ? booked.at - d.now : null,
      driverId: booked?.driverId ?? null,
      views: gig?.ok ? t.events.filter((v) => v.kind === 'gig_viewed' && v.gigId === gig.id).length : 0,
      dropped: gig?.ok ? t.events.some((v) => v.kind === 'gig_dropped' && v.gigId === gig.id) : false,
      refused: gig?.ok ? null : (gig?.reason ?? 'no result'),
    }
  })
  appendFileSync(
    file,
    JSON.stringify({
      kind: 'fee',
      orderId: o.id,
      at: d.now,
      dealerId: o.dealerId,
      option: o.option,
      priceCents: o.priceCents,
      deadline: o.deadline,
      lastPickupAt: o.lastPickupAt,
      lane: lane(o.legs),
      readyAt: o.legs[0].pickup.window.from,
      private: o.legs.map((l: any) => [l.pickup.privateAddress, l.delivery.privateAddress]),
      premium: o.legs.some((l: any) => l.car.premium),
      electric: o.legs.some((l: any) => l.car.electric),
      note: r.note,
      referenceFeeCents: ref,
      windowMinutes: WINDOW,
      load: load(d),
      ...res,
    }) + '\n',
  )
}

async function quoteProbe(run: Run, slots: Slots, e: any, file: string) {
  const d = run.desk,
    q = e.request
  for (const o of q.options) {
    const res = await search(0.7, 2.3, async (x) => {
      const price = Math.round(o.listPriceCents * x)
      const t = await trial(
        run,
        slots,
        [{ type: 'quote', requestId: q.id, prices: { [o.kind]: price } }],
        q.respondBy + 1,
      )
      const won = t.events.some((v) => v.kind === 'order_won' && v.order.id === q.id)
      const lost = t.events.some((v) => v.kind === 'order_lost' && v.requestId === q.id)
      return { high: !won, priceCents: price, decided: won || lost }
    })
    appendFileSync(
      file,
      JSON.stringify({
        kind: 'quote',
        requestId: q.id,
        at: d.now,
        dealerId: q.dealerId,
        batchId: q.batchId,
        option: o.kind,
        options: q.options.map((x: any) => x.kind),
        listPriceCents: o.listPriceCents,
        referenceFeeCents: q.referenceFeeCents,
        lane: lane(q.legs),
        legs: q.legs.length,
        private: q.legs.map((l: any) => [l.pickup.privateAddress, l.delivery.privateAddress]),
        note: q.note?.text ?? null,
        dealer: { ...dealer(d, q.dealerId) },
        ownMult: d.reqs[q.id].mult,
        ...res,
      }) + '\n',
    )
  }
}

// policy variants from this minute to the end of the week, each on its own fork
async function branch(run: Run, slots: Slots, file: string) {
  await flush(run)
  const towns = Object.entries(
    Object.values(run.desk.reqs).reduce(
      (m: Record<string, number>, r) => ((m[r.pickup] = (m[r.pickup] ?? 0) + 1), m),
      {},
    ),
  )
    .sort((a, b) => b[1] - a[1])
    .map(([t]) => t)
  const pick = (k: number) => towns[Math.floor(h(run.desk.seed + run.desk.now + 't' + k) * Math.min(towns.length, 12))]
  const variants: Partial<Params>[] = [
    { qScale: 0.9 },
    { qScale: 1.1 },
    { fOpen: run.desk.p.fOpen - 0.15 },
    { fOpen: run.desk.p.fOpen + 0.15 },
    { townScale: { [pick(0)]: 9 } },
    { townScale: { [pick(1)]: 9 } },
    { townScale: { [pick(2)]: 0.85 } },
  ]
  await Promise.all(
    variants.map(async (v) => {
      await slots.take()
      let id: string | undefined
      try {
        id = (await run.api.req('POST', `/v1/worlds/${run.wid}/fork`)).worldId as string
        const desk: Desk = structuredClone(run.desk)
        desk.p = { ...desk.p, ...v }
        const fork: Run = { api: run.api, wid: id, desk, lastSeq: run.lastSeq, endsAt: run.endsAt }
        await play(fork, run.endsAt)
        const score = await run.api.req('GET', `/v1/worlds/${id}/score`)
        appendFileSync(
          file,
          JSON.stringify({
            kind: 'branch',
            at: run.desk.now,
            variant: v,
            score,
            wonAfter: Object.keys(desk.orders).length - Object.keys(run.desk.orders).length,
            refused: desk.refused,
          }) + '\n',
        )
      } finally {
        if (id) await run.api.req('DELETE', `/v1/worlds/${id}`).catch(() => {})
        slots.give()
      }
    }),
  )
}

// ---------- one seed ----------
async function world(api: Api, seed: string) {
  const dir = `${OUT}/${MODE}/L${LEVEL}/${seed}`
  mkdirSync(dir, { recursive: true })
  const file = `${dir}/probes.jsonl`
  const t0 = Date.now(),
    r0 = api.requests
  const wid = (await api.req('POST', '/v1/worlds', { level: LEVEL, seed })).worldId as string
  try {
    const snap = await api.req('GET', `/v1/worlds/${wid}`)
    writeFileSync(`${dir}/drivers.json`, JSON.stringify(await api.req('GET', `/v1/worlds/${wid}/drivers`)))
    const run: Run = { api, wid, desk: newDesk(BASEP, seed), lastSeq: -1, endsAt: snap.endsAt, events: [] }
    const slots = new Slots(7)
    let probes = 0
    const picked = (id: string) => h(seed + id + 'p') < SHARE
    if (MODE === 'fee')
      await play(
        run,
        snap.endsAt,
        (e) => e.kind === 'order_won' && picked(e.order.id),
        async (e) => {
          await feeProbe(run, slots, e, file)
          probes++
        },
      )
    else if (MODE === 'quote')
      await play(
        run,
        snap.endsAt,
        (e) => e.kind === 'price_request' && picked(e.request.id),
        async (e) => {
          await quoteProbe(run, slots, e, file)
          probes++
        },
      )
    else if (MODE === 'branch') {
      for (const at of AT) {
        await play(run, at)
        await branch(run, slots, file)
        probes += 7
      }
      await play(run, snap.endsAt)
    } else await play(run, snap.endsAt)
    const score = await api.req('GET', `/v1/worlds/${wid}/score`)
    writeFileSync(`${dir}/events.jsonl.gz`, gzipSync(Buffer.from(run.events!.map((e) => JSON.stringify(e)).join('\n'))))
    writeFileSync(
      `${dir}/reveal.json.gz`,
      gzipSync(Buffer.from(JSON.stringify(await api.req('GET', `/v1/worlds/${wid}/reveal`)))),
    )
    const meta = {
      seed,
      level: LEVEL,
      mode: MODE,
      worldId: wid,
      params: BASEP,
      share: SHARE,
      window: WINDOW,
      at: AT,
      score,
      probes,
      refused: run.desk.refused,
      seconds: (Date.now() - t0) / 1000,
      requests: api.requests - r0,
    }
    writeFileSync(`${dir}/meta.json`, JSON.stringify(meta, null, 2))
    console.log(
      `${api.name} ${seed}: ${probes} probes, ${meta.requests} requests, ${meta.seconds.toFixed(0)}s, margin €${(score.marginCents / 100).toFixed(0)}, ${score.wonOrders} orders, ${(100 * score.onTimeShare).toFixed(0)}% on time`,
    )
  } finally {
    await api.req('DELETE', `/v1/worlds/${wid}`).catch(() => {})
  }
}

// ---------- main ----------
if (!KEYS.length) throw new Error('No SPREAD_KEY, SPREAD_KEY1, ... in the environment')
const map = await (await fetch(BASE + '/v1/map')).json()
for (const r of map.roads) ROAD[r.from + '>' + r.to] = { km: r.km, minutes: r.minutes }
const apis = KEYS.map((k, i) => new Api(k, 'key' + (i + 1)))
if (opt('clean') === 'true')
  for (const api of apis)
    for (const w of await api.req('GET', '/v1/worlds'))
      if (!w.ended && w.kind === 'practice' && !w.boardRun) await api.req('DELETE', `/v1/worlds/${w.worldId}`)
const queue = [...SEEDS]
await Promise.all(
  apis.map(async (api) => {
    for (let seed = queue.shift(); seed; seed = queue.shift())
      await world(api, seed).catch((e) => console.error(`${api.name} ${seed} failed: ${e.message}`))
  }),
)
