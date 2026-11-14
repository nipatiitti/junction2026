// The block diagram of ts:lean and everything that touches it, as data: one place to check every name against the
// code and to move a block. The diagram lies flat on the ground. x runs to the right of the picture and z down it;
// a rect is [x0, z0, x1, z1] in world units. The picture is 16:10. `bestPrice()` sits at the exact centre, (0, 0),
// where the zoom in ends. Names are as in the code on main (15 November 2026); prompt.md says why each is in.

/** Label heights in world units: systems biggest, classes medium, functions smallest; tags and notes under them. */
export const SIZES = { system: 6, class: 2.4, function: 1.3, tag: 1.0 }

export const SYSTEMS = [
  {
    id: 'world',
    label: 'SPREAD WORLD',
    path: 'dealers · drivers · the gig app',
    color: '#f59e0b',
    rect: [-70, -82, 70, -68],
  },
  { id: 'kit', label: 'KIT', path: 'vendor/spread-typescript', color: '#94a3b8', rect: [-60, -64, 60, -47] },
  {
    id: 'harness',
    label: 'HARNESS',
    path: 'src/harness',
    color: '#60a5fa',
    rect: [-60, -43, 60, -30],
    align: 'center',
  },
  {
    id: 'lean',
    label: 'TS:LEAN',
    path: 'src/strategies/lean',
    color: '#ef4444',
    rect: [-36, -22.5, 36, 19],
    pathBelow: true,
  },
  {
    id: 'python',
    label: 'PYTHON TWIN',
    path: 'strategies/lean/',
    color: '#f472b6',
    rect: [-92, -22.5, -46, -3],
    note: 'same week, action for action',
    pathBelow: true,
  },
  { id: 'ops', label: 'OPS', path: 'src/ops', color: '#34d399', rect: [-92, 1, -46, 19] },
  {
    id: 'saved',
    label: 'SAVED WEEKS',
    path: 'src/record.ts',
    color: '#a78bfa',
    rect: [46, -22.5, 92, -3],
    pathBelow: true,
  },
  { id: 'analysis', label: 'ANALYSIS', path: 'analysis/', color: '#facc15', rect: [46, 1, 92, 19] },
  { id: 'sim', label: 'SIMULATOR', path: 'sim/', color: '#22d3ee', rect: [-30, 27, 30, 41], note: '40 seeds a batch' },
]

/** Classes: a plate on their system, the name at `labelAt` (its left end) or at the plate's top left. */
export const CLASSES = [
  { id: 'Client', system: 'kit', rect: [-58.6, -54, -40, -48.2] },
  { id: 'World', system: 'kit', rect: [-28.5, -63, 28.5, -48.2], labelAt: [-6, -60.4] },
  { id: 'Guard', system: 'harness', rect: [-58.6, -41.6, -40, -31.4], note: 'a time budget\nfor every call' },
  { id: 'Desk', system: 'harness', rect: [-28.5, -35.4, 28.5, -31], labelAt: [-18.4, -33.2] },
  { id: 'Journal', system: 'harness', rect: [40, -41.6, 58.6, -31.4], note: 'replays a\nrestarted week' },
  { id: 'Lean', system: 'lean', rect: [-1.5, -21.8, 34.6, -9.8] },
  { id: 'Demand', system: 'lean', rect: [-34.5, -6.9, -13, -0.6] },
  { id: 'Supply', system: 'lean', rect: [-34.5, 0.4, -13, 7.6] },
  { id: 'Planner', system: 'lean', rect: [-23, 9.4, 3, 16.6] },
  { id: 'Recorder', system: 'saved', rect: [47.4, -11.4, 90.6, -4.4] },
]

