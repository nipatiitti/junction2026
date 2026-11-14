// sim/oracle.ts <seed> [seed ...] [--week <dir>]... [--json] [--local] [--cap 65] [--per-driver 2] [--premium 1.5]
//   What a dispatcher who saw everything would have made of a week, as nested tiers, and (with --week, a recorded
//   week folder of runs/L8/<seed>/<worldId>) that policy's account next to them. Node 24 compatible.
//
// ASSUMPTIONS. Every number is an upper bound under these, not a forecast.
// - Hidden values are the simulator's for the seed (world.ts, as it is when this runs). For a recorded seed the
//   requests, roster, car facts and cancellations are the server's; dealer limits and driver costs are drawn.
// - Every tier walks the requests in time order at their response deadline, so dealer state is the world's:
//   trust = that dealer's earlier orders delivered on time before this request (max 25, +PRM.trustStep each) and
//   the competitor's morning answer to our win share. A declined request is quoted high (lost: no goodwill cost).
//   Requests the dealer later cancels are skipped by every tier. Every order taken is delivered on time.
// - Every tier reads the notes (real hours, ready time, plates, gearbox, note deadline) and knows which options
//   some driver can do on time at all (timetable and roster are public). No drops, failed visits or slow roads.
// - A booked driver does the gig as world.ts plan() says, at the minute it is won, chaining gigs within a day up
//   to that driver-day's own limit; the plan's cost is the driver's hidden cost.
// - Price rules. "limit": the dealer's limit (the most it accepts) on the option the oracle picks. "m x list":
//   every option it quotes at m x list price, m one number for the week (best in hindsight); the dealer takes the
//   option with the most headroom, as world.ts decide() does.
// - Fee rules. "cost": the driver is paid exactly their cost (a direct offer at cost). "market": orders are taken
//   on a typical-fee rule (price above k x referenceFee, k one number for the week, best in hindsight); the market
//   then books the cheapest on-time driver and we pay --premium (default 1.5) x that driver's cost. The default is
//   what the best recorded policies pay over the simulator's cheapest cost on their own orders (1.5-1.6, printed
//   per week below); with it the blind tier lands near the best recorded weeks.
// - Tiers: a = m x list, market fees (blind); b = limit, market fees (knows dealers only); c = m x list, cost
//   (knows drivers only); d = limit, cost (knows both). b-a and d-c are the value of knowing limits, c-a and d-b
//   the value of knowing costs. m and k are tuned on a fast walk without capacity, then on a few full walks.
// - Assignment in the cost tiers: Lagrangian passes over the time walk. Pass 0 is the old greedy (cheapest
//   on-time driver now, "greedy" in the table). After each pass every driver-day that blocked a later, more
//   profitable order gets a reservation price (the profit that order lost); the next pass charges it when
//   choosing a driver and declines an order worth less than the reservations it would use. The best pass by
//   margin is kept, so it is never below greedy.
// - Capacity rows (the simulator's overload is too gentle): "<=N gigs/driver-day" lowers every working
//   driver-day's limit to N; "<=C orders/day" takes at most C orders per arrival day, the most profitable ones
//   (a per-day profit floor from the previous pass). The volume line repeats d at several such caps.
// - --week: the recorded account (meta.json score, ledger lines). "d on the policy's own orders" replays its won
//   requests and options at the limit and the cheapest driver's cost (taken at any profit). Gap to d = price
//   (own orders: oracle revenue/order minus the policy's) + fee (policy fee/order minus the oracle's) +
//   unservable (own orders the simulator has no on-time driver for) + losses (refunds, penalties, release fees,
//   fines, ...) + selection (d at the policy's own orders per day minus d on its own orders) + volume (d
//   uncapped minus that). The parts add up exactly. The simulator's limits are not the server's: where the
//   policy's price beat the simulator's limit (counted) the price part is understated.
import { readFileSync } from 'node:fs'
import { gunzipSync } from 'node:zlib'
import { createWorld, internals, PRM, packFor } from './world.ts'

const {
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
  crow,
  road,
  dealer,
  morning,
  day,
} = internals

