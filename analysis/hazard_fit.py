"""Booking hazard seen in saved weeks against the prior of src/params/fees.json, by lead band and fresh/seen.

    python3 analysis/hazard_fit.py [--write] <policy> [<fallback policy>] <week dir>...

With --write, sets `hazard.fit` in src/params/fees.json: for each lead band, fresh and seen, the bookings seen over
the bookings the fresh row expected over the same open hours (the fee models' `hazardFit` gives seen gigs the fresh
row's shape). A cell with under 20 open hours takes the fallback policy's ratio, else 1. The prior here is always
the raw table, so writing twice gives the same fit.

For each gig of the week (snapshot): open intervals from its post (and from each drop or no-show) to its booking,
expiry, withdrawal or the end. Exposure in 15-minute slices: daytime clock factor as the prior uses it (night 0.302,
weekend 0.239), lead = order.lastPickupAt - t, fee ratio = fee in the app / the gig's typical fee. Fresh = the first
60 daytime minutes after the post of a car never posted before; seen otherwise."""

import gzip
import json
import sys
from collections import defaultdict

P = json.load(open('src/params/fees.json'))
H = P['hazard']
DAY, HOUR = 1440, 60


def prior(fee, lead, seen):
    band = 0
    while band + 1 < len(H['leadHours']) and lead >= H['leadHours'][band + 1] * HOUR:
        band += 1
    row = (H['seen'] if seen else H['fresh'])[band]
    g = H['feeGrid']
    if fee <= 0:
        return 0
    if fee <= g[0]:
        return row[0] * fee / g[0]
    for i in range(1, len(g)):
        if fee <= g[i]:
            t = (fee - g[i - 1]) / (g[i] - g[i - 1])
            return row[i - 1] + t * (row[i] - row[i - 1])
    return row[-1]


