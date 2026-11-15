# Prompt: build the ts:lean video

Build a 127-second (2:07) technical video for YouTube, 16:10 (1920×1200, 30 fps), that shows how `ts:lean` works: the
dispatch system our team Blib Blib built at Junction 2026 for Bahn's Spread challenge. It is built in `video/` beside
the joke video and shares its player, kit, sound and export (`?video=lean`; `video/README.md` says where its parts
are). Four developers throw spaghetti at a wall, the problem is stated, a race like a car leads into `ts:lean`, and
the solution is shown as a block diagram of the real code: a 15-second zoom in, a closer look at the fees, the chains
and the learning, and a zoom out during which cars and drivers drive along the diagram's lanes the way the code moves
them. `ts:lean` is on screen for 75.5 seconds, well over a minute. It has three cutaway jokes and no more, ends with
the four developers' high five at the same wall, and runs 2:07: the result's second row may take it past 2 minutes.

## The story

The spaghetti says how we got here: four developers throw 63 strategies at a wall, and one sticks. A title card
names the video. Then the problem in four lines, and the list price that failed. Then a race down `ts:lean`'s lanes
leads into the solution, which is the code itself, drawn as a map: its three decisions, how it learns, and the cars
moving through it. Then the result, and back at the wall the four developers high-five under the one strand that
stuck.

## The numbers

| What           | Value                                                                       | Shown in                                     |
| -------------- | --------------------------------------------------------------------------- | -------------------------------------------- |
| `[ALGO]`       | `ts:lean`                                                                   | the strand that sticks, the diagram, the end |
| `[TEAM]`       | Blib Blib                                                                   | the title card, the mark, the end            |
| `[OUR NUMBER]` | +€24,451, our margin a week                                                 | the result                                   |
| `[BASELINE]`   | −€72,456                                                                    | "It did not"                                 |
| `[X]%`         | 99.9999999% on time (the one joke number; the line for being ranked is 90%) | the result                                   |
| Strategies     | 63                                                                          | the spaghetti, the result                    |
| Drivers        | +€3,000 a week, what drivers are paid less ("stolen from poor drivers")     | the result                                   |
| Dealers        | +€19,500 a week, what dealers pay over list ("stolen way more")             | the result                                   |
| Stakeholders   | +€22,500 a week, the two together as "stakeholder value"                    | the result, the voice                        |

The diagram shows no measured effects (they stay in `src/strategies/lean/README.md`), and the result's second row is
Vesa's figures. All euros are game euros. Every text, number and diagram label lives in `video/src/lean/timeline.js`
and `video/src/lean/diagram.js`.

## Format and style

- 127 s (2:07) in all; no view is longer than 15 s. The result's second row takes it past 2 minutes, as Vesa allowed.
  `ts:lean` is on screen from the race to the end of the traffic: 75.5 s, at a calm pace, its deep dives 11 to 14 s
  each.
- In chapter 02 the only words are names, of systems, classes and functions, the cards' titles, and the subtitles;
  graphs, colours and small pictures carry the rest, and the voice says the numbers. Every block keeps the same
  margins (see the block diagram below), and nothing that matters is cut by the edge of the picture.
- A professional technical YouTube look rather than a short: a dark navy ground with a fine grid, rounded panels with
  a rim in each system's colour, clean sans-serif names and monospace code, calm camera moves. The low-poly cast,
  cars and hall of the joke video come back in the scenes; they are our own models, not Roblox assets.
