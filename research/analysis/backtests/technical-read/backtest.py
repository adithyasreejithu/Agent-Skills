"""Backtest helper for the 'Technical read on a stock chart' guide. Standard library only.

    python backtest.py fetch AMAT SMH QQQ        cache daily bars to data/<T>.csv
    python backtest.py fetch --refresh AMAT      re-download
    python backtest.py snapshot AMAT 2026-10-10  indicators using only bars up to that date

Indicators use only bars up to the as-of date (no lookahead). Outcomes are
computed separately, from bars after that date.
"""
import csv
import json
import math
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, 'data')
FIELDS = ['date', 'open', 'high', 'low', 'close', 'adjclose', 'volume']


# ---------- data ----------
def fetch(ticker, refresh=False):
    path = os.path.join(DATA, ticker.replace('^', '_') + '.csv')
    if os.path.exists(path) and not refresh:
        return path
    os.makedirs(DATA, exist_ok=True)
    url = 'https://query1.finance.yahoo.com/v8/finance/chart/%s?range=5y&interval=1d' % ticker
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    d = json.load(urllib.request.urlopen(req, timeout=30))
    r = d['chart']['result'][0]
    q = r['indicators']['quote'][0]
    adj = r['indicators'].get('adjclose', [{}])[0].get('adjclose') or q['close']
    rows = []
    for i, ts in enumerate(r['timestamp']):
        if q['close'][i] is None:
            continue
        day = datetime.fromtimestamp(ts, timezone.utc).strftime('%Y-%m-%d')
        rows.append([day, q['open'][i], q['high'][i], q['low'][i], q['close'][i], adj[i], q['volume'][i]])
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(FIELDS)
        w.writerows(rows)
    return path


def load(ticker):
    path = fetch(ticker)
    bars = []
    with open(path) as f:
        for r in csv.DictReader(f):
            bars.append({k: (r[k] if k == 'date' else float(r[k] or 0)) for k in FIELDS})
    return bars


