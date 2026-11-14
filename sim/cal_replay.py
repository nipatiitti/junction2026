"""Server vs simulator on recorded weeks replayed with sim/replay.ts: what happened to each first posting.
   uv run --with numpy python sim/cal_replay.py replay.jsonl"""
import json, sys, collections, numpy as np
W = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
G = [dict(g, policy=w['policy']) for w in W for g in w['gigs'] if 'refused' not in g]
print(len(W), 'weeks,', len(G), 'first postings,', sum('refused' in g for w in W for g in w['gigs']), 'refused in the simulator')
def wk(side, f): return np.array([f(w[side]) for w in W], float)
for name, f in (('orders', lambda s: s['counts']['order_won']), ('bookings', lambda s: s['counts']['gig_booked']), ('drops', lambda s: s['counts']['gig_dropped']), ('expired', lambda s: s['counts']['gig_expired']),
                ('views', lambda s: s['counts']['gig_viewed']), ('deadline warnings', lambda s: s['counts']['deadline_close']), ('on time %', lambda s: 100 * s['score']['onTimeShare']), ('margin €', lambda s: s['score']['marginCents'] / 100)):
    r, s = wk('real', f), wk('sim', f)
    print('  per week %-18s server %8.1f   simulator %8.1f   correlation %.2f' % (name, r.mean(), s.mean(), np.corrcoef(r, s)[0, 1] if r.std() > 0 and s.std() > 0 else float('nan')))
b = lambda x, cuts: sum(x >= c for c in cuts)
def stat(v, side):
    bk = [g[side].get('booked') for g in v]
    t = np.array([x['at'] - g['at'] for x, g in zip(bk, v) if x], float); fee = np.array([x['fee'] / g['ref'] for x, g in zip(bk, v) if x and g['ref']])
    n = len(v)
    return 'booked %.2f | <=30m %.2f <=3h %.2f | wait p50 %4.0f | fee/typical p50 %.2f | dropped %.2f' % (len(t) / n, (t <= 30).sum() / n, (t <= 180).sum() / n, np.median(t) if len(t) else -1, np.median(fee) if len(fee) else -1, np.mean([bool(g[side].get('dropped')) for g in v]))
CUTS = [('all', lambda g: ''), ('pickup', lambda g: ['today', '+1 day', '+2 or more'][min(2, max(g['from'], g['at']) // 1440 - g['at'] // 1440)]),
        ('opening fee', lambda g: ['<0.7x', '0.7-0.85x', '0.85-1x', '1-1.3x', '1.3x+'][b(g['open0'] / max(g['ref'], 1), [0.7, 0.85, 1, 1.3])]),
        ('posted on', lambda g: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'later'][min(5, g['at'] // 1440)]), ('booked gigs', lambda g: ['<50', '50-150', '150+'][b(g['load']['booked'], [50, 150])]),
        ('cars', lambda g: '1' if g['cars'] == 1 else '2+'), ('private', lambda g: 'yes' if g['private'] else 'no'), ('hour', lambda g: ['<12', '12-15', '15+'][b(g['at'] % 1440 / 60, [12, 15])])]
print('%-24s %6s  %-88s %s' % ('', 'n', 'SERVER', 'SIMULATOR'))
for name, key in CUTS:
    for k in sorted(set(key(g) for g in G)):
        v = [g for g in G if key(g) == k]
        if len(v) >= 50: print('%-24s %6d  %-88s %s' % (f'{name} {k}', len(v), stat(v, 'real'), stat(v, 'sim')))
