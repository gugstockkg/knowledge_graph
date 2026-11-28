"""Align EC2 backtest sets by entry and maturity month."""
import argparse
import csv
from collections import defaultdict
from pathlib import Path
from statistics import median


def month(text):
    return text.replace('-', '')[:6]


def read(path):
    with path.open(newline='', encoding='utf-8-sig') as stream:
        return list(csv.DictReader(stream))


def compound(returns):
    nav = peak = 1.
    mdd = 0.
    for value in returns:
        nav *= 1 + float(value)
        peak = max(peak, nav)
        mdd = min(mdd, nav / peak - 1)
    return nav - 1, mdd


def cohort_key(row):
    return int(row['months']), month(row['start']), month(row['end'])


def factor_windows(groups, track, strategies):
    dates = sorted(set.intersection(*(set(r) for r in strategies.values())))
    serials = [int(d[:4])*12 + int(d[4:]) for d in dates]
    if any(b-a != 1 for a,b in zip(serials, serials[1:])):
        raise ValueError('Missing factor month')
    for horizon in (12, 24):
        for i in range(len(dates)-horizon+1):
            first = serials[i]-2
            start = f'{first//12:04d}{first%12+1:02d}'
            window = dates[i:i+horizon]
            key = horizon, start, window[-1]
            for strategy, returns in strategies.items():
                groups[track, strategy][key] = compound(returns[d] for d in window)


def merge_portfolio(groups, records):
    for row in records:
        track = 'portfolio-' + row['cost_case']
        key = cohort_key(row)
        values = groups[track, row['strategy']]
        result = float(row['net']), float(row['max_drawdown'])
        if key in values and any(abs(x-y)>1e-10 for x,y in zip(values[key],result)):
            raise ValueError(f'Existing portfolio result differs: {track} {key} {row["strategy"]}')
        values[key] = result


def compare(portfolio, stocks, factors, extensions=(), korean=(), shrinkage=()):
    groups = defaultdict(dict)
    for row in portfolio:
        if row['portfolio'] != 'mixed':
            continue
        key = int(row['months']), month(row['start']), month(row['end'])
        groups['portfolio-' + row['cost_case'], row['strategy']][key] = (
            float(row['net']), float(row['max_drawdown']))
    for row in stocks:
        key = int(row['months']), month(row['start']), month(row['end'])
        groups['stocks', row['strategy']][key] = (float(row['net']), float(row['monthly_drawdown']))
    factor_windows(groups, 'public-factors', {
        strategy: {r['month']:r[strategy] for r in factors}
        for strategy in ('timed', 'static', 'market')
    })
    for extension in extensions:
        merge_portfolio(groups, extension)
    for row in korean:
        if float(row['terminal_recovery']) == .5:
            groups['korea', row['strategy']][cohort_key(row)] = float(row['net']), float(row['mdd'])
    if shrinkage:
        models = defaultdict(dict)
        for row in shrinkage:
            models[float(row['cost']), row['model']][row['month']] = row['ret']
        for cost in (0., .001):
            track = 'public-factors' if not cost else 'public-factors-10bp'
            curves = {label: models[cost, model]
                      for model,label in [('market','market'),('static','static'),('sign','timed'),('ridge','ridge')]}
            new = defaultdict(dict)
            factor_windows(new, track, curves)
            for (group,strategy), observations in new.items():
                existing = groups[group,strategy]
                if any(key in existing and any(abs(x-y)>1e-10 for x,y in zip(existing[key],value))
                       for key,value in observations.items()):
                    raise ValueError(f'Existing factor result differs: {group} {strategy}')
                existing.update(observations)
    common = sorted(set.intersection(*(set(windows) for windows in groups.values())))
    if not common:
        raise ValueError('No common entry and maturity windows')
    baselines = {'portfolio-1x':'hold','portfolio-2x':'hold','stocks':'hold','public-factors':'market','public-factors-10bp':'market','korea':'hold'}
    rows = []
    for (track, strategy), values in sorted(groups.items()):
        comparator = groups[track, baselines[track]]
        for horizon in (12, 24):
            windows = [key for key in common if key[0] == horizon]
            net, dd = zip(*(values[key] for key in windows))
            delta = [values[key][0]-comparator[key][0] for key in windows]
            split = len(windows)//2
            rows.append(dict(track=track, strategy=strategy, months=horizon,
                first_entry=windows[0][1], last_entry=windows[-1][1], last_maturity=windows[-1][2],
                windows=len(windows), median_net=median(net), median_drawdown=median(dd),
                paired=median(delta), wins=sum(d>1e-8 for d in delta),
                early_paired=median(delta[:split]), late_paired=median(delta[split:]),
                targets=sum(r >= .15 for r in net)))
    return rows


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ('portfolio', 'stocks', 'factors', 'out'):
        p.add_argument('--'+arg, type=Path, required=True)
    p.add_argument('--portfolio-extension', type=Path, action='append', default=[])
    p.add_argument('--korean', type=Path)
    p.add_argument('--shrinkage', type=Path)
    a = p.parse_args()
    rows = compare(read(a.portfolio), read(a.stocks), read(a.factors),
                   [read(file) for file in a.portfolio_extension],
                   read(a.korean) if a.korean else (), read(a.shrinkage) if a.shrinkage else ())
    with a.out.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
