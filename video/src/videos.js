import { STYLES } from './audio/score.js'
import { drawHeader, drawSafeAreas } from './kit/text.js'
import * as lean from './lean/timeline.js'
import { chrome, titleSafe } from './lean/ui.js'
import { VIEWS as LEAN_VIEWS } from './lean/views/index.js'
import { HEADER, HEIGHT, SEGMENTS, WIDTH } from './timeline.js'
import { VIEWS } from './views/index.js'

// The videos that the player plays. `?video=lean` in the address picks one; the joke video is the default. Each has
// its picture size, its segments, its kinds of view, the styles of its beat, the name of its MP4, `chrome` (what is
// drawn over every frame: the joke video's header, the ts:lean video's chapter tag) and `guides` (the safe areas).
export const VIDEOS = {
  joke: {
    title: 'Joke video',
    file: 'joke-video',
    width: WIDTH,
    height: HEIGHT,
    segments: SEGMENTS,
    views: VIEWS,
    styles: STYLES,
    chrome: (g) => drawHeader(g, HEADER),
    guides: drawSafeAreas,
  },
  lean: {
    title: 'ts:lean video',
    file: 'lean-video',
    width: lean.WIDTH,
    height: lean.HEIGHT,
    segments: lean.SEGMENTS,
    views: LEAN_VIEWS,
    styles: lean.STYLES,
    chrome,
    guides: titleSafe,
  },
}
