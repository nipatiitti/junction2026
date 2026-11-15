// The ts:lean video in one place: the order of its views, their lengths, their chapters, every spoken line with its
// subtitle and time, and the numbers. The brief is prompt.md at the root of the repository. The block
// diagram is in diagram.js. Plain data, so that voices.ts can read the lines in Node.

export const NUMBERS = {
  algo: 'ts:lean',
  team: 'BLIB BLIB',
  ourMargin: '+€24,451', // our margin a week
  baseline: '−€72,456', // the first strategy's week
  onTime: '99.9999999%', // the one joke number
  strategies: 63,
}

/**
 * A spoken line: `voice` names its file in audio/voice/, `at` and `until` are the local times of its caption, `say`
 * is what the voice says (voices.ts reads `ts:lean` as the letters) and `caption` what the screen shows, when they
 * differ (a lying caption is one of those). `rate` speeds the voice up to fit.
 */
const line = (voice, at, until, say, caption = say, rate = 1) => ({ voice, at, until, say, caption, rate })

/** The picture: 16:10, for YouTube. */
export const WIDTH = 1920
export const HEIGHT = 1200

const PROBLEM = { n: '01', title: 'The problem' }
const SOLUTION = { n: '02', title: 'The solution: ts:lean' }
const RESULT = { n: '03', title: 'The result' }

// `chapter` puts the chapter tag on a segment; `bare` leaves the picture without the tag and the mark (the jokes and
// the title card).
export const SEGMENTS = [
  {
    id: 'spaghetti',
    view: 'spaghetti',
    duration: 9.0,
    bare: true,
    lines: [
      line('lean-careful', 0.3, 2.75, 'We tested every strategy carefully.', '[we threw spaghetti at a wall]'),
      line(
        'lean-spaghetti',
        2.9,
        6.7,
        'Spaghetti method: throw all sixty-three at the wall, see what sticks.',
        'Spaghetti method: throw all 63 at the wall, see what sticks.',
        1.08,
      ),
      line('lean-stuck', 6.9, 8.9, 'Only one stuck.'),
    ],
    // tags of strands that slide off (all shelved, see SHELVED.md), and the one that sticks
    tags: ['profit-max', 'max-margin', 'ratchet', 'war-guard'],
    winner: 'ts:lean',
  },
  {
    id: 'title',
    view: 'title',
    duration: 3.0,
    bare: true,
    lines: [],
    texts: {
      title: 'ts:lean',
      line: "How we price a car delivery for Bahn's Spread challenge",
      team: 'Blib Blib · Junction 2026',
    },
  },
  {
    id: 'problem',
    view: 'problem',
    duration: 11.0,
    chapter: PROBLEM,
    lines: [
      line('lean-problem', 0.3, 3.6, 'The problem: price the car now, find a driver later.', undefined, 1.1),
      line('lean-high', 3.7, 6.2, 'Quote too high, and the competitor wins it.', undefined, 1.05),
      line('lean-low', 6.3, 8.6, 'Pay too little, and no driver comes.', undefined, 1.08),
      line('lean-ranked', 8.65, 11.0, 'Under ninety percent: not ranked.', 'Under 90% on time: not ranked.', 1.12),
    ],
    texts: {
      dealer: 'Dealer',
      lean: 'ts:lean',
      drivers: 'Drivers',
      request: 'price_request · list €389',
      high: '1.9 × list',
      competitor: 'Competitor',
      low: 'fee 0.6 × typical',
      late: 'LATE',
      stamp: 'NOT RANKED',
      stampSmall: 'under 90% on time',
    },
  },
  {
    id: 'didnot',
    view: 'didnot',
    duration: 4.5,
    bare: true,
    lines: [
      line('lean-work', 0.3, 1.9, 'This will definitely work.', undefined, 1.1),
      line('lean-didnot', 2.1, 3.4, 'It did not.'),
    ],
    texts: { hour: 'HOUR 2', screen: 'STRATEGY #1:\nquote the list price' },
  },
  {
    // the "I am speed" meme as a way in: a second of dark, three seconds in a car on ts:lean's lanes, a fast zoom out
    id: 'speed',
    view: 'speed',
    duration: 5.5,
    bare: true,
    lines: [line('lean-speed', 0.2, 3.6, 'Focus. Speed. I am speed.')],
  },
  {
    id: 'zoomin',
    view: 'zoom',
    direction: 'in',
    duration: 15.0,
    chapter: SOLUTION,
    lines: [
      line('lean-touches', 0.3, 2.8, 'This is everything around ts:lean.'),
      line('lean-events', 3.0, 6.9, 'Every event comes in here, and ts:lean answers it.'),
      line('lean-decisions', 7.1, 10.8, 'Three decisions: the price, the fee, and the chains.', undefined, 1.12),
      line('lean-price', 11.1, 14.9, 'The price: win chance times profit, minus a load charge.', undefined, 1.12),
    ],
  },
  {
    id: 'fees',
    view: 'zoom',
    direction: 'fees',
    duration: 14.0,
    chapter: SOLUTION,
    lines: [
      line('lean-fees', 1.0, 5.6, 'Fees open low and rise three times, when drivers plan their day.'),
      line('lean-weekend', 7.8, 12.4, "And no raises on weekends: Monday's cars wait for Monday."),
    ],
  },
  {
    id: 'chains',
    view: 'zoom',
    direction: 'chains',
    duration: 14.0,
    chapter: SOLUTION,
    lines: [
      line('lean-chains', 0.8, 5.6, 'Chains: one driver takes up to four cars, one after another.', undefined, 1.05),
      line('lean-chancefee', 7.4, 10.8, "Each chain's fee follows its chance to book."),
    ],
  },
  {
    id: 'learning',
    view: 'zoom',
    direction: 'learning',
    duration: 11.0,
    chapter: SOLUTION,
    lines: [
      line('lean-learn', 0.6, 4.2, 'Every won or lost quote moves the win curve.'),
      line('lean-supply', 5.6, 8.8, 'Every booking teaches what drivers cost.'),
    ],
  },
  {
    id: 'zoomout',
    view: 'zoom',
    direction: 'out',
    duration: 10.0,
    chapter: SOLUTION,
    lines: [
      line('lean-cars', 0.5, 4.6, 'Grey cars are price requests; red ones are won orders.'),
      line('lean-requests', 5.4, 9.0, 'A thousand requests a week, all through these lanes.'),
    ],
  },
  { id: 'traffic', view: 'zoom', direction: 'traffic', duration: 6.0, chapter: SOLUTION, lines: [] },
  {
    id: 'result',
    view: 'result',
    duration: 7.0,
    chapter: RESULT,
    lines: [
      line(
        'lean-margin',
        0.5,
        4.2,
        'Plus twenty-four thousand, four hundred fifty-one euros a week.',
        '+€24,451 a week.',
        1.05,
      ),
      line('lean-ontime', 4.3, 6.8, 'On time: basically always.', '[trust me bro]'),
    ],
    texts: {
      margin: NUMBERS.ourMargin,
      marginLabel: 'margin a week',
      onTime: NUMBERS.onTime,
      onTimeLabel: 'on time (90% to be ranked)',
      strategies: `${NUMBERS.strategies} → 1`,
      strategiesLabel: 'strategies tried → shipped',
      fine: 'All euros are game euros.',
    },
  },
  {
    id: 'ending',
    view: 'ending',
    duration: 9.0,
    bare: true,
    lines: [line('lean-shipit', 1.5, 2.8, 'Ship it!'), line('lean-thatsit', 5.6, 7.8, "That's ts:lean.")],
    texts: { title: NUMBERS.algo, team: `by ${NUMBERS.team} · Junction 2026`, winner: 'ts:lean' },
  },
]

