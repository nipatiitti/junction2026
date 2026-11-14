# Prompt template: a 45-second low-poly "what if" meme video about any project

How to use: fill in the brackets under "Your project", then paste everything below the line into a coding agent
opened in that project (Claude Code works well). The agent builds the video in a `video/` folder: Three.js scenes,
an original beat and sound effects, ElevenLabs voices, and a frame-exact MP4 export to your Downloads folder.
It was first built for a dispatch system at Junction 2026; that version is the reference all through.

---

Build a vertical joke video (1080×1920, 30 fps, at most 45 seconds) about my project, in the low-poly 3D look of
"what if" TikToks, with Three.js, in a new `video/` folder. Plan it first, then build it so that every frame and every
sound can be rendered again exactly, because I will keep changing small things until the end.

## Your project (fill in)

- Project: [NAME], which [WHAT IT DOES, FOR WHOM, IN ONE SENTENCE].
- Four brags, one per scene:
  - speed: [HOW FAST IT IS]
  - result: [WHAT IT EARNS OR ACHIEVES; A NUMBER]
  - what the user wins: [CHEAPER / FASTER / BETTER THAN WHOM]
  - what happens to whoever says no: [THE COMPETITOR, THE SKEPTIC, THE PERSON WHO DECLINES]
- Numbers to flash on screen (placeholders are fine): [OUR NUMBER, e.g. +€24,451 a week] against
  [THE BASELINE, e.g. −€72,612].
- Where it will be shown: [TikTok or Reels → 9:16 | a stage screen → 16:9].
- Name on the end card: [TEAM OR BRAND].
- Local flavour: [PLACE, SEASON, CULTURE, e.g. snowy Finland, a kebab at 3 AM, a "TARJOUS!" banner].
- Language of the lines: [English for memes, unless the audience is local].

## The idea

A joke, not an explainer. No sentence on screen explains anything. The jokes are visual, the lines are short meme
lines, and the real numbers land as punchlines. Audience: people aged 18–26.

- **One thing escalates** and every step makes the consequences bigger, like the TikToks "what if you shouted X at
  110 dB … 370 dB". Our counter was speed: `MACH 1 → MACH 10 → MACH 67 → LIGHT SPEED` (67 doubles as the 6-7 meme).
  Pick a counter that fits the project (speed, users, margin, hours awake, aura).
- **Series-style title cards** between the scenes show the counter: a big number that slams in, a red strip, and one
  short line typed in ("a dealer needs a price", "hour 31 of the hackathon", "3 AM, you need a ride home").
- **A header** stays at the top the whole time: "WHAT IF OUR [THING] KEPT GETTING [FASTER]?"
- **Absurdity grows scene by scene**: a person (hair blown off) → a room (money fills the hall) → a street (snow
  buries the competition) → space (someone launched into orbit) → an eerie ending.
- **Timing**: four scenes of at most 10 s, title cards of 1.2–1.5 s, an end card of 3–4 s; 45 s at most in all.
- **Cartoon slapstick only**: nobody gets hurt; people fly into space and become stars.

## The reference storyboard (adapt it to the project)

| Start | End  | View  | Content                                             |
| ----- | ---- | ----- | --------------------------------------------------- |
| 0.0   | 1.5  | card  | **MACH 1**: "a dealer needs a price"                |
| 1.5   | 10.0 | scene | I AM SPEED: speed                                   |
| 10.0  | 11.2 | card  | **MACH 10**: "hour 31 of the hackathon"             |
| 11.2  | 19.7 | scene | MONEY PRINTER: the result                           |
| 19.7  | 20.9 | card  | **MACH 67**: "3 AM, you need a ride home"           |
| 20.9  | 29.9 | scene | TAXI IS COOKED: the user wins                       |
| 29.9  | 31.1 | card  | **LIGHT SPEED**: "a driver said no"                 |
| 31.1  | 41.1 | scene | NAH, I'D WIN: whoever declines gets launched        |
| 41.1  | 45.0 | end   | NOVEMBER 2026: "Remember November 2026? It was us." |

1. **I am speed** (car dealership in snow). The dealer starts typing "need a price…"; before he finishes, a giant
   price tag drops from the sky. Our red car blasts past in slow motion, the developer leans out of the window:
   "I am speed." Sonic boom; the dealer's mullet stands straight up; he whispers "…bomboclat."
2. **Money printer** (hackathon hall at night: LED strips, beanbags, energy-drink pyramid, a "HOUR 31" neon sign).
   The laptop shows the baseline loss in red. One slow-motion Enter; the number spins like a slot machine and lands
   on our margin in green. Notes fountain out of the laptop ("BRRRRRR"), cover the floor and rise until the sleeping
   teammates float on them ("we're so back."). Through the laptop's webcam, with a LIVE badge and a fake chat:
   "Chat… is this real?"
