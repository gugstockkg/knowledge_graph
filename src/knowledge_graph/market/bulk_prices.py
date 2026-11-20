"""Collect year-to-date daily prices for the full DART-derived symbol universe."""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from urllib.error import HTTPError, URLError
from xml.etree.ElementTree import ParseError

from ..config import get_paths
from .prices import SOURCE, canonical_name, fetch_chart, parse_chart

KST = dt.timezone(dt.timedelta(hours=9))
INDEXES = ('KOSPI', 'KOSDAQ')
NO_CHART = re.compile(br'\s*(?:<\?xml[^?]*\?>\s*)?<protocol\s*/>\s*')


def save(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False) + '\n', encoding='utf-8')
    tmp.replace(path)


def universe(collections, reference, start, end):
    identities = defaultdict(dict)
    index_dates = set()

    def add(row, evidence):
        symbol = row.get('stock_code', '')
        if not re.fullmatch(r'(?=[A-Z0-9]*\d)[A-Z0-9]{6}', symbol) or symbol == '000000':
            return
        corp = row.get('corp_code', '')
        name = row.get('corp_name', '')
        if corp and name:
            identities[symbol][(corp, name)] = {
                'corp_code': corp, 'name': name, 'source': evidence,
            }

    for collection in collections:
        for path in sorted((collection / 'daily_indexes').glob('*.json')):
            if not start.replace('-', '') <= path.stem <= end.replace('-', ''):
                continue
            if path.stem in index_dates:
                continue
            index_dates.add(path.stem)
            for row in json.loads(path.read_text())['filings']:
                if row.get('corp_cls') in ('Y', 'K', 'N'):
                    add(row, 'DART_FILING')
    for row in json.loads(reference.read_text())['rows']:
        add(row, 'DART_CORPCODE')
    result = {code: list(items.values()) for code, items in sorted(identities.items())}
    return {**{symbol: [] for symbol in INDEXES}, **result}, len(index_dates)


def pilot_cache(paths, symbol, end):
    cutoff = dt.datetime.combine(dt.date.fromisoformat(end) + dt.timedelta(days=1),
                                 dt.time(), tzinfo=KST)
    for meta_path in sorted((paths.data / 'pilots/shipbuilding_contracts').glob(
            '*/raw_prices/' + symbol + '.json'), reverse=True):
        raw_path = meta_path.with_suffix('.xml')
        if not raw_path.is_file():
            continue
        meta = json.loads(meta_path.read_text())
        if dt.datetime.fromisoformat(meta['retrieved_at']) < cutoff:
            continue
        body = raw_path.read_bytes()
        if hashlib.sha256(body).hexdigest() == meta['sha256']:
            return body, meta
    return None


def collect(args, paths, out):
    raw_dir = out / 'raw'
    series_dir = out / 'series'
    for path in (raw_dir, series_dir):
        path.mkdir(exist_ok=True)
    reference = Path(args.corp_codes)
    collections = sorted((paths.raw / 'collections').glob('*_*'))
    symbols, index_days = universe(collections, reference, args.start, args.end)
    if len(symbols) <= len(INDEXES):
        raise ValueError('no DART symbols found')
    save(out / 'universe.json', symbols)

    manifest = {
        'start': args.start, 'end': args.end, 'source': SOURCE,
        'symbol_count': len(symbols) - len(INDEXES), 'indexes': list(INDEXES),
        'dart_days_indexed': index_days, 'corp_code_source': str(reference),
        'pid': os.getpid(), 'adjustment_status': 'unverified',
    }
    counts = Counter()
    errors = {}
    bar_count = 0

    def checkpoint(state):
        manifest.update(state=state, counts=dict(counts), price_rows=bar_count, failures=errors,
                        updated_at=dt.datetime.now(KST).isoformat())
        save(out / 'manifest.json', manifest)
        print(state, dict(counts), 'rows', bar_count, flush=True)

    checkpoint('collecting')
    consecutive_errors = 0
    for position, (symbol, identities) in enumerate(symbols.items(), 1):
        path = series_dir / (symbol + '.json')
        previous = json.loads(path.read_text()) if path.is_file() else None
        raw_path = raw_dir / (symbol + '.xml')
        if (previous and previous.get('identities') == identities and raw_path.is_file()
                and hashlib.sha256(raw_path.read_bytes()).hexdigest() == previous.get('sha256')):
            result = previous
        else:
            try:
                cached = pilot_cache(paths, symbol, args.end)
                if cached:
                    body, meta = cached
                else:
                    body, url = fetch_chart(symbol, count=500)
                    meta = {'url': url, 'retrieved_at': dt.datetime.now(KST).isoformat(),
                            'sha256': hashlib.sha256(body).hexdigest()}
                    time.sleep(args.interval)
                if NO_CHART.fullmatch(body) and symbol not in INDEXES:
                    chart, bars = {}, []
                else:
                    chart, bars = parse_chart(body, symbol, args.start, args.end, index=symbol in INDEXES)
                provider_name = chart.get('name', '')
                matches = {i['corp_code'] for i in identities
                           if canonical_name(i['name']) == canonical_name(provider_name)}
                if not bars:
                    status = 'no_bars'
                elif symbol in INDEXES:
                    status = 'index'
                elif len(matches) == 1 and len({i['corp_code'] for i in identities}) == 1:
                    status = 'name_match'
                else:
                    status = 'identity_review'
                tmp = raw_dir / (symbol + '.tmp')
                tmp.write_bytes(body)
                tmp.replace(raw_path)
                result = {'symbol': symbol, 'provider_name': provider_name,
                          'identities': identities, 'status': status, 'bars': bars, **meta}
                save(path, result)
                consecutive_errors = 0
            except (HTTPError, URLError, OSError, ValueError, ParseError) as exc:
                code = exc.code if isinstance(exc, HTTPError) else None
                errors[symbol] = {'type': type(exc).__name__, 'http_status': code}
                consecutive_errors += 1
                checkpoint('stopped_provider_limit' if code in (403, 429) else 'collecting')
                if code in (403, 429) or consecutive_errors >= 5:
                    if code not in (403, 429):
                        checkpoint('stopped_consecutive_errors')
                    return 2
                time.sleep(max(args.interval, 2))
                continue
        counts[result['status']] += 1
        bar_count += len(result['bars'])
        if position % 25 == 0:
            checkpoint('collecting')
    checkpoint('complete_with_errors' if errors else 'complete')
    return 2 if errors else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', required=True)
    parser.add_argument('--end', required=True)
    parser.add_argument('--corp-codes', required=True)
    parser.add_argument('--interval', type=float, default=0.8)
    args = parser.parse_args()
    args.start = dt.date.fromisoformat(args.start).isoformat()
    args.end = dt.date.fromisoformat(args.end).isoformat()
    if not args.start <= args.end < dt.datetime.now(KST).date().isoformat():
        parser.error('use ordered dates ending before today in KST')
    if (dt.date.fromisoformat(args.end) - dt.date.fromisoformat(args.start)).days > 366:
        parser.error('use a window of one year or less')
    if args.interval < 0.8:
        parser.error('interval must be at least 0.8 seconds')
    paths = get_paths()
    out = paths.data / 'market' / 'bulk_naver_daily' / (args.start + '_' + args.end)
    out.mkdir(parents=True, exist_ok=True)
    with (out / '.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('this date range is already being collected') from None
        return collect(args, paths, out)


if __name__ == '__main__':
    raise SystemExit(main())
