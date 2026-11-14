import { rng } from '../kit/rng.js'
import { SOUNDS } from './synth.js'

// The mixer: renders every cue of the video into one stereo buffer, offline, so the preview and the MP4 get the
// same sound. A cue is { at, sound, ...options } for the sound kit, or { at, voice, rate, gain } for a voice line.
// The video is rendered in short pieces at once (each piece holds only the sounds that start in it, and lasts until
// they have rung out). The music and effects are one track and the voices another: every voice line is levelled to
// the same loudness and starts at its first word, the music dips under it, and a soft limiter keeps the peaks under
// full scale.

export const SAMPLE_RATE = 48000
const PIECE = 3 // seconds of cue start times per piece
const VOICE_LEVEL = -10 // dB: the loudest 20 ms of every voice line
const DUCK = 0.6 // how far the music dips under a voice (0.6 = to 40 %)

/** A seeded reverb tail. */
function impulse(ctx, seconds = 1.8) {
  const length = Math.round(ctx.sampleRate * seconds)
  const buffer = ctx.createBuffer(2, length, ctx.sampleRate)
  const rand = rng(7)
  for (let channel = 0; channel < 2; channel++) {
    const data = buffer.getChannelData(channel)
    for (let i = 0; i < length; i++) data[i] = (rand() * 2 - 1) * (1 - i / length) ** 3
  }
  return buffer
}

/** Where a voice line's words start and end (seconds), and the gain that levels it. */
function measure(buffer) {
  const data = buffer.getChannelData(0)
  const window = Math.round(buffer.sampleRate * 0.02)
  const levels = []
  for (let i = 0; i + window <= data.length; i += window) {
    let sum = 0
    for (let j = i; j < i + window; j++) sum += data[j] * data[j]
    levels.push(10 * Math.log10(sum / window + 1e-12))
  }
  const peak = Math.max(...levels)
  const first = levels.findIndex((level) => level > peak - 30)
  const last = levels.findLastIndex((level) => level > peak - 30)
  return {
    lead: Math.max(0, first * 0.02 - 0.02),
    words: (last + 1 - first) * 0.02,
    gain: Math.min(4, Math.max(0.5, 10 ** ((VOICE_LEVEL - peak) / 20))),
  }
}

/** Renders the cues of one piece; times in the piece start at `start`. */
function renderPiece(cues, start, length, lines) {
  const ctx = new OfflineAudioContext(2, Math.ceil(length * SAMPLE_RATE), SAMPLE_RATE)
  const master = ctx.createGain()
  master.gain.value = 0.8
  master.connect(ctx.destination)
  const reverb = ctx.createConvolver()
  reverb.buffer = impulse(ctx)
  const send = ctx.createGain()
  send.gain.value = 0.35
  send.connect(reverb)
  reverb.connect(master)
  for (const cue of cues) {
    const at = Math.max(0, cue.at - start)
    const out = ctx.createGain()
    out.connect(master)
    if (cue.wet) {
      const wet = ctx.createGain()
      wet.gain.value = cue.wet
      out.connect(wet)
      wet.connect(send)
    }
    if (cue.voice) {
      const { buffer, lead, gain } = lines.get(cue.voice)
      out.gain.value = gain * (cue.gain ?? 1)
      const source = ctx.createBufferSource()
      source.buffer = buffer
      source.playbackRate.value = cue.rate ?? 1
      source.connect(out)
      source.start(at, lead)
      continue
    }
    const play = SOUNDS[cue.sound]
    if (!play) throw new Error(`no sound called ${cue.sound}`)
    play(ctx, out, at, cue)
  }
  return ctx.startRendering()
}

/** Renders cues into a new stereo buffer of `frames`, piece by piece. */
async function renderTrack(cues, duration, frames, lines, reach) {
  const pieces = []
  for (let start = 0; start < duration; start += PIECE) {
    const inPiece = cues.filter((cue) => Math.max(0, cue.at) >= start && Math.max(0, cue.at) < start + PIECE)
    if (inPiece.length === 0) continue
    const end = Math.max(PIECE, ...inPiece.map((cue) => Math.max(0, cue.at) - start + reach(cue)))
    pieces.push({ start, rendered: renderPiece(inPiece, start, Math.min(duration - start, end), lines) })
  }
  const track = [new Float32Array(frames), new Float32Array(frames)]
  for (const { start, rendered } of pieces) {
    const piece = await rendered
    const offset = Math.round(start * SAMPLE_RATE)
    for (let c = 0; c < 2; c++) {
      const from = piece.getChannelData(c)
      const count = Math.min(from.length, frames - offset)
      for (let i = 0; i < count; i++) track[c][offset + i] += from[i]
    }
  }
  return track
}

/** Keeps quiet samples as they are and bends loud ones softly towards 0.95. */
function limit(x) {
  const size = Math.abs(x)
  if (size <= 0.7) return x
  return Math.sign(x) * (0.7 + 0.25 * Math.tanh((size - 0.7) / 0.25))
}

/**
 * Renders `cues` into `duration` seconds of stereo sound. `voices` maps a voice line's name to the bytes of its file;
 * voice cues without a file are skipped. `wet` on a cue sends it to the reverb; `rate` speeds a voice line up.
 */
export async function renderMix(cues, duration, { voices = new Map() } = {}) {
  const decoder = new OfflineAudioContext(2, 1, SAMPLE_RATE)
  const lines = new Map()
  for (const [name, bytes] of voices) {
    const buffer = await decoder.decodeAudioData(bytes.slice(0))
    lines.set(name, { buffer, ...measure(buffer) })
  }
  const playable = cues.filter((cue) => cue.at < duration && (!cue.voice || lines.has(cue.voice)))
  const spoken = playable.filter((cue) => cue.voice)
  const bed = playable.filter((cue) => !cue.voice)

  // how long a cue sounds, with room for its release and the reverb
  const reach = (cue) => {
    if (!cue.voice) return (cue.length ?? 1) * 1.4 + 1.8
    const { buffer, lead } = lines.get(cue.voice)
    return (buffer.duration - lead) / (cue.rate ?? 1) + 0.2
  }
  const frames = Math.ceil(duration * SAMPLE_RATE)
  const [music, speech] = await Promise.all([
    renderTrack(bed, duration, frames, lines, reach),
    renderTrack(spoken, duration, frames, lines, reach),
  ])

  // the music dips while someone speaks, with short ramps in and out
  const duck = new Float32Array(frames).fill(1)
  const ramp = Math.round(0.08 * SAMPLE_RATE)
  for (const cue of spoken) {
    const { words } = lines.get(cue.voice)
    const from = Math.round(Math.max(0, cue.at) * SAMPLE_RATE)
    const to = Math.min(frames, Math.round((Math.max(0, cue.at) + words / (cue.rate ?? 1)) * SAMPLE_RATE))
    for (let i = Math.max(0, from - ramp); i < Math.min(frames, to + ramp); i++) {
      const edge = i < from ? (i - (from - ramp)) / ramp : i > to ? 1 - (i - to) / ramp : 1
      duck[i] = Math.min(duck[i], 1 - DUCK * Math.max(0, Math.min(1, edge)))
    }
  }

  const mix = new AudioBuffer({ numberOfChannels: 2, length: frames, sampleRate: SAMPLE_RATE })
  for (let c = 0; c < 2; c++) {
    const out = mix.getChannelData(c)
    for (let i = 0; i < frames; i++) out[i] = limit(music[c][i] * duck[i] + speech[c][i])
  }
  return mix
}
