import * as THREE from 'three'
import { ease, lerp, pop, progress } from '../../kit/anim.js'
import { car } from '../../kit/car.js'
import { character, POSES, pose } from '../../kit/character.js'
import { glowSprite } from '../../kit/fx.js'
import { rng } from '../../kit/rng.js'
import { liveTexture } from '../../kit/sign.js'
import { FRAMES, GROUPS, LINES, ROADS, ROUTES, STOPS } from '../diagram.js'
import { captions, voiceCues } from '../lines.js'
import { buildMap, MONO, THEME } from '../map.js'
import { joined, polyline, queue, reaches } from '../traffic.js'

// The solution, as the code: one view for both zooms (the segment's `direction`). In, 15 s: from a tilted view of the
// whole diagram down to only TS:LEAN at 7.5 and into bestPrice() at 15, with the blocks lighting up as the voice names
// them and the events running in. Out, 10 s: back up from bestPrice() to the whole diagram while cars and drivers
// drive its lanes the way the code moves them; the camera tilts again from 6.0 so the traffic reads as 3D. The texts
// are in timeline.js, the diagram in diagram.js. Beats (local seconds):
//   in   0–4.0 the whole map, the systems light up in turn · 3.4–7.6 event tokens run down into TS:LEAN ·
//        7.5 only TS:LEAN · 8.4–11.4 the price, the fee and the chains light up · 11.5–14.8 the chart draws in,
//        14.6 its peak is marked
//   out  0.9 a request stops at bestPrice() for its price · 2.3 an order stops at stepped() for its fee and gets a
//        driver · 4.6 a chain of three cars waits for its one driver · 6.6 learning runs back to Demand and Supply ·
//        6.0 the tilt starts; weeks, constants and simulator runs fill the outer lanes

const FOV = 30
const TAN = Math.tan(THREE.MathUtils.degToRad(FOV / 2))
const SPEED = 30 // world units a second on the main lanes
const PRICE_TAG = '1.35 × list'
const FEES = ['0.88 × typical', '1.05 × typical', '1.25 × typical']
const deg = THREE.MathUtils.degToRad

const road = (id) => ROADS.find((r) => r.id === id)
const routeOf = (name) => polyline(joined(ROUTES[name].map(road)))

/** A light that rises over 0.15 s at t0, holds, and fades over half a second. */
const pulse = (t, t0, hold = 0.9) => progress(t, t0, t0 + 0.15) * (1 - progress(t, t0 + 0.15 + hold, t0 + 0.65 + hold))

/** A flat plate with text on a coloured ground, for tokens, price tags and signs; set its text with .set(text). */
function plate(text, { bg = '#f8fafc', fg = '#0f172a', size = 0.9, w = 7, h = 1.6 }) {
  const painter = liveTexture(Math.round(w * 64), Math.round(h * 64), (g, state, cw, ch) => {
    g.clearRect(0, 0, cw, ch)
    g.fillStyle = bg
    g.beginPath()
    g.roundRect(2, 2, cw - 4, ch - 4, ch * 0.28)
    g.fill()
    g.fillStyle = fg
    g.font = `700 ${Math.round(size * 64)}px ${MONO}`
    g.textAlign = 'center'
    g.textBaseline = 'middle'
    g.fillText(state.text, cw / 2, ch / 2 + 2)
  })
  painter.set({ text })
  const mesh = new THREE.Mesh(
    new THREE.PlaneGeometry(w, h),
    new THREE.MeshBasicMaterial({ map: painter.texture, transparent: true, depthWrite: false, toneMapped: false }),
  )
  mesh.rotation.x = -Math.PI / 2
  mesh.renderOrder = 5
  return { mesh, set: (value) => painter.set({ text: value }) }
}

/**
 * The camera at local time t: the point it looks at, the height of the ground in the picture, its tilt from straight
 * down and its turn. Keys are [time, frame, easing into it]: the height moves between them on a log scale, so that
 * every doubling of the zoom takes the same time. The zoom in comes down to TS:LEAN by 7.5, lingers there while the
 * three decisions light up, and dives into bestPrice() from 11; the zoom out runs the other way, lingering on TS:LEAN
 * while the chain waits for its driver.
 */
const PATHS = {
  in: [
    [0, 'whole'],
    [7.5, 'lean', 'inOutQuad'],
    [11, 'linger', 'linear'],
    [15, 'key', 'inOutCubic'],
  ],
  out: [
    [0, 'key'],
    [3.6, 'lean', 'inOutCubic'],
    [5.8, 'lingerOut', 'linear'],
    [10, 'whole', 'inOutQuad'],
  ],
}
const SPOTS = {
  ...FRAMES,
  // TS:LEAN whole between the chapter tag and the subtitles, so the lit blocks are never under them
  linger: { centre: [0, -0.5], height: FRAMES.lean.height * 0.97 },
  lingerOut: { centre: [0, -1], height: FRAMES.lean.height * 1.08 },
}