3. **Taxi is cooked** (a city street at 3 AM, heavy snow, a kebab shop). A ride app lists €48.90, €44.20, €41.60;
   the student stares: "Bro…". Our ride pops in at €6.70 and strikes the others out; he does the 6-7 hands while a
   6 and a 7 pop at his hands. Our car drifts in with its headlights, a snow wave hits the lens and buries the
   competitors' cars: "COOKED". The taxi sign flies off in confetti; "W chews." through the windscreen; the old
   taxi driver plays a tiny violin on the kerb.
4. **Nah, I'd win** (truck stop at sunset). Three drivers get the gig offer. The NPC (grey hoodie, "NPC" tag) accepts
   at once in a robot voice. The gym bro reads the fee, laughs, presses DECLINE, does the bicep heart with an aura:
   "Nah, I'd win." Our car passes at light speed and launches him into space, past a satellite: "BOMBOCLAAAT",
   "−∞ AURA", "he did not win". His sunglasses smoke in the crater; the scared driver presses ACCEPT again and again.
5. **End** (a fell under northern lights). A polar bear holds a calendar page "NOVEMBER 2026", turns its head while
   the camera does a dolly zoom, its eyes glint: "Remember November 2026? It was us." The hackathon days get circled
   on the calendar. Team name.

## The meme toolkit (as of November 2026, for ages 18–26)

