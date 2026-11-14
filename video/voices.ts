// Makes the voice lines of the joke video and the ts:lean video with ElevenLabs text to speech.
//   node --env-file=.env.local video/voices.ts                         lines that have no file yet
//   node --env-file=.env.local video/voices.ts --force                 every line again
//   node --env-file=.env.local video/voices.ts scene1-speed scene4-nah these lines again
// The SDK reads ELEVENLABS_API_KEY from the environment (.env.local, which is not committed). Each line is saved as
// video/audio/voice/<name>.mp3, and the player mixes it in at its cue (see sounds() in each view).
// The words come from timeline.js and lean/timeline.js, so a changed line changes its voice; the delivery tags and
// the voices are here.
import { createWriteStream, existsSync, mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { Readable } from 'node:stream'
import { pipeline } from 'node:stream/promises'
import { fileURLToPath } from 'node:url'
import { ElevenLabsClient } from '@elevenlabs/elevenlabs-js'
import { SEGMENTS as LEAN } from './src/lean/timeline.js'
import { SEGMENTS } from './src/timeline.js'

const folder = join(dirname(fileURLToPath(import.meta.url)), 'audio', 'voice')

// Pre-made ElevenLabs voices (listed from the account), cast for the meme roles
const VOICES = {
  adam: 'pNInz6obpgDQGcFmaJgB', // the classic TikTok narrator: the end
  liam: 'TX3LPaxmHKxFdv7VOQHJ', // social media creator: the developer
  callum: 'N2lVS1w4EtoT3dr4eOWO', // husky trickster: Pertti the dealer
  will: 'bIHbv24MWmeRgasZH58o', // relaxed: the sleepy teammate
  charlie: 'IKne3meq5aSn9XLyUdCD', // deep and hyped: the student
  river: 'SAz9YHcvj6GT2YYXdXww', // neutral: the NPC, through a robot filter
  harry: 'SOYHLrjzK2X1ezoPC6cr', // fierce: the gym bro
  chris: 'iP95p4xoKVk53GoZ742B', // down to earth: the scared driver
}

type Effects = { filterPresetId?: string; environmentId?: string; distance?: number }
type Line = { name: string; voice: string; text: string; stability?: number; effects?: Effects }

/** A spoken line from timeline.js; lists are read one after another. */
function words(id: string, key: string): string {
  const said = SEGMENTS.find((segment) => segment.id === id)?.lines?.[key]
  if (said === undefined) throw new Error(`timeline.js has no line ${id}.${key}`)
  return Array.isArray(said) ? said.join(', ') : String(said)
}

/** A line of the ts:lean video by the name of its file; the voice reads ts:lean as the letters. */
function said(name: string): string {
  for (const segment of LEAN)
    for (const line of segment.lines) if (line.voice === name) return line.say.replaceAll('ts:lean', 'T S lean')
  throw new Error(`lean/timeline.js has no line ${name}`)
}

// The ts:lean video: the developer (liam) explains, calm and clear; the narrator (adam) says "It did not."
const CLEAR = '[calm, clear]'
const LEAN_LINES: Line[] = [
  { name: 'lean-careful', voice: VOICES.liam, text: `[deadpan] ${said('lean-careful')}` },
  { name: 'lean-stuck', voice: VOICES.liam, text: `[hushed] ${said('lean-stuck')}` },
  { name: 'lean-problem', voice: VOICES.liam, text: `${CLEAR} ${said('lean-problem')}` },
  { name: 'lean-high', voice: VOICES.liam, text: `${CLEAR} ${said('lean-high')}` },
  { name: 'lean-low', voice: VOICES.liam, text: `${CLEAR} ${said('lean-low')}` },
  { name: 'lean-ranked', voice: VOICES.liam, text: `[serious] ${said('lean-ranked')}` },
  { name: 'lean-work', voice: VOICES.liam, text: `[confident] ${said('lean-work')}` },
  {
    name: 'lean-didnot',
    voice: VOICES.adam,
    text: `[deep, slow] ${said('lean-didnot')}`,
    effects: { environmentId: 'hall', distance: 0.2 },
  },
  { name: 'lean-touches', voice: VOICES.liam, text: `${CLEAR} ${said('lean-touches')}` },
  { name: 'lean-events', voice: VOICES.liam, text: `${CLEAR} ${said('lean-events')}` },
  { name: 'lean-decisions', voice: VOICES.liam, text: `${CLEAR} ${said('lean-decisions')}` },
  { name: 'lean-price', voice: VOICES.liam, text: `${CLEAR} ${said('lean-price')}` },
  { name: 'lean-fees', voice: VOICES.liam, text: `${CLEAR} ${said('lean-fees')}` },
  { name: 'lean-chains', voice: VOICES.liam, text: `${CLEAR} ${said('lean-chains')}` },
  { name: 'lean-learn', voice: VOICES.liam, text: `${CLEAR} ${said('lean-learn')}` },
  { name: 'lean-margin', voice: VOICES.liam, text: `[proud] ${said('lean-margin')}` },
  { name: 'lean-ontime', voice: VOICES.liam, text: `[smug] ${said('lean-ontime')}` },
]

const LINES: Line[] = [
  { name: 'scene1-speed', voice: VOICES.liam, text: `[confident] ${words('scene1', 'speed')}` },
  { name: 'scene1-whisper', voice: VOICES.callum, text: `[whispers] ${words('scene1', 'whisper')}`, stability: 0.3 },
  { name: 'scene2-chat', voice: VOICES.liam, text: `[fast, in disbelief] ${words('scene2', 'chat')}`, stability: 0.3 },
  { name: 'scene2-back', voice: VOICES.will, text: `[sleepy] ${words('scene2', 'back')}` },
  { name: 'scene3-bro', voice: VOICES.charlie, text: `[deadpan] ${words('scene3', 'bro')}` },
  { name: 'scene3-sixseven', voice: VOICES.charlie, text: `[excited] ${words('scene3', 'sixSeven')}`, stability: 0.3 },
  { name: 'scene3-chews', voice: VOICES.charlie, text: `[satisfied] ${words('scene3', 'chews')}` },
  {
    name: 'scene4-accepted',
    voice: VOICES.river,
    text: `[monotone] ${words('scene4', 'accepted')}`,
    stability: 0.9,
    effects: { filterPresetId: 'robot' },
  },
  { name: 'scene4-nah', voice: VOICES.harry, text: `[smug] ${words('scene4', 'nah')}`, stability: 0.3 },
  {
    name: 'scene4-scream',
    voice: VOICES.harry,
    text: `[shouting] ${words('scene4', 'scream')}!`,
    stability: 0.3,
    effects: { environmentId: 'valley', distance: 0.5 },
  },
  {
    name: 'scene4-panic',
    voice: VOICES.chris,
    text: `[panicking, very fast] ${words('scene4', 'panic')}!`,
    stability: 0.3,
  },
  {
    name: 'end-remember',
    voice: VOICES.adam,
    text: `[whispers] ${words('end', 'remember')}`,
    effects: { environmentId: 'hall', distance: 0.2 },
  },
  { name: 'end-us', voice: VOICES.adam, text: `[ominous] ${words('end', 'us')}`, effects: { environmentId: 'hall' } },
  ...LEAN_LINES,
]

const force = process.argv.includes('--force')
const chosen = process.argv.slice(2).filter((arg) => !arg.startsWith('--'))
const unknown = chosen.filter((name) => !LINES.some((line) => line.name === name))
if (unknown.length) throw new Error(`no line called ${unknown.join(', ')}`)

const client = new ElevenLabsClient()
mkdirSync(folder, { recursive: true })
for (const line of LINES) {
  const file = join(folder, `${line.name}.mp3`)
  const wanted = chosen.length ? chosen.includes(line.name) : force || !existsSync(file)
  if (!wanted) continue
  const audio = await client.textToSpeech.convert(line.voice, {
    text: line.text,
    modelId: 'eleven_v4',
    voiceSettings: { stability: line.stability ?? 0.4, similarityBoost: 0.8 },
    ...(line.effects ? { audioEffects: line.effects } : {}),
  })
  await pipeline(Readable.fromWeb(audio), createWriteStream(file))
  console.log(`${line.name}: ${line.text}`)
}
