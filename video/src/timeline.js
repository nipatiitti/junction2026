// The whole video in one place: the order of the views, their lengths and every text on screen.
// Change a length or a line here. The beats inside a scene, with their times, are in its file under views/.

export const FPS = 30
export const WIDTH = 1080
export const HEIGHT = 1920

/** Stays at the top of the picture through the whole video. */
export const HEADER = 'WHAT IF OUR DISPATCHER KEPT GETTING FASTER?'

/** Placeholders until the final is played. */
export const NUMBERS = {
  starterLoss: '−€72,612', // the kit starter on one level 8 week, docs/spread/HANDBOOK.md
  ourMargin: '+€24,451', // our margin a week
  team: 'OUR TEAM', // the team name at the end
}

export const SEGMENTS = [
  { id: 'card1', view: 'card', duration: 1.5, level: 1, big: 'MACH 1', small: 'a dealer needs a price' },
  {
    id: 'scene1',
    view: 'scene1',
    duration: 8.5,
    lines: {
      dealership: 'PERTIN AUTO',
      banner: 'TARJOUS!',
      typing: 'need a price…',
      typedWhenHit: 9, // letters typed when the price lands
      price: '€389',
      reply: 'Price: €389 ✓',
      speed: 'I am speed.',
      whisper: '…bomboclat.',
    },
  },
  { id: 'card2', view: 'card', duration: 1.2, level: 2, big: 'MACH 10', small: 'hour 31 of the hackathon' },
  {
    id: 'scene2',
    view: 'scene2',
    duration: 8.5,
    lines: {
      hour: 'HOUR 31',
      banner: 'HACK 2026',
      screenLabel: 'MARGIN / WEEK',
      brrr: 'BRRRRRRRRR',
      chat: 'Chat… is this real?',
      back: "we're so back.",
      viewers: '67,067 watching',
      feed: [
        ['aalto_dropout', 'W'],
        ['kebab_enjoyer', 'NO WAY'],
        ['npc_driver_67', 'is this real??'],
        ['dispatch_fan', 'HE IS COOKING'],
        ['ratio_king', 'money printer go brrr'],
        ['sleepy_teammate', 'zzz'],
        ['aalto_dropout', 'WWWWWW'],
      ],
    },
  },
  { id: 'card3', view: 'card', duration: 1.2, level: 3, big: 'MACH 67', small: '3 AM, you need a ride home' },
  {
    id: 'scene3',
    view: 'scene3',
    duration: 9,
    lines: {
      clock: '3:07 AM',
      battery: '3%',
      whereTo: 'Where to?',
      where: 'Home',
      // [name, price, wait] for each ride the phone offers, then ours
      rides: [
        ['TAXI', '€48.90', '18 min'],
        ['BLACK APP', '€44.20', '14 min'],
        ['GREEN APP', '€41.60', '12 min'],
      ],
      ours: ['US', '€6.70', '0 min'],
      bro: 'Bro…',
      sixSeven: 'SIX SEVEN!',
      cooked: 'COOKED',
      chews: 'W chews.',
      shop: 'KEBAB 24/7',
    },
  },
  { id: 'card4', view: 'card', duration: 1.2, level: 4, big: 'LIGHT SPEED', small: 'a driver said no' },
  {
    id: 'scene4',
    view: 'scene4',
    duration: 10,
    lines: {
      offer: 'NEW GIG · fee €52',
      ding: 'DING',
      // the gig card on the drivers' phones
      gig: 'NEW GIG',
      route: 'Vantaa → Tampere',
      fee: '€52',
      typical: 'typical fee €58',
      accept: 'ACCEPT',
      decline: 'DECLINE',
      accepted: 'Accepted.',
      laugh: 'HAH',
      nah: "Nah, I'd win.",
      scream: 'BOMBOCLAAAT',
      aura: '−∞ AURA',
      didNot: 'he did not win',
      panic: ['accepted', 'accepted', 'ACCEPTED'],
      diesel: 'DIESEL 1,89',
    },
  },
  {
    id: 'end',
    view: 'end',
    duration: 3.4,
    lines: {
      remember: 'Remember November 2026?',
      us: 'It was us.',
      // the page the bear holds; the circled days are the hackathon
      calendar: { title: 'NOVEMBER', year: 2026, month: 11, circled: [13, 14, 15] },
    },
  },
]
