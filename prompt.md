# Prompt: build the ts:lean video

Build a 48-second vertical video (1080×1920, 30 fps) that shows how `ts:lean` works: the dispatch system our team
Blib Blib built at Junction 2026 for Bahn's Spread challenge. Build it in `video/`, beside the joke video, in its
low-poly style and from its assets. It opens with spaghetti thrown at a wall, says what the problem is, and then shows
the solution as a block diagram of the real code: a 15-second zoom in, then a 10-second zoom out during which cars and
drivers drive along the diagram's lines the way the code moves them. It has three cutaway jokes and no more.

## The story

The spaghetti says how we got here: 63 strategies thrown at a wall, and one stuck. Then the problem in three lines,
and the list price that failed. Then the solution, which is the code itself, drawn as a map with the cars moving
through it. Then the result.

## The numbers

| What           | Value                                                                       | Shown in                                  |
| -------------- | --------------------------------------------------------------------------- | ----------------------------------------- |
| `[ALGO]`       | `ts:lean`                                                                   | the strand that sticks, the diagram, the end |
| `[TEAM]`       | Blib Blib                                                                   | the lanyards, the end                     |
| `[OUR NUMBER]` | +€24,451, our margin a week                                                 | the result                                |
| `[BASELINE]`   | −€72,456                                                                    | "It did not"                              |
| `[X]%`         | 99.9999999% on time (the one joke number; the line for being ranked is 90%) | the result                                |
| Strategies     | 63                                                                          | the spaghetti, the result                 |

The effects tagged on the diagram come from `src/strategies/lean/README.md`: each change against the same code
without it, on the same seeds, at level 8. All euros are game euros. Keep every text, number and diagram label in the
new video's data files, as the joke video keeps its texts in `src/timeline.js`.

## Format and style

- 48.0 s in all, so under 50 s; no view is longer than 15 s.
- The joke video's look (`video/PROMPT.md`, `video/README.md`): low-poly 3D, flat shading, snowy Finland, TikTok
  text. Reuse `video/src/kit/` and the joke video's sets, cast and props; they are our own models, not Roblox assets.
- Hook: the spaghetti, at MrBeast pace (a big claim, a fast reveal, no intro), in style only. By 3.0 s the throw has
  landed and "Only one stuck" is said.
- Technical first. Three cutaway jokes only: the spaghetti, "It did not" and the handshake. Two lying captions: the
  spaghetti's first line and the on-time line of the result.
- Captions on: every spoken line shows as a caption in the `caption()` style, timed to the voice. Spell `ts:lean`,
  Bahn and Blib Blib exactly.
- Header: the section at the top, `THE PROBLEM`, `THE SOLUTION: ts:lean` or `THE RESULT`; none during the three jokes.
- Voices: `liam` explains (the developer's voice in the joke video) and `adam` says "It did not."
- Keep the header and the captions inside TikTok's safe areas (the player's "TikTok safe areas" toggle).

## Timeline (all times in seconds)

| Start | End  | View      | Content                                           |
| ----- | ---- | --------- | ------------------------------------------------- |
| 0.0   | 4.0  | spaghetti | Joke 1: 63 strategies at the wall, one sticks     |
| 4.0   | 12.0 | problem   | THE PROBLEM                                       |
| 12.0  | 15.5 | didnot    | Joke 2: "This will definitely work." "It did not." |
| 15.5  | 30.5 | zoomin    | THE SOLUTION: into the diagram, 15 s              |
| 30.5  | 40.5 | zoomout   | THE SOLUTION: out again, with the traffic, 10 s   |
| 40.5  | 45.0 | result    | THE RESULT                                        |
| 45.0  | 48.0 | handshake | Joke 3, with the end title                        |

## The block diagram

The diagram is the code of `ts:lean` and everything that touches it, laid flat on the snow like a town map: systems
are districts, classes are buildings, functions are small tiles, and the arrows between them are roads. Both zooms
use the same diagram. Name everything exactly as in the code, and keep only the functions that every decision runs
through or whose effect on the week is measured.

### Labels

- Three sizes, 3 : 2 : 1. Systems are the biggest (Arial Black, capitals), classes medium (Arial Black), functions the
  smallest (a monospace font, with `()`). The camera looks straight down for most of both zooms, so every label scales
  by the same factor and the order of the sizes holds on screen at every moment.
