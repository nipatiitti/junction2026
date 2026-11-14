"""Summary of fee probes and week outcomes in a prober output folder, to compare the server with the simulator.
   uv run --with numpy python sim/cal_fee.py data/scrape/probe2 [seed ...]"""
import json, glob, sys, collections, numpy as np
root, seeds = sys.argv[1], set(sys.argv[2:])
rows = []; metas = []
for f in sorted(glob.glob(root + '/fee/L8/*/probes.jsonl')):
    s = f.split('/')[-2]
    if seeds and s not in seeds: continue
    rows += [dict(json.loads(l), seed=s) for l in open(f)]
    try: metas.append(json.load(open(f.replace('probes.jsonl', 'meta.json'))))
    except Exception: pass
for m in metas: print('  %s: %d orders, %.0f%% on time, margin €%.0f' % (m['seed'], m['score']['wonOrders'], 100 * m['score']['onTimeShare'], m['score']['marginCents'] / 100))
def q(v, ps=(10, 25, 50, 75, 90)): return ' '.join('%.2f' % x for x in np.percentile(v, ps)) if len(v) else '-'
def block(name, rs):
    if len(rs) < 8: return
    fl = [r['flip'] for r in rs if r['flip']]
    ab = np.mean([r['ends'] == 'above' for r in rs]); be = np.mean([r['ends'] == 'below' for r in rs])
    mins = [t['minutes'] for r in rs if r['flip'] for t in r['trials'] if t['high']][:]
    first = [min(t['minutes'] for t in r['trials'] if t['high']) for r in rs if r['flip']]
    lowm = [next(t['minutes'] for t in r['trials'] if t['high']) for r in rs if r['flip']]
    views = [t['views'] for r in rs for t in r['trials'] if not t.get('refused')]
    print('%-22s n=%4d flip p10/25/50/75/90: %s | none<=1.8x %.2f all>=0.45x %.2f | min to book at lowest fee p50 %3.0f p90 %3.0f | views p50 %2.0f p90 %3.0f' % (
        name, len(rs), q(fl), ab, be, np.median(lowm) if lowm else -1, np.percentile(lowm, 90) if lowm else -1, np.median(views), np.percentile(views, 90)))
block('all', rows)
block('same_day', [r for r in rows if r['option'] == 'same_day'])
block('next_day+', [r for r in rows if r['option'] != 'same_day'])
for a, b in ((0, 2), (2, 6), (6, 24), (24, 999)):
    block('lead %d-%dh' % (a, b), [r for r in rows if a <= (max(r['readyAt'], r['at']) - r['at']) / 60 < b])
for a, b in ((0, 60), (60, 180), (180, 9999)):
    block('drive %d-%dmin' % (a, b), [r for r in rows if a <= r['referenceFeeCents'] / 38.7 - 40 < b])
for a, b in ((0, 5), (5, 15), (15, 999)):
    block('open gigs %d-%d' % (a, b), [r for r in rows if a <= r['load']['open'] < b])
for a, b in ((9, 12), (12, 15), (15, 21)):
    block('hour %d-%d' % (a, b), [r for r in rows if a <= (r['at'] % 1440) // 60 < b])
big = collections.Counter(r['lane'][0][0] for r in rows).most_common(3)
for t, _ in big: block('from ' + t, [r for r in rows if r['lane'][0][0] == t])
block('private', [r for r in rows if any(any(p) for p in r['private'])])
