import * as THREE from 'three'
import { ease, lerp, pop, progress } from '../../kit/anim.js'
import { car } from '../../kit/car.js'
import { character, POSES, pose } from '../../kit/character.js'
import { glowSprite } from '../../kit/fx.js'
import { rng } from '../../kit/rng.js'
import { liveTexture } from '../../kit/sign.js'
import { FRAMES, GROUPS, LINES, ROADS, ROUTES, STOPS, SYSTEMS } from '../diagram.js'
import { captions, voiceCues } from '../lines.js'
import { buildMap, THEME } from '../map.js'
import { AREAS, chainPanel, feePanel, learnPanel } from '../panels.js'
import { joined, polyline, queue, reaches } from '../traffic.js'

// The solution, as the code: one view for every part of chapter 02, told apart by the segment's `direction` (see
// PLANS). The camera moves over the block diagram on a log scale of height; blocks light up as the voice names them;
// cars and drivers drive its lanes the way the code moves them: a grey car is a price request that stops on the lane
// over bestPrice() for its price (a green coin), a red car is a won order that stops over stepped() while its fee
// climbs (a meter) and a driver gets in, and red cars that wait behind one driver leave together as a chain (a link).
// Nothing on the picture but names and graphs has words or numbers. Beats, in local seconds:
//   in        0–4.0 the whole map, the systems light up · 3.2–7.2 events run into TS:LEAN · 7.5 only TS:LEAN,
//             lingering while the price, fee and chain blocks light up · 11–15 the dive, the chart draws in
//   fees      to the fee column; the card shows the steps and the weekend; orders stop for their fee
//   chains    to the chain blocks; two chains form and leave; the card shows one driver's cars and the booking share
//   learning  to Demand and Supply; sparks run back from observe(); the card moves the win curve and the cost
//   out       up to TS:LEAN and out to the whole map, tilting from 6.0, with traffic everywhere
//   traffic   the whole map, turning slowly, at its busiest

const FOV = 30
const TAN = Math.tan(THREE.MathUtils.degToRad(FOV / 2))
const SPEED = 30 // world units a second on the main lanes
const deg = THREE.MathUtils.degToRad

const road = (id) => ROADS.find((r) => r.id === id)
const routeOf = (name) => polyline(joined(ROUTES[name].map(road)))

/** A light that rises over 0.15 s at t0, holds, and fades over half a second. */
const pulse = (t, t0, hold = 0.9) => progress(t, t0, t0 + 0.15) * (1 - progress(t, t0 + 0.15 + hold, t0 + 0.65 + hold))

/** A flat chip lying on the ground, w × h world units, painted by draw(g, width, height, state); set(state) repaints. */
function chip(w, h, draw, state = {}) {
  const painter = liveTexture(Math.round(w * 64), Math.round(h * 64), (g, s, cw, ch) => {
    g.clearRect(0, 0, cw, ch)
    draw(g, cw, ch, s)
  })
  painter.set(state)
  const mesh = new THREE.Mesh(
    new THREE.PlaneGeometry(w, h),
    new THREE.MeshBasicMaterial({ map: painter.texture, transparent: true, depthWrite: false, toneMapped: false }),
  )
  mesh.rotation.x = -Math.PI / 2
  mesh.renderOrder = 5
  return { mesh, set: (s) => painter.set(s) }
}

/** A rounded rectangle filled with a colour, inset by `inset` pixels. */
function rounded(g, w, h, colour, inset = 2, radius = 0.3) {
  g.fillStyle = colour
  g.beginPath()
  g.roundRect(inset, inset, w - 2 * inset, h - 2 * inset, Math.min(w, h) * radius)
  g.fill()
}

/** What the chips show, as pictures: an event, a price (a coin with a tick), a fee (a meter with `level` of four bars
 * lit), a chain (a link), a saved week and a fitted constant. */