type Cand = { di: number; cost: number; D: number; leave: number; end: number; endPlace: string; counts: number }
type Opt = { kind: string; list: number; o: any; g: any; lo: number; hi: number; cands: Cand[]; has: Set<number> }
type Req = { req: any; cancelled: boolean; dd: number; opts: Opt[] }
type Cfg = {
  price: 'limit' | number
  fee: 'cost' | 'market'
  k?: number
  premium?: number
  fast?: boolean
  lam?: Map<string, number>
  tau?: number[]
  cap?: number[]
  perDriver?: number
  force?: Map<string, string>
  paid?: Map<string, number>
}

// driver d's plan for the option's gig as the driver's day stands; null when not on time
function evalPlan(W: any, d: any, r: Opt): Cand | null {
  W.orders[r.o.id] = r.o
  const pl = plan(W, d, r.g)
  if (!pl) return null
  const last = r.o.legs[r.o.legs.length - 1].delivery
  const counts = last.privateAddress ? Math.max(pl.end, last.window.from) : nextOpen(last.hours, pl.end)
  if (counts > r.g.win[r.g.win.length - 1].to) return null
  return { di: d.i, cost: pl.cost, D: pl.D, leave: pl.leave, end: pl.end, endPlace: pl.endPlace, counts }
}

// every request and option, with each driver's plan on an empty day (the costly part, done once per seed)
export function prepare(seed: string, local = false) {
  const W = createWorld(seed),
    P = packFor(W.pack)
  const reqs: Req[] = []
  const sorted = [...P.requests].sort((a: any, b: any) => a.respondBy - b.respondBy || a.arrivedAt - b.arrivedAt)
  for (const req of sorted) {
    W.now = req.respondBy
    const R: Req = { req, cancelled: false, dd: Math.min(4, day(req.arrivedAt)), opts: [] }
    reqs.push(R)
    for (const opt of req.options) {
      const o = makeOrder(W, req, opt, 0)
      if (cancelAt(W, o)) {
        R.cancelled = true
        break
      }
      o.legs.forEach((l: any, i: number) => {
        // the oracle reads every note
        const t = o.truth[i]
        l.pickup.hours = t.pickupHours
        l.delivery.hours = t.deliveryHours
        l.pickup.window.from = Math.max(l.pickup.window.from, t.readyAt, t.releasedAt ?? 0)
        if (t.noteDeadline && !l.delivery.privateAddress)
          l.delivery.window.to = Math.min(l.delivery.window.to, t.noteDeadline)
      })
      const g: any = {
        id: 'x',
        orderIds: [o.id],
        stops: o.legs.flatMap((l: any, i: number) => [
          { orderId: o.id, leg: i, kind: 'pickup', withPlates: o.truth[i].needsPlates, withCharging: needsCharge(l) },
          { orderId: o.id, leg: i, kind: 'delivery' },
        ]),
        audience: {
          experienced: o.legs.some((l: any) => l.car.premium),
          manualLicence: o.truth.some((t: any) => t.manualGearbox),
        },
        drive: 0,
      }
      for (let k = 1; k < g.stops.length; k++) g.drive += road(place(W, g.stops[k - 1]), place(W, g.stops[k])).minutes
      o.late = false
      windows(W, g)
      const first = Math.max(W.now, g.win[0].from)
      const r: Opt = {
        kind: opt.kind,
        list: opt.listPriceCents,
        o,
        g,
        lo: day(first),
        hi: Math.min(day(g.win[0].to), day(first) + 3, 9),
        cands: [],
        has: new Set(),
      }
      if (!(cars(g).length > 1 && g.drive > 720))
        for (const d of W.drivers) {
          if (!allowed(d, g)) continue
          if (local && crow(d.home, place(W, g.stops[0])) > PRM.nearKm) continue
          const c = evalPlan(W, d, r)
          if (c) r.cands.push(c)
        }
      r.cands.sort((a, b) => a.cost - b.cost)
      r.has = new Set(r.cands.map((c) => c.di))
      R.opts.push(r)
    }
    delete W.orders[req.id]
  }
  return {
    seed,
    W,
    reqs,
    local,
    maxes: W.drivers.map((d: any) => d.days.map((x: any) => x.max)),
    level: W.hid.level / PRM.thrBase,
  }
}
type Ctx = ReturnType<typeof prepare>