- A measured effect sits under its function as a green tag at the function's size, such as `+€1,560 a week`; "(sim)"
  marks a measurement on the simulator, and the others are server weeks.

### Systems

The frame is tall, so the diagram is too: the events come in at the top and go down to `ts:lean` in the middle.

| System (biggest) | Code                                                      | Classes (medium)                      | Functions (smallest)                  | Place                    |
| ---------------- | --------------------------------------------------------- | ------------------------------------- | ------------------------------------- | ------------------------ |
| `SPREAD WORLD`   | Bahn's server: the dealers, the drivers and the gig app   | —                                     | —                                     | top; Pertti and drivers stand in it |
| `KIT`            | `vendor/spread-typescript`                                | `Client`, `World`                     | in `World`: `stream()`, `act()`       | under SPREAD WORLD       |
| `HARNESS`        | `src/harness`                                             | `Desk`, `Guard`, `Journal`            | `playLive()`; in `Desk`: `handle()`   | under KIT                |
| `TS:LEAN`        | `src/strategies/lean`                                     | `Lean`, `Demand`, `Supply`, `Planner` | see "Inside TS:LEAN"                  | the centre, the biggest district |
| `OPS`            | `src/ops`                                                 | —                                     | `canServe()`, `readNote()`, `gigShape()` | right of TS:LEAN      |
| `SAVED WEEKS`    | `src/record.ts`, `data/scrape/runs`, `out/spread.sqlite`  | `Recorder`                            | in `Recorder`: `save()`               | below left               |
| `ANALYSIS`       | `analysis/` (Python)                                      | —                                     | `supply_curve`, `lean_cost`           | below right              |
| `SIMULATOR`      | `sim/`                                                    | —                                     | —                                     | left of TS:LEAN, high    |
| `PYTHON TWIN`    | `strategies/lean/`                                        | —                                     | —                                     | left of TS:LEAN, low     |

### Roads between systems

| From → to                                         | Painted on the road                     | What rides on it                                                       |
| ------------------------------------------------- | --------------------------------------- | ---------------------------------------------------------------------- |
| SPREAD WORLD → `World.stream()`                   | `events`                                | tokens: `price_request`, `order_won`, `gig_booked`, `delivered`        |
| `World.act()` → SPREAD WORLD                      | `actions`                               | `quote`, `post`, `reprice`                                             |
| `World` → `playLive()` → `Desk.handle()`          | —                                       | the same events, one at a time                                         |
| `Desk.handle()` → `Lean`, through `Guard`         | `quote · gig · tick · observe`          | the calls; `Guard` holds each to its time budget                       |
| `Desk` → `Journal`                                | `rebuild`                               | every action, so a restarted week plays on the same                    |
| `Lean` → OPS                                      | —                                       | calls to `canServe()`, `readNote()`, `gigShape()`                      |
| `World` → `Recorder.save()` → SAVED WEEKS         | `every week`                            | finished weeks                                                         |
| SAVED WEEKS → ANALYSIS → TS:LEAN                  | `noise 0.11 · taxLoad 0.47 · order.json` | the measured constants                                                |
| SAVED WEEKS → SIMULATOR → TS:LEAN                 | `40 seeds a batch`                      | a pale copy of the traffic                                             |
| TS:LEAN ↔ PYTHON TWIN                             | `same week, action for action`          | —                                                                      |

### Inside TS:LEAN

`Lean` sits in the middle, its method `quote()` at the exact centre of the whole diagram, and `bestPrice()` inside
`quote()`: the zoom in ends there. Around it:

- left, the price: `Demand` (`belief()`, `learn()`), `Supply` (`ratio()`, `learn()`), `outlook()` with `order.json`,
  and `Lean`'s `cost()` and `load()`, all feeding `quote()`; `canServe()` from OPS stands on the road into it;
- right, the fee: `gig()` → `fees()` → `stepped()`, with `planBy()` and `rested()` beside `stepped()`; `gigShape()`
  from OPS stands on the road into `gig()`;
- below, the chains: `tick()` → `Planner` (`actions()`, `hold()`) → `findChains()`;
- above, by the road in from HARNESS, the learning: `observe()` → `Demand.learn()` and `Supply.learn()`.

