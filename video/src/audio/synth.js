import { rng } from '../kit/rng.js'

// The sound kit: every instrument and effect is built from oscillators, filters and seeded noise, so the mix is the
// same on every render. Each one is play(ctx, out, when, options): it schedules its own nodes at `when` (seconds on
// the context's clock) into the node `out`. Options always take `gain`.

const noises = new WeakMap()
const curves = new WeakMap()

/** Two seconds of seeded white noise, made once per context. */
function noiseBuffer(ctx) {
  if (!noises.has(ctx)) {
    const buffer = ctx.createBuffer(1, ctx.sampleRate * 2, ctx.sampleRate)
    const data = buffer.getChannelData(0)
    const rand = rng(99)
    for (let i = 0; i < data.length; i++) data[i] = rand() * 2 - 1
    noises.set(ctx, buffer)
  }
  return noises.get(ctx)
}

/** A soft-clipping curve for grit. */
function grit(ctx, amount = 2.5) {
  if (!curves.has(ctx)) {
    const curve = new Float32Array(1024)
    for (let i = 0; i < curve.length; i++) curve[i] = Math.tanh(((i / 1023) * 2 - 1) * amount)
    curves.set(ctx, curve)
  }
  const shaper = ctx.createWaveShaper()
  shaper.curve = curves.get(ctx)
  return shaper
}

const hz = (note) => 440 * 2 ** ((note - 69) / 12)

/** A gain node with an attack–decay envelope, connected to out. */
function envelope(ctx, out, when, { gain = 1, attack = 0.005, hold = 0, decay = 0.3 } = {}) {
  const g = ctx.createGain()
  g.gain.setValueAtTime(0, when)
  g.gain.linearRampToValueAtTime(gain, when + attack)
  g.gain.setValueAtTime(gain, when + attack + hold)
  g.gain.exponentialRampToValueAtTime(0.0001, when + attack + hold + decay)
  g.connect(out)
  return g
}

function noise(ctx, when, duration, offset = 0) {
  const source = ctx.createBufferSource()
  source.buffer = noiseBuffer(ctx)
  source.loop = true
  source.start(when, offset % 2)
  source.stop(when + duration + 0.05)
  return source
}

function tone(ctx, type, frequency, when, duration) {
  const osc = ctx.createOscillator()
  osc.type = type
  osc.frequency.setValueAtTime(frequency, when)
  osc.start(when)
  osc.stop(when + duration + 0.05)
  return osc
}

function filter(ctx, type, frequency, q = 1) {
  const f = ctx.createBiquadFilter()
  f.type = type
  f.frequency.value = frequency
  f.Q.value = q
  return f
}

// Drums and bass

export function kick(ctx, out, when, { gain = 1 } = {}) {
  const osc = tone(ctx, 'sine', 160, when, 0.4)
  osc.frequency.exponentialRampToValueAtTime(42, when + 0.12)
  osc.connect(envelope(ctx, out, when, { gain, attack: 0.002, decay: 0.38 }))
}

export function clap(ctx, out, when, { gain = 0.6 } = {}) {
  const band = filter(ctx, 'bandpass', 1300, 0.9)
  band.connect(out)
  for (const [delay, length] of [
    [0, 0.02],
    [0.012, 0.02],
    [0.024, 0.18],
  ]) {
    noise(ctx, when + delay, length, delay * 7).connect(
      envelope(ctx, band, when + delay, { gain, attack: 0.001, decay: length }),
    )
  }
}

export function hat(ctx, out, when, { gain = 0.22, open = false } = {}) {
  const high = filter(ctx, 'highpass', 7500, 0.7)
  noise(ctx, when, 0.3, when * 3.1).connect(high)
  high.connect(envelope(ctx, out, when, { gain, attack: 0.001, decay: open ? 0.22 : 0.045 }))
}