const CHIPS = {
  event: (colour) => (g, w, h) => rounded(g, w, h, colour, 2, 0.5),
  price: (g, w, h) => {
    g.fillStyle = '#16a34a'
    g.beginPath()
    g.arc(w / 2, h / 2, w / 2 - 3, 0, Math.PI * 2)
    g.fill()
    g.strokeStyle = '#ffffff'
    g.lineWidth = w * 0.09
    g.lineCap = 'round'
    g.lineJoin = 'round'
    g.beginPath()
    g.moveTo(w * 0.3, h * 0.52)
    g.lineTo(w * 0.45, h * 0.67)
    g.lineTo(w * 0.72, h * 0.36)
    g.stroke()
  },
  fee: (g, w, h, { level }) => {
    rounded(g, w, h, '#0f172a', 2, 0.18)
    for (let i = 0; i < 4; i++) {
      const bw = w * 0.14
      const x = w * 0.16 + i * w * 0.18
      const bh = h * (0.25 + i * 0.16)
      g.fillStyle = i <= level ? '#f59e0b' : '#334155'
      g.fillRect(x, h * 0.84 - bh, bw, bh)
    }
  },
  chain: (g, w, h) => {
    rounded(g, w, h, '#fbbf24', 2, 0.3)
    g.strokeStyle = '#0f172a'
    g.lineWidth = h * 0.12
    for (const x of [w * 0.22, w * 0.46]) {
      g.beginPath()
      g.roundRect(x, h * 0.3, w * 0.32, h * 0.4, h * 0.2)
      g.stroke()
    }
  },
  week: (g, w, h) => {
    rounded(g, w, h, '#a78bfa', 2, 0.2)
    g.fillStyle = '#4c1d95'
    g.fillRect(w * 0.12, h * 0.16, w * 0.76, h * 0.2)
  },
  constant: (g, w, h) => {
    rounded(g, w, h, '#facc15', 2, 0.2)
    g.fillStyle = '#713f12'
    g.beginPath()
    g.arc(w / 2, h / 2, Math.min(w, h) * 0.18, 0, Math.PI * 2)
    g.fill()
  },
}

/** The framing that shows `rect` [x0, z0, x1, z1] as large as it fits into `area` of the picture (pixels of the
 * 1920×1200 frame), for the camera looking straight down: the point in the picture's middle and the ground's height. */
function fit([x0, z0, x1, z1], { x, y, w, h }) {
  const scale = Math.min(w / (x1 - x0), h / (z1 - z0))
  return {
    centre: [(x0 + x1) / 2 - (x + w / 2 - 960) / scale, (z0 + z1) / 2 - (y + h / 2 - 600) / scale],
    height: 1200 / scale,
  }
}
/** An area with `by` more pixels of margin on every side. */
const inset = ({ x, y, w, h }, by) => ({ x: x + by, y: y + by, w: w - 2 * by, h: h - 2 * by })

// The picture between the chapter tag and the subtitles, inside the title-safe frame; and what a card leaves of it
const CLEAR = { x: 96, y: 136, w: 1728, h: 880 }
const RIGHT_OF_CARD = {
  x: AREAS.left.x + AREAS.left.w + 48,
  y: AREAS.left.y,
  w: 1824 - (AREAS.left.x + AREAS.left.w + 48),
  h: AREAS.left.h,
}
const LEFT_OF_CARD = { x: 96, y: AREAS.right.y, w: AREAS.right.x - 48 - 96, h: AREAS.right.h }
// What each deep dive shows, its edges in the gaps between blocks: the fee column with gig(), fees() and the lane where
// orders wait; tick(), the Planner, the chains and the lane where they form; Demand and Supply with the dotted line
// that feeds them
const LEAN = SYSTEMS.find((s) => s.id === 'lean').rect
const FEE_BLOCKS = [13.05, -18.4, 35.25, 7.675]
const CHAIN_BLOCKS = [-11.6, -14.9, 35.25, 18.25]
const LEARN_BLOCKS = [-35.6, -11.6, -11.6, 7.875]
/** How dark the diagram round a deep dive's blocks gets. */
const DIM = 0.62

