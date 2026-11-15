// The block diagram of ts:lean and everything that touches it, as data: one place to check every name against the
// code and to move a block. The diagram lies flat on the ground. x runs to the right of the picture and z down it;
// a rect is [x0, z0, x1, z1] in world units. The picture is 16:10. `bestPrice()` sits at the exact centre, (0, 0),
// where the zoom in ends. Names are as in the code on main (15 November 2026); prompt.md says why each is in.
//
// The only words on it are names, of systems, classes and functions, and every block keeps the same margins: a system
// keeps 1.5 clear inside its edge, a class plate 0.8 round its name and tiles, a tile is 2.2 high with at least 1 clear
// either side of its name, and tiles side by side keep 0.9 to 1 apart. A class without tiles has its name in its
// middle, and so has a system without blocks (`title: 'middle'`); `title: 'top'` puts a system's name at the top
// centre, out of the way of the lanes.

/** Label heights in world units: systems biggest, classes medium, functions smallest. */
export const SIZES = { system: 6, class: 2.4, function: 1.3 }

export const SYSTEMS = [
  { id: 'world', label: 'SPREAD WORLD', color: '#f59e0b', rect: [-70, -82, 70, -68] },
  { id: 'kit', label: 'KIT', color: '#94a3b8', rect: [-60, -64, 60, -47] },
  { id: 'harness', label: 'HARNESS', color: '#60a5fa', rect: [-60, -43, 60, -28.5], title: 'top' },
  { id: 'lean', label: 'TS:LEAN', color: '#ef4444', rect: [-36, -22.5, 36, 19] },
  { id: 'python', label: 'PYTHON TWIN', color: '#f472b6', rect: [-98, -22.5, -46, -3], title: 'middle' },
  { id: 'ops', label: 'OPS', color: '#34d399', rect: [-98, 1, -46, 19] },
  { id: 'saved', label: 'SAVED WEEKS', color: '#a78bfa', rect: [46, -22.5, 98, -3] },
  { id: 'analysis', label: 'ANALYSIS', color: '#facc15', rect: [46, 1, 98, 19] },
  { id: 'sim', label: 'SIMULATOR', color: '#22d3ee', rect: [-30, 27, 30, 41], title: 'middle' },
]

/** Classes: a plate on their system, the name at its top left, or at `labelAt` (`align` 'center' centres it there). */
export const CLASSES = [
  { id: 'Client', system: 'kit', rect: [-58.5, -56.6, -40, -48.5] },
  { id: 'World', system: 'kit', rect: [-30.5, -62.5, 30.5, -48.5], labelAt: [0, -60.8], align: 'center' },
  { id: 'Guard', system: 'harness', rect: [-58.5, -41.5, -40, -30] },
  { id: 'Desk', system: 'harness', rect: [-30.5, -35, 30.5, -30], labelAt: [-17.7, -32.5] },
  { id: 'Journal', system: 'harness', rect: [40, -41.5, 58.5, -30] },
  { id: 'Lean', system: 'lean', rect: [-6, -21, 34.5, -11.4] },
  { id: 'Demand', system: 'lean', rect: [-34.5, -6.875, -13.5, -0.475] },
  { id: 'Supply', system: 'lean', rect: [-34.5, 0.475, -13.5, 6.875] },
  { id: 'Planner', system: 'lean', rect: [-11, 11.1, 11, 17.5] },
  { id: 'Recorder', system: 'saved', rect: [60, -13, 84, -6.6] },
]

