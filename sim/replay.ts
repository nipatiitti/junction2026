// Replays a recorded week's orders and gig postings in the simulator, to compare what drivers did.
//   pnpm replay <week folder> [...]   -> one JSON line per week: each first posting, on the server and in the simulator
// The simulator's dealers are bypassed: every order the server's week won is injected at its minute with its
// option and price, and every gig the week posted is posted at its minute with its stops, audience and schedule.
import { appendFileSync, readFileSync } from 'node:fs'
import { gunzipSync } from 'node:zlib'
import * as S from './world.ts'

const gz = (p: string) => gunzipSync(readFileSync(p)).toString()
for (const dir of process.argv.slice(2)) {
  const meta = JSON.parse(readFileSync(dir + '/meta.json', 'utf8'))
  const events = gz(dir + '/events.jsonl.gz')
    .split('\n')
    .filter(Boolean)
    .map((l) => JSON.parse(l))
  const snap = JSON.parse(gz(dir + '/snapshot.json.gz'))
  const W = S.createWorld(meta.seed)
  const real: Record<string, any> = {}
  const steps: any[] = []
  for (const e of events) {
    if (e.kind === 'order_won') steps.push({ at: e.at, n: 0, order: e.order })
    else if (e.kind === 'gig_booked') (real[e.gigId] ??= {}).booked ??= { at: e.at, fee: e.feeCents }
    else if (e.kind === 'gig_dropped') (real[e.gigId] ??= {}).dropped = true
    else if (e.kind === 'gig_expired') (real[e.gigId] ??= {}).expired = e.at
  }
  for (const g of snap.gigs) steps.push({ at: g.postedAt, n: 1, gig: g })
  steps.sort((a, b) => a.at - b.at || a.n - b.n)
  const sim: Record<string, string> = {},
    posted = new Set<string>(),
    rows: any[] = []
  for (const s of steps) {
    if (s.at > W.now) S.advance(W, { to: s.at })
    if (s.order) {
      const req = S.requestOf(W, s.order.id)
      if (req)
        S.win(W, req, req.options.find((o: any) => o.kind === s.order.option) ?? req.options[0], s.order.priceCents)
      continue
    }
    const g = s.gig,
      first = g.stops.every((x: any) => !posted.has(x.orderId + ':' + x.leg))
    for (const x of g.stops) posted.add(x.orderId + ':' + x.leg)
    // the snapshot keeps only the LAST schedule; a gig re-priced after a drop or a fee update shows its later (urgent) fee from postedAt.
    // Before that schedule starts, post the fee the server actually booked at (if booked then), else hold its first step.
    const late = g.schedule[0].at - g.postedAt,
      rb = real[g.id]?.booked
    const sched =
      late > 5 && process.env.REPLAY_RAW !== '1' && rb && rb.at < g.schedule[0].at
        ? [{ at: g.postedAt, feeCents: rb.fee }, ...g.schedule]
        : g.schedule
    const r = S.act(W, [{ type: 'post', stops: g.stops, audience: g.audience, schedule: sched }])[0]
    if (!first) continue
    const o = W.orders[g.stops[0].orderId]
    if (!r.ok || !o) {
      rows.push({ gig: g.id, refused: r.reason ?? 'no order' })
      continue
    }
    sim[g.id] = r.id
    const open = Object.values(W.gigs).filter((x: any) => x.status === 'open').length,
      booked = Object.values(W.gigs).filter((x: any) => x.status === 'booked' || x.status === 'working').length
    rows.push({
      gig: g.id,
      simGig: r.id,
      at: s.at,
      ref: [...new Set<string>(g.stops.map((x: any) => x.orderId))].reduce((t, id) => t + (W.orders[id]?.ref ?? 0), 0),
      late,
      open0: g.schedule[0].feeCents,
      open1: sched[0].feeCents,
      top: g.schedule[g.schedule.length - 1].feeCents,
      steps: g.schedule.length,
      from: o.legs[g.stops[0].leg].pickup.window.from,
      lastPickupAt: o.lastPickupAt,
      cars: g.stops.length / 2,
      private: o.legs.some((l: any) => l.pickup.privateAddress || l.delivery.privateAddress),
      pickup: o.legs[g.stops[0].leg].pickup.placeId,
      load: { open, booked },
      real: real[g.id] ?? {},
    })
  }
  S.advance(W, { to: W.endsAt })
  const simEv: Record<string, any> = {}
  const count: Record<string, number> = {}
  for (const e of W.events) {
    count[e.kind] = (count[e.kind] ?? 0) + 1
    if (e.kind === 'gig_booked') (simEv[e.gigId] ??= {}).booked ??= { at: e.at, fee: e.feeCents }
    else if (e.kind === 'gig_dropped') (simEv[e.gigId] ??= {}).dropped = true
    else if (e.kind === 'gig_expired') (simEv[e.gigId] ??= {}).expired = e.at
  }
  for (const r of rows) if (r.simGig) r.sim = simEv[r.simGig] ?? {}
  const rc: Record<string, number> = {}
  for (const e of events) rc[e.kind] = (rc[e.kind] ?? 0) + 1
  const kinds = [
    'order_won',
    'gig_booked',
    'gig_dropped',
    'gig_expired',
    'gig_viewed',
    'delivered',
    'deadline_close',
    'visit_failed',
    'no_show',
  ]
  const line = JSON.stringify({
    seed: meta.seed,
    policy: meta.policy,
    worldId: meta.worldId,
    real: { score: meta.score, counts: Object.fromEntries(kinds.map((k) => [k, rc[k] ?? 0])) },
    sim: { score: S.score(W), counts: Object.fromEntries(kinds.map((k) => [k, count[k] ?? 0])) },
    gigs: rows,
  })
  if (process.env.REPLAY_OUT)
    appendFileSync(process.env.REPLAY_OUT, line + '\n') // one write per week: safe from several processes
  else console.log(line)
}