/** Framings by name: where the camera looks and how much ground fills the picture's height. Each deep dive drifts in
 * slowly from A to B, B fitting its blocks into what the card leaves. */
const SPOTS = {
  ...FRAMES,
  lean: fit(LEAN, CLEAR),
  linger: fit(LEAN, { x: 96, y: 128, w: 1728, h: 896 }),
  lingerOut: fit(LEAN, inset(CLEAR, 20)),
  feeA: fit(FEE_BLOCKS, inset(RIGHT_OF_CARD, 36)),
  feeB: fit(FEE_BLOCKS, RIGHT_OF_CARD),
  chainA: fit(CHAIN_BLOCKS, inset(RIGHT_OF_CARD, 30)),
  chainB: fit(CHAIN_BLOCKS, RIGHT_OF_CARD),
  learnA: fit(LEARN_BLOCKS, inset(LEFT_OF_CARD, 36)),
  learnB: fit(LEARN_BLOCKS, LEFT_OF_CARD),
  wide: { centre: FRAMES.whole.centre, height: 150 },
}

/**
 * What each part does: its camera keys [time, spot, easing into it] (each part starts where the one before ended),
 * the tilt and turn, which blocks light up when, the chart, the event tokens, the traffic, the learning sparks, the
 * outer lanes, the card, and the focus: the blocks a deep dive is about stay bright while the rest of the picture
 * dims (`dim` at time t), the bright part moving from `from` to `to` by `until`, so that nothing half in the picture
 * competes with them.
 */
const PLANS = {
  in: {
    path: [
      [0, 'whole'],
      [7.5, 'lean', 'inOutQuad'],
      [11, 'linger', 'linear'],
      [15, 'key', 'inOutCubic'],
    ],
    angle: (t) => {
      const level = ease.inOutCubic(progress(t, 0, 6.5))
      return [deg(28) * (1 - level), deg(-7) * (1 - level)]
    },
    lights: [
      [GROUPS.touches, 1.0, 0.7],
      [GROUPS.world, 1.7, 0.7],
      [GROUPS.harness, 2.4, 0.7],
      [GROUPS.ops, 3.0, 0.7],
      [GROUPS.saved, 3.4, 0.7],
      [GROUPS.price, 7.9, 1.1],
      [GROUPS.fee, 8.9, 1.1],
      [GROUPS.chains, 9.9, 1.1],
    ],
    chart: [11.4, 14.8],
    tokens: [3.2, 7.2],
    traffic: 'light',
    outer: [0, 7],
  },
  fees: {
    path: [
      [0, 'key'],
      [3.0, 'feeA', 'inOutCubic'],
      [14, 'feeB', 'linear'],
    ],
    lights: [
      [['gig', 'fees'], 0.8, 1.6],
      [['stepped'], 2.6, 3.2],
      [['planBy'], 4.4, 2.6],
      [['rested'], 8.0, 4.2],
    ],
    traffic: 'fees',
    card: [feePanel, AREAS.left],
    focus: { from: FEE_BLOCKS, to: FEE_BLOCKS, until: 3.0, dim: (t) => DIM * ease.outCubic(progress(t, 0.4, 1.6)) },
  },
  chains: {
    path: [
      [0, 'feeB'],
      [3.0, 'chainA', 'inOutCubic'],
      [14, 'chainB', 'linear'],
    ],
    lights: [
      [['tick'], 0.8, 1.0],
      [['Planner', 'actions', 'hold'], 1.8, 1.6],
      [['findChains'], 3.4, 3.6],
      [['bookChance'], 7.6, 4.4],
    ],
    traffic: 'chains',
    card: [chainPanel, AREAS.left],
    focus: { from: FEE_BLOCKS, to: CHAIN_BLOCKS, until: 3.0, dim: () => DIM },
  },
  learning: {
    path: [
      [0, 'chainB'],
      [2.6, 'learnA', 'inOutCubic'],
      [11, 'learnB', 'linear'],
    ],
    lights: [
      [['observe'], 0.5, 1.2],
      [['Demand', 'demandLearn', 'belief'], 1.4, 3.4],
      [['Supply', 'supplyLearn', 'ratio'], 5.8, 4.0],
    ],
    traffic: 'learning',
    sparks: [0.5, 11],
    card: [learnPanel, AREAS.right],
    focus: { from: CHAIN_BLOCKS, to: LEARN_BLOCKS, until: 2.6, dim: () => DIM },
  },
  out: {
    path: [
      [0, 'learnB'],
      [3.6, 'lean', 'inOutCubic'],
      [5.8, 'lingerOut', 'linear'],
      [10, 'whole', 'inOutQuad'],
    ],
    angle: (t) => {
      const rise = ease.inOutCubic(progress(t, 6, 10))
      return [deg(32) * rise, deg(6) * rise]
    },
    traffic: 'story',
    sparks: [7.4, 10],
    outer: [3.5, 10],
    focus: { from: LEARN_BLOCKS, to: LEAN, until: 1.8, dim: (t) => DIM * (1 - ease.inOutCubic(progress(t, 0, 1.8))) },
  },
  traffic: {
    path: [
      [0, 'whole'],
      [6, 'wide', 'linear'],
    ],
    angle: (t) => [deg(32 + t * 0.6), deg(6 + t * 2.2)],
    traffic: 'busy',
    sparks: [0, 6],
    outer: [-6, 6],
  },
}

