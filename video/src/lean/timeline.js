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
    duration: 10.0,
    chapter: PROBLEM,
    lines: [
      line('lean-problem', 0.4, 3.4, 'The problem: price the car now, find a driver later.'),
      line('lean-high', 3.7, 6.0, 'Quote too high, and the competitor wins it.'),
      line('lean-low', 6.2, 8.5, 'Pay too little, and no driver comes in time.'),
      line('lean-ranked', 8.6, 10.0, 'Under ninety percent on time: not ranked.', 'Under 90% on time: not ranked.'),
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
      line(
        'lean-touches',
        0.3,
        3.9,
        "Everything that touches ts:lean: Bahn's world, our harness, ops and saved weeks.",
      ),
      line('lean-events', 4.1, 7.5, 'Every request and booking is an event, and ts:lean answers each one.'),
      line('lean-decisions', 7.8, 11.3, "Three decisions: the price, the driver's fee, and which cars share a driver."),
      line('lean-price', 11.5, 15.0, 'The price: win chance times profit, minus what one more order costs the rest.'),
    ],
  },
  {
    id: 'zoomout',
    view: 'zoom',
    direction: 'out',
    duration: 10.0,
    chapter: SOLUTION,
    lines: [
      line('lean-fees', 0.3, 3.5, 'Won cars become gigs: fees open low and rise when drivers plan.'),
      line(
        'lean-chains',
        3.6,
        7.0,
        'Chains: up to four cars, one driver, fifteen hundred sixty euros a week.',
        'Chains: up to four cars, one driver, +€1,560 a week.',
      ),
      line('lean-learn', 7.2, 10.0, 'And every booking and lost quote teaches the model.'),
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
        0.6,
        3.4,
        'Plus twenty-four thousand, four hundred fifty-one euros a week.',
        '+€24,451 a week.',
      ),
      line('lean-ontime', 3.8, 5.6, 'On time: basically always.', '[trust me bro]'),
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