// one walk of the week under a price rule and a fee rule
export function walk(ctx: Ctx, cfg: Cfg) {
  const { W, reqs } = ctx
  for (const d of W.drivers) {
    d.busy = []
    d.days.forEach(
      (x: any, D: number) => (x.max = cfg.perDriver ? Math.min(ctx.maxes[d.i][D], cfg.perDriver) : ctx.maxes[d.i][D]),
    )
  }
  W.dealers = {}
  W.orders = {}
  const busyOn: Set<number>[] = Array.from({ length: 12 }, () => new Set())
  const done: Record<string, number[]> = {}
  const res = {
    orders: 0,
    revenueCents: 0,
    feeCents: 0,
    marginCents: 0,
    won: 0,
    lost: 0,
    cancelled: 0,
    noDriver: 0,
    unprofitable: 0,
    capped: 0,
    aboveLimit: 0,
    byDay: [0, 1, 2, 3, 4].map(() => ({ requests: 0, orders: 0, marginCents: 0 })),
    regret: new Map<string, number>(),
    wanted: [[], [], [], [], []] as number[][],
  }
  const lam = (c: Cand) => (cfg.lam ? (cfg.lam.get(c.di + ':' + c.D) ?? 0) : 0)
  let mornings = 0
  for (const R of reqs) {
    const req = R.req
    W.now = req.respondBy
    for (; mornings < day(W.now); mornings++) morning(W)
    const Dl = dealer(W, req.dealerId)
    res.byDay[R.dd].requests++
    Dl.trust = Math.min(25, (done[req.dealerId] ?? []).filter((t) => t <= W.now).length)
    Dl.n++
    if (R.cancelled) {
      res.cancelled++
      continue
    }
    if (cfg.force && !cfg.force.has(req.id)) continue // replaying a policy's own orders: it declined this one
    const thr = thresholds(W, req)
    if (cfg.paid && cfg.force && (cfg.paid.get(req.id) ?? 0) > thr[cfg.force.get(req.id)!]) res.aboveLimit++ // the policy's price beat the simulator's limit
    // the drivers who can do each option on time now, with their real cost given the gigs they already hold
    const live = R.opts
      .filter((r) => !cfg.force || r.kind === cfg.force.get(req.id))
      .map((r) => {
        if (cfg.fast) return { r, L: r.cands, touched: null as Set<number> | null }
        const touched = new Set<number>()
        for (let D = r.lo; D <= r.hi; D++) for (const di of busyOn[D]) touched.add(di)
        const L = r.cands.filter((c) => !touched.has(c.di))
        const p0 = r.o.legs[r.g.stops[0].leg].pickup.placeId,
          w0to = r.g.win[0].to,
          today = day(W.now)
        const reach = (from: string, t: number) =>
          t + (from === p0 ? 10 : road(from, p0).minutes * PRM.ptF + PRM.ptFix) <= w0to
        for (const di of touched) {
          const d = W.drivers[di]
          // a driver who could not do it on an empty day can now only through a chain, or from home today
          // (a driver who already works for us today is around): skip when neither can reach the pickup in time
          if (
            !r.has.has(di) &&
            !d.busy.some((b: any) => b.D >= r.lo && b.D <= r.hi && reach(b.endPlace, b.end + 10)) &&
            !(
              d.busy.some((b: any) => b.D === today) &&
              reach(d.home, Math.max(W.now, today * 1440 + d.days[today].from))
            )
          )
            continue
          if (!allowed(d, r.g)) continue
          if (
            ctx.local &&
            crow(d.home, p0) > PRM.nearKm &&
            !d.busy.some((x: any) => crow(x.endPlace, p0) <= PRM.nearKm)
          )
            continue
          const c = evalPlan(W, d, r)
          if (c) L.push(c)
        }
        return { r, L, touched }
      })
    const priceOf = (r: Opt) => (cfg.price === 'limit' ? Math.floor(thr[r.kind]) : Math.round(cfg.price * r.list))
    const dealerPick = (qs: { r: Opt; q: number }[]) => {
      // world.ts decide(): the largest headroom wins
      let best: any = null
      for (const x of qs) {
        const s = Math.log(thr[x.r.kind] / x.q)
        if (s >= 0 && (!best || s > best.s)) best = { ...x, s }
      }
      return best
    }
    let pick: { r: Opt; price: number; c: Cand; fee: number } | null = null
    if (cfg.fee === 'cost') {
      const opts = live
        .filter((x) => x.L.length)
        .map((x) => {
          const price = priceOf(x.r)
          let c: Cand | null = null,
            sc = -Infinity
          for (const y of x.L) {
            const s = price - y.cost - lam(y)
            if (s > sc) {
              sc = s
              c = y
            }
          }
          return { ...x, price, c: c!, score: sc, profit: price - c!.cost }
        })
      if (!opts.length) {
        res.noDriver++
        continue
      }
      const ok = cfg.force ? opts : opts.filter((x) => x.profit > 0 && x.score > 0) // a forced order is taken at any profit
      let ch: any = null
      if (cfg.price === 'limit') {
        for (const x of ok) if (!ch || x.score > ch.score) ch = x
      } else {
        const b = dealerPick(ok.map((x) => ({ r: x.r, q: x.price, x })))
        ch = b?.x ?? null
      }
      // what the cheapest driver on an empty day would have made: a busy driver-day that blocked it is a reservation
      if (cfg.lam && !cfg.fast) {
        let sa: any = null
        for (const x of opts)
          if (x.r.cands.length && thr[x.r.kind] >= x.price) {
            const p = x.price - x.r.cands[0].cost
            if (!sa || p > sa.p) sa = { p, c: x.r.cands[0], x }
          }
        const got = ch ? ch.profit : 0
        if (sa && sa.p > got && sa.x.touched?.has(sa.c.di)) {
          const key = sa.c.di + ':' + sa.c.D
          res.regret.set(key, Math.max(res.regret.get(key) ?? 0, sa.p - got))
        }
      }
      if (!ch) {
        if (cfg.price !== 'limit' && ok.length) res.lost++
        else res.unprofitable++
        continue
      }
      res.wanted[R.dd].push(ch.profit)
      if (cfg.cap && (res.byDay[R.dd].orders >= cfg.cap[R.dd] || ch.profit < (cfg.tau?.[R.dd] ?? 0))) {
        res.capped++
        continue
      }
      pick = { r: ch.r, price: ch.price, c: ch.c, fee: ch.c.cost }
    } else {
      // market fee: the order is taken on the typical-fee rule (price above k x typical fee); the market then books
      // the cheapest on-time driver and we pay the market premium over that driver's cost
      const est = cfg.k! * req.referenceFeeCents
      const opts = live
        .filter((x) => x.L.length)
        .map((x) => ({ ...x, price: priceOf(x.r) }))
        .filter((x) => x.price > est)
      if (!live.some((x) => x.L.length)) {
        res.noDriver++
        continue
      }
      let ch: any = null
      if (cfg.price === 'limit') {
        for (const x of opts) if (!ch || x.price > ch.price) ch = x
      } else ch = dealerPick(opts.map((x) => ({ r: x.r, q: x.price, x })))?.x ?? null
      if (!ch) {
        res.unprofitable++
        continue
      }
      let c: Cand = ch.L[0]
      for (const y of ch.L) if (y.cost < c.cost) c = y
      pick = { r: ch.r, price: ch.price, c, fee: c.cost * cfg.premium! }
    }
    Dl.won++
    res.won++
    const p = pick!
    const d = W.drivers[p.c.di]
    d.busy.push({ g: req.id, D: p.c.D, start: p.c.leave, end: p.c.end, endPlace: p.c.endPlace })
    if (!cfg.fast) busyOn[p.c.D].add(p.c.di)
    ;(done[req.dealerId] ??= []).push(p.c.counts)
    const m = p.price - Math.round(p.fee)
    res.orders++
    res.revenueCents += p.price
    res.feeCents += Math.round(p.fee)
    res.marginCents += m
    res.byDay[R.dd].orders++
    res.byDay[R.dd].marginCents += m
  }
  W.orders = {}
  for (const d of W.drivers) {
    d.busy = []
    d.days.forEach((x: any, D: number) => (x.max = ctx.maxes[d.i][D]))
  }
  return res
}
type Res = ReturnType<typeof walk>