/** Functions: a tile with the name in the monospace font. bestPrice()'s tile is its chart. */
export const FUNCTIONS = [
  { id: 'stream', label: 'stream()', owner: 'World', rect: [-29, -55.3, -19, -53.1] },
  { id: 'act', label: 'act()', owner: 'World', rect: [19, -55.3, 29, -53.1] },
  { id: 'playLive', label: 'playLive()', system: 'harness', rect: [-29, -39.2, -19, -37] },
  { id: 'handle', label: 'handle()', owner: 'Desk', rect: [-29, -33.6, -19, -31.4] },
  // Lean: four columns in two rows, the right two over the fee column
  { id: 'cost', label: 'cost()', owner: 'Lean', rect: [-5.2, -17.6, 3.25, -15.4] },
  { id: 'load', label: 'load()', owner: 'Lean', rect: [4.15, -17.6, 12.6, -15.4] },
  { id: 'gig', label: 'gig()', owner: 'Lean', rect: [13.5, -17.6, 23.15, -15.4] },
  { id: 'fees', label: 'fees()', owner: 'Lean', rect: [24.05, -17.6, 33.7, -15.4] },
  { id: 'quote', label: 'quote()', owner: 'Lean', rect: [-5.2, -14.4, 3.25, -12.2] },
  { id: 'tick', label: 'tick()', owner: 'Lean', rect: [4.15, -14.4, 12.6, -12.2] },
  { id: 'observe', label: 'observe()', owner: 'Lean', rect: [13.5, -14.4, 23.15, -12.2] },
  // the middle band: Demand and Supply, bestPrice(), the fee column
  { id: 'bestPrice', label: 'bestPrice()', system: 'lean', rect: [-11, -6.875, 11, 6.875], chart: true },
  { id: 'demandLearn', label: 'learn()', owner: 'Demand', rect: [-33.7, -3.475, -24.5, -1.275] },
  { id: 'belief', label: 'belief()', owner: 'Demand', rect: [-23.5, -3.475, -14.3, -1.275] },
  { id: 'ratio', label: 'ratio()', owner: 'Supply', rect: [-33.7, 3.875, -24.5, 6.075] },
  { id: 'supplyLearn', label: 'learn()', owner: 'Supply', rect: [-23.5, 3.875, -14.3, 6.075] },
  { id: 'stepped', label: 'stepped()', system: 'lean', rect: [13.5, -6.875, 34.5, -4.675] },
  { id: 'planBy', label: 'planBy()', system: 'lean', rect: [13.5, -1.1, 34.5, 1.1] },
  { id: 'rested', label: 'rested()', system: 'lean', rect: [13.5, 4.675, 34.5, 6.875] },
  // the bottom band: outlook(), the Planner, the chains
  { id: 'outlook', label: 'outlook()', system: 'lean', rect: [-34.5, 13.2, -13.5, 15.4] },
  { id: 'actions', label: 'actions()', owner: 'Planner', rect: [-10.2, 14.5, -0.5, 16.7] },
  { id: 'hold', label: 'hold()', owner: 'Planner', rect: [0.5, 14.5, 10.2, 16.7] },
  { id: 'findChains', label: 'findChains()', system: 'lean', rect: [13.5, 11.1, 34.5, 13.3] },
  { id: 'bookChance', label: 'bookChance()', system: 'lean', rect: [13.5, 15.3, 34.5, 17.5] },
  { id: 'readNote', label: 'readNote()', system: 'ops', rect: [-96.5, 10.25, -72.75, 12.45] },
  { id: 'canServe', label: 'canServe()', system: 'ops', rect: [-71.25, 10.25, -47.5, 12.45] },
  { id: 'gigShape', label: 'gigShape()', system: 'ops', rect: [-96.5, 13.45, -72.75, 15.65] },
  { id: 'save', label: 'save()', owner: 'Recorder', rect: [60.8, -9.6, 83.2, -7.4] },
  { id: 'supplyCurve', label: 'analysis.supply_curve', system: 'analysis', rect: [47.5, 11.85, 71.25, 14.05] },
  { id: 'leanCost', label: 'analysis.lean_cost', system: 'analysis', rect: [72.75, 11.85, 96.5, 14.05] },
]