export function bass(ctx, out, when, { gain = 0.7, note = 29, length = 0.4 } = {}) {
  const osc = tone(ctx, 'sine', hz(note) * 1.6, when, length + 0.2)
  osc.frequency.exponentialRampToValueAtTime(hz(note), when + 0.03)
  const shaper = grit(ctx)
  const low = filter(ctx, 'lowpass', 900)
  osc.connect(shaper)
  shaper.connect(low)
  low.connect(envelope(ctx, out, when, { gain, attack: 0.004, hold: length * 0.6, decay: length * 0.4 + 0.15 }))
}

/** The phonk cowbell: two detuned squares through a band filter. */
export function cowbell(ctx, out, when, { gain = 0.16, note = 77 } = {}) {
  const band = filter(ctx, 'bandpass', hz(note) * 2.2, 1.4)
  band.connect(envelope(ctx, out, when, { gain, attack: 0.001, decay: 0.28 }))
  for (const ratio of [1, 1.48]) tone(ctx, 'square', hz(note) * ratio, when, 0.3).connect(band)
}

// Tones

export function pad(ctx, out, when, { gain = 0.12, notes = [53, 56, 60], length = 2, cutoff = 900 } = {}) {
  const low = filter(ctx, 'lowpass', cutoff, 0.7)
  low.connect(
    envelope(ctx, out, when, { gain, attack: Math.min(0.6, length / 3), hold: length / 2, decay: length / 2 }),
  )
  for (const note of notes) {
    for (const detune of [-9, 9]) {
      const osc = tone(ctx, 'sawtooth', hz(note), when, length + 0.6)
      osc.detune.value = detune
      osc.connect(low)
    }
  }
}

export function musicBox(ctx, out, when, { gain = 0.25, note = 84 } = {}) {
  for (const [ratio, level] of [
    [1, 1],
    [3, 0.25],
  ]) {
    tone(ctx, 'sine', hz(note) * ratio, when, 1.3).connect(
      envelope(ctx, out, when, { gain: gain * level, attack: 0.002, decay: 1.2 }),
    )
  }
}

/** A tiny sad violin: a bowed saw with vibrato, one note per [note, start, length]. */
export function violin(ctx, out, when, { gain = 0.14, notes = [] } = {}) {
  const band = filter(ctx, 'bandpass', 1600, 0.8)
  band.connect(out)
  for (const [note, start, length] of notes) {
    const at = when + start
    const osc = tone(ctx, 'sawtooth', hz(note), at, length)
    const wobble = tone(ctx, 'sine', 5.5, at, length)
    const depth = ctx.createGain()
    depth.gain.value = 14
    wobble.connect(depth)
    depth.connect(osc.detune)
    osc.connect(envelope(ctx, band, at, { gain, attack: 0.08, hold: length * 0.6, decay: length * 0.4 }))
  }
}

export function ding(ctx, out, when, { gain = 0.3, notes = [88, 93] } = {}) {
  notes.forEach((note, i) => {
    const at = when + i * 0.09
    tone(ctx, 'sine', hz(note), at, 0.7).connect(envelope(ctx, out, at, { gain, attack: 0.002, decay: 0.6 }))
    tone(ctx, 'sine', hz(note + 12), at, 0.4).connect(envelope(ctx, out, at, { gain: gain * 0.2, decay: 0.3 }))
  })
}

export function twinkle(ctx, out, when, { gain = 0.18 } = {}) {
  ;[96, 100, 103, 108].forEach((note, i) => {
    const at = when + i * 0.06
    tone(ctx, 'sine', hz(note), at, 0.6).connect(envelope(ctx, out, at, { gain, attack: 0.002, decay: 0.5 }))
  })
}