function frameAt(direction, t) {
  const keys = PATHS[direction]
  let i = 1
  while (i < keys.length - 1 && t > keys[i][0]) i++
  const [t0, from] = keys[i - 1]
  const [t1, to, easing] = keys[i]
  const k = ease[easing](progress(t, t0, t1))
  const a = SPOTS[from]
  const b = SPOTS[to]
  const height = Math.exp(lerp(Math.log(a.height), Math.log(b.height), k))
  const centre = [lerp(a.centre[0], b.centre[0], k), lerp(a.centre[1], b.centre[1], k)]
  if (direction === 'in') {
    const level = ease.inOutCubic(progress(t, 0, 6.5))
    return { centre, height, tilt: deg(28) * (1 - level), turn: deg(-7) * (1 - level) }
  }
  const rise = ease.inOutCubic(progress(t, 6, 10))
  return { centre, height, tilt: deg(32) * rise, turn: deg(6) * rise }
}

/** Highlights of the zoom in: [group, time] as the voice names each. */
const LIGHTS_IN = [
  ['touches', 1.0],
  ['world', 1.7],
  ['harness', 2.4],
  ['ops', 3.0],
  ['saved', 3.4],
  ['price', 8.5],
  ['fee', 9.5],
  ['chains', 10.5],
]