| Function                   | In          | What it does                                                                                                   | Tag                  |
| -------------------------- | ----------- | -------------------------------------------------------------------------------------------------------------- | -------------------- |
| `quote()`                  | `Lean`      | quotes each option that `canServe()` lets through                                                              |                      |
| `bestPrice()`              | `demand.ts` | the price, from 0.90 to 3.00 × list, with the most chance to win × (price − cost after the charge)             |                      |
| `belief()`, `learn()`      | `Demand`    | the win curve: the log price that wins is a sum of effects (world, day, dealer, pickup place, delivery place, option); each won or lost quote moves each effect by its share of the doubt (a Kalman step on a logistic curve) |                      |
| `cost()`                   | `Lean`      | what the drivers will cost: typical fee × 0.98 × `Supply.ratio()` × the order model, plus the chance to be late × list |                |
| `ratio()`, `learn()`       | `Supply`    | what bookings pay for such a car this week, by pickup place, delivery place and pickup today                  | `+€769 a week (sim)` |
| `outlook()`                | `outlook.ts` | the order model in `order.json`: the request's cost against the mean order, and its chance to be late          | `+€771 a week`       |
| `load()`                   | `Lean`      | the charge for what one more order costs the others: cost × (1 + 0.47 × orders per driver)                    | `+€972 a week`       |
| `canServe()`               | `src/ops`   | lets through only options that can arrive on time with five hours to spare                                    |                      |
| `gig()`, `fees()`          | `Lean`      | turn a won order into a gig and choose its fee schedule                                                        |                      |
| `stepped()`                | `fees.ts`   | opens at 0.88 × typical and rises three times, to 1.05, 1.25 and 1.55                                          | `every week ranked`  |
| `planBy()`                 | `fees.ts`   | times the raises to when drivers plan: by 21:00 the evening before for a pickup before 16:00                   |                      |
| `rested()`                 | `fees.ts`   | no raises over the weekend for cars due on the Monday                                                          | `+€624 a week`       |
| `tick()`                   | `Lean`      | every 15 minutes: reprices what drivers gave back and lets `Planner` post chains                               |                      |
| `actions()`, `hold()`      | `Planner`   | post the chains; a new car waits up to 2 hours for a partner                                                   | `+€826 a week (sim)` |
| `findChains()`             | `chains.ts` | up to 4 cars for one driver: hops of 60 road minutes at most, 8 hours of driving, 15% under the cars' fees     | `+€1,560 a week`     |
| `observe()`                | `Lean`      | every event teaches `Demand` and `Supply`                                                                      |                      |

Where the tags come from: `+€1,560`, `+€972`, `+€771` and `+€624` are means over 10 server seeds, `+€769` and
`+€826` over 40 simulator seeds, and `every week ranked` is against a flat fee that left 3 of 5 server weeks under
90%.

### The chart inside `bestPrice()`

- Across: the price × list, from 0.90 (the scan goes on to 3.00).
- The win chance, falling: `chance(p) = 1 / (1 + e^((ln p − μ) / scale))`, with μ = ln 1.40 (half of the quotes win
  at 1.40 × list) and scale 0.11.
- The margin, rising: `p − cost`, for an example cost of 1.00 × list after the charge.
- Their product, with its peak marked `quote`: at 1.35 × list, where 58% of such quotes win.
- Under it, in the monospace font: `quote = argmax chance(p) × (p × list − cost × (1 + 0.47 × load))`.

## Scenes

Times inside a scene are its local seconds. "Says" is the voice; the caption shows the same words unless a lying
caption is given.

### Spaghetti – joke 1 (4.0 s)

- Set: the hackathon hall at night from scene 2 (RGB strips, beanbags, pizza boxes, the can pyramid), a bare wall, a
  giant pot.
- Cast: the developer and two teammates.
- Beats: 0.0 the first frame is already mid-throw, in slow motion: 63 strands of spaghetti fly at the wall, each with
  a tiny name tag. 1.4 they slap the wall. 1.6–3.0 they slide down; tags in close-up get a red `ELIMINATED` stamp:
  `profit-max`, `max-margin`, `ratchet`, `war-guard` (all shelved, see `SHELVED.md`); a counter on the wall runs from
  63 to 1. 3.0–4.0 one strand still sticks; push in on its tag, `ts:lean`; sparkles.
- Says: "We tested every strategy carefully." (0.2–2.0). Lying caption: `[we threw 63 at a wall]`. "Only one stuck."
  (2.6–3.5).
- Sound: whoosh on the throw, three splats from 1.4, slot under the counter, twinkle at 3.0.

### Problem – THE PROBLEM (8.0 s)