export function kaching(ctx, out, when, { gain = 0.22 } = {}) {
  ;[
    [96, 0],
    [100, 0.07],
    [103, 0.07],
  ].forEach(([note, delay]) => {
    tone(ctx, 'square', hz(note), when + delay, 0.4).connect(
      envelope(ctx, out, when + delay, { gain: gain * 0.5, decay: 0.35 }),
    )
  })
  const high = filter(ctx, 'highpass', 6000)
  noise(ctx, when, 0.4, 1.3).connect(high)
  high.connect(envelope(ctx, out, when, { gain: gain * 0.6, decay: 0.35 }))
}

// Effects

export function tap(ctx, out, when, { gain = 0.12 } = {}) {
  const band = filter(ctx, 'bandpass', 3200, 2)
  noise(ctx, when, 0.03, when * 5.7).connect(band)
  band.connect(envelope(ctx, out, when, { gain, attack: 0.001, decay: 0.025 }))
}

export function whoosh(ctx, out, when, { gain = 0.35, length = 0.5, from = 300, to = 3500 } = {}) {
  const band = filter(ctx, 'bandpass', from, 1.1)
  band.frequency.setValueAtTime(from, when)
  band.frequency.exponentialRampToValueAtTime(to, when + length)
  noise(ctx, when, length, when * 2.3).connect(band)
  band.connect(envelope(ctx, out, when, { gain, attack: length * 0.6, decay: length * 0.5 }))
}

export function riser(ctx, out, when, { gain = 0.2, length = 1 } = {}) {
  const g = ctx.createGain()
  g.gain.setValueAtTime(0.0001, when)
  g.gain.exponentialRampToValueAtTime(gain, when + length)
  g.gain.setValueAtTime(0, when + length + 0.01)
  g.connect(out)
  const high = filter(ctx, 'highpass', 400, 0.8)
  high.frequency.exponentialRampToValueAtTime(6000, when + length)
  noise(ctx, when, length, 0.7).connect(high)
  high.connect(g)
  const osc = tone(ctx, 'sawtooth', 180, when, length)
  osc.frequency.exponentialRampToValueAtTime(1400, when + length)
  const low = filter(ctx, 'lowpass', 2000)
  osc.connect(low)
  low.connect(g)
}

/** A deep impact: a falling sine with a thump of noise. */
export function boom(ctx, out, when, { gain = 0.8, length = 1.1 } = {}) {
  const osc = tone(ctx, 'sine', 75, when, length)
  osc.frequency.exponentialRampToValueAtTime(32, when + length * 0.8)
  const shaper = grit(ctx)
  osc.connect(shaper)
  shaper.connect(envelope(ctx, out, when, { gain, attack: 0.003, decay: length }))
  const low = filter(ctx, 'lowpass', 600)
  noise(ctx, when, 0.15, 0.2).connect(low)
  low.connect(envelope(ctx, out, when, { gain: gain * 0.8, attack: 0.001, decay: 0.12 }))
}

export function sonicBoom(ctx, out, when, { gain = 0.9 } = {}) {
  const low = filter(ctx, 'lowpass', 1200)
  low.frequency.exponentialRampToValueAtTime(200, when + 1.4)
  noise(ctx, when, 1.6, 0.9).connect(low)
  low.connect(envelope(ctx, out, when, { gain, attack: 0.002, decay: 1.5 }))
  const crack = filter(ctx, 'highpass', 2500)
  noise(ctx, when, 0.08, 1.7).connect(crack)
  crack.connect(envelope(ctx, out, when, { gain: gain * 0.7, attack: 0.001, decay: 0.07 }))
  boom(ctx, out, when, { gain: gain * 0.8, length: 1.4 })
}

export function engine(ctx, out, when, { gain = 0.25, length = 1, from = 55, to = 190 } = {}) {
  const osc = tone(ctx, 'sawtooth', from, when, length)
  osc.frequency.exponentialRampToValueAtTime(to, when + length)
  const low = filter(ctx, 'lowpass', 1100)
  const shaper = grit(ctx)
  osc.connect(shaper)
  shaper.connect(low)
  low.connect(envelope(ctx, out, when, { gain, attack: length * 0.3, hold: length * 0.4, decay: length * 0.3 + 0.1 }))
}