// known-cost tiers: Lagrangian passes (reservation prices on driver-days, and a per-day profit floor under a cap).
// warm: start from another run's reservations and its wanted profits (for the cap's first floor).
type Warm = { lam: Map<string, number>; wanted: number[][] }
export function optimise(ctx: Ctx, cfg: Cfg, passes = 5, warm?: Warm) {
  const floor = (wanted: number[][]) =>
    wanted.map((w, D) => {
      const s = [...w].sort((a, b) => b - a)
      return s.length > cfg.cap![D] ? s[cfg.cap![D] - 1] : 0
    })
  let lam = warm?.lam ?? new Map<string, number>(),
    tau = cfg.cap && warm ? floor(warm.wanted) : undefined
  let best: (Res & { lam: Map<string, number> }) | null = null,
    first: Res | null = null,
    bestPass = 0
  for (let p = 0; p < passes; p++) {
    const r = walk(ctx, { ...cfg, lam, tau })
    if (p === 0) first = r
    if (!best || r.marginCents > best.marginCents) {
      best = { ...r, lam }
      bestPass = p
    }
    const next = new Map<string, number>()
    for (const [k, v] of lam) if (v * 0.7 > 1) next.set(k, v * 0.7)
    for (const [k, v] of r.regret) next.set(k, Math.max(next.get(k) ?? 0, v))
    lam = next
    if (cfg.cap) tau = floor(r.wanted)
  }
  return { ...best!, firstMarginCents: first!.marginCents, bestPass }
}

