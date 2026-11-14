import { rng } from '../kit/rng.js'
import { SOUNDS } from './synth.js'

// The mixer: renders every cue of the video into one stereo buffer, offline, so the preview and the MP4 get the
// same sound. A cue is { at, sound, ...options } for the sound kit, or { at, voice, gain } for a recorded line.
// The video is rendered in short pieces at once (each piece holds only the sounds that start in it, and lasts until
// they have rung out), the pieces are added up, and a soft limiter keeps the peaks under full scale.

export const SAMPLE_RATE = 48000
const PIECE = 3 // seconds of cue start times per piece

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
    out.gain.value = cue.voice ? (cue.gain ?? 1) : 1
    out.connect(master)
    if (cue.wet) {
      const wet = ctx.createGain()
      wet.gain.value = cue.wet
      out.connect(wet)
      wet.connect(send)
    }
    if (cue.voice) {
      const source = ctx.createBufferSource()
      source.buffer = lines.get(cue.voice)
      source.connect(out)
      source.start(at)
      continue
    }
    const play = SOUNDS[cue.sound]
    if (!play) throw new Error(`no sound called ${cue.sound}`)
    play(ctx, out, at, cue)
  }
  return ctx.startRendering()
}

/** Keeps quiet samples as they are and bends loud ones softly towards 0.95. */
function limit(x) {
  const size = Math.abs(x)
  if (size <= 0.7) return x
  return Math.sign(x) * (0.7 + 0.25 * Math.tanh((size - 0.7) / 0.25))
}

/**
 * Renders `cues` into `duration` seconds of stereo sound. `voices` maps a voice line's name to the bytes of its file;
 * voice cues without a file are skipped. `wet` on a cue sends it to the reverb.
 */
export async function renderMix(cues, duration, { voices = new Map() } = {}) {
  const decoder = new OfflineAudioContext(2, 1, SAMPLE_RATE)
  const lines = new Map()
  for (const [name, bytes] of voices) lines.set(name, await decoder.decodeAudioData(bytes.slice(0)))
  const playable = cues.filter((cue) => cue.at < duration && (!cue.voice || lines.has(cue.voice)))

  // how long a cue sounds, with room for its release and the reverb
  const reach = (cue) => (cue.voice ? lines.get(cue.voice).duration : (cue.length ?? 1) * 1.4) + 1.8
  const pieces = []
  for (let start = 0; start < duration; start += PIECE) {
    const inPiece = playable.filter((cue) => Math.max(0, cue.at) >= start && Math.max(0, cue.at) < start + PIECE)
    const end = Math.max(PIECE, ...inPiece.map((cue) => Math.max(0, cue.at) - start + reach(cue)))
    const length = Math.min(duration - start, end)
    pieces.push({ start, rendered: inPiece.length ? renderPiece(inPiece, start, length, lines) : null })
  }

  const frames = Math.ceil(duration * SAMPLE_RATE)
  const mix = new AudioBuffer({ numberOfChannels: 2, length: frames, sampleRate: SAMPLE_RATE })
  const channels = [mix.getChannelData(0), mix.getChannelData(1)]
  for (const { start, rendered } of pieces) {
    if (!rendered) continue
    const piece = await rendered
    const offset = Math.round(start * SAMPLE_RATE)
    for (let c = 0; c < 2; c++) {
      const from = piece.getChannelData(c)
      const to = channels[c]
      const count = Math.min(from.length, frames - offset)
      for (let i = 0; i < count; i++) to[offset + i] += from[i]
    }
  }
  for (const channel of channels) for (let i = 0; i < channel.length; i++) channel[i] = limit(channel[i])
  return mix
}
