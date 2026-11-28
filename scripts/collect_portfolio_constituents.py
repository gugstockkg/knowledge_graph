"""Collect dated SPY and KODEX 200 holdings and constituent total-return prices."""
import argparse
import calendar
import csv
import datetime as dt
import json
import re
from urllib.error import HTTPError
import time
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

import backtest_portfolio_exit as base


def fetch(url, path, body=None, timeout=15):
    if path.is_file():
        return json.loads(path.read_bytes())
    headers = {'User-Agent': 'Research portfolio study contact ops@fintos.ai'}
    if body is not None:
        headers['Content-Type'] = 'application/json'
    with urlopen(Request(url, data=body, headers=headers), timeout=timeout) as reply:
        data = reply.read()
    obj = json.loads(data)
    path.write_bytes(data)
    return obj


def normalize(name):
    return re.sub(r'[^a-z0-9]', '', re.sub(
        r'\b(incorporated|inc|corporation|corp|company|co|limited|ltd|plc|class [a-z]|the)\b',
        '', name.lower()))


def scan_us(source):
    reported = {}
    with (source / 'holdings_edges.csv').open() as f:
        for row in csv.DictReader(f):
            reported[row['accession']] = (row['report'], row['known'], row['source'])
    rows = []
    for accession, (day, known, link) in sorted(reported.items()):
        for r in ET.parse(source / f'{accession}.xml').getroot().findall('.//{*}invstOrSec'):
            if r.findtext('{*}assetCat') != 'EC' or r.findtext('{*}payoffProfile') != 'Long':
                continue
            cusip = r.findtext('{*}cusip')
            lei = r.findtext('{*}lei')
            issuer = r.findtext('{*}name')
            rows.append(dict(market='US', snapshot=day, known=known, source=link, security=cusip,
                             issuer=lei if lei and lei not in ('N/A', 'NA') else normalize(issuer),
                             name=issuer, weight=float(r.findtext('{*}pctVal')) / 100))
    return rows


def scan_kr(day, root):
    d = day.strftime('%Y.%m.%d')
    url = f'https://www.samsungfund.com/api/v1/kodex/product-pdf/2ETF01.do?gijunYMD={d}'
    try:
        pdf = fetch(url, root / f'{day}.json')['pdf']
        assert pdf['gijunYMD'] == day.strftime('%Y%m%d') and pdf['nowCnt'] == len(pdf['list'])
    except (OSError, KeyError, AssertionError, TypeError, ValueError) as exc:
        print('KODEX unavailable', day, exc, flush=True)
        return []
    rows = []
    for r in pdf['list']:
        isin = r['itmNo']
        if not isinstance(isin, str) or not re.fullmatch(r'[0-9]{5}[0-9A-Z]', isin) or not r['ratio']:
            continue
        security = isin
        rows.append(dict(market='KR', snapshot=str(day), known='', source=url,
                         security=security, issuer=security[:5], name=r['secNm'],
                         weight=float(r['ratio']) / 100))
    if len(rows) < 175:
        print('KODEX incomplete', day, len(rows), flush=True)
        return []
    return rows


def ticker_maps(rows, root):
    sec = fetch('https://www.sec.gov/files/company_tickers.json', root / 'company_tickers.json')
    names = defaultdict(set)
    for r in sec.values():
        names[normalize(r['title'])].add(r['ticker'])
    mapped = {}
    for r in rows:
        choices = names[normalize(r['name'])]
        if len(choices) == 1:
            mapped[r['security']] = next(iter(choices)).replace('.', '-')
    mapped.update({v: k for k, v in base.CUSIP.items()})
    candidates = Counter(r['security'] for r in rows if r['security'] not in mapped)
    identifiers = [cusip for cusip, _ in candidates.most_common(140)]
    for i in range(0, len(identifiers), 10):
        batch = identifiers[i:i + 10]
        target = root / f'figi-{i:03}.json'
        try:
            body = json.dumps([dict(idType='ID_CUSIP', idValue=c, exchCode='US') for c in batch])
            obj = fetch('https://api.openfigi.com/v3/mapping', target, body.encode())
        except (OSError, ValueError) as exc:
            print('OpenFIGI skipped', i, exc, flush=True)
            if isinstance(exc, HTTPError) and exc.code == 429:
                break
            continue
        for cusip, result in zip(batch, obj):
            tickers = {x['ticker'] for x in result.get('data', ()) if x['marketSector'] == 'Equity'}
            if len(tickers) == 1:
                mapped[cusip] = next(iter(tickers)).replace('.', '-')
        time.sleep(8)
    return mapped


def monthly_chart(ticker, root):
    path = root / f'{ticker}.json'
    start = calendar.timegm(dt.date(2018, 1, 1).timetuple())
    end = calendar.timegm(dt.date(2026, 11, 27).timetuple())
    for host in (1, 2):
        url = (f'https://query{host}.finance.yahoo.com/v8/finance/chart/{quote(ticker)}'
               f'?period1={start}&period2={end}&interval=1mo')
        try:
            result = fetch(url, path)['chart']['result'][0]
            if result['meta']['symbol'] != ticker:
                return ticker, {}
            return ticker, {base.date_label(t, result['meta']['exchangeTimezoneName']).strftime('%Y-%m'): p
                            for t, p in zip(result['timestamp'],
                                            result['indicators']['adjclose'][0]['adjclose'])
                            if p and p > 0}
        except (OSError, TypeError, KeyError, IndexError, ValueError):
            continue
    return ticker, {}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pilot', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    root = args.out
    for directory in ('kr', 'prices', 'identity'):
        (root / directory).mkdir(parents=True, exist_ok=True)
    us = scan_us(args.pilot / 'nport')
    local_raw = args.pilot / 'raw'
    rows = base.fetch('069500.KS', local_raw, dt.date(2015, 2, 1), dt.date(2026, 11, 26))[0]
    months = {}
    for day in sorted(rows):
        if day >= dt.date(2019, 9, 1):
            months[day.year, day.month] = day
    kr = []
    for day in months.values():
        cached = (root / 'kr' / f'{day}.json').exists()
        if cached or day.month % 3 == 0:
            kr.extend(scan_kr(day, root / 'kr'))
            if not cached:
                time.sleep(3)
    print('KODEX snapshots', len({r['snapshot'] for r in kr}), flush=True)
    mapped = ticker_maps(us, root / 'identity')
    all_rows = us + kr
    for row in all_rows:
        row['ticker'] = mapped.get(row['security'], '') if row['market'] == 'US' else row['security'] + '.KS'
    base.dump_csv(root / 'constituents.csv', all_rows)
    tickers = sorted({row['ticker'] for row in all_rows if row['ticker']})
    print('rows', len(us), len(kr), 'potential ticker links', len(mapped), 'price candidates', len(tickers), flush=True)
    with ThreadPoolExecutor(max_workers=8) as pool:
        prices = {}
        for i, (ticker, series) in enumerate(pool.map(lambda t: monthly_chart(t, root / 'prices'), tickers), 1):
            if series:
                prices[ticker] = series
            if i % 100 == 0:
                print('prices', i, 'available', len(prices), flush=True)
    (root / 'monthly.json').write_text(json.dumps(prices, separators=(',', ':')))
    print('available series', len(prices), flush=True)


if __name__ == '__main__':
    main()