- Set: a clean stretch of snow like the diagram's ground. Left, Pertti's dealership from scene 1; in the middle, an
  empty block marked `ts:lean ?`; right, a parking lot with the NPC driver, the gym bro and the scared driver from
  scene 4, phones in hand.
- Beats: 0–2.8 a request card flies from Pertti to the block: `price_request · list €389`. 2.8–5.0 a price tag
  `1.9 × list` pops up, and a grey car marked `COMPETITOR` drives in and takes the car. 5.0–7.0 the drivers' phones
  show the gig at `0.6 × typical`; they shrug and pocket the phones; a clock spins; the car's tag turns `LATE`.
  7.0–8.0 an on-time gauge falls under its `90%` line, and a red stamp lands: `NOT RANKED`, `under 90% on time`.
- Says: "The problem: price the car now, find a driver later." (0.2–2.7). "Quote too high, and the competitor wins
  it." (2.9–4.8). "Pay too little, and no driver comes in time." (5.0–7.0).
- Sound: ding at 0.2, whoosh for the competitor at 3.2, ticks for the clock, boom on the stamp at 7.4.

### It did not – joke 2 (3.5 s)

- Set: the developer's desk in the hall by day, banner `HOUR 2`; the laptop screen reads
  `STRATEGY #1: quote the list price` (what the kit's starter does).
- Beats: 0–1.5 knuckles crack, then a confident Enter. 1.5 hard cut to black: no header, no music. 1.8–2.6 the
  narrator speaks on black. 2.8–3.5 back at the desk: the screen shows `−€72,456` in red, and the laptop smokes.
- Says: "This will definitely work." (0.2–1.4). The narrator: "It did not." (1.8–2.6).
- Sound: a tap on Enter, silence on black, slide (falling) at 2.8.

### Zoom in – THE SOLUTION (15.0 s)

- Camera: straight down over the centre of the diagram, in one move with no cut. Keyframes: at 0.0 the whole diagram
  fills the frame; at 7.5 only TS:LEAN fills it, every other system out of frame; at 15.0 `bestPrice()` fills it.
  Between the keyframes the camera's height changes on a log scale, so the zoom feels even, easing in at the start
  and out at the end.
- Beats: 0–4.0 the whole map; each system lights up as the voice names it. 4.0–7.5 the camera dives at TS:LEAN while
  event tokens run along the roads from SPREAD WORLD through `World.stream()` and `Desk.handle()` into `Lean`. 7.5
  only TS:LEAN is on screen. 7.5–11.5 the three decisions light up in turn: the price (left and centre), the fee
  (right), the chains (below). 11.5–15.0 the push into `quote()` and `bestPrice()`: the tile opens into its chart, and
  at 14.6 the peak gets its mark.
- Says: "Everything that touches ts:lean: Bahn's world, our harness, ops and saved weeks." (0.2–3.8). "Every request
  and booking is an event, and ts:lean answers each one." (4.0–7.4). "Three decisions: the price, the driver's fee,
  and which cars share a driver." (7.7–11.3). "The price: win chance times profit, minus what one more order costs
  the rest." (11.5–14.9).
- Sound: the beat low and filtered under the voice, a soft tap as each block lights up, a riser from 11.5, ding at
  14.6.

### Zoom out – THE SOLUTION (10.0 s)

- Camera: the same path backwards: `bestPrice()` at 0.0, TS:LEAN filling the frame at 4.0, the whole diagram at 10.0.
  From 7.0 the camera tilts to about 35° so the cars read as 3D, and the labels stay readable.
- Beats: as the camera pulls back, the roads fill with traffic that moves the way the code does:
  - A grey car is a price request. It drives from SPREAD WORLD along `events` and through `Desk.handle()` into
    `quote()`; at `canServe()` a barrier lifts, at `bestPrice()` a price tag pops onto its roof, and it drives back
    out along `actions`.
  - A red car is a won order (`order_won`). It drives into `gig()`; over the road at `stepped()` a fee sign ticks from
    0.88 to 1.05 to 1.25 × typical; a driver walks over from SPREAD WORLD, gets in and drives it out (`delivered`).
  - At `findChains()` up to four red cars line up behind one driver and leave together, under a sign
    `chain · 1 driver`.
  - Small glowing tokens ride back on thin dotted lines from `observe()` to `Demand.learn()` (`order_won`,
    `order_lost`) and to `Supply.learn()` (`gig_booked`).
  - Wide, every road is busy: `Recorder.save()` sends finished weeks to SAVED WEEKS, ANALYSIS sends `noise 0.11`,
    `taxLoad 0.47` and `order.json` back up into TS:LEAN, and SIMULATOR runs a pale copy of the traffic.
- Says: "Won cars become gigs: fees open low and rise when drivers plan." (0.3–3.4). "Chains: up to four cars, one
  driver, fifteen hundred sixty euros a week." (3.6–7.0), captioned `Chains: up to four cars, one driver, +€1,560 a
  week.` "And every booking and lost quote teaches the model." (7.2–9.8).
- Sound: engines that rise with the traffic, a whoosh on the tilt at 7.0, where the beat comes back to full.

### Result – THE RESULT (4.5 s)

- Set: the whole diagram stays behind, dimmed, its traffic still moving. In front, a board: `+€24,451 a week`,
  `on time 99.9999999%` on a gauge past its `90%` line, `63 strategies → 1`, and in small text
  `all euros are game euros`.
- Says: "Plus twenty-four thousand, four hundred fifty-one euros a week." (0.2–2.8), captioned `+€24,451 a week.` "On
  time: basically always." (3.0–4.2). Lying caption: `[trust me bro]`.
- Sound: slot as the numbers spin in, kaching at 2.0.

### Handshake – joke 3 and the end (3.0 s)

- Set: the hall; a whiteboard with the same diagram drawn by hand in marker; bright, soft, washed-out stock-photo
  light.
- Cast: the developer and a teammate, both with `BLIB BLIB` lanyards.
- Beats: 0–3.0 a firm handshake, both smiling at the camera, held far too long: a slow push-in, and the smiles never
  move. 1.0 the end title fades in: `ts:lean`, and under it `by BLIB BLIB`. 2.2 the teammate blinks once.
- Says: nothing. The silence is the joke.
- Sound: elevator music (music box only).

## Voice lines

Made with ElevenLabs like the joke video's (`video/voices.ts`, pre-made voices, delivery tags); neither voice is a
copy of a real person's. Name the files `lean-…` so they never overwrite the joke video's. The voice gets
`T S lean`, so it says the letters; the captions keep `ts:lean`.

| Name             | Voice | Delivery        | Text for the voice                                                                   | Caption                                              |
| ---------------- | ----- | --------------- | ------------------------------------------------------------------------------------ | ---------------------------------------------------- |
| `lean-careful`   | liam  | `[deadpan]`     | We tested every strategy carefully.                                                  | [we threw 63 at a wall]                              |
| `lean-stuck`     | liam  | `[hushed]`      | Only one stuck.                                                                      | as said                                              |
| `lean-problem`   | liam  | `[calm, clear]` | The problem: price the car now, find a driver later.                                 | as said                                              |
| `lean-high`      | liam  | `[calm, clear]` | Quote too high, and the competitor wins it.                                          | as said                                              |
| `lean-low`       | liam  | `[calm, clear]` | Pay too little, and no driver comes in time.                                         | as said                                              |
| `lean-work`      | liam  | `[confident]`   | This will definitely work.                                                           | as said                                              |
| `lean-didnot`    | adam  | `[deep, slow]`  | It did not.                                                                          | as said                                              |
| `lean-touches`   | liam  | `[calm, clear]` | Everything that touches T S lean: Bahn's world, our harness, ops and saved weeks.    | as said, with `ts:lean`                              |
| `lean-events`    | liam  | `[calm, clear]` | Every request and booking is an event, and T S lean answers each one.                | as said, with `ts:lean`                              |
| `lean-decisions` | liam  | `[calm, clear]` | Three decisions: the price, the driver's fee, and which cars share a driver.         | as said                                              |
| `lean-price`     | liam  | `[calm, clear]` | The price: win chance times profit, minus what one more order costs the rest.        | as said                                              |
| `lean-fees`      | liam  | `[calm, clear]` | Won cars become gigs: fees open low and rise when drivers plan.                      | as said                                              |
| `lean-chains`    | liam  | `[calm, clear]` | Chains: up to four cars, one driver, fifteen hundred sixty euros a week.             | Chains: up to four cars, one driver, +€1,560 a week. |
| `lean-learn`     | liam  | `[calm, clear]` | And every booking and lost quote teaches the model.                                  | as said                                              |
| `lean-margin`    | liam  | `[proud]`       | Plus twenty-four thousand, four hundred fifty-one euros a week.                      | +€24,451 a week.                                     |
| `lean-ontime`    | liam  | `[smug]`        | On time: basically always.                                                           | [trust me bro]                                       |

## New things to build

Everything else comes from the joke video.

- The diagram as data: one file that lists every system, class, function, road and tag with its place, read by both
  zoom views, so that each name can be checked against the code and changed in one place.
- Slabs for systems, raised boxes for classes and small tiles for functions, in the palette's colours: TS:LEAN
  `ourRed`, HARNESS `denim`, KIT `metal`, OPS `pine`, SPREAD WORLD `taxiYellow`, SAVED WEEKS `wall`, ANALYSIS `gold`,
  SIMULATOR `glass`, PYTHON TWIN a lighter red.
- Labels from `textTexture()` in the three sizes; a monospace font for functions (a new `MONO` beside `FONT` and `UI`
  in `text.js`); the green tags.
- Roads: asphalt strips (`C.asphalt`) with dashed white lines, arrowheads and the label painted on; thin dotted lines
  for the learning tokens.
- Traffic: `car()` in grey for requests and red for orders; drivers from `character()`; event tokens as small glowing
  pills with the event's name; the barrier at `canServe()`, the fee sign at `stepped()`, the `chain · 1 driver` sign.
- The chart inside `bestPrice()`, drawn with `liveTexture()` from the real `chance()` formula.
- The log-scale camera path of both zooms, with the keyframes above.
- The spaghetti strands with tags, the splats, the `ELIMINATED` stamps and the wall counter; the problem's request
  card, competitor car, gauge and `NOT RANKED` stamp; the whiteboard with the hand-drawn diagram; the lanyards.
- No new sounds: whoosh, splat, slot, twinkle, ding, tap, boom, slide, riser, engine, kaching and musicBox are in
  `video/src/audio/synth.js` already.

## How to build it

- Follow `video/README.md`. Reuse `src/kit/`, `src/audio/`, the player and the MP4 export; give this video its own
  timeline file and view files, and let the player choose which video to play and render.
- Every frame depends only on its time, the traffic too: each car follows its road by a formula of the time from a
  seeded start, never by stepping a simulation.
- The diagram must match the code that it is built from. Check each name with `grep` before rendering: `ts:lean`
  changes often (`rested()` came on 15 November).

## Pacing and sound

- One idea per line, and the picture shows each thing as the voice names it.
- An effect on most cuts and every reveal; the sounds are listed with each scene.
- Music: the joke video's beat from `audio/score.js`, low and filtered under the explanation, full in the spaghetti
  and from 7.0 in the zoom out, silent on the black frame, and elevator music (music box only) for the handshake. The
  mixer dips it under speech to about 15–20% of its level. No copyrighted songs: they get videos muted or blocked.

## Before you upload

### Filled in

- [x] `[ALGO]`: `ts:lean`
- [x] `[TEAM]`: Blib Blib
- [ ] The team members' names for the end card, if you want them there
- [x] `[OUR NUMBER]`: +€24,451
- [x] `[BASELINE]`: −€72,456
- [x] `[X]%`: 99.9999999% on time, above the 90% line for being ranked
- [x] The number of strategies: 63

### Check

- [ ] Under 50 seconds, and the spaghetti makes someone curious within 3 seconds
- [ ] Three cutaway jokes at most: the spaghetti, "It did not" and the handshake
- [ ] Every system, class and function on the diagram exists under that name in the code, and every tag's number is
      in `src/strategies/lean/README.md`
- [ ] Systems biggest, classes medium, functions smallest, and all of them readable on a phone at the zoom's middle
- [ ] +€24,451 and −€72,456 match the test URL; 99.9999999% is the one joke number
- [ ] Captions on for every line, readable on a phone, with `ts:lean`, Bahn and Blib Blib spelled right
- [ ] No real logos or copyrighted music
- [ ] Any teammate a character is based on has seen it and laughs
- [ ] Someone who hasn't seen it watched it once, and you fixed the parts where they got bored
- [ ] Exported at 1080×1920, 30 fps, H.264, and the uploaded version plays with sound

All amounts in the simulation are game euros. Facts about the challenge come from Bahn's
[How it works](https://spread.bahnexpress.com/how) page, and facts about `ts:lean` from its
[README](src/strategies/lean/README.md).