export default {
  sounds(segment) {
    const cues = voiceCues(segment)
    if (segment.direction === 'in') {
      for (const [, at] of LIGHTS_IN) cues.push({ at, sound: 'tap', gain: 0.14 })
      cues.push(
        { at: 0, sound: 'whoosh', length: 1.0, from: 200, to: 1400, gain: 0.2 },
        { at: 7.3, sound: 'whoosh', length: 0.6, from: 400, to: 2200, gain: 0.16 },
        { at: 11.5, sound: 'riser', length: 3.1, gain: 0.12 },
        { at: 14.6, sound: 'ding', gain: 0.24 },
      )
      for (let at = 3.4; at < 7.6; at += 0.32) cues.push({ at, sound: 'tap', gain: 0.04 })
    } else {
      cues.push(
        { at: 0.9, sound: 'kaching', gain: 0.12 },
        { at: 2.3, sound: 'slot', length: 0.25, gain: 0.07 },
        { at: 2.7, sound: 'slot', length: 0.25, gain: 0.07 },
        { at: 3.3, sound: 'ding', gain: 0.16 },
        { at: 4.6, sound: 'slot', length: 0.3, gain: 0.07 },
        { at: 5.8, sound: 'ding', gain: 0.16 },
        { at: 0.5, sound: 'engine', length: 2.5, from: 60, to: 140, gain: 0.07 },
        { at: 4.0, sound: 'engine', length: 3, from: 70, to: 170, gain: 0.08 },
        { at: 6.0, sound: 'whoosh', length: 1.4, from: 200, to: 1400, gain: 0.22 },
        { at: 7.0, sound: 'engine', length: 3, from: 80, to: 200, gain: 0.1 },
      )
    }
    return cues
  },

  build(segment) {
    const direction = segment.direction
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

    // Zoom in: event tokens that run down from Bahn's world into TS:LEAN
    const tokenRoute = polyline(joined(['events', 'stream', 'loop', 'calls'].map(road)))
    const kinds = [
      ['price_request', '#2563eb'],
      ['order_won', '#dc2626'],
      ['gig_booked', '#16a34a'],
      ['delivered', '#b45309'],
    ]
    const tokens = []
    if (direction === 'in') {
      for (let i = 0, at = 3.4; at < 7.6; i++, at += 0.32) {
        const [text, bg] = kinds[i % kinds.length]
        const token = plate(text, { bg, fg: '#ffffff', w: 7.6, h: 1.5 })
        scene.add(token.mesh)
        tokens.push({ token, at })
      }
    }

    // Zoom out: the traffic on the main loop, in the order the vehicles set off
    const loop = routeOf('quote')
    const dPrice = loop.distanceOf(STOPS.price)
    const dFee = loop.distanceOf(STOPS.fee)
    const vehicles = []
    const add = (kind, arrive, { wait = 0, gap } = {}) => {
      const at = kind === 'request' ? dPrice : dFee
      const stops = wait > 0 ? [{ d: at, wait }] : []
      vehicles.push({ kind, start: arrive - at / SPEED, speed: SPEED, stops, gap, wait })
    }
    if (direction === 'out') {
      add('request', 0.9, { wait: 0.7 })
      add('order', 2.3, { wait: 1.0 })
      add('request', 2.7, { wait: 0.6 })
      add('chain', 4.6, { wait: 1.3 })
      add('chain', 4.6 + 3.4 / SPEED, { gap: 3.4 })
      add('chain', 4.6 + 6.8 / SPEED, { gap: 3.4 })
      add('request', 5.4, { wait: 0.5 })
      add('request', 6.4, { wait: 0.5 })
      add('order', 7.4, { wait: 0.8 })
      add('request', 8.2, { wait: 0.4 })
      add('request', 8.8, { wait: 0.4 })
      add('order', 9.4, { wait: 0.5 })
      add('request', 9.9, { wait: 0.3 })
    }
    vehicles.sort((a, b) => a.start - b.start)
    for (const v of vehicles) {
      const body = car({ color: v.kind === 'request' ? '#94a3b8' : '#ef4444' })
      body.root.scale.setScalar(0.7)
      body.root.visible = false
      scene.add(body.root)
      v.body = body
      if (v.kind === 'request') {
        v.tag = plate(PRICE_TAG, { bg: '#16a34a', fg: '#ffffff', w: 5.6, h: 1.4 })
        v.tag.mesh.visible = false
        scene.add(v.tag.mesh)
      } else if (v.kind === 'order' || (v.kind === 'chain' && !v.gap)) {
        const driver = character({ shirt: '#5a7d9a', hood: true })
        driver.root.scale.setScalar(0.7)
        pose(driver, POSES.sit)
        driver.root.visible = false
        body.driver.add(driver.root)
        v.driver = driver
      }
    }
    const feeSign = plate(FEES[0], { w: 8.4, h: 1.6 })
    feeSign.mesh.position.set(STOPS.fee[0], Y.road + 2.2, STOPS.fee[1] - 2.6)
    feeSign.mesh.visible = false
    scene.add(feeSign.mesh)
    const chainSign = plate('chain · 1 driver', { bg: '#fbbf24', fg: '#0f172a', w: 9, h: 1.7 })
    chainSign.mesh.visible = false
    scene.add(chainSign.mesh)

    // learning runs back from observe() to Demand and Supply; the outer lanes fill once the view is wide
    const learnLine = polyline(LINES.find((l) => l.id === 'learn').points)
    const sparks = []
    if (direction === 'out') {
      for (let at = 7.6; at < 10; at += 0.3) {
        const spark = glowSprite('#86efac')
        spark.scale.setScalar(1.6)
        spark.visible = false
        scene.add(spark)
        sparks.push({ spark, at })
      }
    }
    const outer = []
    if (direction === 'out') {
      const weeks = routeOf('weeks')
      const constants = routeOf('constants')
      const seeds = routeOf('seeds')
      const rand = rng(51)
      for (let at = 4.5; at < 10; at += 0.6) {
        const p = plate('week', { bg: '#a78bfa', fg: '#0f172a', w: 4.2, h: 1.5 })
        scene.add(p.mesh)
        outer.push({ mesh: p.mesh, route: weeks, at, speed: 30, lift: Y.road + 0.6 })
      }
      const names = ['noise 0.11', 'taxLoad 0.47', 'order.json']
      for (let i = 0, at = 5.5; at < 10; i++, at += 0.8) {
        const p = plate(names[i % names.length], { bg: '#facc15', fg: '#0f172a', w: 6.6, h: 1.4 })
        scene.add(p.mesh)
        outer.push({ mesh: p.mesh, route: constants, at, speed: 7, lift: Y.road + 0.6 })
      }
      for (let at = 5.0; at < 10; at += 0.8 + rand() * 0.3) {
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

    return {
      scene,
      camera,
      update(t) {
        const { centre, height, tilt, turn } = frameAt(direction, t)
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
        if (direction === 'in') {
          for (const [group, at] of LIGHTS_IN) {
            const a = pulse(t, at, ['price', 'fee', 'chains'].includes(group) ? 1.1 : 0.7)
            if (a > 0) for (const id of GROUPS[group]) map.highlight(id, a)
          }
          map.highlight('bestPrice', progress(t, 11.4, 11.7) * (1 - progress(t, 14.2, 14.8)))
          map.chart(progress(t, 11.6, 14.8))
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
        let chainMiddle = null
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
            v.tag.mesh.position.set(spot[0], Y.road + 2.4, spot[1] - 2.2)
          }
          if (v.driver) {
            const leaves = arrive + v.wait
            v.driver.root.visible = t >= leaves - 0.25
            v.driver.root.scale.setScalar(0.7 * Math.max(0.01, pop(t, leaves - 0.25, 0.25)))
          }
          if ((v.kind === 'order' || (v.kind === 'chain' && !v.gap)) && Math.abs(d - dFee) < 0.06)
            waiting = { k: progress(t, arrive, arrive + v.wait), v, arrive }
          if (v.kind === 'chain' && v.gap && !chainMiddle) chainMiddle = spot
        })
        feeSign.mesh.visible = waiting !== null
        if (waiting) {
          feeSign.set(FEES[Math.min(FEES.length - 1, Math.floor(waiting.k * FEES.length))])
          feeSign.mesh.scale.setScalar(Math.max(0.01, pop(t, waiting.arrive, 0.2)))
        }
        // the chain's sign comes up when its one driver has booked and the cars set off together
        const lead = vehicles.find((v) => v.kind === 'chain' && !v.gap)
        const setOff = lead ? reaches(dFee, lead) + lead.wait - 0.2 : Infinity
        const chainOn = t >= setOff && chainMiddle
        chainSign.mesh.visible = Boolean(chainOn)
        if (chainOn) {
          chainSign.mesh.position.set(chainMiddle[0] - 2.2, Y.road + 3, chainMiddle[1] - 2.4)
          chainSign.mesh.scale.setScalar(Math.max(0.01, pop(t, setOff, 0.25)))
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
        captions(g, t, segment)
      },
    }
  },
}
