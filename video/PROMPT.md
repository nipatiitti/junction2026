# Prompt: build the joke video

Copy everything below the line into a new Claude Code session opened in this repository.

---

Build a 44.5-second vertical joke video (1080×1920, 30 fps) about our Spread dispatcher, with Three.js, in a new
`video/` folder of this repository. Do the work in one go; you can go fast at first and polish later.

## The joke

Our product is the dispatcher we built at Junction 2026 for Bahn's Spread challenge: car dealers in Finland ask for a
price to move a car, we quote, and freelance drivers book the gig at a fee we set. The video turns that into a meme
"what if" story for people aged 18–26: how fast it is, how much money it makes, how it gets you a cheaper ride than a
taxi app, and how drivers who decline our fee get destroyed (cartoon slapstick only). No explanation on screen, only
short funny lines. The structure copies a "what if" TikTok: one thing escalates (here our speed, shown as a MACH
number) and the consequences get bigger each time, ending in space.

## Look

- Low-poly 3D like Roblox-style "what if" TikToks: blocky characters (box head, torso, arms and legs on pivots, simple
  black box eyes), faceted pine trees with snow, flat-shaded buildings with window rows, snowy Finland.
- Flat shading (`MeshLambertMaterial` with `flatShading: true`), saturated colours, a warm low sun with soft shadows,
  light fog, gradient sky.
- Text like TikTok: bold white sans (Arial Black / Impact) with a thick black outline. Title cards have a big number
  with a red strip under it and one short line below.
- During the whole video a header at the top reads `WHAT IF OUR DISPATCHER KEPT GETTING FASTER?`

## Timeline (all times in seconds)

| Start | End  | View   | Content                                    |
| ----- | ---- | ------ | ------------------------------------------ |
| 0.0   | 1.5  | card   | **MACH 1** · "a dealer needs a price"      |
| 1.5   | 10.0 | scene1 | I AM SPEED                                 |
| 10.0  | 11.2 | card   | **MACH 10** · "hour 31 of the hackathon"   |
| 11.2  | 19.7 | scene2 | MONEY PRINTER                              |
| 19.7  | 20.9 | card   | **MACH 67** · "3 AM, you need a ride home" |
| 20.9  | 29.9 | scene3 | TAXI IS COOKED                             |
| 29.9  | 31.1 | card   | **LIGHT SPEED** · "a driver said no"       |
| 31.1  | 41.1 | scene4 | NAH, I'D WIN                               |
| 41.1  | 44.5 | end    | NOVEMBER 2026                              |

Cards: the number slams in (scale from 1.6 to 1 with ease-out-back), the line types in, speed streaks fly past behind.
No scene is longer than 10 s. Recurring cast: a developer in a red hoodie (sunglasses when cool) and our bright red
low-poly hatchback.

### Scene 1 – I AM SPEED (8.5 s)

- Set: a car dealership in a snowy Finnish suburb in morning sun; bunting flags, a "TARJOUS!" banner, rows of parked
  low-poly cars, snowbanks, pines.
- Cast: car dealer Pertti (mullet, mustache, leather jacket, gold chain, jeans, phone in hand); the developer driving
  the red car.
- Beats: 0–2 Pertti types "need a price…" (the text types out in a phone bubble). 2–2.4 a giant price tag drops from
  the sky in front of him, bounces, camera shake. 3–5.8 the red car blasts past left to right with snow spray, speed
  lines and a sonic-boom ring; the camera whips after it; slow motion while the developer leans out of the window:
  "I am speed." 5.8–8.5 Pertti stands with his hair blown straight up, slow push-in, he whispers "…bomboclat."

### Scene 2 – MONEY PRINTER (8.5 s)

- Set: a hackathon hall at night: RGB LED strips, beanbags, pizza boxes, a pyramid of energy-drink cans.
- Cast: the developer at a laptop with a pixel face on its screen; teammates asleep in beanbags.
- Beats: 0–2 the screen shows `−€72,612` in red. 2–4 slow-motion Enter; the number spins to `+€24,451` in green.
  4–7 euro notes shoot out of the laptop and fill the hall; the sleepers float on the money in their beanbags; the can
  pyramid falls. 7–8.5 developer: "Chat… is this real?" A sleeper mumbles: "we're so back."
