import * as THREE from 'three'
import { progress } from '../kit/anim.js'
import { flash, speedLines } from '../kit/fx.js'
import { rng } from '../kit/rng.js'
import { drawCard } from '../kit/text.js'

// A title card between scenes: streaks fly at the camera, faster at every level, and the MACH number slams in.
// The segment in timeline.js gives the level (1–4), the big number and the small line.

const SPEED = [45, 90, 170, 340]
const BACKGROUND = ['#1b060b', '#220610', '#2a0714', '#000000']
const LENGTH = 220
const COUNT = 320

export default {
  build(segment) {
    const level = segment.level ?? 1
    const rand = rng(100 + level)
    const scene = new THREE.Scene()
    scene.background = new THREE.Color(BACKGROUND[level - 1])
    const camera = new THREE.PerspectiveCamera(70, 9 / 16, 0.1, 400)
    const streaks = []
    const object = new THREE.InstancedMesh(
      new THREE.BoxGeometry(0.06, 0.06, 1),
      new THREE.MeshBasicMaterial({ color: '#ffffff', toneMapped: false }),
      COUNT,
    )
    object.frustumCulled = false
    const color = new THREE.Color()
    for (let i = 0; i < COUNT; i++) {
      const a = rand() * Math.PI * 2
      const r = rand.range(2.5, 22)
      streaks.push({ x: Math.cos(a) * r, y: Math.sin(a) * r, z: rand() * LENGTH, length: rand.range(2, 7) })
      object.setColorAt(i, color.set(rand() < 0.3 ? '#ff2a3a' : '#ffffff'))
    }
    scene.add(object)
    const dummy = new THREE.Object3D()
    return {
      scene,
      camera,
      update(t) {
        camera.rotation.set(0, 0, t * 0.25 * level)
        for (let i = 0; i < COUNT; i++) {
          const s = streaks[i]
          dummy.position.set(s.x, s.y, -LENGTH + ((s.z + SPEED[level - 1] * t) % LENGTH))
          dummy.scale.set(1, 1, s.length * (1 + level * 0.8))
          dummy.updateMatrix()
          object.setMatrixAt(i, dummy.matrix)
        }
        object.instanceMatrix.needsUpdate = true
      },
      overlay(g, t) {
        speedLines(g, t, 0.25 + level * 0.15, { seed: 20 + level })
        drawCard(g, t, segment.duration, segment.big, segment.small)
        if (level === 4) flash(g, progress(t, segment.duration - 0.3, segment.duration))
      },
    }
  },
}
