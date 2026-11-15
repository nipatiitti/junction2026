import * as THREE from 'three'
import { ease, lerp, progress } from '../../kit/anim.js'
import { car } from '../../kit/car.js'
import { character, POSES, pose } from '../../kit/character.js'
import { flash, shake, speedLines, vignette } from '../../kit/fx.js'
import { FRAMES, ROADS, ROUTES } from '../diagram.js'
import { captions, voiceCues } from '../lines.js'
import { buildMap, THEME } from '../map.js'
import { joined, polyline } from '../traffic.js'

// The "I am speed" meme as the way into ts:lean (our own version: our car, our voice, no film): a second of dark with
// the voice, three seconds in a red car racing down ts:lean's lanes through stream(), playLive() and handle() onto the
// lane over bestPrice(), then a fast zoom out that ends exactly on the first frame of the zoom in. Beats (local s):
//   0–1.0 dark, "Focus." · 1.0–4.0 the chase camera behind the car, speed lines · 4.0–5.5 the fast zoom out

const DARK = 1.0
const RACE = 4.0
const END = 5.5
const SPEED = 38 // so that the car reaches the lane over bestPrice() just as the race ends
const deg = THREE.MathUtils.degToRad

const road = (id) => ROADS.find((r) => r.id === id)

/** The whole diagram as the zoom in starts: tilted 28° and turned −7° (views/zoom.js). */
function wholeView() {
  const { centre, height } = FRAMES.whole
  const distance = height / (2 * Math.tan(deg(15)))
  const tilt = deg(28)
  const turn = deg(-7)
  const away = distance * Math.sin(tilt)
  return {
    position: new THREE.Vector3(
      centre[0] + away * Math.sin(turn),
      distance * Math.cos(tilt),
      centre[1] + away * Math.cos(turn),
    ),
    look: new THREE.Vector3(centre[0], 0, centre[1]),
    up: new THREE.Vector3(-Math.sin(turn), 0, -Math.cos(turn)),
    fov: 30,
  }
}

export default {
  sounds(segment) {
    return [
      ...voiceCues(segment),
      { at: 0.85, sound: 'engine', length: 1.2, from: 60, to: 260, gain: 0.3 },
      { at: DARK, sound: 'whoosh', length: 0.5, from: 300, to: 3000, gain: 0.35 },
      ...[1.7, 2.4, 3.1, 3.7].map((at) => ({ at, sound: 'whoosh', length: 0.35, from: 600, to: 4000, gain: 0.22 })),
      { at: 3.0, sound: 'riser', length: 1.0, gain: 0.16 },
      { at: RACE, sound: 'sonicBoom', gain: 0.5 },
      { at: RACE, sound: 'whoosh', length: 1.3, from: 200, to: 2600, gain: 0.3 },
    ]
  },

  build(segment) {
    const scene = new THREE.Scene()
    scene.background = new THREE.Color(THEME.ground)
    scene.fog = new THREE.Fog(THEME.ground, 400, 900)
    scene.add(new THREE.HemisphereLight('#ffffff', '#334155', 1.5))
    const sun = new THREE.DirectionalLight('#ffffff', 1.1)
    sun.position.set(-40, 120, 70)
    scene.add(sun)
    const map = buildMap(scene)
    map.chart(1)
    const Y = map.heights

    const route = polyline(joined(ROUTES.quote.map(road)))
    const hero = car({ color: '#ef4444' })
    hero.root.scale.setScalar(0.7)
    const driver = character({ shirt: '#d6262c', hood: true, sunglasses: true })
    driver.root.scale.setScalar(0.7)
    pose(driver, POSES.sit)
    hero.driver.add(driver.root)
    scene.add(hero.root)

    const camera = new THREE.PerspectiveCamera(55, 16 / 10, 0.1, 3000)
    const end = wholeView()
    const look = new THREE.Vector3()
    const ahead = (d, by) => {
      const [x, z] = route.at(d + by)
      return new THREE.Vector3(x, 0, z)
    }
    /** The chase camera at distance d along the route: behind and above the car, looking down the lane ahead. */
    const chase = (d) => {
      const [x, z] = route.at(d)
      const back = ahead(d, -6)
      const front = ahead(d, 6)
      const dir = front.clone().sub(back).setY(0).normalize()
      return {
        position: new THREE.Vector3(x, Y.road + 3.2, z).addScaledVector(dir, -7.5),
        look: new THREE.Vector3(x, Y.road + 0.6, z).addScaledVector(dir, 9),
        up: new THREE.Vector3(0, 1, 0),
        fov: 55,
      }
    }
    const distanceAt = (t) => SPEED * Math.max(0, Math.min(t, RACE) - DARK)

    return {
      scene,
      camera,
      update(t) {
        const d = distanceAt(t)
        const [x, z, heading] = route.at(d)
        hero.root.position.set(x, Y.road + 0.02, z)
        hero.root.rotation.y = -heading
        hero.spin(d)
        const from = chase(distanceAt(Math.min(t, RACE)))
        const k = ease.inOutCubic(progress(t, RACE, END))
        const at = from.position.clone().lerp(end.position, ease.inCubic(Math.min(1, k * 1.15)))
        // the height climbs on a log scale, so the zoom out reads as one fast, even pull
        const height = Math.exp(lerp(Math.log(from.position.y), Math.log(end.position.y), k))
        at.y = height
        const [sx, sy] = shake(t, DARK, RACE - DARK, 0.12, { seed: 4 })
        camera.position.set(at.x + sx, at.y + sy, at.z)
        look.copy(from.look).lerp(end.look, k)
        camera.up.copy(from.up).lerp(end.up, k).normalize()
        camera.fov = lerp(from.fov, end.fov, k)
        camera.near = Math.max(0.1, height * 0.02)
        camera.far = Math.max(400, height * 6)
        camera.updateProjectionMatrix()
        camera.lookAt(look)
      },
      overlay(g, t) {
        if (t < DARK) {
          g.fillStyle = '#000000'
          g.fillRect(0, 0, 1920, 1200)
        } else {
          const race = progress(t, DARK, DARK + 0.3) * (1 - progress(t, RACE, RACE + 0.6))
          speedLines(g, t, 0.75 * race, { seed: 9, count: 110 })
          vignette(g, 0.55 * race)
          flash(g, 0.6 * (1 - progress(t, DARK, DARK + 0.25)), '0,0,0')
          flash(g, 0.35 * (1 - progress(t, RACE, RACE + 0.25)) * (t >= RACE ? 1 : 0))
        }
        captions(g, t, segment)
      },
    }
  },
}
