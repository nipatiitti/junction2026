# Prompt: build the ts:lean video

Build a 58.5-second technical video for YouTube, 16:10 (1920×1200, 30 fps), that shows how `ts:lean` works: the
dispatch system our team Blib Blib built at Junction 2026 for Bahn's Spread challenge. It is built in `video/` beside
the joke video and shares its player, kit, sound and export (`?video=lean`; `video/README.md` says where its parts
are). It opens with spaghetti thrown at a wall, states the problem, and shows the solution as a block diagram of the
real code: a 15-second zoom in and a 10-second zoom out during which cars and drivers drive along the diagram's lanes
the way the code moves them. It has three cutaway jokes and no more, and it stays under 1.5 minutes.

## The story

The spaghetti says how we got here: 63 strategies thrown at a wall, and one stuck. A title card names the video. Then
the problem in four lines, and the list price that failed. Then the solution, which is the code itself, drawn as a
map with the cars moving through it. Then the result, and the end title.

## The numbers

| What           | Value                                                                       | Shown in                                  |
| -------------- | --------------------------------------------------------------------------- | ----------------------------------------- |
| `[ALGO]`       | `ts:lean`                                                                   | the strand that sticks, the diagram, the end |
| `[TEAM]`       | Blib Blib                                                                   | the title card, the mark, the end         |
| `[OUR NUMBER]` | +€24,451, our margin a week                                                 | the result                                |
| `[BASELINE]`   | −€72,456                                                                    | "It did not"                              |
| `[X]%`         | 99.9999999% on time (the one joke number; the line for being ranked is 90%) | the result                                |
| Strategies     | 63                                                                          | the spaghetti, the result                 |

The effects tagged on the diagram come from `src/strategies/lean/README.md`: each change against the same code
without it, on the same seeds, at level 8. All euros are game euros. Every text, number and diagram label lives in
`video/src/lean/timeline.js` and `video/src/lean/diagram.js`.

## Format and style

- 58.5 s in all; no view is longer than 15 s; never over 90 s.
- A professional technical YouTube look rather than a short: a dark navy ground with a fine grid, rounded panels with
  a rim in each system's colour, clean sans-serif names and monospace code, calm camera moves. The low-poly cast,
  cars and hall of the joke video come back in the scenes; they are our own models, not Roblox assets.