/** The camera at local time t: the point it looks at, the height of the ground in the picture, the tilt, the turn. */
function frameAt(plan, t) {
  const keys = plan.path
  let i = 1
  while (i < keys.length - 1 && t > keys[i][0]) i++
  const [t0, from] = keys[i - 1]
  const [t1, to, easing] = keys[i]
  const k = ease[easing](progress(t, t0, t1))
  const a = SPOTS[from]
  const b = SPOTS[to]
  const height = Math.exp(lerp(Math.log(a.height), Math.log(b.height), k))
  const centre = [lerp(a.centre[0], b.centre[0], k), lerp(a.centre[1], b.centre[1], k)]
  const [tilt, turn] = plan.angle?.(t) ?? [0, 0]
  return { centre, height, tilt, turn }
}

/**
 * The vehicles of a part, as [kind, the time it reaches its stop, options]: a request stops at the price, an order
 * and a chain's first car at the fee; a chain's other cars wait behind their first.
 */
function schedule(name) {
  const list = []
  const request = (arrive, wait = 0.3) => list.push(['request', arrive, { wait }])
  const order = (arrive, wait = 0.6) => list.push(['order', arrive, { wait }])
  const chain = (arrive, wait, cars, group) => {
    list.push(['chain', arrive, { wait, group }])
    for (let i = 1; i < cars; i++) list.push(['chain', arrive + (i * 3.4) / SPEED, { gap: 3.4, group }])
  }
  if (name === 'light') {
    for (let at = -6; at < 10.5; at += 1.3) request(at)
    for (let at = -4; at < 10.5; at += 3.9) order(at)
  } else if (name === 'fees') {
    for (const at of [1.4, 5.0, 8.6, 12.0]) order(at, at < 11 ? 2.4 : 1.4)
    for (let at = -5; at < 14; at += 1.6) request(at, 0.25)
  } else if (name === 'chains') {
    chain(2.2, 3.0, 4, 'a')
    chain(8.6, 2.6, 3, 'b')
    for (let at = -5; at < 14; at += 1.6) request(at, 0.25)
  } else if (name === 'learning') {
    for (let at = -4; at < 11; at += 1.2) request(at, 0.4)
    for (const at of [2.0, 6.0, 9.4]) order(at, 0.6)
  } else if (name === 'story') {
    request(0.9, 0.7)
    order(2.3, 1.0)
    request(2.7, 0.6)
    chain(4.6, 1.3, 3, 'a')
    for (let at = 5.4; at < 10.5; at += 0.8) request(at, 0.3)
    for (let at = 6.2; at < 10.5; at += 2.0) order(at, 0.5)
  } else if (name === 'busy') {
    for (let at = -8; at < 6.5; at += 0.45) request(at, 0.15)
    for (let at = -7; at < 6.5; at += 1.2) order(at, 0.4)
    chain(1.0, 0.8, 3, 'busy')
    chain(4.2, 0.8, 3, 'late')
  }
  return list
}

