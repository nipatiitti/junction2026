"""The prior of what a won order really costs, by what is known when it is quoted: src/params/cost.json.

    python3 analysis/cost_fit.py [--write] [--policies=ts-bidprice,dispatch]

Every won, not cancelled order of the saved level 8 weeks of the policies (`ts-bidprice` by default):
- `fee`: what its cars cost in drivers, over its typical fee: the driver fees after every raise, drop, reprice and
  urgent schedule, plus waiting, release fees, failed visits and fines.
- `late`: its late refunds and undelivered penalty, over its price.
Each is a mean over a cell of the option and the hours from the win to the last pickup, times one multiplier for
each feature known at quote time: premium car, private address, trade-in, a Friday pickup, few drivers near the
delivery place. A thin cell leans on its option's mean. Several policies weigh the same, whatever their week counts.
The bidprice strategy learns the ratio of what it pays to this prior during the week (src/strategies/bidprice)."""

import gzip
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

RUNS = Path('data/scrape/runs/L8')
# Our own weeks by default: their schedules and prices are the ones whose cost `c` must carry. `dispatch.py` pays
# less (1.16 × typical, 1.5% of the price late, against 1.33 and 5.7%), so pooling it under-prices our orders.
POLICIES = next((a.split('=', 1)[1].split(',') for a in sys.argv if a.startswith('--policies=')), ['ts-bidprice'])
LEADS = [0, 6, 12, 24, 48]  # lower edges, hours from the win to the last pickup
OPTIONS = ['same_day', 'next_day', 'within_3_days']
FEATURES = ['premium', 'private', 'tradeIn', 'friday', 'fewNear']
SHRINK = 30  # orders' weight of the option mean in a cell
COSTS = {'driver_fee', 'release_fee', 'waiting', 'failed_visit', 'fine'}
LATE = {'late_refund', 'undelivered_penalty'}
DAY = 1440
MAP = json.load(open('data/scrape/runs/map.json'))


def km(a, b):
    r = math.pi / 180
    h = math.sin((b['lat'] - a['lat']) * r / 2) ** 2 + math.cos(a['lat'] * r) * math.cos(b['lat'] * r) * math.sin(
        (b['lon'] - a['lon']) * r / 2
    ) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


PLACES = {p['id']: p for p in MAP['places']}
ROADS = {(r['from'], r['to']): r['minutes'] for r in MAP['roads']}


def minutes(a, b):
    return 0 if a == b else ROADS.get((a, b), math.inf)


def drive(legs):
    """Road minutes to move the cars one after the other, as `driveMinutes` in src/ops/map.ts."""
    total, here = 0, None
    for leg in legs:
        if here is not None:
            total += minutes(here, leg['pickup']['placeId'])
        total += minutes(leg['pickup']['placeId'], leg['delivery']['placeId'])
        here = leg['delivery']['placeId']
    return total