// The beat under each view (see audio/score.js): quiet under the explanation, full in the spaghetti, once the car
// races and once the traffic is out, none in the narrator's beat; the ending gets the party beat.
export const STYLES = {
  spaghetti: { kick: [0, 10], clap: [8], bass: 'trap', level: 0.8 },
  problem: { kick: [0, 10], clap: [8], bass: 'trap', level: 0.4 },
  didnot: { kick: [0, 10], clap: [8], bass: 'trap', level: 0.4, rest: [[1.95, 3.4]] },
  speed: { kick: [0, 3, 8, 10], clap: [4, 12], bass: 'phonk', cowbell: true, level: (t) => (t < 1.0 ? 0 : 0.9) },
  zoomin: { kick: [0, 8], clap: [8], bass: 'trap', level: 0.35 },
  fees: { kick: [0, 8], clap: [8], bass: 'trap', level: 0.35 },
  chains: { kick: [0, 8], clap: [8], bass: 'trap', level: 0.35 },
  learning: { kick: [0, 8], clap: [8], bass: 'trap', level: 0.35 },
  zoomout: { kick: [0, 4, 8, 12], clap: [4, 12], bass: 'party', level: (t) => (t < 6 ? 0.45 : 0.9) },
  traffic: { kick: [0, 4, 8, 12], clap: [4, 12], bass: 'party', level: 0.9 },
  result: { kick: [0, 4, 8, 12], clap: [4, 12], bass: 'party', level: 0.8 },
  ending: { kick: [0, 4, 8, 12], clap: [4, 12], bass: 'party', level: 1 },
}