const SOUNDS = {
  in: () => [
    ...[1.0, 1.7, 2.4, 3.0, 3.4, 8.5, 9.5, 10.5].map((at) => ({ at, sound: 'tap', gain: 0.14 })),
    { at: 0, sound: 'whoosh', length: 1.0, from: 200, to: 1400, gain: 0.2 },
    { at: 7.3, sound: 'whoosh', length: 0.6, from: 400, to: 2200, gain: 0.16 },
    { at: 11.5, sound: 'riser', length: 3.1, gain: 0.12 },
    { at: 14.6, sound: 'ding', gain: 0.24 },
    ...Array.from({ length: 13 }, (_, i) => ({ at: 3.4 + i * 0.32, sound: 'tap', gain: 0.04 })),
  ],
  fees: () => [
    { at: 0, sound: 'whoosh', length: 0.9, from: 300, to: 1800, gain: 0.16 },
    ...[2.3, 3.2, 4.0, 4.6].map((at) => ({ at, sound: 'slot', length: 0.2, gain: 0.07 })),
    { at: 7.8, sound: 'ding', gain: 0.18 },
  ],
  chains: () => [
    { at: 0, sound: 'whoosh', length: 0.9, from: 300, to: 1800, gain: 0.16 },
    ...[1.4, 2.15, 2.9, 3.65].map((at) => ({ at, sound: 'tap', gain: 0.12 })),
    { at: 5.2, sound: 'kaching', gain: 0.14 },
    { at: 5.4, sound: 'engine', length: 1.6, from: 70, to: 170, gain: 0.08 },
    { at: 9.8, sound: 'ding', gain: 0.16 },
  ],
  learning: () => [
    { at: 0, sound: 'whoosh', length: 0.9, from: 300, to: 1800, gain: 0.16 },
    ...[1.4, 2.3, 3.2].map((at) => ({ at, sound: 'ding', gain: 0.12 })),
    { at: 5.9, sound: 'twinkle', gain: 0.14 },
  ],
  out: () => [
    { at: 0.9, sound: 'kaching', gain: 0.12 },
    { at: 2.3, sound: 'slot', length: 0.25, gain: 0.07 },
    { at: 3.3, sound: 'ding', gain: 0.16 },
    { at: 4.6, sound: 'slot', length: 0.3, gain: 0.07 },
    { at: 5.8, sound: 'ding', gain: 0.16 },
    { at: 0.5, sound: 'engine', length: 2.5, from: 60, to: 140, gain: 0.07 },
    { at: 4.0, sound: 'engine', length: 3, from: 70, to: 170, gain: 0.08 },
    { at: 6.0, sound: 'whoosh', length: 1.4, from: 200, to: 1400, gain: 0.22 },
    { at: 7.0, sound: 'engine', length: 3, from: 80, to: 200, gain: 0.1 },
  ],
  traffic: () => [{ at: 0, sound: 'engine', length: 5.9, from: 90, to: 220, gain: 0.12 }],
}