/** Roads that the traffic drives on: { points, width }. */
export const ROADS = [
  {
    id: 'events',
    points: [
      [-24, -68],
      [-24, -55.3],
    ],
  },
  {
    id: 'stream',
    points: [
      [-24, -53.1],
      [-24, -39.2],
    ],
  },
  {
    id: 'loop',
    points: [
      [-24, -37],
      [-24, -33.6],
    ],
  },
  {
    id: 'calls',
    points: [
      [-24, -31.4],
      [-24, -25.5],
      [-39, -25.5],
      [-39, -9],
    ],
  },
  {
    id: 'lane',
    points: [
      [-39, -9],
      [39, -9],
    ],
    width: 1.6,
  },
  {
    id: 'back',
    points: [
      [39, -9],
      [39, -25.5],
      [24, -25.5],
      [24, -53.1],
    ],
  },
  {
    id: 'actions',
    points: [
      [24, -55.3],
      [24, -68],
    ],
  },
  {
    id: 'weeks',
    points: [
      [60, -55.5],
      [72, -55.5],
      [72, -22.5],
    ],
  },
  {
    id: 'fits',
    points: [
      [72, -3],
      [72, 1],
    ],
  },
  {
    id: 'constants',
    points: [
      [46, 14.3],
      [36, 14.3],
    ],
  },
  {
    id: 'seeds',
    points: [
      [98, -13],
      [104, -13],
      [104, 34],
      [30, 34],
    ],
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
      [-46, -17.5],
      [-36, -17.5],
    ],
  },
  {
    id: 'ops',
    points: [
      [-36, 14.3],
      [-46, 14.3],
    ],
    width: 1.6,
  },
]

/** Thin lines of data between blocks, under the tiles; `dotted` for what learning sends back. */
export const LINES = [
  // quote() into bestPrice(), cost() and load() into quote()
  {
    points: [
      [-0.975, -12.2],
      [-0.975, -6.875],
    ],
  },
  {
    points: [
      [-0.975, -15.4],
      [-0.975, -14.4],
    ],
  },
  {
    points: [
      [4.15, -16.5],
      [3.7, -16.5],
      [3.7, -13.3],
      [3.25, -13.3],
    ],
  },
  // belief() into bestPrice()
  {
    points: [
      [-14.3, -2.375],
      [-11, -2.375],
    ],
  },
  // Supply and outlook() into cost(), round the left edge and under the name TS:LEAN
  {
    points: [
      [-34.5, 4.975],
      [-35.25, 4.975],
      [-35.25, -13.3],
      [-5.6, -13.3],
      [-5.6, -16.5],
      [-5.2, -16.5],
    ],
  },
  {
    points: [
      [-34.5, 14.3],
      [-35.25, 14.3],
      [-35.25, 4.975],
    ],
  },
  // gig() into fees(), fees() down the fee column
  {
    points: [
      [23.15, -16.5],
      [24.05, -16.5],
    ],
  },
  {
    points: [
      [28.875, -15.4],
      [28.875, -6.875],
    ],
  },
  {
    points: [
      [24, -4.675],
      [24, -1.1],
    ],
  },
  {
    points: [
      [24, 1.1],
      [24, 4.675],
    ],
  },
  // tick() runs the Planner, which uses the chains
  {
    points: [
      [12.25, -12.2],
      [12.25, 9],
      [0, 9],
      [0, 11.1],
    ],
  },
  {
    points: [
      [11, 12.2],
      [13.5, 12.2],
    ],
  },
  {
    points: [
      [24, 13.3],
      [24, 15.3],
    ],
  },
  // the Desk writes the Journal
  {
    points: [
      [30.5, -32.5],
      [40, -32.5],
    ],
  },
  // what observe() learns goes back to Supply and Demand
  {
    id: 'learn',
    points: [
      [18.325, -12.2],
      [18.325, -10.6],
      [-12.25, -10.6],
      [-12.25, 4.975],
      [-13.5, 4.975],
    ],
    dotted: true,
  },
  {
    points: [
      [-12.25, -2.375],
      [-13.5, -2.375],
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
export const STOPS = { price: [0, -9], fee: [24, -9] }

/** The framings the zooms pass through: the whole diagram between the chapter tag and the subtitles, and bestPrice()
 * (the height of the ground in the picture, and the point in its middle). views/zoom.js fits the others. */
export const FRAMES = {
  whole: { centre: [0, -17], height: 166 },
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