def few_near(roster):
    homes = defaultdict(int)
    for d in roster:
        homes[d['homePlaceId']] += 1
    near = {p: sum(n for h, n in homes.items() if h in PLACES and km(PLACES[p], PLACES[h]) <= 30) for p in PLACES}
    median = sorted(near.values())[len(near) // 2]
    return {p for p, n in near.items() if n < 0.5 * median}


def deadline(request, option):
    return next((o['deadline'] for o in request['options'] if o['kind'] == option), request['options'][0]['deadline'])


def band(hours):
    return max(i for i, edge in enumerate(LEADS) if hours >= edge) if hours >= 0 else 0


def orders_of(week):
    events = [json.loads(line) for line in gzip.open(week / 'events.jsonl.gz', 'rt')]
    few = few_near(json.load(gzip.open(week / 'drivers.json.gz', 'rt')))
    requests, rows, cancelled = {}, {}, set()
    fee, late = defaultdict(int), defaultdict(int)
    for e in events:
        k = e['kind']
        if k == 'price_request':
            requests[e['request']['id']] = e['request']
        elif k == 'order_won':
            o, r = e['order'], requests.get(e['order']['id'])
            if not r:
                continue
            legs = o['legs']
            ready = max(e['at'], legs[0]['pickup']['window']['from'])
            rows[o['id']] = {
                'option': o['option'],
                # As the strategy sees it when it quotes: the option's deadline less the drive, from the request.
                'lead': band((deadline(r, o['option']) - drive(r['legs']) - r['arrivedAt']) / 60),
                'premium': any(leg['car']['premium'] for leg in legs),
                'private': any(leg['pickup']['privateAddress'] or leg['delivery']['privateAddress'] for leg in legs),
                'tradeIn': len(legs) > 1,
                'friday': (ready // DAY) % 7 == 4,
                'fewNear': legs[0]['delivery']['placeId'] in few,
                'typical': r['referenceFeeCents'],
                'price': o['priceCents'],
            }
        elif k == 'order_cancelled':
            cancelled.add(e['orderId'])
        elif k == 'ledger' and e['line']['orderId']:
            line = e['line']
            if line['kind'] in COSTS:
                fee[line['orderId']] -= line['cents']
            elif line['kind'] in LATE:
                late[line['orderId']] -= line['cents']
    out = []
    for oid, row in rows.items():
        if oid in cancelled or row['typical'] <= 0 or row['price'] <= 0:
            continue
        out.append({**row, 'fee': fee[oid] / row['typical'], 'late': late[oid] / row['price']})
    return out


def fit(rows, key):
    """Cell means by option and lead band (shrunk to the option mean), and one multiplier for each feature, by
    backfitting: a feature's multiplier is the mean of its orders over what the rest predicts."""
    w = lambda r: r['w']  # noqa: E731
    mult = {f: 1.0 for f in FEATURES}

    def rest(r, skip=None):
        m = 1.0
        for f in FEATURES:
            if f != skip and r[f]:
                m *= mult[f]
        return m

    for _ in range(5):
        by_option, by_cell = defaultdict(lambda: [0.0, 0.0]), defaultdict(lambda: [0.0, 0.0])
        for r in rows:
            y = r[key] / rest(r)
            by_option[r['option']][0] += w(r) * y
            by_option[r['option']][1] += w(r)
            by_cell[(r['option'], r['lead'])][0] += w(r) * y
            by_cell[(r['option'], r['lead'])][1] += w(r)
        total = sum(v[1] for v in by_cell.values())
        n_of = lambda wsum: wsum / total * len(rows)  # noqa: E731
        option_mean = {o: s / max(n, 1e-9) for o, (s, n) in by_option.items()}
        cell = {}
        for (o, b), (s, n) in by_cell.items():
            k = n_of(n)
            cell[(o, b)] = (s / n * k + option_mean[o] * SHRINK) / (k + SHRINK)
        for f in FEATURES:
            num = den = 0.0
            for r in rows:
                if r[f]:
                    num += w(r) * r[key]
                    den += w(r) * cell[(r['option'], r['lead'])] * rest(r, f)
            mult[f] = num / den if den > 0 else 1.0
    table = {o: [round(cell.get((o, b), option_mean.get(o, 0)), 4) for b in range(len(LEADS))] for o in OPTIONS}
    return table, {f: round(m, 3) for f, m in mult.items()}


def main():
    rows, weeks = [], defaultdict(int)
    by_policy = defaultdict(list)
    for week in sorted(RUNS.glob('*/*')):
        meta = json.load(open(week / 'meta.json'))
        if meta.get('policy') in POLICIES and (week / 'events.jsonl.gz').exists():
            by_policy[meta['policy']].extend(orders_of(week))
            weeks[meta['policy']] += 1
    for policy, policy_rows in by_policy.items():
        for r in policy_rows:
            r['w'] = 1 / len(policy_rows)  # each policy weighs the same
        rows.extend(policy_rows)
    fee, fee_mult = fit(rows, 'fee')
    late, late_mult = fit(rows, 'late')
    counts = defaultdict(int)
    for r in rows:
        counts[(r['option'], r['lead'])] += 1
    print(f'weeks: {dict(weeks)}, orders: { {p: len(r) for p, r in by_policy.items()} }')
    for policy, policy_rows in by_policy.items():
        n = len(policy_rows)
        print(
            f'{policy}: fee paid / typical {sum(r["fee"] for r in policy_rows) / n:.3f}, '
            f'late cost / price {sum(r["late"] for r in policy_rows) / n:.4f}'
        )
    print('\nfee paid / typical, and late cost / price, by option and hours from the request to its last pickup (deadline less the drive):')
    print(f'{"":15s}' + ''.join(f'{f"{edge}h+":>18s}' for edge in LEADS))
    for o in OPTIONS:
        cells = [f'{fee[o][b]:6.2f} {late[o][b]:6.3f} {counts[(o, b)]:4d}' for b in range(len(LEADS))]
        print(f'{o:15s}' + ''.join(f'{c:>18s}' for c in cells))
    print('\nmultipliers: fee', fee_mult, '\n             late', late_mult)
    if '--write' in sys.argv:
        out = {
            'leadHours': LEADS,
            'fee': fee,
            'late': late,
            'feeMultiplier': fee_mult,
            'lateMultiplier': late_mult,
            'orders': len(rows),
            'weeks': dict(weeks),
        }
        Path('src/params/cost.json').write_text(json.dumps(out, indent=2) + '\n')
        print('wrote src/params/cost.json')


main()