// one week-wide number (or two) by a grid on the fast walk (no capacity), then the full walk on the best and its
// neighbours: the markup m (list price multiple) and the typical-fee multiple k that a price must beat
export function tune(ctx: Ctx, mk: (m: number, k: number) => Cfg, useM: boolean, useK: boolean) {
  let m = 1.4,
    k = useK ? 0.4 : 0
  const val = (cfg: Cfg) => walk(ctx, { ...cfg, fast: true }).marginCents
  if (useM) {
    let b = -Infinity
    for (const x of grid(0.9, 2.4, 0.1)) {
      const v = val(mk(x, k))
      if (v > b) {
        b = v
        m = x
      }
    }
  }
  if (useK) {
    let b = -Infinity
    for (const x of grid(0.2, 2.2, 0.2)) {
      const v = val(mk(m, x))
      if (v > b) {
        b = v
        k = x
      }
    }
  }
  let best: Res | null = null
  // with limit prices volume (so capacity) moves with k: check a wider k range on the full walk
  const tries = useM
    ? [
        [m - 0.05, k],
        [m, k],
        [m + 0.05, k],
      ]
    : [...new Set([k, 0.2, 0.6, 1.0, 1.4])].map((kk) => [m, kk])
  for (const [mm, kk] of tries) {
    const r = walk(ctx, mk(mm, kk))
    if (!best || r.marginCents > best.marginCents) {
      best = r
      m = mm
      k = kk
    }
  }
  return { m: +m.toFixed(2), k: +k.toFixed(2), r: best! }
}
const grid = (a: number, b: number, s: number) =>
  Array.from({ length: Math.round((b - a) / s) + 1 }, (_, i) => +(a + i * s).toFixed(3))