- Chapters: a tag at the top left with the chapter's number in a red square (`01 The problem`, `02 The solution:
  ts:lean`, `03 The result`), and a mark at the top right (`ts:lean · Blib Blib`). The jokes and the title card have
  neither.
- Subtitles on for every spoken line: white sans-serif in a dark box at the bottom centre, at most two lines. Spell
  `ts:lean`, Bahn and Blib Blib exactly. Two lying subtitles: the spaghetti's first line and the on-time line.
- Hook: the spaghetti. By 3.0 s the throw has landed and the strands are sliding off.
- Voices: `liam` explains (the developer's voice in the joke video) and `adam` says "It did not."
- Three cutaway jokes only: the spaghetti, "It did not" and the handshake.

## Timeline (all times in seconds)

| Start | End  | View      | Chapter                | Content                                             |
| ----- | ---- | --------- | ---------------------- | --------------------------------------------------- |
| 0.0   | 5.0  | spaghetti |                        | Joke 1: 63 strategies at the wall, one sticks       |
| 5.0   | 8.0  | title     |                        | `ts:lean`, what the video is about, the team        |
| 8.0   | 18.0 | problem   | 01 The problem         | price now, driver later; too high; too little; 90%  |
| 18.0  | 22.0 | didnot    |                        | Joke 2: "This will definitely work." "It did not."  |
| 22.0  | 37.0 | zoomin    | 02 The solution        | into the diagram, 15 s                              |
| 37.0  | 47.0 | zoomout   | 02 The solution        | out again, with the traffic, 10 s                   |
| 47.0  | 54.0 | result    | 03 The result          | three cards: margin, strategies, on time            |
| 54.0  | 58.5 | handshake |                        | Joke 3, with the end title as a lower third         |

## The block diagram

The code of `ts:lean` and everything that touches it, laid flat like a map: systems are panels, classes are plates,
functions are tiles, and the arrows between them are lanes. Both zooms and the result use the same diagram. Every name
is as in the code, and only the functions that every decision runs through or whose effect is measured are in.

- Labels in three sizes: systems the biggest (bold sans-serif, in the system's colour, with the code's path beside or
  under them), classes medium (bold sans-serif), functions the smallest (monospace, with `()`). A measured effect sits
  under its function as a green tag, such as `+€1,560 a week`; "(sim)" marks a simulator measurement.
- Layout for 16:10: Bahn's world, the kit and the harness stacked above TS:LEAN; the Python twin and the ops on its
  left; the saved weeks and the analysis on its right; the simulator below. Inside TS:LEAN: the `Lean` class across
  the top, `Demand` and `Supply` on the left, `bestPrice()` at the exact centre, the fee functions on the right, and
  `Planner` with `findChains()` at the bottom. The main loop runs down from Bahn's world, round TS:LEAN on its left,
  along the lane over `bestPrice()`, and back up on its right.
- Systems: SPREAD WORLD (Bahn's server), KIT (`vendor/spread-typescript`: `Client`, `World` with `stream()` and
  `act()`), HARNESS (`src/harness`: `playLive()`, `Desk` with `handle()`, `Guard`, `Journal`), TS:LEAN
  (`src/strategies/lean`), OPS (`src/ops`: `canServe()`, `readNote()`, `gigShape()`), PYTHON TWIN
  (`strategies/lean/`), SAVED WEEKS (`src/record.ts`: `Recorder` with `save()`), ANALYSIS (`analysis/`:
  `supply_curve`, `lean_cost`), SIMULATOR (`sim/`).
- Inside TS:LEAN, with their tags: `quote()`, `cost()`, `load()` (`+€972 a week`), `gig()`, `fees()`, `tick()` and
  `observe()` in `Lean`; `belief()` and `learn()` in `Demand`; `ratio()` (`+€769 a week (sim)`) and `learn()` in
  `Supply`; `outlook()` (`+€771 a week`) with `order.json`; `stepped()` (`every week ranked`), `planBy()` and
  `rested()` (`+€624 a week`); `actions()` and `hold()` (`+€826 a week (sim)`) in `Planner`; `findChains()`
  (`+€1,560 a week`) and `bookChance()` (`+€1,126 a week`, the chain model of #351, with `chain.json`); and
  `bestPrice()`, whose tile is the chart.
- The chart inside `bestPrice()`: on the left, the win chance `chance(p) = 1/(1 + e^((ln p − μ)/s))` with μ = ln 1.40
  and s = 0.11, the margin `p − cost` for an example cost of 1.00 × list, and their product with its peak marked:
  `quote 1.35 × list`, where 58% of such quotes win. On the right, the legend and the formula
  `quote = argmax chance(p) × (p·list − cost·(1 + 0.47·load))`.

## Scenes

Times inside a scene are its local seconds.

- **Spaghetti (5.0 s), joke 1.** The hackathon hall at night. The first frame is already mid-throw in slow motion:
  63 strands fly at a white wall and slap it at 1.4. From 1.6 to 3.0 they slide off; `profit-max`, `max-margin`,
  `ratchet` and `war-guard` (all shelved, see `SHELVED.md`) get an ELIMINATED stamp, and a counter on the wall runs
  from 63 to 1. Then the camera pushes in on the one that sticks, `ts:lean`, with sparkles. Says "We tested every
  strategy carefully." (subtitle `[we threw 63 at a wall]`) and "Only one stuck."
- **Title (3.0 s).** Over the drifting grid: `ts:lean` rises in, a red rule grows under it, then "How we price a car
  delivery for Bahn's Spread challenge" and "Blib Blib · Junction 2026".
- **Problem (10.0 s), chapter 01.** Three panels: the dealer (Pertti and a car), `ts:lean`, and three drivers. A
  `price_request` card flies to `ts:lean` and a `gig` card to the drivers. Too high: a `1.9 × list` tag, and the
  competitor's grey car drives in and leaves with the dealer's car. Too little: a `fee 0.6 × typical` tag, the drivers
  shrug, a clock spins and a new car gets `LATE`. Then an on-time gauge falls under 90% and is stamped NOT RANKED.
  Says the four lines of the problem.
- **It did not (4.0 s), joke 2.** Hour 2, the developer's desk; the screen reads `STRATEGY #1: quote the list price`.
  "This will definitely work." Enter at 1.4, a hard cut to black at 1.8, the narrator on black: "It did not." At 3.2
  the screen shows `−€72,456`, the laptop smokes and the head drops.
