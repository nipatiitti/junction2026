import { subtitle } from './ui.js'

// The spoken lines of a segment (timeline.js): their voice cues for the score, and their subtitles on the picture.

/** The voice cues of a segment's lines. */
export const voiceCues = (segment) =>
  segment.lines.map((line) => ({ at: line.at, voice: line.voice, rate: line.rate, gain: line.gain ?? 1 }))

/** Draws the subtitle of every line of the segment that is on at local time t. */
export function captions(g, t, segment, options = {}) {
  for (const line of segment.lines) subtitle(g, t, line.caption, line.at, line.until, options)
}
