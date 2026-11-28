"""Replay the ETF-relative rule with broad point-in-time membership and matched placebos."""
import argparse
import csv
import datetime as dt
import json
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import backtest_portfolio_exit as base

RULE = 'sp_gap'


def read(path):
    with path.open() as f:
        return list(csv.DictReader(f))


def coverage(study, records, prices, kr_lag):
    groups = defaultdict(list)
    for row in records:
        known = (base.iso(row['known']) if row['known']
                 else base.iso(row['snapshot']) + dt.timedelta(days=kr_lag))
        groups[row['market'], known, row['snapshot'], row['source']].append(row)
    market = {'US': {}, 'KR': {}}
    for (country, known, report, source), rows in sorted(groups.items()):
        issuers = defaultdict(list)
        for r in rows:
            issuers[r['issuer']].append(r)
        market[country][known] = report, source, issuers
    market = {k: base.series(v) for k, v in market.items()}
    audit, signals, strata = [], {}, defaultdict(list)
    for day, leader in study.market_leader.items():
        if not leader:
            continue
        anchor = str(base.month_shift(day, -12))[:7]
        recent = str(base.month_shift(day, -1))[:7]
        country_data = {}
        for country, ticker in [('US', base.US[0]), ('KR', base.KR[0])]:
            observations = market[country]
            if not observations[0] or day <= observations[0][0]:
                continue
            report, source, issuers = base.prior(observations, day, strict=True)
            if (day - base.iso(report)).days > 185:
                continue
            adjusted = base.series(study.data[ticker][0])
            reference = (base.prior(adjusted, base.month_end(base.month_shift(day, -1)))[2]
                         / base.prior(adjusted, base.month_end(base.month_shift(day, -12)))[2])
            available, lower, captured, total_weight = 0, 0, 0., 0.
            for securities in issuers.values():
                weight = sum(float(r['weight']) for r in securities)
                total_weight += weight
                for r in sorted(securities, key=lambda x: -float(x['weight'])):
                    p = prices.get(r['ticker'], {})
                    if anchor in p and recent in p:
                        available += 1
                        captured += weight
                        lower += p[recent] / p[anchor] < reference
                        break
            n = len(issuers)
            missing = n - available
            # Require the direction to survive even if every missing issuer votes the other way.
            vote = True if lower > n / 2 else False if lower + missing <= n / 2 else None
            usable = available >= .8 * n and captured >= .8 * total_weight
            country_data[country] = (report, source, vote, usable)
            audit.append(dict(day=day, market=country, leader=leader, report=report, source=source,
                              issuers=n, covered=available, covered_weight=captured/total_weight,
                              below=lower, possible_below=lower+missing, usable=usable, majority=vote))
        if len(country_data) == 2 and all(item[-1] for item in country_data.values()):
            report, source, vote, _ = country_data[leader]
            if vote is not None:
                signals[day] = report, source, {RULE: vote}
                strata[leader, day.year // 2].append(day)
    return audit, signals, strata


class Silent:
    def writerow(self, _):
        pass


def metrics(rows, baseline):
    d = [r['net'] - b['net'] for r, b in zip(rows, baseline)]
    return dict(n=len(rows), median_net=statistics.median(r['net'] for r in rows),
                median_mdd=statistics.median(r['max_drawdown'] for r in rows),
                targets=sum(r['target'] for r in rows), median_delta=statistics.median(d),
                wins=sum(x > 1e-10 for x in d), ties=sum(abs(x) <= 1e-10 for x in d))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pilot', type=Path, required=True)
    parser.add_argument('--constituents', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--kr-lag', type=int, default=7)
    parser.add_argument('--placebos', type=int, default=8)
    parser.add_argument('--pool-periods', action='store_true', help='Match placebo counts by market only')
    a = parser.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    data = {s: base.fetch(s, a.pilot / 'raw', base.iso('2015-02-01'), base.iso('2026-11-26'))
            for s in (*base.ASSETS, base.FX)}
    study = base.Study(data)
    audit, signals, strata = coverage(study, read(a.constituents / 'constituents.csv'),
                                      json.loads((a.constituents / 'monthly.json').read_text()), a.kr_lag)
    base.dump_csv(a.out / 'coverage.csv', audit)
    if a.pool_periods:
        pooled = defaultdict(list)
        for (market, _), dates in strata.items():
            pooled[market].extend(dates)
        strata = pooled
    n_active = sum(r[2][RULE] for r in signals.values())
    base.dump_csv(a.out / 'signals.csv', [
        dict(day=d, market=study.market_leader[d], report=v[0], source=v[1], reduced=v[2][RULE])
        for d, v in signals.items()])
    print('eligible', len(signals), 'active', n_active,
          'by market', dict(Counter(study.market_leader[d] for d in signals)), flush=True)
    if not n_active:
        return
    anchors = [r for r in read(a.baseline) if r['portfolio'] == 'etf' and r['strategy'] in ('hold', 'relative')]
    hold, relative = {}, {}
    for r in anchors:
        group = hold if r['strategy'] == 'hold' else relative
        group[r['start'], r['months']] = {
            **r, **{k: float(r[k]) for k in ('net', 'max_drawdown')}, 'target': int(r['target'])}

    def replay(chosen, writer):
        study.spy_signals = {d: (r[0], r[1], {RULE: d in chosen}) for d, r in signals.items()}
        output = {}
        for key, row in relative.items():
            start, end = base.iso(row['start']), base.iso(row['end'])
            output[key] = (study.run(start, end, 'etf', RULE, writer)
                           if any(start <= d < end for d in chosen) else row)
        return output

    actual = {d for d, r in signals.items() if r[2][RULE]}
    with (a.out / 'orders.csv').open('w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(('portfolio', 'strategy', 'start', 'end', 'decision_date', 'trade_date',
                         'symbol', 'side', 'reason', 'shares_signed', 'local_price', 'fx_krw',
                         'cost_krw', 'cash_krw', 'holdings_asof', 'holdings_source'))
        graph = replay(actual, writer)
    placebo = {}
    assignments = []
    for i in range(a.placebos):
        rng = random.Random(2212026 + i)
        dates = {d for items in strata.values() for d in rng.sample(items, len(actual.intersection(items)))}
        assert len(dates) == len(actual)
        assignments.extend(dict(seed=i, day=d, market=study.market_leader[d]) for d in sorted(dates))
        placebo[i] = replay(dates, Silent())
    base.dump_csv(a.out / 'placebo_dates.csv', assignments)
    periods = {'all': ('2016', '2027'), 'recent': ('2021-11-26', '2027'),
               '2016~17': ('2016', '2018'), '2018~19': ('2018', '2020'), '2020~21': ('2020', '2022'),
               '2022~23': ('2022', '2024'), '2024+': ('2024', '2027')}
    stats = []
    for h in ('12', '24'):
        for period, (lo, hi) in periods.items():
            keys = [k for k in relative if k[1] == h and lo <= k[0] < hi]
            for scope, selected in [('all', keys), ('affected', [
                    k for k in keys if any(base.iso(k[0]) <= d < base.iso(relative[k]['end']) for d in actual)])]:
                if not selected:
                    continue
                bs = [relative[k] for k in selected]
                for name, sample in [('hold', hold), ('relative', relative), ('graph', graph), *[
                        (f'placebo_{i}', r) for i, r in placebo.items()]]:
                    stats.append(dict(months=h, period=period, scope=scope, strategy=name,
                                      **metrics([sample[k] for k in selected], bs)))
    base.dump_csv(a.out / 'metrics.csv', stats)
    base.dump_csv(a.out / 'cohorts.csv', list(graph.values()))


if __name__ == '__main__':
    main()
