"""Reproduce the fixed-universe KRW portfolio pilot from archived Yahoo chart data."""
import argparse
import bisect
import calendar
import csv
import datetime as dt
import hashlib
import json
import random
import statistics
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

US = ('SPY', 'AAPL', 'MSFT', 'NVDA')
KR = ('069500.KS', '005930.KS', '000660.KS', '005380.KS')
FX = 'KRW=X'
ASSETS = US + KR
STRATEGIES = ('hold', 'rebalance', 'trend', 'exit', 'partial')
COST = 0.001
FX_COST = 0.001
TARGET = .15
CUSIP = {'AAPL': '037833100', 'MSFT': '594918104', 'NVDA': '67066G104'}
CAP = .06
GRAPH_STRATEGIES = ('g1_direct', 'g1_lookthrough', 'g1_matched_cash')


def spy_holdings(root):
    root.mkdir(exist_ok=True, parents=True)
    agent = {'User-Agent': 'Research portfolio backtest ops@fintos.ai'}

    def get(url, target):
        if not target.exists():
            with urlopen(Request(url, headers=agent), timeout=20) as response:
                target.write_bytes(response.read())
            time.sleep(.25)
        return target.read_bytes()

    filings = json.loads(get('https://data.sec.gov/submissions/CIK0000884394.json',
                             root / 'submissions.json'))['filings']['recent']
    edges, snapshots = [], {}
    for form, accession, filed, report, document in zip(
            *(filings[key] for key in ('form', 'accessionNumber', 'filingDate', 'reportDate', 'primaryDocument'))):
        if form != 'NPORT-P' or not '2019-01-01' <= report < '2026-11-27' or filed >= '2026-11-27':
            continue
        url = f'https://www.sec.gov/Archives/edgar/data/884394/{accession.replace("-", "")}/{document.split("/")[-1]}'
        try:
            xml = ET.fromstring(get(url, root / f'{accession}.xml'))
        except (OSError, ET.ParseError) as exc:
            print('SEC skip', accession, exc, flush=True)
            continue
        weights = defaultdict(float)
        mapped = {}
        for row in xml.findall('.//{*}invstOrSec'):
            security = row.findtext('{*}cusip')
            weight = row.findtext('{*}pctVal')
            if security is None or not weight:
                continue
            w = float(weight) / 100
            weights[security] += w
            edges.append(dict(fund='SPY', security=security, weight=w, report=report, known=filed,
                              accession=accession, source=url))
        for symbol, security in CUSIP.items():
            if security in weights:
                mapped[symbol] = weights[security]
        if len(mapped) == len(CUSIP) and .9 < sum(weights.values()) < 1.1:
            snapshots[iso(filed)] = (report, accession, mapped)
    dump_csv(root / 'holdings_edges.csv', edges)
    dump_csv(root / 'issuer_edges.csv', [dict(security=c, issuer=s) for s, c in CUSIP.items()])
    print('SEC usable snapshots', len(snapshots), 'fund-security observations', len(edges), flush=True)
    return series(snapshots)



def month_shift(day, months):
    year, month = divmod(day.year * 12 + day.month - 1 + months, 12)
    return dt.date(year, month + 1, min(day.day, calendar.monthrange(year, month + 1)[1]))


def month_end(day):
    return day.replace(day=calendar.monthrange(day.year, day.month)[1])


def iso(value):
    return dt.date.fromisoformat(value)


def date_label(timestamp, zone):
    return dt.datetime.fromtimestamp(timestamp, ZoneInfo(zone)).date()


