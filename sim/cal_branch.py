"""Server vs simulator: how the week's result moves when the policy changes (prober --mode branch).
   uv run python sim/cal_branch.py <real dir> <sim dir> seed [seed ...]"""
import json, sys, collections
def load(root, seed):
    return json.load(open(f'{root}/branch/L8/{seed}/meta.json'))['score'], [json.loads(l) for l in open(f'{root}/branch/L8/{seed}/probes.jsonl')]
def name(v):
    if 'qScale' in v: return 'quotes x%.1f' % v['qScale']
    if 'fOpen' in v: return 'opening fee %+.2f' % (v['fOpen'] - 0.9)
    return 'town'
agg = collections.defaultdict(lambda: [[], []])
for seed in sys.argv[3:]:
    (rm, rr), (sm, sr) = load(sys.argv[1], seed), load(sys.argv[2], seed)
    print(f"{seed} base: SERVER {rm['wonOrders']} orders {100*rm['onTimeShare']:.0f}% €{rm['marginCents']/100:.0f} | SIM {sm['wonOrders']} orders {100*sm['onTimeShare']:.0f}% €{sm['marginCents']/100:.0f}")
    for i, (rows, b) in enumerate(((rr, rm), (sr, sm))):
        for r in rows:
            s = r['score']; agg[name(r['variant'])][i].append((s['wonOrders'] - b['wonOrders'], (s['marginCents'] - b['marginCents']) / 100, 100 * (s['onTimeShare'] - b['onTimeShare'])))
print('%-20s %-44s %s' % ('mean effect', 'SERVER (orders, margin, on-time points)', 'SIMULATOR'))
for k in sorted(agg):
    f = lambda v: '%+5.0f orders %+7.0f€ %+5.1fpp (n=%d)' % (*[sum(x[j] for x in v) / len(v) for j in range(3)], len(v)) if v else '-'
    print('%-20s %-44s %s' % (k, f(agg[k][0]), f(agg[k][1])))
