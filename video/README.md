# Joke video

A 44.5-second vertical video (1080×1920, 30 fps) about our dispatcher, in the low-poly 3D look of a "what if"
TikTok, made with Three.js. `PROMPT.md` has the full brief: the joke, the look, every scene and its beats.

## Run it

```bash
node video/serve.ts --port 8790
```

Open <http://localhost:8790>. The menu plays the whole video or one view. Space plays and pauses, the arrow keys
step one frame (with Shift, one second), Home goes back to the start. The address holds the view and its local time
(`#view=scene1&t=3.200`), so a link opens that frame. When a file under `video/` changes, the page reloads by itself
and stays on the same frame. "TikTok safe areas" shades the parts that TikTok's buttons and caption cover.

**Render MP4** renders the selected view, or the whole video, frame by frame and saves it to `video/out/<view>.mp4`
(H.264, about 12 Mbit/s; not committed). It needs a Chromium-based browser, which has WebCodecs. The video has no
sound yet.

## Where things are

| File              | What it holds                                                                         |
| ----------------- | ------------------------------------------------------------------------------------- |
| `src/timeline.js` | the order of the views, their lengths, every text on screen and the numbers           |
| `src/views/*.js`  | one file per view: its set, its cast and its beats with their times                   |
| `src/kit/*.js`    | shared by every view: characters, car, world props, effects, text, easing, randomness |
| `src/main.js`     | the player                                                                            |
| `src/export.js`   | the MP4 export                                                                        |
| `serve.ts`        | the static server, the reload signal and the endpoint that saves the MP4              |

To change a line or a length, edit `timeline.js`. To change what happens and when, edit the beats in the scene's
file; each file lists its beats at the top. A new kind of view exports `{ build(segment) }` and goes in
`src/views/index.js`. In the browser console, `player.frame('scene2', 3.2)` draws one frame of a view, for example
to save stills.

## Repeatable frames

Every frame depends only on its time. A view sets every position from its local time `t` with the keyframe and
easing helpers in `kit/anim.js`, random values come from seeded generators in `kit/rng.js`, and particles move by
formula. Scrubbing to a time always gives the same picture, and a change to one beat leaves the rest of the video as
it was. Three.js (0.186.1) and mp4-muxer (5.2.2) load from jsDelivr at pinned versions.

## Status

The title cards and scenes 1–4 are built. The end is a rough set with its cast and main beats.
The spoken lines are captions for now; voices, sound effects and music are still to come. The numbers in
`timeline.js` are placeholders until the final is played.