- Chapters: a tag at the top left with the chapter's number in a red square (`01 The problem`, `02 The solution:
  ts:lean`, `03 The result`), and a mark at the top right (`ts:lean · Blib Blib`). The jokes, the title card and the
  end have neither.
- Subtitles on for every spoken line: white sans-serif in a dark box at the bottom centre, at most two lines. Spell
  `ts:lean`, Bahn and Blib Blib exactly. Two lying subtitles: the spaghetti's first line and the on-time line.
- Hook: the spaghetti. The first frame is already mid-throw; the strands slap the wall from 1.2 s and slide off from
  1.9 s.
- Voices: `liam` explains (the developer's voice in the joke video) and `adam` says "It did not."
- Three cutaway jokes only: the spaghetti, "It did not" and "I am speed". The end goes back to the spaghetti wall
  instead of adding a fourth.

## Timeline (all times in seconds)

| Start | End   | View      | Chapter         | Content                                                                     |
| ----- | ----- | --------- | --------------- | --------------------------------------------------------------------------- |
| 0.0   | 9.0   | spaghetti |                 | Joke 1: four developers throw 63 strategies at the wall                     |
| 9.0   | 12.0  | title     |                 | `ts:lean`, what the video is about, the team                                |
| 12.0  | 23.0  | problem   | 01 The problem  | price now, driver later; too high; too little; 90%                          |
| 23.0  | 27.5  | didnot    |                 | Joke 2: "This will definitely work." "It did not."                          |
| 27.5  | 33.0  | speed     |                 | Joke 3: "I am speed", a race down `ts:lean`'s lanes                         |
| 33.0  | 48.0  | zoomin    | 02 The solution | into the diagram, 15 s                                                      |
| 48.0  | 62.0  | fees      | 02 The solution | the fee steps and the weekend                                               |
| 62.0  | 76.0  | chains    | 02 The solution | one driver for up to four cars, and the chain's fee                         |
| 76.0  | 87.0  | learning  | 02 The solution | the win curve and the driver costs learn from every quote                   |
| 87.0  | 97.0  | zoomout   | 02 The solution | out again, with the traffic, 10 s                                           |
| 97.0  | 103.0 | traffic   | 02 The solution | the whole map at its busiest                                                |
| 103.0 | 118.0 | result    | 03 The result   | six cards: margin, strategies, on time; drivers, stakeholder value, dealers |
| 118.0 | 127.0 | ending    |                 | the four developers' high five, with the end title                          |

## The block diagram

The code of `ts:lean` and everything that touches it, laid flat like a map: systems are panels, classes are plates,
functions are tiles, and the arrows between them are lanes. Both zooms and the result use the same diagram. Every name
is as in the code, and only the functions that every decision runs through or whose effect is measured are in.

- Names are its only words, in three sizes: systems the biggest (bold sans-serif, in the system's colour), classes
  medium (bold sans-serif), functions the smallest (monospace, with `()`). No paths, notes, numbers or tags; the
  measured effects stay in `src/strategies/lean/README.md`.
- One grid of margins (`video/src/lean/diagram.js` says it, and every block keeps it): a system keeps 1.5 clear inside
  its edge, a class plate 0.8 round its name and tiles, a tile is 2.2 high with at least 1 clear either side of its
  name, and neighbours keep 0.9 to 1 apart. A class or system with nothing inside has its name in its middle.
- Layout for 16:10: Bahn's world, the kit and the harness stacked above TS:LEAN; the Python twin and the ops on its
  left; the saved weeks and the analysis on its right; the simulator below. Inside TS:LEAN, in three bands: the name
  and the `Lean` class across the top; `Demand` and `Supply` on the left, `bestPrice()` at the exact centre and the fee
  functions on the right; `outlook()`, the `Planner` and the chain functions along the bottom. The main loop runs down
  from Bahn's world, round TS:LEAN on its left, along the lane over `bestPrice()`, and back up on its right.
- Systems: SPREAD WORLD (Bahn's server), KIT (`vendor/spread-typescript`: `Client`, `World` with `stream()` and
  `act()`), HARNESS (`src/harness`: `playLive()`, `Desk` with `handle()`, `Guard`, `Journal`), TS:LEAN
  (`src/strategies/lean`), OPS (`src/ops`: `canServe()`, `readNote()`, `gigShape()`), PYTHON TWIN
  (`strategies/lean/`), SAVED WEEKS (`src/record.ts`: `Recorder` with `save()`), ANALYSIS (`analysis/`:
  `supply_curve`, `lean_cost`), SIMULATOR (`sim/`). The paths are for the reader of this brief; the picture has only
  the names.
- Inside TS:LEAN: `cost()`, `load()`, `gig()`, `fees()`, `quote()`, `tick()` and `observe()` in `Lean`; `learn()` and
  `belief()` in `Demand`; `ratio()` and `learn()` in `Supply`; `stepped()`, `planBy()` and `rested()`; `outlook()`;
  `actions()` and `hold()` in `Planner`; `findChains()` and `bookChance()` (the chain model of #351); and
  `bestPrice()`, whose tile is the chart.
- The chart inside `bestPrice()`: its name and three curves, the win chance `chance(p) = 1/(1 + e^((ln p − μ)/s))`
  with μ = ln 1.40 and s = 0.11 (blue), the margin `p − cost` for an example cost of 1.00 × list (orange), and their
  product (green), with its peak, the quote at 1.35 × list, marked. No axis numbers, legend or formula.

## Scenes

Times inside a scene are its local seconds.

- **Spaghetti (9.0 s), joke 1.** The hackathon hall at night. Four developers in red, blue, green and purple shirts
  stand in front of a white wall, each tipping a pot of spaghetti held out in front of them. The first frame is
  already mid-throw in slow motion: 63 bundles of thin cooked strands fly at the wall and slap it from 1.2, each with
  a splash of tomato sauce. From 1.9 to 5.4 they slide down, the last on the floor by 6.7; `profit-max`, `max-margin`,
  `ratchet` and `war-guard` (all shelved, see `SHELVED.md`) get an ELIMINATED stamp, and a counter on the wall runs
  from 63 to 1. Then the camera pushes in on the one that sticks, a single strand, `ts:lean`, with sparkles. The floor
  is clean until the first ones slide off, and no sauce lands on the counter. Says "We tested every strategy
  carefully." (subtitle `[we threw spaghetti at a wall]`), "Spaghetti method: throw all sixty-three at the wall, see
  what sticks." and "Only one stuck."
- **Title (3.0 s).** Over the drifting grid: `ts:lean` rises in, a red rule grows under it, then "How we price a car
  delivery for Bahn's Spread challenge" and "Blib Blib · Junction 2026".
- **Problem (11.0 s), chapter 01.** Three panels: the dealer (Pertti and a car), `ts:lean`, and three drivers. A
  `price_request` card flies to `ts:lean` and a `gig` card to the drivers. Too high: a `1.9 × list` tag, and the
  competitor's grey car drives in and leaves with the dealer's car. Too little: a `fee 0.6 × typical` tag, the drivers
  shrug, a clock spins and a new car gets `LATE`. Then an on-time gauge falls under 90% and is stamped NOT RANKED.
  Says the four lines of the problem.
- **It did not (4.5 s), joke 2.** Hour 2, the developer's desk; the screen reads `STRATEGY #1: quote the list
  price`. "This will definitely work." Enter at 1.4, a hard cut at 1.95 to the laptop's webcam: the developer's face
  frozen in dark red light, a blinking REC dot, while the narrator says "It did not." At 3.4 the screen shows
  `−€72,456`, the laptop smokes and the head drops.
- **I am speed (5.5 s), joke 3.** Our own take on the meme, with nothing from the film: one second of black, then
  from 1.0 a chase camera behind a red car with a driver in sunglasses, racing down `ts:lean`'s main loop through
  `stream()`, `playLive()` and `handle()` onto the lane over `bestPrice()`, with speed lines. The voice whispers
  "Focus. Speed. I am speed." At 4.0 a sonic boom and a fast zoom out that ends exactly on the zoom in's first frame.
- **Zoom in (15.0 s), chapter 02.** One move with no cut, its height on a log scale. At 0 the whole diagram, seen
  tilted and slightly turned; the camera levels out by 6.5 and comes down so that at 7.5 only TS:LEAN fills the frame,
  lingers there while the three decisions light up, and dives from 11 until `bestPrice()` fills it at 15. The systems
  light up as the voice names them (1.0–3.4), events in four colours (price requests, won orders, booked gigs,
  deliveries) run down into TS:LEAN (3.2–7.2), the price, fee and chain functions light up in turn (7.9–11.0), and the
  chart draws in from 11.4 and marks its peak at the end.
- **Fees (14.0 s), chapter 02.** The camera glides to the fee column on the right of TS:LEAN, and the rest of the
  picture dims, so only the blocks it is about stay bright. A card on the left holds two graphs under their
  functions' names: `stepped()`, the fee opening low and rising three times while drivers plan their day, then the
  top; and `rested()`, the same steps held flat over the weekend (the shaded band) where they would have risen
  (dashed). Red cars stop over `stepped()` while a meter of four bars fills. Says "Fees open low and rise three times,
  when drivers plan their day." and "And no raises on weekends: Monday's cars wait for Monday."
- **Chains (14.0 s), chapter 02.** On to `tick()`, the `Planner`, `findChains()` and `bookChance()`, the bright part
  moving with the camera. The card: `findChains()`, four cars on one route and the one driver going from the first to
  the last; and `bookChance()`, the share of chains that book before it (grey) and with it (green, taller). Two
  chains form on the lane and leave together under a link sign. Says "Chains: one driver takes up to four cars, one
  after another." and "Each chain's fee follows its chance to book."
- **Learning (11.0 s), chapter 02.** On to `Demand` and `Supply` on the left; green sparks run back from
  `observe()`. The card, now on the right: `Demand.learn()`, the win curve whose middle moves as won (green) and lost
  (red) quotes land on it; and `Supply.ratio()`, bookings coming in one by one while the line climbs to what drivers
  really cost. Says "Every won or lost quote moves the win curve." and "Every booking teaches what drivers cost."
- **Zoom out (10.0 s), chapter 02.** The dimming fades as the camera goes back up to TS:LEAN, then out to the whole
  diagram by 10, tilting again from 6.0. A grey car is a price request: it comes down the loop, stops on the lane
  over `bestPrice()` for its price (a green coin with a tick), and goes back out. A red car is a won order: it stops
  over `stepped()` while the fee meter fills and a driver gets in. Red cars that wait behind one driver leave
  together as a chain, and weeks, constants and simulator runs fill the outer lanes as coloured chips. Says "Grey cars
  are price requests; red ones are won orders." and "A thousand requests a week, all through these lanes."
- **Traffic (6.0 s), chapter 02.** The whole map, turning slowly as the camera rises, with the most cars of the
  video. No voice; the music comes up.
- **Result (15.0 s), chapter 03.** The diagram stays behind, dimmed, with its traffic. Six cards come up in two rows
  of three. The first: `+€24,451` (margin a week), `63 → 1` (strategies tried → shipped) and the on-time share, its
  decimals ticking in to `99.9999999%`. Says the margin line and "On time: basically always." (subtitle `[trust me
  bro]`). Then, as the voice says "By stealing from drivers and dealers, we add twenty-two thousand five hundred euros
  to stakeholder value each week." (subtitle with `€22,500`), the second row: `+€3,000` "stolen from poor drivers, we
  pay them less, every week" at "drivers" (8.2), `+€19,500` "stolen way more from dealers, they pay over list price,
  a week" at "dealers" (8.9), and in the middle, glowing, `+€22,500` "stakeholder value added, from drivers and
  dealers, a week" at the number (9.9). "All euros are game euros." under the cards.
- **Ending (9.0 s), the end.** Back at the spaghetti wall at hour 48, under a `SHIPPED` banner: sauce, fallen strands,
  and `ts:lean`, the single strand, still stuck with its tag. The four developers, with `BLIB BLIB` lanyards, stand in
  a ring. At 1.1 they wind up and jump, and their hands meet at 1.7 in a four-way high five ("Ship it!"), hanging in
  slow motion while confetti and spaghetti burst. They land by 3.6 and cheer while the camera circles a quarter turn
  round them. At 3.0 the end title comes up as a lower third: `ts:lean`, "by BLIB BLIB · Junction 2026". "That's
  ts:lean." Fade to black from 8.4.

## Voice lines

Made with ElevenLabs like the joke video's (`video/voices.ts`, pre-made voices, delivery tags); neither voice is a
copy of a real person's. The files are named `lean-…` so they never overwrite the joke video's, and the voice reads
`ts:lean` as the letters. Each line fits its subtitle's time; a few are sped up by at most 1.12 (`rate`). The words,
subtitles and times are in `video/src/lean/timeline.js`: `lean-careful`, `lean-spaghetti`, `lean-stuck`,
`lean-problem`, `lean-high`, `lean-low`, `lean-ranked`, `lean-work`, `lean-didnot`, `lean-speed`, `lean-touches`,
`lean-events`, `lean-decisions`, `lean-price`, `lean-fees`, `lean-weekend`, `lean-chains`, `lean-chancefee`,
`lean-learn`, `lean-supply`, `lean-cars`, `lean-requests`, `lean-margin`, `lean-ontime`, `lean-stealing`, `lean-shipit`,
`lean-thatsit`.

## Sound

The joke video's beat from `audio/score.js`, quiet under the explanation and fuller in the spaghetti, the race and
once the traffic is out; silent under the narrator; after the race's second of silence, a phonk beat with a cowbell;
a party beat for the high five; an effect on most cuts and reveals. The mixer dips the music under speech. No
copyrighted songs, and nothing from the film the speed joke points at.

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

- [x] The voice lines are made (`node --env-file=.env.local video/voices.ts`), and each fits its subtitle's time
- [ ] About 2 minutes (2:07), and the spaghetti makes someone curious within 3 seconds
- [ ] Three cutaway jokes at most: the spaghetti, "It did not" and "I am speed"
- [ ] Every system, class and function on the diagram exists under that name in the code
- [ ] +€24,451 and −€72,456 match the test URL; 99.9999999% is the one joke number
- [ ] Subtitles on for every line, readable at 1080p, with `ts:lean`, Bahn and Blib Blib spelled right
- [ ] No real logos, copyrighted music or film clips
- [ ] Any teammate a character is based on has seen it and laughs
- [ ] Someone who hasn't seen it watched it once, and you fixed the parts where they got bored
- [ ] Exported at 1920×1200, 30 fps, H.264, and the uploaded version plays with sound

All amounts in the simulation are game euros. Facts about the challenge come from Bahn's
[How it works](https://spread.bahnexpress.com/how) page, and facts about `ts:lean` from its
[README](src/strategies/lean/README.md).
