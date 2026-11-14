// pnpm oracle <seed> [seed ...] [--json]   -> what a dispatcher who saw everything would have made of each week
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

// ---------- the oracle ----------
// What a dispatcher who could see everything would have made of this week: every dealer's limit, every
// driver's day and what each gig costs each driver. It walks the requests in time order, prices each at
// the dealer's limit, hands it to the cheapest driver who can still do it on time at exactly that
// driver's cost, and declines what would lose money. No drops, no failed visits, no waiting for raises.
// It is a reference to measure a policy against, not a proven optimum: it is greedy in time, so it can
// give a driver to an early order that a later one needed more, and no real policy can reach it.
// With `local`, only drivers who would plausibly see the gig count: those who live within reach of the
// pickup, or whose earlier gig that day ends there. That is nearer to what posting in the app can find.
export function oracle(seed: string, local = false) {
  const W = createWorld(seed),
    P = packFor(W.pack)
  const res: any = {
    seed,
    requests: P.requests.length,
    orders: 0,
    revenueCents: 0,
    feeCents: 0,
    marginCents: 0,
    noDriver: 0,
    unprofitable: 0,
    cancelled: 0,
    byDay: [0, 1, 2, 3, 4].map(() => ({ requests: 0, orders: 0, marginCents: 0 })),
    level: W.hid.level / PRM.thrBase,
    warDay: W.hid.warDay,
    outageDay: W.hid.outDay,
  }
  const done: Record<string, number[]> = {} // dealer -> minutes at which its orders arrived on time
  let mornings = 0
  for (const req of P.requests) {
    W.now = req.respondBy
    for (; mornings < day(W.now); mornings++) morning(W)
    const D = dealer(W, req.dealerId),
      dd = Math.min(4, day(req.arrivedAt))
    res.byDay[dd].requests++
    D.trust = Math.min(25, (done[req.dealerId] ?? []).filter((t) => t <= W.now).length)
    D.n++
    const thr = thresholds(W, req)
    let best: any = null,
      feasible = false
    for (const opt of req.options) {
      const o = makeOrder(W, req, opt, Math.floor(thr[opt.kind]))
      const ca = cancelAt(W, o)
      if (ca) {
        res.cancelled++
        best = null
        delete W.orders[req.id]
        break
      } // the dealer cancels it later: not worth a driver
      // the oracle reads every note: real hours, real ready time, plates, gearbox, the note's deadline
      o.legs.forEach((l: any, i: number) => {
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
      if (!(cars(g).length > 1 && g.drive > 720))
        for (const d of W.drivers) {
          if (!allowed(d, g)) continue
          const p0 = place(W, g.stops[0])
          if (local && crow(d.home, p0) > PRM.nearKm && !d.busy.some((x: any) => crow(x.endPlace, p0) <= PRM.nearKm))
            continue
          const pl = plan(W, d, g)
          if (!pl) continue
          const last = o.legs[o.legs.length - 1].delivery
          const counts = last.privateAddress ? Math.max(pl.end, last.window.from) : nextOpen(last.hours, pl.end)
          if (counts > g.win[g.win.length - 1].to) continue // would be late
          feasible = true
          const profit = o.priceCents - pl.cost
          if (!best || profit > best.profit) best = { profit, price: o.priceCents, cost: pl.cost, d, pl, counts }
        }
      delete W.orders[req.id]
    }
    if (!best) {
      if (!feasible) res.noDriver++
      continue
    }
    if (best.profit <= 0) {
      res.unprofitable++
      continue
    }
    D.won++
    best.d.busy.push({ g: req.id, D: best.pl.D, start: best.pl.leave, end: best.pl.end, endPlace: best.pl.endPlace })
    ;(done[req.dealerId] ??= []).push(best.counts)
    res.orders++
    res.revenueCents += best.price
    res.feeCents += Math.round(best.cost)
    res.marginCents += Math.round(best.profit)
    res.byDay[dd].orders++
    res.byDay[dd].marginCents += Math.round(best.profit)
  }
  return res
}

if (process.argv[1] === import.meta.filename) {
  const eur = (c: number) => '€' + Math.round(c / 100).toLocaleString('en')
  for (const seed of process.argv.slice(2).filter((a) => !a.startsWith('--')))
    for (const local of [false, true]) {
      const t = Date.now(),
        r = oracle(seed, local)
      console.log(
        `${seed} ${local ? '[local drivers only]' : '[any driver]'}: oracle margin ${eur(r.marginCents)} on ${r.orders} of ${r.requests} requests (revenue ${eur(r.revenueCents)}, fees ${eur(r.feeCents)})`,
      )
      console.log(
        `  declined: ${r.unprofitable} would lose money, ${r.noDriver} no driver on time, ${r.cancelled} cancelled later`,
      )
      if (local) continue
      console.log(
        `  by day: ${r.byDay.map((d: any, i: number) => `${['Mon', 'Tue', 'Wed', 'Thu', 'Fri'][i]} ${d.orders}/${d.requests} ${eur(d.marginCents)}`).join(' | ')}`,
      )
      console.log(
        `  world: competitor level ${r.level.toFixed(2)}x list, price war ${['Mon', 'Tue', 'Wed', 'Thu', 'Fri'][r.warDay]}, outage ${['Mon', 'Tue', 'Wed', 'Thu', 'Fri'][r.outageDay]}  (${Date.now() - t} ms)`,
      )
      if (process.argv.includes('--json')) console.log(JSON.stringify(r))
    }
}