- The two numbers are placeholders (the kit starter's loss on one level 8 week, our best mean margin); keep them in the
  timeline config so they are easy to change.

### Scene 3 – TAXI IS COOKED (9 s)

- Set: a Helsinki street at 3 AM in heavy snow; a neon "KEBAB 24/7" sign, a taxi rank, tram rails.
- Cast: a student (puffer jacket, beanie, kebab in hand); an older taxi driver "Unc" by a yellow taxi; a black car and
  a green car (no logos, no brand names); our red car.
- Beats: 0–2.5 the phone fills the screen with `€48.90`, `€44.20`, `€41.60`; the student stares: "Bro…". 2.5–4.5 a
  new line `€6.70` with a boom; the student does the 6-7 hand gesture while the camera circles him: "SIX SEVEN!"
  4.5–7 the red car drifts in, a snow wave buries the black and green cars, the taxi meter bursts into confetti.
  7–9 the student gets in, biting the kebab: "W chews." Unc plays a tiny violin on the kerb.

### Scene 4 – NAH, I'D WIN (10 s)

- Set: a truck-stop parking lot by a snowy motorway at sunset; then space with a low-poly Earth.
- Cast: three gig drivers: an NPC driver (grey hoodie, blank face, an "NPC" tag over his head), a gym bro (tank top in
  the frost, sunglasses, protein shake), a scared driver (small, glasses).
- Beats: 0–2 all phones ding with a gig offer; the NPC taps accept: "Accepted." 2–4 the gym bro laughs at the fee,
  does the bicep heart (flexed arm, other hand makes a heart) and declines: "Nah, I'd win." 4–6 the red car passes at
  light speed (white flash, sonic-boom ring) and launches him into the sky, shake trailing. 6–8 in space he flies past
  a satellite, "BOMBOCLAAAT" fading, and becomes a twinkling star; text "−∞ AURA". 8–10 back on the lot the scared
  driver taps accept again and again: "accepted accepted ACCEPTED."

### End – NOVEMBER 2026 (3.4 s)

- Set: a snowy fell at night under northern lights.
- Cast: a low-poly polar bear holding a calendar page "NOVEMBER 2026".
- Beats: the bear turns slowly to the camera and stares; text "Remember November 2026? It was us." and a team-name
  line (placeholder in the config). Do not use any copyrighted song.

Spoken lines are on-screen captions for now. Leave a place in each view for audio (voice lines and sound effects) to
be added later.

## Structure

```text
video/
  index.html        player page; import map for three
  serve.ts          Node static server (node video/serve.ts --port 8790)
  README.md
  src/
    main.js         player: build views on demand, play, seek, export
    timeline.js     every segment, its view, duration and texts in one place
    export.js       frame-exact MP4 export
    kit/            shared by every view
      rng.js        seeded random (mulberry32)
      anim.js       clamp, lerp, easings, keyframe tracks, progress between two times
      palette.js    named colours
      materials.js  cached flat-shaded materials by colour
      character.js  blocky character with options (hair, mullet, mustache, hood, beanie, sunglasses, chain, tank
                    top, puffer) and pose helpers (walk, type on phone, point, flex, bicep heart, 6-7 hands)
      car.js        low-poly car with colour, taxi sign and driver seat
      world.js      ground, snowbanks, pines, buildings, lamp posts, bunting, signs from canvas text, sky, fog, lights
      fx.js         snowfall, bursts (notes, confetti), speed lines, sonic-boom ring, camera shake
      text.js       2D drawing: title card, header, speech captions, phone bubbles
    views/
      card.js
      scene1-speed.js
      scene2-money.js
      scene3-taxi.js
      scene4-decline.js
      end-bear.js
```

- Each view is its own file and exports `{ id, build(kit) }`; `build` returns `{ scene, camera, update(t), overlay(g,
  t), dispose() }`, where `t` is the view's local time and `g` the 2D context of the output canvas.
- Every frame is a pure function of time: no `Math.random`, no physics stepping, no state carried between frames.
  Particles get their start values from the seeded generator and move by formula, so scrubbing to any time gives the
  same picture, and a small change renders the same video except for that change.
- Render the 3D view into a WebGL canvas at 1080×1920, then draw it into a 2D output canvas and draw the text on top.
  The page shows the output canvas scaled to fit; the export encodes the same canvas.

## Player

- A view menu (All and every view), play/pause, restart, a scrubber, frame step back and forward, loop, the time and
  frame number, and a toggle that shows TikTok's safe areas.
- The URL hash keeps the state (`#view=scene1&t=3.20`). `serve.ts` watches `video/` and tells the page to reload on
  any change (server-sent events), so editing a scene file reloads the page at the same view and time.
- "Render MP4" renders the selected view or the whole timeline frame by frame at 30 fps with WebCodecs
  (`VideoEncoder`, codec `avc1.640028`, about 12 Mbit/s) and mp4-muxer, then POSTs the file to `serve.ts`, which writes
  it to `video/out/<name>.mp4`. Add `/video/out` to `.gitignore`.

## Technical choices (checked on 2026-11-14)

- Plain JavaScript ES modules in the browser, no build step and no new npm dependencies. Import three through an
  import map: `https://cdn.jsdelivr.net/npm/three@0.186.1/build/three.module.js`.
- mp4-muxer: `https://cdn.jsdelivr.net/npm/mp4-muxer@5.2.2/build/mp4-muxer.mjs` (exports `Muxer`,
  `ArrayBufferTarget`).
- In three r186 `PCFSoftShadowMap` is removed: use `PCFShadowMap`.
- `serve.ts` runs directly on Node (22.18 or later, which strips TypeScript types); use only `node:` modules.
- Code style is Biome's: single quotes, no semicolons, trailing commas, 2-space indent, lines up to 120. Lint with
  `npx --yes @biomejs/biome@2.6.7 check video` (pnpm may be missing on this Mac).

## Rules

- Do not write or run tests. Check the work by looking at it: open the player in the browser pane, check the console
  for errors and take a screenshot of every view.
- Do not create GitHub issues. Commit on the current branch with short imperative messages.
- Write `video/README.md`: how to run the player, how views and the kit are organised, where to change timing and
  texts, and how to export. Add this line to the Commands list in `AGENTS.md`:
  `- Serve the joke-video player: node video/serve.ts --port 8790`
- First pass: the kit, the player, the export, the cards and scene 1 in full; scenes 2–4 and the end as rough sets with
  their cast and main beats. Then improve the scenes one at a time.