def fetch(symbol, root, start, end):
    path = root / f'{symbol}.json'
    a, b = (calendar.timegm(d.timetuple()) for d in (start, end + dt.timedelta(days=2)))
    query = f'period1={a}&period2={b}&interval=1d&events=div%2Csplits'
    if not path.exists():
        for attempt in range(4):
            host = 1 + attempt % 2
            url = f'https://query{host}.finance.yahoo.com/v8/finance/chart/{quote(symbol)}?{query}'
            try:
                with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=35) as reply:
                    body = reply.read()
                chart = json.loads(body)['chart']['result'][0]
                assert chart['meta']['symbol'] == symbol
                path.write_bytes(body)
                break
            except (OSError, ValueError, KeyError, TypeError) as exc:
                if attempt == 3:
                    raise
                print(symbol, str(exc), flush=True)
                time.sleep(attempt + 1)
    body = path.read_bytes()
    chart = json.loads(body)['chart']['result'][0]
    zone = chart['meta']['exchangeTimezoneName']
    events = chart.get('events', {})
    divs = defaultdict(float)
    splits = {}
    for entry in events.get('dividends', {}).values():
        divs[date_label(entry['date'], zone)] += entry['amount']
    for entry in events.get('splits', {}).values():
        splits[date_label(entry['date'], zone)] = entry['numerator'] / entry['denominator']
    prices = chart['indicators']['quote'][0]
    adj = chart['indicators']['adjclose'][0]['adjclose']
    rows = {}
    for i, ts in enumerate(chart['timestamp']):
        op, close = prices['open'][i], prices['close'][i]
        if op is None or close is None or not (start <= date_label(ts, zone) <= end):
            continue
        day = date_label(ts, zone)
        assert day not in rows and min(op, close) > 0
        rows[day] = (op, close, adj[i] or close)
    days = sorted(rows)
    shifted = {}
    for day in list(divs):
        if start <= day <= end and day not in rows:
            i = bisect.bisect_right(days, day)
            assert i < len(days) and (days[i] - day).days <= 4, (symbol, day)
            shifted[str(day)] = str(days[i])
            divs[days[i]] += divs.pop(day)
    discrepancies = []
    for previous, day in zip(days, days[1:]):
        if day in divs:
            op, close, adjusted = rows[day]
            _, prior_close, prior_adjusted = rows[previous]
            error = abs((close + divs[day]) / prior_close - adjusted / prior_adjusted)
            discrepancies.append(error)
    # The vendor's historical quote prices use split-normalized units.
    for day, ratio in splits.items():
        if day in rows and day != days[0]:
            prior = days[bisect.bisect_left(days, day) - 1]
            assert .6 < rows[day][1] / rows[prior][1] < 1.6, (symbol, day, ratio)
    missing_events = sorted(str(day) for day in divs.keys() - rows.keys() if start <= day <= end)
    assert not missing_events, (symbol, missing_events)
    report = dict(symbol=symbol, first=str(days[0]), last=str(days[-1]), bars=len(days),
                  distributions=sum(start <= day <= end for day in divs),
                  splits=sum(start <= day <= end for day in splits),
                  dividend_return_max_gap=max(discrepancies, default=0), shifted_distributions=json.dumps(shifted),
                  sha256=hashlib.sha256(body).hexdigest())
    assert len(days) >= 1200 and max(discrepancies, default=0) < .06, report
    return rows, divs, splits, report


def prior(series, day, strict=False):
    days, values = series
    i = (bisect.bisect_left if strict else bisect.bisect_right)(days, day) - 1
    if i < 0:
        raise ValueError(f'No prior observation for {day}')
    return values[days[i]]


def series(values):
    return sorted(values), values


def dump_csv(path, records):
    if records:
        with path.open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)