Memes age in weeks. Before writing, check what is current (Know Your Meme's weekly roundup, TikTok trends) and
swap out anything stale; note the date you checked.

| Meme                             | What it is                                                     | How we used it                                                                                                       |
| -------------------------------- | -------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| "I am speed"                     | a line from a racing film, now a meme                          | said by the developer leaning out of the speeding car                                                                |
| BOMBOCLAT                        | Jamaican patois exclamation, a staple of "what if" TikToks     | a whispered "…bomboclat." and a scream fading into space; it is a curse word, so twice at most if a jury will see it |
| 6-7 ("six seven")                | palms up, hands going up and down in turn                      | a €6.70 price, MACH 67, a 6 and a 7 popping at each hand                                                             |
| W chews / L nibbles              | "good food" / "bad food" (new in November 2026)                | said through a mouthful of kebab                                                                                     |
| Bicep Heart                      | flex one arm, make a heart with the other hand (November 2026) | the gym bro's pose before his downfall, with a glowing heart                                                         |
| "Nah, I'd win"                   | anime line of overconfidence                                   | the gym bro declines the offer; then "he did not win"                                                                |
| "Chat, is this real?"            | streamer talking to their chat                                 | the developer to the laptop's webcam, with a LIVE badge and a scrolling chat                                         |
| "we're so back" / "it's so over" | mood swings of the internet                                    | mumbled by a sleeping teammate floating on money                                                                     |
| Money printer go brrr            | printing money                                                 | "BRRRRRR" text and a buzzing printer sound                                                                           |
| Aura (+1000 / −∞)                | social points for cool or cringe moments                       | "−∞ AURA" when the gym bro becomes a star                                                                            |
| NPC                              | someone acting like a game character                           | a tag over a head, a monotone robot voice, an idle head turn                                                         |
| Cooked / washed                  | done for / past it                                             | a "COOKED" stamp over the buried competitors                                                                         |
| Unc                              | an older guy                                                   | the taxi driver with a tiny sad violin                                                                               |
| Remember November 2026           | an eerie AI polar bear "meme from the future" (Sep–Nov 2026)   | the end card: "It was us."                                                                                           |
| Viral sound effects              | impact booms, speed lines, sad violin                          | made from scratch in the sound kit, never sampled                                                                    |

Rules: no copyrighted songs, characters or clips (no film characters behind a quote, no hit song behind a meme), no
real brand logos (use colours: the "black app", the "green app"), slapstick instead of violence.

## The look

- Low-poly like Roblox-style "what if" TikToks: blocky people (box head and torso, arms and legs on pivots, black box
  eyes), faceted pines with snow, flat-shaded buildings with window rows, snowbanks from jittered icosahedrons.
- `MeshLambertMaterial` with `flatShading`, saturated colours, a low sun or a moon with soft shadows, light fog,
  gradient sky domes, neon signs that ignore light, aurora curtains with additive blending.
- Text like TikTok: bold white sans (Arial Black / Impact) with a thick black outline; cards with a slammed number and
  a red strip; spoken lines as pop-in captions; phone screens drawn in 2D (chat bubbles, a ride app, a gig card,
  notification banners); a LIVE chat overlay.
- Camera language: push-ins, whip pans that follow the action, slow motion, a dolly zoom for the eerie end, shakes on
  impacts, a snap zoom on the punchline; vignette and film grain at the end.
- Keep the TikTok safe areas clear: top 160 px, bottom 420 px, right 140 px (draw them as an optional overlay).

## Technology

- **No build step.** Plain JavaScript ES modules in the browser; Three.js through an import map from jsDelivr at a
  pinned version (we used `three@0.186.1`). In r186 `PCFSoftShadowMap` is gone: use `PCFShadowMap`.
- **Files**:
  - `video/serve.ts`: a dependency-free Node server (Node ≥ 22.18 runs TypeScript directly). It serves `video/`,
    tells the page to reload when a file changes (server-sent events and `fs.watch`), lists recorded voices
    (`GET /voices`), and saves posted files to `~/Downloads` with free names (`-2`, `-3`), or to `video/out/` with
    `?to=out`.
  - `video/index.html`, `src/main.js`: the player.
  - `src/timeline.js`: every segment with its view, duration and every text on screen; placeholder numbers.
  - `src/views/*.js`: one file per view, exporting `{ sounds(segment), build(segment) }`; `build` returns
    `{ scene, camera, update(t), overlay(g, t) }`. Each file lists its beats with local times at the top.
  - `src/kit/*.js`, shared by every view: seeded random and smooth noise, easing and keyframe tracks and slow motion,
    palette, cached flat materials, a blocky character with options (hair, mullet, mustache, hood, beanie, cap,
    sunglasses, glasses, chain, tank top, puffer, tired eyes) and poses (phone, sit, arms up, 6-7, bicep heart), a
    low-poly car (driver and passenger seats, window opacity, snow, a removable taxi sign), world props (sky, stars,
    lights, snowy ground, pines, buildings, lamps, bunting, signs and live canvas textures), effects (snowfall,
    bursts of notes and confetti and snow, a sonic-boom ring, glow sprites, camera shake, 2D speed lines, flash,
    sparkle, vignette, grain) and 2D text (outlined text, header, cards, captions, phones, banners, a live chat).
  - `src/audio/synth.js`, `score.js`, `mix.js`: the sound (below).
  - `src/export.js`: the MP4 export. `voices.ts`: the ElevenLabs voices.
- **Every frame is a function of its time**: views set every position from `t` with keyframes and easing, random
  values come from seeded generators, particles move by formula (parabolas with an analytic landing time), canvas
  textures repaint only when their state changes. Scrubbing to any time gives the same picture.
- **Rendering**: a WebGL canvas (`preserveDrawingBuffer`, ACES tone mapping) is drawn into a 2D output canvas, the
  view's overlay and the header go on top, and the output canvas is what the page shows and the export encodes.
- **Player**: a view menu (all or one view), play and pause, a scrubber, frame steps, loop, mute, safe areas; the
  address holds the view and its local time (`#view=scene2&t=3.200`) and survives the automatic reloads; console
  hooks `player.frame(view, t)`, `await player.render(view, { saveTo: 'out' })` and `await player.sound()`.
- **Export**: WebCodecs `VideoEncoder` (H.264 `avc1.640028`, about 12 Mbit/s) and `AudioEncoder` (AAC
  `mp4a.40.2` at 192 kbit/s, Opus as a fallback), muxed with `mp4-muxer@5.2.2` (`fastStart: 'in-memory'`,
  `firstTimestampBehavior: 'offset'` because AAC adds priming), drawn frame by frame at exact times, posted to the
  server, saved as `joke-video-<view>.mp4` in Downloads.

## Sound

- **Synthesized, never sampled**: kick, clap, hats, an 808 with grit, a phonk cowbell, pads, a music box, a bowed
  violin with vibrato, and effects (impact boom, sonic boom, whoosh, riser, ding, kaching, slot-machine ticks,
  money-printer buzz, engine, tyre screech, splat, snore, slide whistle, drone, twinkle), all from oscillators,
  filters and seeded noise.
- **Score**: an original 140 BPM trap beat (phonk with a cowbell riff for the drift scene). Each scene has a style
  and windows where the beat rests for big moments (slow motion, the Enter key, the aura) or plays only hi-hats; the
  title cards and the end have no beat, only their effects.
- **Cues**: each view's `sounds(segment)` returns cues at the same local times as its beats, e.g.
  `{ at: 2.25, sound: 'boom', gain: 0.8 }` or `{ at: 3.55, voice: 'scene1-speed', rate: 1.1 }`.
- **Mix**: rendered once when the page loads with `OfflineAudioContext`, in 3-second pieces at once (each piece holds
  only the cues that start in it and lasts until they ring out; one context for the whole video took 25 s, the
  pieces take about 1 s). Music and voices render as separate tracks; every voice line is levelled to the same
  loudness (its loudest 20 ms at −10 dB), starts at its first word, and the music dips to 40 % under it; a soft
  limiter keeps the sum under 0.95. The same buffer plays in the preview (the picture follows the sound's clock)
  and goes into the MP4.

## Voices with ElevenLabs

- Set up once from the project folder: `npx -y @elevenlabs/cli@latest onboard init`, then follow what it prints. It
  signs the user in in the browser and writes the key to `.env.local` (check that git ignores it). Its rules are good
  rules: never open or print the env file, never put the key in code, never ask for a key in chat, write no code
  until it says so, and ask before making a test clip.
- Use `@elevenlabs/elevenlabs-js` (with the project's package manager) and the model `eleven_v4`, which takes delivery
  tags such as `[whispers]`, `[shouting]`, `[deadpan]`, `[smug]`, `[excited]`, `[sleepy]`, `[panicking, very fast]`.
- Never use voice IDs from memory: list the account's pre-made voices and cast by name. Our cast: Adam (the classic
  TikTok narrator, for the eerie end), Liam (social-media creator: the developer), Callum (husky: the whisper),
  Charlie (deep and hyped: the student), Will (relaxed: the sleepy one), Harry (fierce: the gym bro), Chris (the
  scared driver), River through the `robot` filter (the NPC). Audio effects add rooms: `valley` for a scream into
  space, `hall` for the narrator. Character settings: stability 0.3–0.4, similarity 0.8.
- `voices.ts` takes the words from `timeline.js`, adds the tags, saves `audio/voice/<name>.mp3`, skips lines that
  exist, and remakes named lines (`node --env-file=.env.local video/voices.ts scene4-nah`). Commit the mp3 files so
  rendering needs no key.
- Measure every line before timing it: the file length includes silence and reverb, so find where speech starts and
  ends (20 ms RMS windows; on macOS `afconvert` to WAV first). Whispers and mumbling run long; remake them with
  tighter tags, use `rate` (1.1–1.2) for the last bit, and move or lengthen beats so no line runs into the next view.

## How to work

1. Storyboard first: a table of times and views, then per scene its set, cast, beats with local seconds, lines and
   memes. Agree on the format (9:16 or 16:9) before code.
2. Build the player, the timeline, the kit and the export; then the title cards and scene 1 in full; rough sets for
   the other scenes so the whole timeline plays.
3. Finish one scene at a time. After each change, look at it: render a 3×3 contact sheet of frames from the page
   (`player.frame` into a canvas, posted to `/save?to=out&name=sheet.jpg`) and read the image; fix framing, then
   check again. Watch the console for errors.
4. Then the sound, then the voices, then a full render. Lint and format after every step; keep the docs (a README in
   `video/`) and the run commands current.

## Mistakes we made, so you don't

- A vertical frame is narrow: horizontal coverage is `2 · distance · tan(vfov / 2) · 0.5625`. Three people side by
  side at 50° need the camera about 10 units away.
- Signs and neon near the top collide with the header; captions placed over faces hide the joke. Put text under the
  subject and inside the safe areas.
- Particles thrown at the camera look enormous: aim fountains up and away.
- A ring seen edge-on is a line: turn sonic-boom rings to face the camera.
- When the camera flies to space, hide the sky dome (it shows from outside) and switch the fog off.
- Things that fall must land: compute the landing time instead of clamping at a guessed time.
- Unlit glowing materials read as white snow at night; lit ones turn grey-blue.
- Additive aurora curtains add up fast; keep their opacity near 0.5 or the night turns into day.
- `OfflineAudioContext` slows down with thousands of filter nodes: render in pieces. Give each piece enough length
  for its longest sound, or long sounds get cut.
- AAC encoders add priming: use `firstTimestampBehavior: 'offset'` in the muxer.
- Background browser tabs throttle timers, so long exports there are slow; agents' shells on macOS may not read
  `~/Downloads` (check exports in `video/out/`); a reload in the middle of a multi-file edit can load half-updated
  files, so reload once more before judging.

## Done when

- Every view is built and checked with contact sheets, without console errors, and the video is at most 45 s.
- Music, effects and voices play in the preview and in the MP4; no line runs into the next view; nothing clips.
- All texts and numbers live in `timeline.js`, the beats at the top of each view, the casting in `voices.ts`.
- `video/README.md` says how to run the player, render, change texts and timing, and remake voices.