export function screech(ctx, out, when, { gain = 0.2, length = 0.7 } = {}) {
  const band = filter(ctx, 'bandpass', 2600, 9)
  const wobble = tone(ctx, 'sine', 7, when, length)
  const depth = ctx.createGain()
  depth.gain.value = 350
  wobble.connect(depth)
  depth.connect(band.frequency)
  noise(ctx, when, length, 3.3).connect(band)
  band.connect(envelope(ctx, out, when, { gain, attack: 0.03, hold: length * 0.6, decay: length * 0.4 }))
}

export function splat(ctx, out, when, { gain = 0.5 } = {}) {
  const band = filter(ctx, 'bandpass', 700, 1.5)
  band.frequency.exponentialRampToValueAtTime(180, when + 0.25)
  noise(ctx, when, 0.3, 4.1).connect(band)
  band.connect(envelope(ctx, out, when, { gain, attack: 0.002, decay: 0.28 }))
}

/** The money printer: a buzzing low square that pulses. */
export function brrr(ctx, out, when, { gain = 0.22, length = 2 } = {}) {
  const osc = tone(ctx, 'square', 52, when, length)
  const low = filter(ctx, 'lowpass', 700)
  const pulse = ctx.createGain()
  pulse.gain.value = 0.5
  const lfo = tone(ctx, 'square', 22, when, length)
  const depth = ctx.createGain()
  depth.gain.value = 0.5
  lfo.connect(depth)
  depth.connect(pulse.gain)
  osc.connect(low)
  low.connect(pulse)
  pulse.connect(envelope(ctx, out, when, { gain, attack: 0.08, hold: length - 0.4, decay: 0.3 }))
}

/** A slot machine: ticks that speed up and climb. */
export function slot(ctx, out, when, { gain = 0.12, length = 0.35 } = {}) {
  let at = 0
  for (let i = 0; at < length; i++) {
    tone(ctx, 'square', 900 + i * 60, when + at, 0.03).connect(
      envelope(ctx, out, when + at, { gain, attack: 0.001, decay: 0.025 }),
    )
    at += Math.max(0.02, 0.06 - i * 0.004)
  }
}

/** A whistle that slides from one pitch to another: a rocket going up, or a scream fading away. */
export function slide(ctx, out, when, { gain = 0.15, length = 1.2, from = 300, to = 1800 } = {}) {
  const osc = tone(ctx, 'sine', from, when, length)
  osc.frequency.exponentialRampToValueAtTime(to, when + length)
  osc.connect(envelope(ctx, out, when, { gain, attack: 0.05, hold: length * 0.6, decay: length * 0.4 }))
}

export function snore(ctx, out, when, { gain = 0.12, length = 1.6 } = {}) {
  const low = filter(ctx, 'lowpass', 380, 3)
  noise(ctx, when, length, 6.6).connect(low)
  const g = ctx.createGain()
  g.gain.setValueAtTime(0, when)
  g.gain.linearRampToValueAtTime(gain, when + length * 0.45)
  g.gain.linearRampToValueAtTime(0, when + length)
  low.connect(g)
  g.connect(out)
}

/** A short low hum that swells, under a dramatic moment. */
export function drone(ctx, out, when, { gain = 0.18, length = 2, note = 29 } = {}) {
  pad(ctx, out, when, { gain, notes: [note, note + 7, note + 12], length, cutoff: 500 })
}

/** Every sound by the name the cues use. */
export const SOUNDS = {
  kick,
  clap,
  hat,
  bass,
  cowbell,
  pad,
  musicBox,
  violin,
  ding,
  twinkle,
  kaching,
  tap,
  whoosh,
  riser,
  boom,
  sonicBoom,
  engine,
  screech,
  splat,
  brrr,
  slot,
  slide,
  snore,
  drone,
}
