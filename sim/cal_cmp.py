"""Server vs simulator on the same seeds and the same prober settings.
   uv run --with numpy python sim/cal_cmp.py <real dir> <sim dir> seed [seed ...]"""
import json, glob, sys, collections, numpy as np
real, sim, seeds = sys.argv[1], sys.argv[2], sys.argv[3:]
def load(root):
    rows = []; ms = []
    for s in seeds:
        f = f'{root}/fee/L8/{s}/probes.jsonl'
        try: rows += [dict(json.loads(l), seed=s) for l in open(f)]; ms.append(json.load(open(f.replace('probes.jsonl', 'meta.json'))))
        except Exception as e: print('missing', f)
    return rows, ms
b = lambda x, cuts: sum(x >= c for c in cuts)
CUTS = [
    ('all', lambda r: ''),
    ('pickup', lambda r: ['today', '+1 day', '+2 or more'][min(2, max(r['readyAt'], r['at']) // 1440 - r['at'] // 1440)]),
    ('won on', lambda r: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'][min(4, r['at'] // 1440)]),
    ('booked gigs', lambda r: ['<50', '50-150', '150-300', '300+'][b(r['load']['booked'], [50, 150, 300])]),
    ('typical fee', lambda r: ['<€40', '€40-90', '€90+'][b(r['referenceFeeCents'], [4000, 9000])]),
    ('hour', lambda r: ['<12', '12-15', '15+'][b((r['at'] % 1440) / 60, [12, 15])]),
    ('private', lambda r: 'yes' if any(any(p) for p in r['private']) else 'no'),
]
def stat(v):
    if len(v) < 10: return '%4d  -' % len(v)
    fl = [r['flip'] for r in v if r['flip']]
    low = [next(t['minutes'] for t in r['trials'] if t['high']) for r in v if r['flip']]
    vw = [t['views'] for r in v for t in r['trials'] if not t.get('refused') and t['x'] <= 1.8]
    return '%4d none %.2f | flip %s | wait %3.0f | views %2.0f' % (len(v), np.mean([r['ends'] == 'above' for r in v]), ' '.join('%.2f' % x for x in np.percentile(fl, [10, 50, 90])), np.median(low), np.median(vw))
R, RM = load(real); S, SM = load(sim)
for name, ms in (('server', RM), ('sim', SM)):
    print('%-7s' % name, ' | '.join('%s %d orders %.0f%% €%.0f' % (m['seed'], m['score']['wonOrders'], 100 * m['score']['onTimeShare'], m['score']['marginCents'] / 100) for m in ms))
print('%-22s %-62s %s' % ('', 'SERVER  (n, none<=1.8x, flip p10 p50 p90, min to book, views)', 'SIMULATOR'))
for name, key in CUTS:
    for k in sorted(set(key(r) for r in R)):
        print('%-22s %-62s %s' % (f'{name} {k}', stat([r for r in R if key(r) == k]), stat([r for r in S if key(r) == k])))