- **Zoom in (15.0 s), chapter 02.** One move with no cut, its height on a log scale. At 0 the whole diagram, seen
  tilted and slightly turned; the camera levels out by 6.5 and comes down so that at 7.5 only TS:LEAN fills the frame,
  lingers there while the three decisions light up, and dives from 11 until `bestPrice()` fills it at 15. The systems light up as the voice names them (1.0–3.4), event tokens (`price_request`,
  `order_won`, `gig_booked`, `delivered`) run down into TS:LEAN (3.4–7.6), the price, fee and chain functions light
  up in turn (8.5–11.6), and the chart draws in from 11.6, its peak marked at 14.6.
- **Zoom out (10.0 s), chapter 02.** The way back: up to TS:LEAN by 3.6, lingering while the chain waits, then out
  to the whole diagram by 10, tilting again from 6.0. A grey car is a price request:
  it comes down the loop, stops on the lane over `bestPrice()` for its price tag, and goes back out. A red car is a
  won order: it stops over `stepped()` while a fee sign ticks 0.88, 1.05, 1.25 × typical, and a driver gets in. Three
  red cars wait behind one driver and leave together under `chain · 1 driver`. Green sparks run back from
  `observe()` to `Demand` and `Supply`, and weeks, constants and simulator runs fill the outer lanes.
- **Result (7.0 s), chapter 03.** The diagram stays behind, dimmed, with its traffic. Three cards come up:
  `+€24,451` (margin a week), `63 → 1` (strategies tried → shipped) and the on-time share, its decimals ticking in to
  `99.9999999%`. "All euros are game euros." Says the margin line and "On time: basically always." (subtitle
  `[trust me bro]`).
- **Handshake (4.5 s), joke 3 and the end.** The developer and a teammate with `BLIB BLIB` lanyards shake hands in
  front of a whiteboard with the same diagram drawn by hand, in stock-photo light, for far too long; the teammate
  blinks once. At 1.0 the end title comes up as a lower third: `ts:lean`, "by BLIB BLIB · Junction 2026". Elevator
  music only.

## Voice lines

Made with ElevenLabs like the joke video's (`video/voices.ts`, pre-made voices, delivery tags); neither voice is a
copy of a real person's. The files are named `lean-…` so they never overwrite the joke video's, and the voice reads
`ts:lean` as the letters. The words, subtitles and times are in `video/src/lean/timeline.js`:
`lean-careful`, `lean-stuck`, `lean-problem`, `lean-high`, `lean-low`, `lean-ranked`, `lean-work`, `lean-didnot`,
`lean-touches`, `lean-events`, `lean-decisions`, `lean-price`, `lean-fees`, `lean-chains`, `lean-learn`,
`lean-margin`, `lean-ontime`.

## Sound

The joke video's beat from `audio/score.js`, quiet under the explanation and fuller in the spaghetti and once the
traffic is out, silent on the black frame; a music box for the handshake; an effect on most cuts and reveals. The
mixer dips the music under speech. No copyrighted songs.

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

- [ ] The voice lines are made (`node --env-file=.env.local video/voices.ts`), and each fits its subtitle's time
- [ ] Under 90 seconds, and the spaghetti makes someone curious within 3 seconds
- [ ] Three cutaway jokes at most: the spaghetti, "It did not" and the handshake
- [ ] Every system, class and function on the diagram exists under that name in the code, and every tag's number is
      in `src/strategies/lean/README.md`
- [ ] +€24,451 and −€72,456 match the test URL; 99.9999999% is the one joke number
- [ ] Subtitles on for every line, readable at 1080p, with `ts:lean`, Bahn and Blib Blib spelled right
- [ ] No real logos or copyrighted music
- [ ] Any teammate a character is based on has seen it and laughs
- [ ] Someone who hasn't seen it watched it once, and you fixed the parts where they got bored
- [ ] Exported at 1920×1200, 30 fps, H.264, and the uploaded version plays with sound

All amounts in the simulation are game euros. Facts about the challenge come from Bahn's
[How it works](https://spread.bahnexpress.com/how) page, and facts about `ts:lean` from its
[README](src/strategies/lean/README.md).