const pick = (r: any, extra: any = {}) => ({
  marginCents: r.marginCents,
  orders: r.orders,
  revenueCents: r.revenueCents,
  feeCents: r.feeCents,
  revPerOrder: r.orders ? Math.round(r.revenueCents / r.orders) : 0,
  feePerOrder: r.orders ? Math.round(r.feeCents / r.orders) : 0,
  byDayOrders: r.byDay.map((d: any) => d.orders),
  noDriver: r.noDriver,
  ...(r.aboveLimit ? { aboveLimit: r.aboveLimit } : {}),
  ...extra,
})

export function oracle(
  seed: string,
  opt: {
    local?: boolean
    cap?: number
    perDriver?: number
    premium?: number
    weeks?: { perDay: number[]; options: [string, string][]; prices: [string, number][] }[]
  } = {},
) {
  const t0 = Date.now(),
    ctx = prepare(seed, !!opt.local),
    cap = opt.cap ?? 65,
    per = opt.perDriver ?? 2,
    premium = opt.premium ?? 1.5
  const tA = tune(ctx, (m, k) => ({ price: m, fee: 'market', k, premium }), true, true)
  const tB = tune(ctx, (_m, k) => ({ price: 'limit', fee: 'market', k, premium }), false, true)
  const d = optimise(ctx, { price: 'limit', fee: 'cost' })
  const warm = { lam: d.lam, wanted: d.wanted }
  const tC = tune(ctx, (m) => ({ price: m, fee: 'cost', lam: d.lam }), true, false)
  const caps = (c: number) => [c, c, c, c, c]
  const tiers: Record<string, any> = {
    a: pick(tA.r, { rule: `${tA.m} x list if >${tA.k} x typ, market` }),
    b: pick(tB.r, { rule: `limit if >${tB.k} x typ, market` }),
    c: pick(optimise(ctx, { price: tC.m, fee: 'cost' }, 2, warm), { rule: `${tC.m} x list, cost` }),
    d: pick(d, { rule: 'limit, cost', greedyMarginCents: d.firstMarginCents, bestPass: d.bestPass }),
    perDriver: pick(optimise(ctx, { price: 'limit', fee: 'cost', perDriver: per }, 2, warm), {
      rule: `limit, cost, <=${per} gigs/driver-day`,
    }),
    cap: pick(optimise(ctx, { price: 'limit', fee: 'cost', cap: caps(cap) }, 2, warm), {
      rule: `limit, cost, <=${cap} orders/day`,
    }),
  }
  const volume = [30, 60, 100].map((c) => {
    const r = optimise(ctx, { price: 'limit', fee: 'cost', cap: caps(c) }, 1, warm)
    return { capPerDay: c, orders: r.orders, marginCents: r.marginCents }
  })
  volume.push({ capPerDay: cap, orders: tiers.cap.orders, marginCents: tiers.cap.marginCents })
  volume.sort((x, y) => x.capPerDay - y.capPerDay)
  volume.push({ capPerDay: Infinity, orders: d.orders, marginCents: d.marginCents })
  const weeks = (opt.weeks ?? []).map((w) => ({
    own: pick(walk(ctx, { price: 'limit', fee: 'cost', force: new Map(w.options), paid: new Map(w.prices) }), {
      rule: "limit, cost, the policy's own orders",
    }),
    capped: pick(optimise(ctx, { price: 'limit', fee: 'cost', cap: w.perDay }, 2, warm), {
      rule: `limit, cost, policy's orders/day ${w.perDay.join('/')}`,
    }),
  }))
  return {
    seed,
    requests: ctx.reqs.length,
    cancelled: ctx.reqs.filter((r) => r.cancelled).length,
    level: +ctx.level.toFixed(3),
    local: !!opt.local,
    premium,
    tiers,
    volume,
    weeks,
    ms: Date.now() - t0,
  }
}

