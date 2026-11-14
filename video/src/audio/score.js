import { VIEWS } from '../views/index.js'

// The score: an original 140 BPM trap and phonk beat under the scenes, plus every view's own sound cues.
// Each scene picks a style below; `rest` lists the local times when the beat stops (for a big moment), and
// `hatsOnly` the times when only the hi-hats play. The title cards and the end have no beat, only their effects.

export const BPM = 140
const STEP = 60 / BPM / 4 // a sixteenth note

// 808 notes (MIDI) by sixteenth step within a bar
const BASS = {
  trap: { 0: 29, 6: 29, 10: 32, 14: 27 },
  party: { 0: 29, 4: 29, 8: 36, 12: 34 },
  phonk: { 0: 29, 3: 29, 6: 32, 8: 34, 11: 32, 14: 27 },
}
// the phonk cowbell riff over two bars, by sixteenth step
const COWBELL = {
  0: 77,
  2: 77,
  3: 80,
  6: 79,
  8: 77,
  10: 75,
  11: 72,
  14: 75,
  16: 77,
  18: 77,
  19: 80,
  22: 82,
  24: 80,
  26: 79,
  27: 77,
  30: 72,
}

const STYLES = {
  scene1: { kick: [0, 10], clap: [8], bass: 'trap', rest: [[3.4, 4.95]] },
  scene2: {
    kick: [0, 4, 8, 12],
    clap: [4, 12],
    bass: 'party',
    rest: [[0, 3.3]],
    hatsOnly: [[7.0, 8.5]],
  },
  scene3: {
    kick: [0, 3, 10],
    clap: [8],
    bass: 'phonk',
    cowbell: true,
    rest: [
      [2.45, 2.7],
      [8.25, 9],
    ],
  },
  scene4: { kick: [0, 10], clap: [8], bass: 'trap', rest: [[2.6, 8.0]], hatsOnly: [[8.0, 10]] },
}

const within = (windows, t) => (windows ?? []).some(([a, b]) => t >= a && t < b)

function beat(segments, total) {
  const cues = []
  for (let n = 0; n * STEP < total; n++) {
    const time = n * STEP
    const segment = segments.find((s) => time >= s.start && time < s.start + s.duration)
    const style = STYLES[segment?.id]
    if (!style) continue
    const t = time - segment.start
    const hatsOnly = within(style.hatsOnly, t)
    if (within(style.rest, t) && !hatsOnly) continue
    const step = n % 16
    const bar = Math.floor(n / 16)
    const roll = bar % 2 === 1 && step >= 12
    if (step % 2 === 0 || roll)
      cues.push({ at: time, sound: 'hat', gain: roll ? 0.15 : 0.2, open: step === 14 && !roll })
    if (hatsOnly) continue
    if (style.kick.includes(step)) cues.push({ at: time, sound: 'kick', gain: 0.9 })
    if (style.clap.includes(step)) cues.push({ at: time, sound: 'clap', gain: 0.5, wet: 0.25 })
    const note = BASS[style.bass][step]
    if (note) cues.push({ at: time, sound: 'bass', note, length: STEP * 3, gain: 0.55 })
    const bell = style.cowbell && COWBELL[(bar % 2) * 16 + step]
    if (bell) cues.push({ at: time, sound: 'cowbell', note: bell, gain: 0.14, wet: 0.2 })
  }
  return cues
}

/** Every cue of the video in its own time: the beat, then each view's sounds and voice lines. */
export function cueSheet(segments) {
  const total = segments.reduce((sum, s) => Math.max(sum, s.start + s.duration), 0)
  const cues = beat(segments, total)
  for (const segment of segments) {
    for (const cue of VIEWS[segment.view].sounds?.(segment) ?? []) cues.push({ ...cue, at: segment.start + cue.at })
  }
  return cues
}

/** The names of the voice lines that the cues ask for. */
export const voiceNames = (cues) => [...new Set(cues.filter((c) => c.voice).map((c) => c.voice))]