/** Functions: a tile with the name in the monospace font; `tag` is a measured effect in green under it. */
export const FUNCTIONS = [
  { id: 'stream', label: 'stream()', owner: 'World', rect: [-28, -56.4, -20, -54.6] },
  { id: 'act', label: 'act()', owner: 'World', rect: [20, -56.4, 28, -54.6] },
  { id: 'playLive', label: 'playLive()', system: 'harness', rect: [-28, -40, -20, -38.2] },
  { id: 'handle', label: 'handle()', owner: 'Desk', rect: [-28, -34, -20, -32.2] },
  { id: 'cost', label: 'cost()', owner: 'Lean', rect: [-0.8, -17.3, 7.2, -15.5] },
  { id: 'load', label: 'load()', owner: 'Lean', rect: [8, -17.7, 16, -14.9], tag: '+€972 a week' },
  { id: 'gig', label: 'gig()', owner: 'Lean', rect: [16.8, -17.3, 24.8, -15.5] },
  { id: 'fees', label: 'fees()', owner: 'Lean', rect: [25.6, -17.3, 33.6, -15.5] },
  { id: 'quote', label: 'quote()', owner: 'Lean', rect: [-0.8, -13, 7.2, -11.2] },
  { id: 'tick', label: 'tick()', owner: 'Lean', rect: [8, -13, 16, -11.2] },
  { id: 'observe', label: 'observe()', owner: 'Lean', rect: [25.6, -13, 33.6, -11.2] },
  { id: 'bestPrice', label: 'bestPrice()', system: 'lean', rect: [-11, -6.875, 11, 6.875], chart: true },
  { id: 'demandLearn', label: 'learn()', owner: 'Demand', rect: [-33.8, -3.3, -24.2, -1.5] },
  { id: 'belief', label: 'belief()', owner: 'Demand', rect: [-23.2, -3.3, -13.6, -1.5] },
  { id: 'ratio', label: 'ratio()', owner: 'Supply', rect: [-33.8, 3.6, -24.2, 6.6], tag: '+€769 a week (sim)' },
  { id: 'supplyLearn', label: 'learn()', owner: 'Supply', rect: [-23.2, 4.2, -13.6, 6] },
  { id: 'outlook', label: 'outlook()', system: 'lean', rect: [-34.5, 9.6, -25, 12.6], tag: '+€771 a week' },
  { id: 'stepped', label: 'stepped()', system: 'lean', rect: [13, -6.9, 34.5, -4.1], tag: 'every week ranked' },
  { id: 'planBy', label: 'planBy()', system: 'lean', rect: [13, -2.9, 34.5, -1.1] },
  { id: 'rested', label: 'rested()', system: 'lean', rect: [13, 0.1, 34.5, 2.9], tag: '+€624 a week' },
  { id: 'actions', label: 'actions()', owner: 'Planner', rect: [-22.4, 13, -11, 14.8] },
  { id: 'hold', label: 'hold()', owner: 'Planner', rect: [-10, 12.4, 2.4, 15.4], tag: '+€826 a week (sim)' },
  { id: 'findChains', label: 'findChains()', system: 'lean', rect: [6, 11.2, 21, 14.2], tag: '+€1,560 a week' },
  { id: 'bookChance', label: 'bookChance()', system: 'lean', rect: [22, 11.2, 34.5, 14.2], tag: '+€1,126 a week' },
  { id: 'readNote', label: 'readNote()', system: 'ops', rect: [-90.6, 7.4, -70.8, 9.2] },
  { id: 'canServe', label: 'canServe()', system: 'ops', rect: [-69.4, 7.4, -49.6, 9.2] },
  { id: 'gigShape', label: 'gigShape()', system: 'ops', rect: [-90.6, 11.4, -70.8, 13.2] },
  { id: 'save', label: 'save()', owner: 'Recorder', rect: [74, -9.2, 89.8, -7.4] },
  { id: 'supplyCurve', label: 'analysis.supply_curve', system: 'analysis', rect: [47.4, 7.4, 70, 9.2] },
  { id: 'leanCost', label: 'analysis.lean_cost', system: 'analysis', rect: [47.4, 11, 70, 12.8] },
]

/** Notes in the tag size: [text, x, z, align]. */
export const NOTES = [
  ['order.json', -34.5, 14, 'left'],
  ['chain.json', 22, 15.6, 'left'],
  ['→ noise 0.11 · taxLoad 0.47 · order.json', 47.4, 16.2, 'left'],
]

