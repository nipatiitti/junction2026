import * as THREE from 'three'
import { renderMix } from './audio/mix.js'
import { cueSheet, voiceNames } from './audio/score.js'
import { exportMp4 } from './export.js'
import { drawHeader, drawSafeAreas } from './kit/text.js'
import { FPS, HEADER, HEIGHT, SEGMENTS, WIDTH } from './timeline.js'
import { VIEWS } from './views/index.js'

// The player: builds each view when it is first needed, draws any time of the video, plays it with its sound,
// seeks and exports. The view and the time live in the address (#view=scene1&t=3.200), so a reload comes back to
// the same frame. The sound of the whole video is rendered once when the page loads (see audio/), and the same
// sound plays in the preview and goes into the MP4.

const $ = (id) => document.getElementById(id)
const out = $('out')
const g = out.getContext('2d')
const status = (text) => {
  $('status').textContent = text
}

const glCanvas = document.createElement('canvas')
const renderer = new THREE.WebGLRenderer({ canvas: glCanvas, antialias: true, preserveDrawingBuffer: true })
renderer.setPixelRatio(1)
renderer.setSize(WIDTH, HEIGHT, false)
renderer.shadowMap.enabled = true
renderer.shadowMap.type = THREE.PCFShadowMap
renderer.toneMapping = THREE.ACESFilmicToneMapping
renderer.toneMappingExposure = 1.05

let total = 0
const segments = SEGMENTS.map((segment) => {
  const placed = { ...segment, start: total }
  total += segment.duration
  return placed
})

const built = new Map()
function view(segment) {
  if (!built.has(segment.id)) built.set(segment.id, VIEWS[segment.view].build(segment))
  return built.get(segment.id)
}

/** Draws the frame at `time` (seconds from the start of the video) on the output canvas. */
function draw(time, { guides = true } = {}) {
  const segment = segments.find((s) => time < s.start + s.duration) ?? segments.at(-1)
  const t = Math.min(Math.max(time - segment.start, 0), segment.duration - 1e-4)
  const v = view(segment)
  v.update(t)
  renderer.render(v.scene, v.camera)
  g.drawImage(glCanvas, 0, 0)
  v.overlay?.(g, t)
  drawHeader(g, HEADER)
  if (guides && $('safe').checked) drawSafeAreas(g)
  return { segment, t }
}

const state = { view: 'all', time: 0, playing: false }
let dirty = true
let exporting = false

function range() {
  if (state.view === 'all') return [0, total]
  const segment = segments.find((s) => s.id === state.view)
  return [segment.start, segment.start + segment.duration]
}

// Sound: the mix of the whole video, and the source that plays it from the current time.
let mix = null
let audio = null
let sound = null

async function prepareSound() {
  status('sound: rendering…')
  const cues = cueSheet(segments)
  const files = await fetch('/voices')
    .then((response) => response.json())
    .catch(() => [])
  const voices = new Map()
  for (const name of voiceNames(cues)) {
    const file = files.find((f) => f.replace(/\.[^.]+$/, '') === name)
    if (file) voices.set(name, await fetch(`audio/voice/${file}`).then((response) => response.arrayBuffer()))
  }
  mix = await renderMix(cues, total, { voices })
  status(voices.size ? `sound ready · ${voices.size} voice lines` : 'sound ready')
  if (state.playing) startSound()
  return mix
}

function stopSound() {
  sound?.source.stop()
  sound = null
}

function startSound() {
  stopSound()
  if (!mix || !state.playing || $('mute').checked) return
  if (!audio) {
    audio = new AudioContext()
    audio.onstatechange = () => {
      if (audio.state === 'running' && state.playing) startSound()
    }
  }
  if (audio.state !== 'running') {
    audio.resume()
    return
  }
  const source = audio.createBufferSource()
  source.buffer = mix
  source.connect(audio.destination)
  const at = audio.currentTime + 0.03
  source.start(at, Math.min(state.time, mix.duration))
  sound = { source, at, from: state.time }
}

function setPlaying(playing) {
  state.playing = playing
  dirty = true
  if (playing) startSound()
  else stopSound()
}

// In the address, t is the time within the selected view (as in the beats of each scene file).
function readHash() {
  const params = new URLSearchParams(location.hash.slice(1))
  const name = params.get('view')
  if (name === 'all' || segments.some((s) => s.id === name)) state.view = name
  const time = Number.parseFloat(params.get('t'))
  state.time = range()[0] + (Number.isFinite(time) ? time : 0)
  state.playing = params.get('play') === '1'
}

function writeHash() {
  const play = state.playing ? '&play=1' : ''
  const t = state.time - range()[0]
  history.replaceState(null, '', `#view=${state.view}&t=${t.toFixed(3)}${play}`)
}

