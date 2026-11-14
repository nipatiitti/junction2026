"""Builds one data pack per recorded seed: everything the server fixes per seed, whatever the policy does.
   uv run python sim/build_data.py   ->  sim/data/L<level>/<seed>.json.gz and sim/data/map.json
   Reads the saved weeks under data/scrape/ (runs, passive, starter, probe2) and, when present, out/scrape/explore-*."""
import json, glob, gzip, os, sys, collections
from multiprocessing import Pool
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'sim', 'data')
CAP = 14  # worlds read per seed
MARKET = json.load(open(os.path.join(ROOT, 'sim', 'market.json')))['market'] if os.path.exists(os.path.join(ROOT, 'sim', 'market.json')) else {}

def opener(p):
    return gzip.open(p, 'rt') if p.endswith('.gz') else open(p)

def first(*paths):
    for p in paths:
        if os.path.exists(p): return p

def one(args):
    (level, seed), dirs = args
    pack = dict(seed=seed, level=level, requests=None, drivers=None, truths={}, cancels={}, changes={}, forecasts=None, won={})
    for d in dirs[:CAP]:
        try:
            rv = json.load(opener(first(d + '/reveal.json.gz', d + '/reveal.json')))
        except Exception:
            continue
        if not isinstance(rv, dict) or 'requests' not in rv: continue
        if pack['requests'] is None: pack['requests'] = [x['request'] for x in rv['requests']]
        for o in rv['orders']:
            pack['truths'].setdefault(o['orderId'], [{k: v for k, v in l.items() if k not in ('pickedUpAt', 'deliveredAt')} for l in o['legs']])
        dp = first(d + '/drivers.json.gz', d + '/drivers.json')
        if dp and pack['drivers'] is None:
            pack['drivers'] = [{k: x[k] for k in ('id', 'homePlaceId', 'rating', 'licence', 'completedGigs')} for x in json.load(opener(dp))]
        ep = first(d + '/events.jsonl.gz')
        if not ep: continue
        fc = []
        for line in opener(ep):
            if '"order_won"' in line:
                o = json.loads(line)['order']
                pack['won'].setdefault(o['id'], {}).setdefault(o['option'], dict(deadline=o['deadline'], lastPickupAt=o['lastPickupAt'],
                    windows=[[l['pickup']['window'], l['delivery']['window']] for l in o['legs']]))
            elif '"order_cancelled"' in line:
                e = json.loads(line); pack['cancels'].setdefault(e['orderId'], e['at'])
            elif '"order_changed"' in line:
                e = json.loads(line)
                if e.get('message'):
                    lst = pack['changes'].setdefault(e['order']['id'], [])
                    if not any(c['at'] == e['at'] for c in lst):
                        lst.append(dict(at=e['at'], message=e['message'], deadline=e['order']['deadline'],
                                        places=[[l['pickup']['placeId'], l['delivery']['placeId']] for l in e['order']['legs']]))
            elif '"forecast"' in line:
                fc.append(json.loads(line))
        if pack['forecasts'] is None: pack['forecasts'] = fc
    if not pack['requests'] or not pack['drivers']: return None
    pack['forecasts'] = pack['forecasts'] or []
    pack['market'] = MARKET.get(seed)  # the server's price level per weekday, recovered from recorded quotes (sim/market.json)
    os.makedirs(f'{OUT}/L{level}', exist_ok=True)
    with gzip.open(f'{OUT}/L{level}/{seed}.json.gz', 'wt') as f: json.dump(pack, f, separators=(',', ':'))
    return (level, seed, len(pack['requests']), len(pack['truths']), len(pack['cancels']), len(pack['changes']))

if __name__ == '__main__':
    groups = collections.defaultdict(list)
    sources = [ROOT + '/data/scrape/' + s for s in ('runs', 'passive', 'starter', 'probe2')] + sorted(glob.glob(ROOT + '/out/scrape/explore-*'))
    for m in (m for src in sources for m in glob.glob(src + '/**/meta.json', recursive=True)):
        d = json.load(open(m))
        if d.get('level') != 8 or d.get('kind') == 'board' or '/board/' in m: continue
        groups[(d['level'], d['seed'])].append(os.path.dirname(m))
    for k in groups: groups[k].sort(key=lambda p: -os.path.getsize(first(p + '/reveal.json.gz', p + '/reveal.json') or p))
    with Pool(14) as p: res = [r for r in p.imap_unordered(one, groups.items(), chunksize=2) if r]
    n = len(res); print(n, 'packs', 'truth coverage of requests: %.2f' % (sum(r[3] for r in res) / sum(r[2] for r in res)),
                        'cancels/seed %.1f changes/seed %.1f' % (sum(r[4] for r in res) / n, sum(r[5] for r in res) / n))
    import shutil; shutil.copy(first(ROOT + '/data/scrape/runs/map.json', ROOT + '/data/scrape/passive/map.json'), OUT + '/map.json')