class Study:
    def __init__(self, data, holdings=None):
        self.data = data
        self.holdings = holdings
        self.closes = {s: series({d: row[1] for d, row in data[s][0].items()}) for s in ASSETS}
        self.fx = series({d: row[1] for d, row in data[FX][0].items()})
        self.days = sorted(set().union(*(data[s][0] for s in ASSETS)))
        self.months = {}
        for day in self.days:
            self.months[day.year, day.month] = day
        self.trend = {}
        for day in self.months.values():
            state = {}
            for market, s in [('US', US[0]), ('KR', KR[0])]:
                prices = series(data[s][0])
                history = [prior(prices, month_end(month_shift(day, -i)))[2]
                           for i in range(10) if month_shift(day.replace(day=1), -i) >= prices[0][0]]
                state[market] = len(history) == 10 and history[0] > statistics.mean(history)
            self.trend[day] = state

    def run(self, start, deadline, portfolio, strategy, ledger):
        weights = dict(zip(ASSETS, (.5, 0, 0, 0, .3, 0, 0, 0) if portfolio == 'etf'
                           else (.4, 1/30, 1/30, 1/30, .2, 1/30, 1/30, 1/30)))
        held = dict.fromkeys(ASSETS, 0.)
        balance = 1_000_000.
        navs = [balance]
        trades = 0
        early = False
        mark_hit = False
        target_date = ''
        exit_started = False
        exit_signal = 'none'
        pending = {}
        previous_state = self.trend[start]
        signals = strategy in ('trend', 'exit', 'partial')
        start_value = balance

        def schedule(day, assets, rule, fractions):
            for s in assets:
                if weights[s] or held[s]:
                    pending[s] = (day, rule, fractions[s])

        def rate(s, day):
            return prior(self.fx, day, strict=True) if s in US else 1.

        def value(day):
            return balance + sum(held[s] * prior(self.closes[s], day) * rate(s, day)
                                 for s in ASSETS)

        graph_active = strategy in GRAPH_STRATEGIES
        graph_report = graph_filing = ''
        graph_changes = 0

        def queue_weights(day, state, rule):
            nonlocal graph_report, graph_filing, graph_changes
            amount = value(day)
            desired = {s: weights[s] * amount * state['US' if s in US else 'KR'] for s in ASSETS}
            if graph_active:
                report, accession, overlap = prior(self.holdings, day, strict=True)
                if (day - iso(report)).days <= 185:
                    graph_report, graph_filing = report, accession
                    caps = {s: max(0., (CAP - weights['SPY'] * overlap[s]) * amount)
                            for s in CUSIP}
                    reduced = {s: min(desired[s], caps[s]) for s in CUSIP}
                    total_cut = sum(desired[s] - reduced[s] for s in CUSIP)
                    graph_changes += sum(desired[s] > reduced[s] for s in CUSIP)
                    if strategy == 'g1_lookthrough':
                        desired.update(reduced)
                    elif strategy == 'g1_matched_cash':
                        scale = 1 - total_cut / sum(desired[s] for s in CUSIP)
                        desired.update({s: desired[s] * scale for s in CUSIP})
                    else:
                        desired.update({s: min(desired[s], CAP * amount) for s in CUSIP})
            schedule(day, ASSETS, rule, desired)

        queue_weights(start, previous_state if signals else {'US': True, 'KR': True}, 'initial')
        final_dates = {s: self.closes[s][0][bisect.bisect_right(self.closes[s][0], deadline) - 1]
                       for s in ASSETS}
        for day in self.days[bisect.bisect_right(self.days, start):bisect.bisect_right(self.days, deadline)]:
            # In UTC the Korean regular session ends before the US regular session opens.
            for market in (KR, US):
                for s in market:
                    if held[s] and day in self.data[s][1]:
                        # Recognize the distribution on its effective session.
                        balance += held[s] * self.data[s][1][day] * rate(s, day)
                executable = []
                for s, (decision, rule, intended) in list(pending.items()):
                    rows = self.data[s][0]
                    if s not in market or day not in rows:
                        continue
                    if day >= final_dates[s] and not rule.startswith('target_'):
                        del pending[s]
                        continue
                    price = rows[day][0] * rate(s, day)
                    quantity = -held[s] * intended if rule.startswith('target_') else intended / price - held[s]
                    executable.append((quantity, s, decision, rule, price))
                executable.sort()
                for quantity, s, decision, rule, price in executable:
                    fee = COST + FX_COST * (s in US)
                    if quantity > 0:
                        quantity = min(quantity, max(0., balance) / (price * (1 + fee)))
                    if abs(quantity) > 1e-8:
                        held[s] += quantity
                        balance -= quantity * price + abs(quantity) * price * fee
                        trades += 1
                        future_split = 1.
                        for when, ratio in self.data[s][2].items():
                            if when > day:
                                future_split *= ratio
                        ledger.writerow((portfolio, strategy, start, deadline, decision, day, s,
                                         'BUY' if quantity > 0 else 'SELL', rule, quantity / future_split,
                                         price / rate(s, day) * future_split, rate(s, day),
                                         abs(quantity) * price * fee, balance, graph_report, graph_filing))
                    del pending[s]
                for s in market:
                    if day != final_dates[s] or held[s] <= 1e-8:
                        continue
                    fx = rate(s, day)
                    price = self.data[s][0][day][1]
                    gross = held[s] * price * fx
                    cost = gross * (COST + FX_COST * (s in US))
                    balance += gross - cost
                    trades += 1
                    future_split = 1.
                    for when, ratio in self.data[s][2].items():
                        if when > day:
                            future_split *= ratio
                    ledger.writerow((portfolio, strategy, start, deadline, start, day, s,
                                     'SELL', 'scheduled_deadline_close', -held[s] / future_split,
                                     price * future_split, fx, cost, balance, '', ''))
                    held[s] = 0.
                    pending.pop(s, None)
            if exit_started and exit_signal == 'target_full' and not pending and not any(held.values()):
                if not target_date and balance >= start_value * (1 + TARGET):
                    target_date = str(day)
                    early = day < deadline
            nav = value(day)
            navs.append(nav)
            if day == deadline:
                break
            exit_candidate = strategy in ('exit', 'partial') and not exit_started and any(held.values())
            liquidation = balance + sum(held[s] * prior(self.closes[s], day) * rate(s, day)
                                        * (1 - COST - FX_COST * (s in US)) for s in ASSETS)
            mark_hit = mark_hit or liquidation >= start_value * (1 + TARGET)
            if exit_candidate and liquidation >= start_value * (1 + TARGET):
                exit_started = True
                exit_signal = 'target_full' if strategy == 'exit' else 'target_half'
                pending.clear()
                fractions = dict.fromkeys(ASSETS, 1. if strategy == 'exit' else .5)
                schedule(day, [s for s in ASSETS if held[s]], exit_signal, fractions)
            elif not exit_started and day in self.trend and strategy != 'hold':
                state = self.trend[day] if signals else {'US': True, 'KR': True}
                if state != previous_state or day.month % 3 == 0:
                    queue_weights(day, state, 'trend_change' if state != previous_state else 'quarterly')
                    previous_state = state

        assert not any(quantity > 1e-8 for quantity in held.values())
        navs[-1] = balance
        peak = navs[0]
        mdd = 0.
        for nav in navs:
            peak = max(peak, nav)
            mdd = min(mdd, nav / peak - 1)
        return dict(portfolio=portfolio, strategy=strategy, start=str(start), end=str(deadline),
                    net=balance / start_value - 1, max_drawdown=mdd, early=int(early),
                    target=int(bool(target_date) or balance >= start_value * (1 + TARGET)),
                    target_date=target_date, trades=trades, mark_hit=int(mark_hit),
                    cap_candidates=graph_changes)