function seek(time) {
  const [a, b] = range()
  state.time = Math.min(Math.max(time, a), b - 1 / FPS)
  dirty = true
  if (state.playing) startSound()
}

const step = (frames) => {
  setPlaying(false)
  seek((Math.round(state.time * FPS) + frames) / FPS)
}

function showTime({ segment, t }) {
  const [a, b] = range()
  $('scrub').min = a
  $('scrub').max = b
  $('scrub').value = state.time
  $('play').textContent = state.playing ? 'Pause' : 'Play'
  $('time').textContent =
    `${state.time.toFixed(2)} s · frame ${Math.round(state.time * FPS)} · ${segment.id} ${t.toFixed(2)} s`
}

let last = performance.now()
let lastHash = 0
function tick(now) {
  if (exporting) return
  const dt = Math.min(0.1, (now - last) / 1000)
  last = now
  const [a, b] = range()
  if (state.time < a || state.time >= b) seek(a)
  if (state.playing) {
    // follow the sound's clock while it plays, so picture and sound stay together
    if (sound && audio.state === 'running') state.time = sound.from + Math.max(0, audio.currentTime - sound.at)
    else state.time += dt
    if (state.time >= b) {
      if ($('loop').checked) seek(a)
      else {
        state.time = b - 1 / FPS
        setPlaying(false)
      }
    }
  }
  if (state.playing || dirty) {
    showTime(draw(state.time))
    dirty = false
  }
  if (now - lastHash > 250) {
    writeHash()
    lastHash = now
  }
  requestAnimationFrame(tick)
}

function fillMenu() {
  const menu = $('view')
  menu.add(new Option(`All (${total.toFixed(1)} s)`, 'all'))
  for (const s of segments) menu.add(new Option(`${s.id} · ${s.big ?? s.view} (${s.duration} s)`, s.id))
  menu.value = state.view
}

$('view').onchange = (e) => {
  state.view = e.target.value
  seek(range()[0])
}
$('play').onclick = () => setPlaying(!state.playing)
$('restart').onclick = () => seek(range()[0])
$('back').onclick = () => step(-1)
$('fwd').onclick = () => step(1)
$('scrub').oninput = (e) => {
  setPlaying(false)
  seek(Number(e.target.value))
}
$('safe').onchange = () => {
  dirty = true
}
$('mute').onchange = () => {
  if (state.playing) startSound()
}
addEventListener('keydown', (e) => {
  if (e.target.tagName === 'SELECT') return
  if (e.code === 'Space') {
    e.preventDefault()
    setPlaying(!state.playing)
  } else if (e.code === 'ArrowRight') step(e.shiftKey ? FPS : 1)
  else if (e.code === 'ArrowLeft') step(e.shiftKey ? -FPS : -1)
  else if (e.code === 'Home') seek(range()[0])
})

/** Renders a view (or 'all') with its sound to an MP4 in Downloads, or in video/out/ with saveTo 'out'. */
async function render(id, { saveTo } = {}) {
  if (exporting) return null
  exporting = true
  setPlaying(false)
  if (id !== state.view) {
    state.view = id
    $('view').value = id
  }
  const [a, b] = range()
  let file = null
  try {
    status('waiting for the sound…')
    const audioMix = await soundReady
    file = await exportMp4({
      canvas: out,
      from: a,
      to: b,
      fps: FPS,
      draw: (time) => draw(time, { guides: false }),
      audio: audioMix,
      name: `joke-video-${id}.mp4`,
      saveTo,
      onProgress: (k) => status(`rendering ${Math.round(k * 100)} %`),
    })
    status(`saved ${file}`)
  } catch (error) {
    console.error(error)
    status(`export failed: ${error.message}`)
  }
  exporting = false
  dirty = true
  last = performance.now()
  requestAnimationFrame(tick)
  return file
}

$('render').onclick = () => render(state.view)

// Reload when serve.ts says a file changed; the address keeps the view and the time.
new EventSource('/events').onmessage = (e) => {
  if (e.data !== 'reload' || exporting) return
  writeHash()
  location.reload()
}

// A pasted or edited address jumps to its view and time (the player's own updates do not fire this).
addEventListener('hashchange', () => {
  readHash()
  $('view').value = state.view
  dirty = true
  if (state.playing) startSound()
  else stopSound()
})

readHash()
fillMenu()
const soundReady = prepareSound().catch((error) => {
  console.error(error)
  status(`sound failed: ${error.message}`)
  return null
})

// For checks from the console: player.frame('scene2', 3.2) draws that frame of that view, without the guides;
// await player.sound() gives the rendered mix; await player.render('card1', { saveTo: 'out' }) renders to video/out/.
window.player = {
  segments,
  frame: (id, t) => draw((segments.find((s) => s.id === id)?.start ?? 0) + t, { guides: false }),
  sound: () => soundReady,
  render,
}

requestAnimationFrame(tick)
