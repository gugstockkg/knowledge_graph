"""Align three EC2 backtest sets by entry and maturity month."""
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


def compare(portfolio, stocks, factors):
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
    serials = [int(row['month'][:4])*12 + int(row['month'][4:]) for row in factors]
    if any(b-a != 1 for a,b in zip(serials, serials[1:])):
        raise ValueError('Missing factor month')
    for horizon in (12, 24):
        for i in range(len(factors)-horizon+1):
            first = serials[i]-2
            start = f'{first//12:04d}{first%12+1:02d}'
            window = factors[i:i+horizon]
            key = horizon, start, window[-1]['month']
            for strategy in ('timed', 'static', 'market'):
                groups['public-factors', strategy][key] = compound(row[strategy] for row in window)
    common = sorted(set.intersection(*(set(windows) for windows in groups.values())))
    if not common:
        raise ValueError('No common entry and maturity windows')
    baselines = {'portfolio-1x':'hold','portfolio-2x':'hold','stocks':'hold','public-factors':'market'}
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
    a = p.parse_args()
    rows = compare(read(a.portfolio), read(a.stocks), read(a.factors))
    with a.out.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