# ---------- indicators (all causal) ----------
def sma(vals, n):
    out = [None] * len(vals)
    s = 0.0
    for i, v in enumerate(vals):
        s += v
        if i >= n:
            s -= vals[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def ema(vals, n):
    out = [None] * len(vals)
    k = 2.0 / (n + 1)
    prev = None
    for i, v in enumerate(vals):
        if v is None:
            continue
        prev = v if prev is None else v * k + prev * (1 - k)
        out[i] = prev
    return out


def bollinger(vals, n=20, k=2.0):
    mid = sma(vals, n)
    up, lo = [None] * len(vals), [None] * len(vals)
    for i in range(n - 1, len(vals)):
        w = vals[i - n + 1:i + 1]
        sd = math.sqrt(sum((x - mid[i]) ** 2 for x in w) / n)  # population SD, as TradingView
        up[i], lo[i] = mid[i] + k * sd, mid[i] - k * sd
    return mid, up, lo


def rsi(vals, n=14):
    out = [None] * len(vals)
    if len(vals) <= n:
        return out
    gains = [max(vals[i] - vals[i - 1], 0) for i in range(1, len(vals))]
    losses = [max(vals[i - 1] - vals[i], 0) for i in range(1, len(vals))]
    ag, al = sum(gains[:n]) / n, sum(losses[:n]) / n
    out[n] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(n, len(gains)):
        ag = (ag * (n - 1) + gains[i]) / n
        al = (al * (n - 1) + losses[i]) / n
        out[i + 1] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def macd(vals, fast=12, slow=26, sig=9):
    ef, es = ema(vals, fast), ema(vals, slow)
    line = [a - b if a is not None and b is not None else None for a, b in zip(ef, es)]
    sg = ema([x if x is not None else None for x in line], sig)
    hist = [a - b if a is not None and b is not None else None for a, b in zip(line, sg)]
    return line, sg, hist


def anchored_vwap_year(bars):
    """VWAP anchored to Jan 1 of each bar's year, typical price (H+L+C)/3 on daily bars."""
    out, year, pv, v = [], None, 0.0, 0.0
    for b in bars:
        y = b['date'][:4]
        if y != year:
            year, pv, v = y, 0.0, 0.0
        tp = (b['high'] + b['low'] + b['close']) / 3
        pv += tp * b['volume']
        v += b['volume']
        out.append(pv / v if v else None)
    return out


def compute(bars):
    c = [b['close'] for b in bars]
    mid, up, lo = bollinger(c)
    m, s, h = macd(c)
    return {
        'sma20': sma(c, 20), 'sma50': sma(c, 50), 'sma200': sma(c, 200),
        'bb_mid': mid, 'bb_up': up, 'bb_lo': lo,
        'rsi': rsi(c), 'macd': m, 'macd_sig': s, 'macd_hist': h,
        'vwap_year': anchored_vwap_year(bars),
    }


def asof_index(bars, date):
    """Index of the last bar dated on or before `date` (no later data used)."""
    idx = None
    for i, b in enumerate(bars):
        if b['date'] <= date:
            idx = i
        else:
            break
    return idx


def snapshot(ticker, date):
    bars = load(ticker)
    i = asof_index(bars, date)
    past = bars[:i + 1]  # truncate first: guarantees no lookahead
    ind = compute(past)
    j = len(past) - 1
    close = past[j]['close']
    hi = max(b['high'] for b in past[-252:])
    snap = {'ticker': ticker, 'date': past[j]['date'], 'close': close,
            'off_52w_high_pct': round((close / hi - 1) * 100, 1)}
    for k, v in ind.items():
        snap[k] = None if v[j] is None else round(v[j], 2)
    return snap


HORIZONS = (5, 10)


def outcomes(ticker, date, kind, levels):
    """State as of `date` (causal) plus what happened in the next 5 and 10 trading days."""
    bars = load(ticker)
    i = asof_index(bars, date)
    snap = snapshot(ticker, date)
    close = bars[i]['close']
    state = {
        'pct_b': None if snap['bb_up'] is None else round((close - snap['bb_lo']) / (snap['bb_up'] - snap['bb_lo']), 2),
        'vs_sma50_pct': round((close / snap['sma50'] - 1) * 100, 1) if snap['sma50'] else None,
        'vs_sma200_pct': round((close / snap['sma200'] - 1) * 100, 1) if snap['sma200'] else None,
        'vs_vwap_pct': round((close / snap['vwap_year'] - 1) * 100, 1) if snap['vwap_year'] else None,
    }
    res = {'asof': bars[i]['date'], 'close': round(close, 2), 'snapshot': snap, 'state': state,
           'forward_days_available': len(bars) - 1 - i, 'horizons': {}}
    past = [b['close'] for b in bars[max(0, i - 500):i + 1]]
    for h in HORIZONS:
        if i + h >= len(bars):
            res['horizons'][h] = None  # not enough follow-up yet
            continue
        fwd = bars[i + 1:i + h + 1]
        lo, hi = min(b['low'] for b in fwd), max(b['high'] for b in fwd)
        minclose = min(b['close'] for b in fwd)
        rets = [past[j + h] / past[j] - 1 for j in range(len(past) - h)]
        base = sum(rets) / len(rets) if rets else None
        out = {'ret_pct': round((fwd[-1]['close'] / close - 1) * 100, 1),
               'worst_pct': round((lo / close - 1) * 100, 1), 'best_pct': round((hi / close - 1) * 100, 1),
               'baseline_ret_pct': None if base is None else round(base * 100, 1)}
        lv = []
        for L in levels:
            if kind == 'target':
                lv.append({'level': L, 'reached': hi >= L})
            else:
                lv.append({'level': L, 'dist_pct': round((L / close - 1) * 100, 1),
                           'touched': lo <= L, 'closed_below': minclose < L * 0.99})
        if kind == 'pullback_mid':
            mid = snap['bb_mid']
            lv.append({'level': round(mid, 2), 'label': 'middle band', 'dist_pct': round((mid / close - 1) * 100, 1),
                       'touched': lo <= mid, 'closed_below': minclose < mid * 0.99})
        out['levels'] = lv
        res['horizons'][h] = out
    return res


def study(tickers, end_date):
    """Event study: how often each rule fires over the cached history up to end_date, and what
    followed, against the same ticker's unconditional forward returns. Signals less than
    min_gap days apart on one ticker count once."""
    th = json.load(open(os.path.join(HERE, 'thresholds.json')))
    R, gap = th['rules'], th['study']['min_gap_days_between_signals']
    ev = {k: {h: [] for h in HORIZONS} for k in ('lower_band', 'oversold', 'both', 'at_200d', 'stretched_up')}
    allr = {h: [] for h in HORIZONS}
    mid_hit = {'stretched_up': [], 'uncond': []}
    last = {}
    for t in tickers:
        bars = [b for b in load(t) if b['date'] <= end_date]
        ind = compute(bars)
        c = [b['close'] for b in bars]
        for i in range(200, len(bars) - max(HORIZONS)):
            hr = {h: (c[i + h] / c[i] - 1) * 100 for h in HORIZONS}
            for h in HORIZONS:
                allr[h].append(hr[h])
            up, lo, rs = ind['bb_up'][i], ind['bb_lo'][i], ind['rsi'][i]
            if None in (up, lo, rs) or up == lo:
                continue
            pb = (c[i] - lo) / (up - lo)
            run = (c[i] / c[i - R['stretched_up']['run_days']] - 1) * 100
            hit = {'lower_band': pb <= R['lower_band']['pct_b_max'],
                   'oversold': rs <= R['oversold']['rsi_max'],
                   'at_200d': ind['sma200'][i] and abs(c[i] / ind['sma200'][i] - 1) * 100 <= R['at_200d']['within_pct'],
                   'stretched_up': pb >= R['stretched_up']['pct_b_min'] and run >= R['stretched_up']['run_pct']}
            hit['both'] = hit['lower_band'] and hit['oversold']
            midtouch = min(b['low'] for b in bars[i + 1:i + 11]) <= ind['bb_mid'][i]
            if pb >= 0.85:  # like-for-like baseline: same upper-band zone, no run condition
                mid_hit['uncond'].append(midtouch)
            for k, fired in hit.items():
                if fired and i - last.get((t, k), -999) >= gap:
                    last[(t, k)] = i
                    for h in HORIZONS:
                        ev[k][h].append(hr[h])
                    if k == 'stretched_up':
                        mid_hit['stretched_up'].append(midtouch)
    out = {'end_date': end_date, 'tickers': tickers, 'rules': {}}
    for k, byh in ev.items():
        row = {}
        for h, xs in byh.items():
            base = allr[h]
            row[h] = {'n': len(xs),
                      'mean_ret_pct': round(sum(xs) / len(xs), 2) if xs else None,
                      'pct_positive': round(100 * sum(x > 0 for x in xs) / len(xs), 1) if xs else None,
                      'baseline_mean_ret_pct': round(sum(base) / len(base), 2),
                      'baseline_pct_positive': round(100 * sum(x > 0 for x in base) / len(base), 1)}
        out['rules'][k] = row
    su, un = mid_hit['stretched_up'], mid_hit['uncond']
    out['stretched_up_touches_mid_10d'] = {'n': len(su), 'pct': round(100 * sum(su) / len(su), 1) if su else None,
                                          'baseline_pct': round(100 * sum(un) / len(un), 1)}
    return out


def report_data(results, back=110, fwd=16):
    """Per case: bars and indicator series for a chart window around the as-of date."""
    cache, out = {}, []
    for r in results:
        t = r['ticker']
        if t not in cache:
            bars = load(t)
            cache[t] = (bars, compute(bars))
        bars, ind = cache[t]
        i = asof_index(bars, r['date'])
        a, b = max(0, i - back), min(len(bars), i + fwd + 1)
        rd = lambda x: None if x is None else round(x, 3)
        out.append({'id': r['id'], 'asof_index': i - a,
                    'bars': [[bars[j]['date'], rd(bars[j]['open']), rd(bars[j]['high']), rd(bars[j]['low']), rd(bars[j]['close'])] for j in range(a, b)],
                    'series': {k: [rd(ind[k][j]) for j in range(a, b)] for k in
                               ('sma50', 'sma200', 'bb_mid', 'bb_up', 'bb_lo', 'vwap_year', 'rsi', 'macd', 'macd_sig', 'macd_hist')}})
    return out


if __name__ == '__main__' and sys.argv[1:2] == ['report']:
    res = json.load(open(os.path.join(HERE, 'results-calibration.json'), encoding='utf-8'))
    charts = {c['id']: c for c in report_data(res)}
    os.makedirs(os.path.join(HERE, 'report'), exist_ok=True)
    path = os.path.join(HERE, 'report', 'cases.json')
    with open(path, 'w') as f:  # a JSON array with one case per line
        f.write('[\n' + ',\n'.join(json.dumps({**r, 'chart': charts[r['id']]}, separators=(',', ':')) for r in res) + '\n]\n')
    summ = {'cases': len(res), 'by_kind': {}}
    for h in ('5', '10'):
        sup = [r for r in res if r['kind'] == 'support' and r['horizons'][h]]
        lv = [x for r in sup for x in r['horizons'][h]['levels']]
        below = [x for x in lv if x['dist_pct'] < 0]
        bnc = [r for r in res if r['kind'] == 'bounce' and r['horizons'][h]]
        allc = [r for r in res if r['horizons'][h]]
        summ[h] = {
            'cases_with_followup': len(allc),
            'mean_ret_pct': round(sum(r['horizons'][h]['ret_pct'] for r in allc) / len(allc), 1),
            'mean_baseline_pct': round(sum(r['horizons'][h]['baseline_ret_pct'] for r in allc) / len(allc), 1),
            'up_cases': sum(r['horizons'][h]['ret_pct'] > 0 for r in allc),
            'levels_below_price': len(below), 'below_touched': sum(x['touched'] for x in below),
            'first_level_cases': len(sup), 'first_level_touched': sum(r['horizons'][h]['levels'][0]['touched'] for r in sup),
            'first_level_touched_and_held': sum(r['horizons'][h]['levels'][0]['touched'] and not r['horizons'][h]['levels'][0]['closed_below'] for r in sup),
            'bounce_cases': len(bnc), 'bounce_mean_ret_pct': round(sum(r['horizons'][h]['ret_pct'] for r in bnc) / len(bnc), 1),
            'bounce_mean_baseline_pct': round(sum(r['horizons'][h]['baseline_ret_pct'] for r in bnc) / len(bnc), 1),
            'bounce_beat_baseline': sum(r['horizons'][h]['ret_pct'] > r['horizons'][h]['baseline_ret_pct'] for r in bnc)}
    pm = [r for r in res if r['kind'] == 'pullback_mid' and r['horizons']['5']]
    summ['pullback_mid'] = {'cases': len(pm), 'touched_5d': sum(r['horizons']['5']['levels'][-1]['touched'] for r in pm)}
    tg = [r for r in res if r['kind'] == 'target' and r['horizons']['10']]
    summ['target'] = {'cases': len(tg), 'reached_10d': sum(r['horizons']['10']['levels'][0]['reached'] for r in tg)}
    summ['study'] = json.load(open(os.path.join(HERE, 'results-study-2026-10-30.json')))
    summ['crosscheck'] = json.load(open(os.path.join(HERE, 'crosscheck-calibration.json'), encoding='utf-8'))
    summ['thresholds'] = json.load(open(os.path.join(HERE, 'thresholds.json')))
    json.dump(summ, open(os.path.join(HERE, 'report', 'summary.json'), 'w'), indent=1)
    print('wrote', path, os.path.getsize(path), 'bytes')
    sys.exit(0)

if __name__ == '__main__' and sys.argv[1:2] == ['study']:
    res = study(sys.argv[3:], sys.argv[2])
    path = os.path.join(HERE, 'results-study-%s.json' % sys.argv[2])
    json.dump(res, open(path, 'w'), indent=1)
    print(json.dumps(res, indent=1))
    sys.exit(0)

if __name__ == '__main__' and sys.argv[1:2] == ['cases']:
    doc = json.load(open(os.path.join(HERE, 'cases.json'), encoding='utf-8'))
    results = []
    for c in doc['cases']:
        r = outcomes(c['ticker'], c['date'], c['kind'], c['levels'])
        r.update({k: c[k] for k in ('id', 'video', 'date', 'ticker', 'kind', 'levels', 'quote')})
        results.append(r)
    out = os.path.join(HERE, 'results-calibration.json')
    json.dump(results, open(out, 'w', encoding='utf-8'), indent=1)
    print('wrote', out, len(results))
    sys.exit(0)

if __name__ == '__main__':
    a = sys.argv[1:]
    if not a:
        print(__doc__)
    elif a[0] == 'fetch':
        refresh = '--refresh' in a
        for t in [x for x in a[1:] if not x.startswith('--')]:
            try:
                print(t, fetch(t, refresh))
            except Exception as e:  # keep going on a bad ticker
                print(t, 'FAILED', e)
            time.sleep(0.3)
    elif a[0] == 'snapshot':
        print(json.dumps(snapshot(a[1], a[2]), indent=1))