def clock(t):
    m = t % DAY
    return (H['night'] if (m < 7 * HOUR or m >= 23 * HOUR) else 1) * (H['weekend'] if (t // DAY) % 7 >= 5 else 1)


def band_of(lead):
    return '<3h' if lead < 180 else '3-12h' if lead < 720 else '12-24h' if lead < 1440 else '24h+'


def fee_at(schedule, t):
    fee = schedule[0]['feeCents']
    for s in schedule:
        if s['at'] <= t:
            fee = s['feeCents']
    return fee


def fee_band(r):
    return '<0.9' if r < 0.9 else '0.9-1.2' if r < 1.2 else '1.2-1.6' if r < 1.6 else '1.6-2.2' if r < 2.2 else '2.2+'


expo = defaultdict(lambda: [0.0, 0.0, 0, 0.0])  # key -> [exposure hours (clock-weighted), prior expected, booked]


def week(d):
    ev = [json.loads(line) for line in gzip.open(f'{d}/events.jsonl.gz', 'rt')]
    snap = json.load(gzip.open(f'{d}/snapshot.json.gz', 'rt'))
    end = snap['endsAt']
    typical, last, legs_n = {}, {}, {}
    for e in ev:
        if e['kind'] == 'price_request':
            typical[e['request']['id']] = e['request']['referenceFeeCents']
        elif e['kind'] in ('order_won', 'order_changed'):
            last[e['order']['id']] = e['order']['lastPickupAt']
            legs_n[e['order']['id']] = len(e['order']['legs'])
    gig_events = defaultdict(list)
    for e in ev:
        if 'gigId' in e and e['kind'] in ('gig_booked', 'gig_dropped', 'no_show', 'gig_expired'):
            gig_events[e['gigId']].append(e)
        if e['kind'] == 'order_cancelled':
            for g in e['gigs']:
                gig_events[g['gigId']].append({'kind': 'gig_expired', 'at': e['at']})
        if e['kind'] == 'deadline_close':
            last[e['orderId']] = e['lastPickupAt']
    posted_cars = set()
    for g in sorted(snap['gigs'], key=lambda g: g['postedAt']):
        oid = g['stops'][0]['orderId']
        if oid not in typical or oid not in last:
            continue
        cars = [s for s in g['stops'] if s['kind'] == 'pickup']
        typ = sum(typical.get(s['orderId'], 0) / legs_n.get(s['orderId'], 1) for s in cars)
        keys = {(s['orderId'], s['leg']) for s in cars}
        fresh_until = None if keys & posted_cars else g['postedAt']
        posted_cars |= keys
        # Open intervals.
        opened, intervals = g['postedAt'], []
        for e in sorted(gig_events[g['id']], key=lambda e: e['at']):
            if e['kind'] == 'gig_booked' and opened is not None:
                intervals.append((opened, e['at'], True))
                opened = None
            elif e['kind'] in ('gig_dropped', 'no_show'):
                opened = e['at']
            elif e['kind'] == 'gig_expired' and opened is not None:
                intervals.append((opened, e['at'], False))
                opened = None
        if opened is not None:
            stop = end if g['status'] != 'withdrawn' else opened  # withdrawn: time unknown, count nothing
            intervals.append((opened, stop, False))
        # Fresh: first 60 daytime minutes after the post.
        fresh_start = None
        if fresh_until is not None:
            t = fresh_until
            m = t % DAY
            fresh_start = t - m + 7 * HOUR if m < 7 * HOUR else (t - m + DAY + 7 * HOUR if m >= 23 * HOUR else t)
        for a, b, booked in intervals:
            t = a
            while t < b:
                u = min(b, t + 15)
                lead = last[oid] - t
                if lead < -DAY:  # long past the last pickup: leave out
                    t = u
                    continue
                fresh = fresh_start is not None and fresh_start <= t < fresh_start + 60 and a == g['postedAt']
                r = fee_at(g['schedule'], t) / max(1, typ)
                k = (band_of(max(lead, 0)), 'fresh' if fresh else 'seen', fee_band(r))
                hrs = (u - t) / 60 * clock(t)
                expo[k][0] += hrs
                expo[k][1] += hrs * prior(r, max(lead, 0), not fresh)
                expo[k][3] += hrs * prior(r, max(lead, 0), False)
                t = u
            if booked:
                lead = last[oid] - b
                fresh = fresh_start is not None and fresh_start <= b < fresh_start + 60 and a == g['postedAt']
                r = fee_at(g['schedule'], b) / max(1, typ)
                expo[(band_of(max(lead, 0)), 'fresh' if fresh else 'seen', fee_band(r))][2] += 1


def ratios(policy, dirs):
    expo.clear()
    for d in dirs:
        if json.load(open(f'{d}/meta.json'))['policy'] == policy:
            week(d)
    tot = defaultdict(lambda: [0.0, 0.0, 0, 0.0])
    for (band, state, fb), (h, e, n, f) in expo.items():
        for key in [(band, state), (band, state, fb)]:
            t = tot[key]
            t[0] += h
            t[1] += e
            t[2] += n
            t[3] += f
    return tot


BANDS = ['<3h', '3-12h', '12-24h', '24h+']
args = [a for a in sys.argv[1:] if a != '--write']
policy = args[0]
fallback = args[1] if len(args) > 1 and '/' not in args[1] else None
dirs = args[2:] if fallback else args[1:]
tot = ratios(policy, dirs)
print(f'{policy}: booked / prior-expected over the same open hours (daytime-weighted hours)')
for key in sorted(tot, key=lambda k: (BANDS.index(k[0]), k[1], k[2] if len(k) > 2 else '')):
    h, e, n, f = tot[key]
    if h < 3:
        continue
    print(
        f"{' / '.join(key):28s} hours {h:8.1f}  booked {n:5d}  rate {n / h:6.3f}  prior {e / h:6.3f}  "
        f'ratio {n / max(e, 1e-9):5.2f}  over fresh-shaped {n / max(f, 1e-9):5.3f}'
    )
if '--write' in sys.argv:
    back = ratios(fallback, dirs) if fallback else {}

    def fit(state, band):
        for source in (tot, back):
            h, _, n, f = source.get((band, state), [0, 0, 0, 0])
            if h >= 20 and f > 0:
                return round(n / f, 3)
        return 1.0

    fees = json.load(open('src/params/fees.json'))
    fees['hazard']['fit'] = {state: [fit(state, band) for band in BANDS] for state in ('fresh', 'seen')}
    open('src/params/fees.json', 'w').write(json.dumps(fees, indent=2) + '\n')
    print('wrote hazard.fit:', fees['hazard']['fit'])