// ---------- a recorded week ----------
export function readWeek(dir: string) {
  const meta = JSON.parse(readFileSync(dir + '/meta.json', 'utf8'))
  const lines = gunzipSync(readFileSync(dir + '/events.jsonl.gz'))
    .toString()
    .split('\n')
    .filter(Boolean)
    .map((l) => JSON.parse(l))
  const acc: Record<string, number> = {},
    wonDay: Record<string, number> = {},
    option: Record<string, string> = {},
    price: Record<string, number> = {},
    cancelled = new Set<string>()
  let delivered = 0
  for (const e of lines) {
    if (e.kind === 'ledger') {
      acc[e.line.kind] = (acc[e.line.kind] ?? 0) + e.line.cents
      if (e.line.kind === 'revenue') delivered++
    } else if (e.kind === 'order_won') {
      wonDay[e.order.id] = Math.min(4, day(e.at))
      option[e.order.id] = e.order.option
      price[e.order.id] = e.order.priceCents
    } else if (e.kind === 'order_cancelled') cancelled.add(e.orderId)
  }
  const perDay = [0, 0, 0, 0, 0]
  for (const [id, D] of Object.entries(wonDay)) if (!cancelled.has(id)) perDay[D]++
  const revenue = acc.revenue ?? 0,
    fees = -(acc.driver_fee ?? 0),
    margin = meta.score.marginCents
  return {
    dir,
    seed: meta.seed,
    policy: meta.policy,
    worldId: meta.worldId,
    ranked: meta.score.ranked,
    onTimeShare: meta.score.onTimeShare,
    marginCents: margin,
    orders: meta.score.wonOrders,
    delivered,
    revenueCents: revenue,
    feeCents: fees,
    otherCents: margin - revenue + fees,
    accounts: acc,
    perDay,
    revPerOrder: delivered ? Math.round(revenue / delivered) : 0,
    feePerOrder: delivered ? Math.round(fees / delivered) : 0,
    options: Object.entries(option).filter(([id]) => !cancelled.has(id)),
    prices: Object.entries(price).filter(([id]) => !cancelled.has(id)),
  }
}
type Week = ReturnType<typeof readWeek>
// own: tier d on the policy's own orders (same requests, same options); capped: tier d at its orders per day
export function gap(w: Week, own: any, capped: any, full: any) {
  const Np = w.delivered,
    rp = w.revenueCents / Np,
    fp = w.feeCents / Np,
    Ns = own.orders
  const price = Ns * (own.revenueCents / Ns - rp),
    fee = Ns * (fp - own.feeCents / Ns),
    count = (Ns - Np) * (rp - fp)
  return {
    priceCents: Math.round(price),
    feeCents: Math.round(fee),
    countCents: Math.round(count),
    lossesCents: -w.otherCents,
    selectionCents: capped.marginCents - own.marginCents,
    volumeCents: full.marginCents - capped.marginCents,
    totalCents: full.marginCents - w.marginCents,
  }
}