export default {
  sounds(segment) {
    return [...voiceCues(segment), ...SOUNDS[segment.direction]()]
  },

  build(segment) {
    const plan = PLANS[segment.direction]
    const scene = new THREE.Scene()
    scene.background = new THREE.Color(THEME.ground)
    scene.fog = new THREE.Fog(THEME.ground, 400, 900)
    scene.add(new THREE.HemisphereLight('#ffffff', '#334155', 1.5))
    const sun = new THREE.DirectionalLight('#ffffff', 1.1)
    sun.position.set(-40, 120, 70)
    scene.add(sun)
    const map = buildMap(scene)
    const camera = new THREE.PerspectiveCamera(FOV, 16 / 10, 0.5, 3000)
    const Y = map.heights

    // Dealers and drivers stand in Bahn's world, for when the camera tilts
    const crowd = [[character({ shirt: '#6b4a32', hair: 'mullet', mustache: true, chain: true }), 8, -73]]
    const shirts = ['#8d939b', '#5a7d9a', '#c0392b', '#7e57c2', '#2e8b57', '#d35400', '#3d5a8a']
    shirts.forEach((shirt, i) => {
      crowd.push([character({ shirt, hood: i % 2 === 0, beanie: i % 3 === 1 ? '#2b7de9' : null }), 34 + i * 4.4, -73])
    })
    for (const [person, x, z] of crowd) {
      person.root.scale.setScalar(1.8)
      person.root.position.set(x, Y.slab, z)
      pose(person, POSES.phone)
      scene.add(person.root)
    }

    // Events that run down from Bahn's world into TS:LEAN, in four colours: price requests, won orders, booked gigs
    // and deliveries
    const tokenRoute = polyline(joined(['events', 'stream', 'loop', 'calls'].map(road)))
    const kinds = ['#2563eb', '#dc2626', '#16a34a', '#b45309']
    const tokens = []
    if (plan.tokens) {
      for (let i = 0, at = plan.tokens[0]; at < plan.tokens[1]; i++, at += 0.32) {
        const token = chip(3.2, 1.3, CHIPS.event(kinds[i % kinds.length]))
        scene.add(token.mesh)
        tokens.push({ token, at })
      }
    }

    // The traffic on the main loop, in the order the vehicles set off
    const loop = routeOf('quote')
    const dPrice = loop.distanceOf(STOPS.price)
    const dFee = loop.distanceOf(STOPS.fee)
    const vehicles = schedule(plan.traffic).map(([kind, arrive, { wait = 0, gap, group }]) => {
      const at = kind === 'request' ? dPrice : dFee
      return {
        kind,
        start: arrive - at / SPEED,
        speed: SPEED,
        stops: wait > 0 ? [{ d: at, wait }] : [],
        gap,
        group,
        wait,
      }
    })
    vehicles.sort((a, b) => a.start - b.start)
    for (const v of vehicles) {
      const body = car({ color: v.kind === 'request' ? '#94a3b8' : '#ef4444' })
      body.root.scale.setScalar(0.7)
      body.root.visible = false
      scene.add(body.root)
      v.body = body
      v.lead = v.kind === 'order' || (v.kind === 'chain' && !v.gap)
      if (v.kind === 'request') {
        v.tag = chip(1.8, 1.8, CHIPS.price)
        v.tag.mesh.visible = false
        scene.add(v.tag.mesh)
      } else if (v.lead) {
        const driver = character({ shirt: '#5a7d9a', hood: true })
        driver.root.scale.setScalar(0.7)
        pose(driver, POSES.sit)
        driver.root.visible = false
        body.driver.add(driver.root)
        v.driver = driver
      }
    }
    const feeSign = chip(2.6, 1.9, CHIPS.fee, { level: 0 })
    feeSign.mesh.position.set(STOPS.fee[0], Y.road + 2.2, STOPS.fee[1] - 2.2)
    feeSign.mesh.visible = false
    scene.add(feeSign.mesh)
    const groups = [...new Set(vehicles.filter((v) => v.group).map((v) => v.group))]
    const chainSigns = new Map(
      groups.map((group) => {
        const sign = chip(2.8, 1.6, CHIPS.chain)
        sign.mesh.visible = false
        scene.add(sign.mesh)
        return [group, sign]
      }),
    )

    // Learning runs back from observe() to Demand and Supply
    const learnLine = polyline(LINES.find((l) => l.id === 'learn').points)
    const sparks = []
    if (plan.sparks) {
      for (let at = plan.sparks[0]; at < plan.sparks[1]; at += 0.3) {
        const spark = glowSprite('#86efac')
        spark.scale.setScalar(1.6)
        spark.visible = false
        scene.add(spark)
        sparks.push({ spark, at })
      }
    }
    // The outer lanes: finished weeks to the saved weeks, constants up from the analysis, runs from the simulator
    const outer = []
    if (plan.outer) {
      const [from, to] = plan.outer
      const weeks = routeOf('weeks')
      const constants = routeOf('constants')
      const seeds = routeOf('seeds')
      const rand = rng(51)
      for (let at = from; at < to; at += 0.6) {
        const p = chip(1.8, 1.8, CHIPS.week)
        scene.add(p.mesh)
        outer.push({ mesh: p.mesh, route: weeks, at, speed: 30, lift: Y.road + 0.6 })
      }
      for (let at = from; at < to; at += 0.8) {
        const p = chip(1.6, 1.6, CHIPS.constant)
        scene.add(p.mesh)
        outer.push({ mesh: p.mesh, route: constants, at, speed: 7, lift: Y.road + 0.6 })
      }
      for (let at = from; at < to; at += 0.7 + rand() * 0.3) {
        const ghost = car({ color: '#67e8f9', glass: 0.3 })
        ghost.root.scale.setScalar(0.7)
        scene.add(ghost.root)
        outer.push({ mesh: ghost.root, route: seeds, at, speed: 26, lift: Y.road, car: ghost })
      }
    }

    const place = (object, [x, z, heading], y) => {
      object.position.set(x, y, z)
      object.rotation.y = -heading
    }

    // The spotlight: everything but the focus's blocks dims; the camera looks straight down in a deep dive, so the
    // blocks' rect is a rect in the picture too
    const corner = new THREE.Vector3()
    const toScreen = (x, z) => {
      corner.set(x, Y.tile, z).project(camera)
      return [(corner.x + 1) * 960, (1 - corner.y) * 600]
    }
    function spotlight(g, t) {
      const { from, to, until, dim } = plan.focus
      const a = dim(t)
      if (a <= 0.005) return
      const k = ease.inOutCubic(progress(t, 0, until))
      camera.updateMatrixWorld()
      const [x0, y0] = toScreen(lerp(from[0], to[0], k), lerp(from[1], to[1], k))
      const [x1, y1] = toScreen(lerp(from[2], to[2], k), lerp(from[3], to[3], k))
      const hole = [Math.min(x0, x1), Math.min(y0, y1), Math.abs(x1 - x0), Math.abs(y1 - y0), 18]
      g.save()
      g.fillStyle = `rgba(5, 8, 16, ${a})`
      g.beginPath()
      g.rect(0, 0, 1920, 1200)
      g.roundRect(...hole)
      g.fill('evenodd')
      g.strokeStyle = `rgba(226, 232, 240, ${a * 0.3})`
      g.lineWidth = 2
      g.beginPath()
      g.roundRect(...hole)
      g.stroke()
      g.restore()
    }

    return {
      scene,
      camera,
      update(t) {
        const { centre, height, tilt, turn } = frameAt(plan, t)
        const distance = height / (2 * TAN)
        const lift = distance * Math.cos(tilt)
        const away = distance * Math.sin(tilt)
        camera.position.set(centre[0] + away * Math.sin(turn), lift, centre[1] + away * Math.cos(turn))
        camera.up.set(-Math.sin(turn), 0, -Math.cos(turn))
        camera.near = distance * 0.05
        camera.far = distance * 6
        camera.updateProjectionMatrix()
        camera.lookAt(centre[0], 0, centre[1])

        // the lights, and the chart
        for (const ids of Object.values(GROUPS)) for (const id of ids) map.highlight(id, 0)
        for (const [ids, at, hold] of plan.lights ?? []) {
          const a = pulse(t, at, hold)
          if (a > 0) for (const id of ids) map.highlight(id, a)
        }
        if (plan.chart) {
          map.highlight('bestPrice', progress(t, 11.4, 11.7) * (1 - progress(t, 14.2, 14.8)))
          map.chart(progress(t, ...plan.chart))
        } else map.chart(1)

        for (const { token, at } of tokens) {
          const age = t - at
          const d = age * 26
          token.mesh.visible = age >= 0 && d < tokenRoute.length
          if (!token.mesh.visible) continue
          const [x, z] = tokenRoute.at(d)
          token.mesh.position.set(x, Y.road + 0.5, z)
          token.mesh.material.opacity = Math.max(0, Math.min(1, age / 0.2, (tokenRoute.length - d) / 4))
        }

        // the traffic
        const where = queue(loop, vehicles, t)
        let waiting = null
        const middles = new Map()
        vehicles.forEach((v, i) => {
          const d = where[i]
          const on = d >= 0 && Number.isFinite(d)
          v.body.root.visible = on
          if (v.tag) v.tag.mesh.visible = false
          if (!on) return
          const spot = loop.at(d)
          place(v.body.root, spot, Y.road + 0.02)
          v.body.spin(d)
          const stopAt = v.stops[0]?.d ?? Infinity
          const arrive = reaches(stopAt, v)
          if (v.tag && d >= stopAt - 0.05 && t >= arrive - 0.02) {
            v.tag.mesh.visible = true
            v.tag.mesh.scale.setScalar(Math.max(0.01, pop(t, arrive, 0.25)))
            v.tag.mesh.position.set(spot[0], Y.road + 2.4, spot[1] - 2.0)
          }
          if (v.driver) {
            const leaves = arrive + v.wait
            v.driver.root.visible = t >= leaves - 0.25
            v.driver.root.scale.setScalar(0.7 * Math.max(0.01, pop(t, leaves - 0.25, 0.25)))
          }
          if (v.lead && Math.abs(d - dFee) < 0.06) waiting = { k: progress(t, arrive, arrive + v.wait), arrive }
          if (v.group && v.gap && !middles.has(v.group)) middles.set(v.group, spot)
        })
        feeSign.mesh.visible = waiting !== null
        if (waiting) {
          feeSign.set({ level: Math.min(3, Math.floor(waiting.k * 4)) })
          feeSign.mesh.scale.setScalar(Math.max(0.01, pop(t, waiting.arrive, 0.2)))
        }
        // a chain's sign comes up when its one driver has booked and its cars set off together
        for (const [group, sign] of chainSigns) {
          const lead = vehicles.find((v) => v.group === group && !v.gap)
          const setOff = reaches(dFee, lead) + lead.wait - 0.2
          const middle = middles.get(group)
          sign.mesh.visible = t >= setOff && Boolean(middle)
          if (!sign.mesh.visible) continue
          sign.mesh.position.set(middle[0], Y.road + 3, middle[1] - 2.0)
          sign.mesh.scale.setScalar(Math.max(0.01, pop(t, setOff, 0.25)))
        }

        for (const { spark, at } of sparks) {
          const d = (t - at) * 12
          spark.visible = d >= 0 && d < learnLine.length
          if (!spark.visible) continue
          const [x, z] = learnLine.at(d)
          spark.position.set(x, Y.road + 0.4, z)
        }
        for (const item of outer) {
          const d = (t - item.at) * item.speed
          item.mesh.visible = d >= 0 && d < item.route.length
          if (!item.mesh.visible) continue
          const spot = item.route.at(d)
          if (item.car) {
            place(item.mesh, spot, item.lift)
            item.car.spin(d)
          } else item.mesh.position.set(spot[0], item.lift, spot[1])
        }
      },
      overlay(g, t) {
        if (plan.focus) spotlight(g, t)
        if (plan.card) plan.card[0](g, t, segment.duration, plan.card[1])
        captions(g, t, segment)
      },
    }
  },
}