/** Roads that the traffic drives on, with what is painted beside them: { points, width, label, labelAt, turn }. */
export const ROADS = [
  {
    id: 'events',
    points: [
      [-24, -68],
      [-24, -56.4],
    ],
    label: 'events',
    labelAt: [-27.4, -65],
    turn: true,
  },
  {
    id: 'stream',
    points: [
      [-24, -54.6],
      [-24, -40],
    ],
  },
  {
    id: 'loop',
    points: [
      [-24, -38.2],
      [-24, -34],
    ],
  },
  {
    id: 'calls',
    points: [
      [-24, -32.2],
      [-24, -26.5],
      [-39, -26.5],
      [-39, -8],
    ],
  },
  {
    id: 'lane',
    points: [
      [-39, -8],
      [39, -8],
    ],
    width: 1.6,
  },
  {
    id: 'back',
    points: [
      [39, -8],
      [39, -26.5],
      [24, -26.5],
      [24, -54.6],
    ],
  },
  {
    id: 'actions',
    points: [
      [24, -56.4],
      [24, -68],
    ],
    label: 'actions',
    labelAt: [27.4, -65],
    turn: true,
  },
  {
    id: 'weeks',
    points: [
      [60, -55.5],
      [69, -55.5],
      [69, -22.5],
    ],
    label: 'every week',
    labelAt: [72.4, -40],
    turn: true,
  },
  {
    id: 'fits',
    points: [
      [69, -3],
      [69, 1],
    ],
  },
  {
    id: 'constants',
    points: [
      [46, 14],
      [36, 14],
    ],
  },
  {
    id: 'seeds',
    points: [
      [92, -13],
      [98, -13],
      [98, 34],
      [30, 34],
    ],
    label: 'recorded seeds',
    labelAt: [101.4, 10],
    turn: true,
  },
  {
    id: 'simulate',
    points: [
      [0, 27],
      [0, 19],
    ],
  },
  {
    id: 'twin',
    points: [
      [-46, -13],
      [-36, -13],
    ],
  },
  {
    id: 'ops',
    points: [
      [-36, 13],
      [-46, 13],
    ],
    width: 1.6,
  },
]

/** Thin lines of data between blocks, under the tiles; `dotted` for what learning sends back. */
export const LINES = [
  {
    points: [
      [3.2, -11.2],
      [3.2, -6.875],
    ],
  },
  {
    points: [
      [3.2, -15.5],
      [3.2, -13],
    ],
  },
  {
    points: [
      [8, -15.6],
      [7.6, -15.6],
      [7.6, -12.1],
      [7.2, -12.1],
    ],
  },
  {
    points: [
      [-13.6, -2.4],
      [-11, -2.4],
    ],
  },
  {
    points: [
      [-34.5, 5.1],
      [-35.3, 5.1],
      [-35.3, -11.4],
      [-1.1, -11.4],
      [-1.1, -16.4],
      [-0.8, -16.4],
    ],
  },
  {
    points: [
      [-34.5, 11.1],
      [-35.3, 11.1],
      [-35.3, 5.1],
    ],
  },
  {
    points: [
      [24.8, -16.4],
      [25.6, -16.4],
    ],
  },
  {
    points: [
      [32, -15.5],
      [32, -6.9],
    ],
  },
  {
    points: [
      [23.75, -4.1],
      [23.75, -2.9],
    ],
  },
  {
    points: [
      [23.75, -1.1],
      [23.75, 0.1],
    ],
  },
  {
    points: [
      [12, -11.2],
      [12, 10.2],
      [3, 10.2],
    ],
  },
  {
    points: [
      [2.4, 13.9],
      [6, 13.9],
    ],
  },
  {
    points: [
      [21, 12.7],
      [22, 12.7],
    ],
  },
  {
    points: [
      [28.5, -33.2],
      [40, -33.2],
    ],
  },
  {
    id: 'learn',
    points: [
      [29.6, -11.2],
      [29.6, -9.3],
      [-12.4, -9.3],
      [-12.4, 5.1],
      [-13.6, 5.1],
    ],
    dotted: true,
  },
  {
    points: [
      [-12.4, -2.4],
      [-13.6, -2.4],
    ],
    dotted: true,
  },
]

/** The routes the traffic takes, as roads in order. */
export const ROUTES = {
  // a request comes in as an event, gets its price at bestPrice() and goes back out as a quote
  quote: ['events', 'stream', 'loop', 'calls', 'lane', 'back', 'actions'],
  weeks: ['weeks'],
  seeds: ['seeds'],
  constants: ['constants'],
}

/** Where a request stops for its price, and an order for its fee, on the lane above the centre. */
export const STOPS = { price: [0, -8], fee: [23.75, -8] }

/** The framings the zooms pass through: the whole diagram, only TS:LEAN, and bestPrice() (the height of the ground
 * in the picture, and the point in its middle). */
export const FRAMES = {
  whole: { centre: [0, -20.5], height: 160 },
  lean: { centre: [0, -0.5], height: 56 },
  key: { centre: [0, 0], height: 19.6 },
}

/** The blocks that light up together when the voice names them. */
export const GROUPS = {
  touches: ['lean'],
  world: ['world', 'kit'],
  harness: ['harness'],
  ops: ['ops'],
  saved: ['saved', 'analysis', 'sim', 'python'],
  price: ['Demand', 'Supply', 'outlook', 'cost', 'load', 'quote', 'bestPrice'],
  fee: ['gig', 'fees', 'stepped', 'planBy', 'rested'],
  chains: ['tick', 'Planner', 'findChains', 'bookChance'],
}