// ---------- CLI ----------
if (process.argv[1] === import.meta.filename) {
  const argv = process.argv.slice(2),
    json = argv.includes('--json')
  const val = (f: string) => {
    const i = argv.indexOf(f)
    return i >= 0 ? argv[i + 1] : undefined
  }
  const weeks: Week[] = []
  for (let i = 0; i < argv.length; i++) if (argv[i] === '--week') weeks.push(readWeek(argv[++i].replace(/\/$/, '')))
  const skip = new Set(
    ['--week', '--cap', '--per-driver', '--premium'].flatMap((f) => argv.flatMap((a, i) => (a === f ? [i + 1] : []))),
  )
  const seeds = argv.filter((a, i) => !a.startsWith('--') && !skip.has(i))
  for (const w of weeks) if (!seeds.includes(w.seed)) seeds.push(w.seed)
  const eur = (c: number) => (c < 0 ? '-' : '') + '€' + Math.abs(Math.round(c / 100)).toLocaleString('en')
  const pad = (s: any, n: number) => String(s).padStart(n)
  const out: any[] = []
  for (const seed of seeds) {
    const mine = weeks.filter((w) => w.seed === seed)
    const r: any = oracle(seed, {
      local: argv.includes('--local'),
      cap: val('--cap') ? +val('--cap')! : undefined,
      perDriver: val('--per-driver') ? +val('--per-driver')! : undefined,
      premium: val('--premium') ? +val('--premium')! : undefined,
      weeks: mine,
    })
    r.recorded = mine.map(({ options, prices, ...w }, i) => ({
      ...w,
      feePremium: +(w.feePerOrder / r.weeks[i].own.feePerOrder).toFixed(3),
      oracleOwnOrders: r.weeks[i].own,
      oracleAtPolicyVolume: r.weeks[i].capped,
      gap: gap(w as Week, r.weeks[i].own, r.weeks[i].capped, r.tiers.d),
    }))
    delete r.weeks
    out.push(r)
    if (json) continue
    const T = r.tiers
    console.log(
      `\n${seed}: ${r.requests} requests (${r.cancelled} cancelled later), competitor level ${r.level}x list${r.local ? ', local drivers only' : ''}  [${r.ms} ms]`,
    )
    const n = r.requests - r.cancelled,
      share = (o: number) => ((100 * o) / n).toFixed(0) + '%'
    console.log(
      `  ${'tier'.padEnd(40)}${pad('margin', 9)}${pad('orders', 7)}${pad('share', 6)}${pad('rev/ord', 8)}${pad('fee/ord', 8)}`,
    )
    const row = (name: string, x: any) =>
      console.log(
        `  ${name.padEnd(40)}${pad(eur(x.marginCents), 9)}${pad(x.orders, 7)}${pad(share(x.orders), 6)}${pad(eur(x.revPerOrder), 8)}${pad(eur(x.feePerOrder), 8)}`,
      )
    row(`a blind   ${T.a.rule}`, T.a)
    row(`b limits  ${T.b.rule}`, T.b)
    row(`c costs   ${T.c.rule}`, T.c)
    row(`d both    (greedy ${eur(T.d.greedyMarginCents)})`, T.d)
    row(`d ${T.perDriver.rule.replace('limit, cost, ', '')}`, T.perDriver)
    row(`d ${T.cap.rule.replace('limit, cost, ', '')}`, T.cap)
    console.log(
      `  value of knowing limits: ${eur(T.b.marginCents - T.a.marginCents)} blind fees, ${eur(T.d.marginCents - T.c.marginCents)} known costs | knowing costs: ${eur(T.c.marginCents - T.a.marginCents)} fixed markup, ${eur(T.d.marginCents - T.b.marginCents)} known limits`,
    )
    console.log(
      `  volume (d at a cap of orders/day: orders, margin): ${r.volume.map((v: any) => `${v.capPerDay === Infinity ? 'none' : v.capPerDay}: ${v.orders} (${share(v.orders)}) ${eur(v.marginCents)}`).join(' | ')}`,
    )
    for (const w of r.recorded) {
      const g = w.gap
      console.log(
        `  week ${w.policy} ${w.worldId}${w.ranked ? '' : ' (unranked)'}: orders/day ${w.perDay.join('/')}, on time ${(100 * w.onTimeShare).toFixed(1)}%, other lines ${eur(w.otherCents)}`,
      )
      row('  policy (recorded)', w)
      row("  d on the policy's own orders", w.oracleOwnOrders)
      console.log(
        `    (the simulator finds no on-time driver for ${w.oracleOwnOrders.noDriver} of them; the policy's price is above the simulator's limit on ${w.oracleOwnOrders.aboveLimit ?? 0}; its fee premium over the cheapest driver's cost ${(w.feePerOrder / w.oracleOwnOrders.feePerOrder).toFixed(2)}x)`,
      )
      row("  d at the policy's orders/day", w.oracleAtPolicyVolume)
      console.log(
        `    gap to d ${eur(g.totalCents)} = price ${eur(g.priceCents)} + fee ${eur(g.feeCents)} + unservable ${eur(g.countCents)} + losses ${eur(g.lossesCents)} + selection ${eur(g.selectionCents)} + volume ${eur(g.volumeCents)}`,
      )
    }
  }
  if (json)
    console.log(
      JSON.stringify(out, (k, v) => (v === Infinity ? null : k === 'accounts' || k === 'dir' ? undefined : v)),
    )
}
