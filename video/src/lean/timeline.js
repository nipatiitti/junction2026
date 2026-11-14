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
    duration: 5.0,
    bare: true,
    lines: [
      line('lean-careful', 0.3, 2.7, 'We tested every strategy carefully.', '[we threw 63 at a wall]'),
      line('lean-stuck', 3.2, 4.9, 'Only one stuck.'),
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
      line('lean-ranked', 8.7, 11.0, 'Under ninety percent: not ranked.', 'Under 90% on time: not ranked.', 1.1),
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
    duration: 4.0,
    bare: true,
    lines: [line('lean-work', 0.3, 1.7, 'This will definitely work.'), line('lean-didnot', 2.1, 3.2, 'It did not.')],
    texts: { hour: 'HOUR 2', screen: 'STRATEGY #1:\nquote the list price' },
  },
  {
    id: 'zoomin',
    view: 'zoom',
    direction: 'in',
    duration: 15.0,
    chapter: SOLUTION,
    lines: [
      line('lean-touches', 0.3, 3.3, 'This is everything around ts:lean.'),
      line('lean-events', 3.6, 7.5, 'Every event comes in here, and ts:lean answers it.'),
      line('lean-decisions', 7.7, 11.2, 'Three decisions: the price, the fee, and the chains.', undefined, 1.12),
      line('lean-price', 11.3, 15.0, 'The price: win chance times profit, minus a load charge.', undefined, 1.12),
    ],
  },
  {
    id: 'zoomout',
    view: 'zoom',
    direction: 'out',
    duration: 10.0,
    chapter: SOLUTION,
    lines: [
      line('lean-fees', 0.3, 4.3, 'Won cars become gigs; fees start low and rise.'),
      line('lean-chains', 4.4, 7.8, 'Chains: one driver takes up to four cars.'),
      line('lean-learn', 7.9, 10.0, 'Every outcome teaches the model.'),
    ],
  },
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
    id: 'handshake',
    view: 'handshake',
    duration: 4.5,
    bare: true,
    lines: [],
    texts: { title: NUMBERS.algo, team: `by ${NUMBERS.team} · Junction 2026` },
  },
]

// The beat under each view (see audio/score.js): quiet under the explanation, full in the spaghetti and once the
// traffic is out, none on the black frame; the handshake has its elevator music in its own sounds.
export const STYLES = {
  spaghetti: { kick: [0, 10], clap: [8], bass: 'trap', level: 0.8 },
  problem: { kick: [0, 10], clap: [8], bass: 'trap', level: 0.4 },
  didnot: { kick: [0, 10], clap: [8], bass: 'trap', level: 0.4, rest: [[1.8, 4.0]] },
  zoomin: { kick: [0, 8], clap: [8], bass: 'trap', level: 0.35 },
  zoomout: { kick: [0, 4, 8, 12], clap: [4, 12], bass: 'party', level: (t) => (t < 7 ? 0.4 : 0.9) },
  result: { kick: [0, 4, 8, 12], clap: [4, 12], bass: 'party', level: 0.8 },
}
