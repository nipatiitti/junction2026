# Joke video and ts:lean video

Two videos share this player, its kit, its sound and its MP4 export:

- **The joke video** (the default): a 45-second vertical video (1080×1920, 30 fps) about our dispatcher, in the
  low-poly 3D look of a "what if" TikTok, made with Three.js, with its own music and sound effects. `PROMPT.md` has
  the full brief: the joke, the look, every scene and its beats.
- **The ts:lean video** (`?video=lean`): a 58.5-second technical video in 16:10 (1920×1200, 30 fps) for YouTube. It
  opens with 63 strategies thrown at a wall like spaghetti, states the problem, and shows `ts:lean` as a block
  diagram of the real code: a 15-second zoom into `bestPrice()` and a 10-second zoom out while cars and drivers
  drive its lanes the way the code moves them. `prompt.md` at the root of the repository has its brief; the
  section [The ts:lean video](#the-tslean-video) below says where its parts are.

## Run it

```bash
node video/serve.ts --port 8790
```

Open <http://localhost:8790>. The menu plays the whole video or one view. Space plays and pauses, the arrow keys
step one frame (with Shift, one second), Home goes back to the start. The address holds the view and its local time
(`#view=scene1&t=3.200`), so a link opens that frame. When a file under `video/` changes, the page reloads by itself
and stays on the same frame. "TikTok safe areas" shades the parts that TikTok's buttons and caption cover; "mute"
silences the preview only.

**Render MP4** renders the selected view, or the whole video, frame by frame with its sound and saves it in your
Downloads folder as `joke-video-<view>.mp4` (`-2`, `-3`, … when that name is taken). `--out <folder>` on
`serve.ts` saves somewhere else. The video is H.264 at about 12 Mbit/s and the sound AAC at 192 kbit/s (Opus where the
browser has no AAC encoder). It needs a Chromium-based browser, which has WebCodecs.

## Where things are

| File                 | What it holds                                                                         |
| -------------------- | ------------------------------------------------------------------------------------- |
| `src/timeline.js`    | the order of the views, their lengths, every text on screen and the numbers           |
| `src/views/*.js`     | one file per view: its set, its cast, its beats with their times, and its sounds      |
| `src/kit/*.js`       | shared by every view: characters, car, world props, effects, text, easing, randomness |
| `src/audio/synth.js` | the sound kit: drums, 808, cowbell, pads, and effects such as boom, whoosh and ding   |
| `src/audio/score.js` | the beat under each scene, and where it rests for big moments                         |
| `src/audio/mix.js`   | renders all the sound of the video into one track                                     |
| `audio/voice/`       | the voice lines (see below)                                                           |
| `voices.ts`          | makes the voice lines with ElevenLabs                                                 |
| `src/main.js`        | the player                                                                            |
| `src/export.js`      | the MP4 export                                                                        |
| `serve.ts`           | the static server, the reload signal and the endpoint that saves the MP4              |

To change a line or a length, edit `timeline.js`. To change what happens and when, edit the beats in the scene's
file; each file lists its beats at the top. A new kind of view exports `{ build(segment), sounds(segment) }` and goes
in `src/views/index.js`. In the browser console, `player.frame('scene2', 3.2)` draws one frame of a view, and
`await player.render('scene3', { saveTo: 'out' })` renders a view into `video/out/` (not committed) instead of
Downloads.

## Sound

The music is an original 140 BPM trap beat, phonk with a cowbell riff in scene 3, built note by note in
`audio/score.js`; the title cards and the end have no beat, only their effects. Each view's `sounds()` lists its
effects at the same local times as its beats, for example `{ at: 2.25, sound: 'boom', gain: 0.8 }`. All of it is made
from oscillators, filters and seeded noise, rendered once when the page loads (about a second), so every render
sounds the same and the MP4 gets exactly what the preview plays.

Voice lines come from ElevenLabs text to speech, with meme voices cast in `voices.ts` (which voice says which line,
and its delivery tags such as `[whispers]`); the words themselves come from `timeline.js`. Each line is saved as
`video/audio/voice/<name>.mp3` and committed, so rendering needs no key; the page mixes it in at the line's cue. The mixer levels every line to the same loudness, starts it at its
first word and dips the music under it; `rate` on a voice cue (in the view's `sounds()`) speeds a line up to fit.

```bash
node --env-file=.env.local video/voices.ts
```

makes the lines of both videos that have no file yet; `--force` makes every line again, and names (`scene1-speed scene4-nah`) make
just those again. It needs `pnpm install` (for the ElevenLabs SDK) and an ElevenLabs key in `.env.local`, which
`npx -y @elevenlabs/cli@latest onboard init` sets up once (the key is never committed). A recording of your own with
the same name (`.mp3`, `.m4a`, `.wav` or `.ogg`) works too. The names are `scene1-speed`, `scene1-whisper`,
`scene2-chat`, `scene2-back`, `scene3-bro`, `scene3-sixseven`, `scene3-chews`, `scene4-accepted`, `scene4-nah`,
`scene4-scream`, `scene4-panic`, `end-remember` and `end-us`.

## Repeatable frames

Every frame depends only on its time. A view sets every position from its local time `t` with the keyframe and
easing helpers in `kit/anim.js`, random values come from seeded generators in `kit/rng.js`, and particles move by
formula. Scrubbing to a time always gives the same picture, and a change to one beat leaves the rest of the video as
it was. Three.js (0.186.1) and mp4-muxer (5.2.2) load from jsDelivr at pinned versions.

## The ts:lean video

Open <http://localhost:8790/?video=lean>, or pick it in the player's first menu. Its picture is 16:10, its chapter
tag, mark and subtitles are drawn by `src/lean/ui.js` (the "safe areas" box shows the title-safe and action-safe
frames instead of TikTok's), and Render MP4 saves `lean-video-<view>.mp4`.

| File                       | What it holds                                                                        |
| -------------------------- | ------------------------------------------------------------------------------------ |
| `src/lean/timeline.js`     | the views in order, their lengths and chapters, every spoken line with its subtitle   |
| `src/lean/diagram.js`      | the block diagram as data: systems, classes, functions, lanes, lines, the zoom frames |
| `src/lean/map.js`          | builds the diagram in 3D, and draws the chart inside `bestPrice()`                   |
| `src/lean/traffic.js`      | cars on the lanes as formulas of time: stops, and queues behind the car ahead         |
| `src/lean/views/*.js`      | spaghetti, title, problem, didnot, zoom (both zooms), result, handshake               |
| `src/lean/ui.js`           | the chapter tag, the mark, subtitles and the lower third                              |
| `src/lean/sets.js`         | the hackathon hall and the laptop desk, shared by three views                         |

The diagram's names are the code's names on main (15 November 2026), and every green tag is a measured effect from
`src/strategies/lean/README.md`; check them again before a render when `ts:lean` has changed. Its voice lines are
`lean-*` in `voices.ts` and are made like the joke video's (below); until they exist the video plays with subtitles
only.

## Status

All nine views are built, with music and effects: the four title cards, scenes 1–4 and the end. The spoken lines are
captions until voice files are recorded. The numbers and the team name in `timeline.js` are placeholders until the
final is played.