def summarize(cohorts):
    out = []
    groups = defaultdict(list)
    benchmarks = {(r['start'], r['months']): r['net'] for r in cohorts
                  if r['portfolio'] == 'etf' and r['strategy'] == 'hold'}
    periods = {'2018_q4_entry': ('2018-09-01', '2018-12-31'),
               '2020_q1_entry': ('2019-12-01', '2020-03-31'),
               '2022_bear_entry': ('2021-12-01', '2022-10-31')}
    paired_hold = {(r['start'], r['months'], r['portfolio']): r for r in cohorts if r['strategy'] == 'hold'}
    random_starts = {}
    bottom_quintile = {}
    for h in (12, 24):
        starts = sorted(start for start, months in benchmarks if months == h)
        random_starts[h] = set(random.Random(20261128 + h).sample(starts, len(starts) // 2))
        bottom_quintile[h] = set(sorted(starts, key=lambda day: benchmarks[day, h])[:len(starts) // 5])
    for row in cohorts:
        row['window'] = 'extension' if row['start'] < '2021-11-26' else 'five_year'
    for row in cohorts:
        key = row['start'], row['months']
        benchmark = benchmarks[key]
        regime = 'up' if benchmark >= .10 else 'down' if benchmark <= -.10 else 'middle'
        labels = ['all', regime]
        if benchmark < 0:
            labels.append('benchmark_loss')
        if row['start'] in bottom_quintile[row['months']]:
            labels.append('bottom_quintile')
        labels.extend(label for label, (first, last) in periods.items() if first <= row['start'] <= last)
        if row['start'] in random_starts[row['months']]:
            labels.append('random')
        for label in labels:
            for window in ('all_years', row['window']):
                groups[window, row['months'], label, row['portfolio'], row['strategy']].append(row)
    for (window, months, sample, portfolio, strategy), rows in sorted(groups.items()):
        baseline = [paired_hold[r['start'], months, portfolio] for r in rows]
        return_gaps = [r['net'] - b['net'] for r, b in zip(rows, baseline)]
        drawdown_gaps = [r['max_drawdown'] - b['max_drawdown'] for r, b in zip(rows, baseline)]
        out.append(dict(window=window, months=months, sample=sample, portfolio=portfolio, strategy=strategy,
                        n=len(rows), targets=sum(r['target'] for r in rows),
                        early=sum(r['early'] for r in rows),
                        median_net=statistics.median(r['net'] for r in rows),
                        median_mdd=statistics.median(r['max_drawdown'] for r in rows),
                        worst_net=min(r['net'] for r in rows),
                        hold_targets=sum(b['target'] for b in baseline),
                        median_return_delta_vs_hold=statistics.median(return_gaps),
                        median_drawdown_delta_vs_hold=statistics.median(drawdown_gaps),
                        wins_vs_hold=sum(gap > 1e-10 for gap in return_gaps),
                        ties_vs_hold=sum(abs(gap) <= 1e-10 for gap in return_gaps),
                        trades=sum(r['trades'] for r in rows), cap_candidates=sum(r['cap_candidates'] for r in rows)))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--start', type=iso, default=iso('2021-11-26'))
    parser.add_argument('--end', type=iso, default=iso('2026-11-26'))
    parser.add_argument('--spy-graph', action='store_true')
    args = parser.parse_args()
    raw = args.out / 'raw'
    raw.mkdir(exist_ok=True, parents=True)
    data = {}
    for s in ASSETS + (FX,):
        data[s] = fetch(s, raw, month_shift(args.start, -11), args.end)
        print(data[s][3], flush=True)
    dump_csv(args.out / 'coverage.csv', [v[3] for v in data.values()])
    holdings = spy_holdings(args.out / 'nport') if args.spy_graph else None
    study = Study(data, holdings)
    end = min(max(value[0]) for value in data.values())
    cohorts = []
    with (args.out / 'orders.csv').open('w', newline='', encoding='utf-8') as stream:
        ledger = csv.writer(stream)
        ledger.writerow(('portfolio', 'strategy', 'start', 'end', 'decision_date', 'trade_date',
                         'symbol', 'side', 'reason', 'shares_signed', 'local_price', 'fx_krw',
                         'cost_krw', 'cash_krw', 'holdings_asof', 'holdings_filing'))
        for start in study.months.values():
            if start < args.start:
                continue
            for months in (12, 24):
                end_month = month_shift(start, months)
                deadline = study.months.get((end_month.year, end_month.month))
                if deadline is None or (end_month.year, end_month.month) >= (end.year, end.month):
                    continue
                for portfolio in ('etf', 'mixed'):
                    for strategy in STRATEGIES:
                        row = study.run(start, deadline, portfolio, strategy, ledger)
                        row['months'] = months
                        cohorts.append(row)
                if holdings and holdings[0] and start >= iso('2021-11-26') and start > holdings[0][0]:
                    for strategy in GRAPH_STRATEGIES:
                        row = study.run(start, deadline, 'mixed', strategy, ledger)
                        row['months'] = months
                        cohorts.append(row)
    assert cohorts
    dump_csv(args.out / 'cohorts.csv', cohorts)
    summary = summarize(cohorts)
    dump_csv(args.out / 'summary.csv', summary)
    print(f'{len(cohorts)} cohort-strategy observations; common end {end}')
    for r in summary:
        if r['sample'] in ('all', 'up', 'down', 'random') and r['window'] == 'all_years':
            print(r['months'], r['sample'], r['portfolio'], r['strategy'], r['n'], r['targets'],
                  round(100*r['median_net'], 2), round(100*r['median_mdd'], 2))


if __name__ == '__main__':
    main()
