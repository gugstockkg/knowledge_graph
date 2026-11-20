"""Collect a bounded, reproducible contract, price and news evidence sample."""
import argparse
import csv
import datetime as dt
import hashlib
import json
import re
import time
import zipfile
from collections import Counter, defaultdict
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

from ..config import get_paths
from ..market.prices import SOURCE, canonical_name, fetch_chart, parse_chart

COMPANIES = {
    'HD한국조선해양', '한화오션', '삼성중공업', 'HD현대중공업', 'HJ중공업',
    '케이에스피', 'STX엔진', '동성화인텍', '한국카본', 'HD현대마린엔진',
    '인화정공', '대양전기공업', '세진중공업', '오리엔탈정공',
}
MARKETS = {'Y': 'KOSPI', 'K': 'KOSDAQ'}
LABELS = {
    '판매공급계약내용': 'description',
    '체결계약명': 'description',
    '계약상대': 'buyer',
    '계약상대방': 'buyer',
    '계약금액총액원': 'amount_krw',
    '계약금액원': 'amount_krw',
    '확정계약금액': 'fixed_amount_krw',
    '조건부계약금액': 'conditional_amount_krw',
    '조건부계약여부': 'conditional',
    '최근매출액원': 'supplier_sales_krw',
    '매출액대비': 'reported_sales_pct',
    '시작일': 'start_date',
    '종료일': 'end_date',
    '계약수주일자': 'signed_date',
    '대금지급조건등': 'payment_terms',
    '유보사유': 'withholding_reason',
    '자회사인': 'reported_subsidiary',
}
KST = dt.timezone(dt.timedelta(hours=9))


class TableRows(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self.row = []
            self.cell = None
        elif tag in ('td', 'th', 'te', 'tu') and self.row is not None:
            self.cell = [self.getpos()[0], [], []]
        elif tag == 'a' and self.cell is not None:
            self.cell[2].extend(v for k, v in attrs if k in ('href', 'onclick') and v)
        elif tag in ('br', 'p') and self.cell is not None:
            self.cell[1].append(' ')

    def handle_data(self, data):
        if self.cell is not None:
            self.cell[1].append(data)

    def handle_endtag(self, tag):
        if tag in ('td', 'th', 'te', 'tu') and self.cell is not None:
            line, fragments, links = self.cell
            self.row.append((' '.join(''.join(fragments).split()), line, links))
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            self.rows.append(self.row)
            self.row = self.cell = None


def compact(text):
    return re.sub(r'[^0-9A-Za-z가-힣]', '', text)


def parse_contract(document):
    parser = TableRows()
    parser.feed(document)
    result = {}
    section = None
    for row in parser.rows:
        for i, (label, _, _) in enumerate(row[:-1]):
            numbered = re.match(r'^(\d+)\.\s*(.*)', label)
            if numbered:
                section = int(numbered[1])
                label = numbered[2]
            key = LABELS.get(compact(label))
            if compact(label) == '관련공시':
                refs = sorted(set(re.findall(r'(?<!\d)\d{14}(?!\d)', ' '.join(
                    text for cell in row[i+1:] for text in [cell[0], *cell[2]]))))
                if refs:
                    result['related_receipts'] = {'value': refs, 'line': row[i+1][1]}
            if not key or key in result:
                continue
            if key == 'supplier_sales_krw' and section != 2:
                continue
            text, line, _ = row[i+1]
            value = text if text not in ('', '-', '－', '—') else None
            if value is not None and key.endswith('_krw'):
                digits = value.replace(',', '').replace(' ', '')
                value = int(digits) if digits.isdigit() else None
            elif value is not None and key == 'reported_sales_pct':
                try:
                    value = float(value.replace('%', '').replace(',', ''))
                except ValueError:
                    value = None
            elif value is not None and key.endswith('_date'):
                try:
                    value = dt.date.fromisoformat(value).isoformat()
                except ValueError:
                    value = None
            result[key] = {'value': value, 'text': text, 'line': line}
    return result


def field(fields, key):
    return fields.get(key, {}).get('value')


def is_subsidiary_report(title, fields):
    return '자회사의주요경영사항' in compact(title) or bool(field(fields, 'reported_subsidiary'))


def buyer_lookup_name(text):
    # Some forms append an English company name to the Korean legal name.
    if re.search(r'[가-힣]', text):
        text = re.sub(r'\s+\([A-Za-z][^가-힣()]*\)\s*$', '', text)
    return canonical_name(text)


def is_marine_contract(description):
    return bool(re.search(
        r'선박|선박엔진|운반선|컨테이너선|보냉|엔진|유조선|탱커|LNGC|VLCC|VLGC|LPGC|PC선|RORO|FPSO',
        description, re.IGNORECASE,
    ))


def json_save(path, value):
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(path)


def bytes_save(path, value):
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_bytes(value)
    tmp.replace(path)


def csv_save(path, headers, rows):
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('w', encoding='utf-8-sig', newline='') as out:
        writer = csv.DictWriter(out, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def date_iso(value):
    return dt.datetime.strptime(value, '%Y%m%d').date().isoformat()


def read_archive(path, receipt):
    with zipfile.ZipFile(path) as archive:
        member = next((n for n in archive.namelist() if Path(n).name == receipt + '.xml'), None)
        if member is None:
            raise ValueError('main document missing')
        body = archive.read(member)
    try:
        document = body.decode('utf-8-sig')
    except UnicodeDecodeError:
        document = body.decode('cp949')
    return document, member, hashlib.sha256(body).hexdigest()


def select_events(collections, start, end, limit):
    names = {canonical_name(name) for name in COMPANIES}
    filings = {}
    listed = defaultdict(dict)
    for collection in collections:
        for index in sorted((collection / 'daily_indexes').glob('*.json')):
            for row in json.loads(index.read_text())['filings']:
                day = date_iso(row['rcept_dt'])
                if not start <= day <= end:
                    continue
                corp = row.get('corp_code', '')
                receipt = row.get('rcept_no', '')
                symbol = row.get('stock_code', '')
                if not re.fullmatch(r'\d{8}', corp) or not re.fullmatch(r'\d{14}', receipt):
                    continue
                key = canonical_name(row['corp_name'])
                if row.get('corp_cls') in MARKETS and re.fullmatch(r'\d{6}', symbol):
                    listed[key][(corp, symbol)] = {
                        'corp_code': corp, 'name': row['corp_name'], 'symbol': symbol,
                        'market': MARKETS[row['corp_cls']],
                    }
                title = compact(row['report_nm'])
                if key in names and '단일판매' in title and '공급계약' in title:
                    path = collection / 'documents' / corp / (receipt + '.zip')
                    if receipt not in filings or (path.is_file() and not filings[receipt][1].is_file()):
                        filings[receipt] = (row, path)
    counts = Counter(title_matches=len(filings))
    originals = []
    corrections = []
    for receipt, (row, path) in sorted(filings.items(), reverse=True):
        if not path.is_file():
            counts['archive_pending'] += 1
            continue
        counts['archives_available'] += 1
        try:
            document, member, digest = read_archive(path, receipt)
            fields = parse_contract(document)
        except (ValueError, OSError, zipfile.BadZipFile):
            counts['invalid_archive'] += 1
            continue
        title = row['report_nm']
        if is_subsidiary_report(title, fields):
            counts['subsidiary_reports_excluded'] += 1
            continue
        correction = '정정' in title or '해지' in title or '취소' in title
        item = {
            'receipt_no': receipt, 'receipt_date': date_iso(row['rcept_dt']), 'title': title,
            'source_url': 'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=' + receipt,
            'archive': str(path), 'document_member': member, 'document_sha256': digest,
            'supplier_corp_code': row['corp_code'], 'fields': fields,
        }
        if correction:
            corrections.append(item)
            continue
        supplier = listed.get(canonical_name(row['corp_name']), {})
        buyer_name = field(fields, 'buyer')
        buyer = listed.get(buyer_lookup_name(buyer_name), {}) if buyer_name else {}
        if len(supplier) != 1:
            counts['unresolved_supplier'] += 1
            continue
        if not field(fields, 'amount_krw') or not field(fields, 'description'):
            counts['incomplete_contract_fields'] += 1
            continue
        if not is_marine_contract(field(fields, 'description')):
            counts['outside_marine_scope'] += 1
            continue
        seller = next(iter(supplier.values()))
        customer = next(iter(buyer.values())) if len(buyer) == 1 else None
        if customer and seller['corp_code'] == customer['corp_code']:
            counts['same_entity'] += 1
            continue
        item.update(supplier=seller, buyer=customer, amendments=[],
                    buyer_status='listed_exact_name_match' if customer else 'unresolved')
        originals.append(item)
    selected = []
    # Prefer priced counterparties, then round robin across suppliers.
    for resolved in (True, False):
        if len(selected) == limit:
            break
        by_supplier = defaultdict(list)
        for item in originals:
            if bool(item['buyer']) == resolved:
                by_supplier[item['supplier_corp_code']].append(item)
        for offset in range(limit):
            for group in by_supplier.values():
                if offset < len(group):
                    selected.append(group[offset])
                    if len(selected) == limit:
                        break
            if len(selected) == limit:
                break
    lookup = {row['receipt_no']: row for row in selected}
    for amendment in reversed(corrections):
        refs = field(amendment['fields'], 'related_receipts') or []
        matches = [lookup[ref] for ref in refs if ref in lookup and
                   lookup[ref]['supplier_corp_code'] == amendment['supplier_corp_code'] and
                   lookup[ref]['receipt_date'] <= amendment['receipt_date']]
        if len(matches) == 1:
            matches[0]['amendments'].append(amendment)
            counts['linked_amendments'] += 1
        else:
            counts['amendments_without_selected_explicit_match'] += 1
    counts['eligible_originals'] = len(originals)
    counts['selected_originals'] = len(selected)
    counts['selected_listed_pairs'] = sum(bool(item['buyer']) for item in selected)
    return selected, dict(counts)


def collect_prices(events, end, out, refresh):
    raw = out / 'raw_prices'
    raw.mkdir(exist_ok=True)
    securities = {p['symbol']: p for e in events for p in (e['supplier'], e['buyer']) if p}
    for market in sorted({p['market'] for p in securities.values()}):
        securities[market] = {'symbol': market, 'market': market, 'name': market}
    start = (min(dt.date.fromisoformat(e['receipt_date']) for e in events)
             - dt.timedelta(days=60)).isoformat()
    snapshots = {}
    failures = {}
    for symbol, security in sorted(securities.items()):
        path = raw / (symbol + '.xml')
        meta_path = raw / (symbol + '.json')
        is_index = symbol in ('KOSPI', 'KOSDAQ')
        try:
            cached = None
            if not refresh and path.is_file() and meta_path.is_file():
                candidate = path.read_bytes()
                meta = json.loads(meta_path.read_text())
                if hashlib.sha256(candidate).hexdigest() == meta.get('sha256'):
                    cached = candidate
            if cached is None:
                body, url = fetch_chart(symbol, count=500)
                meta = {'url': url, 'retrieved_at': dt.datetime.now(dt.timezone.utc).isoformat(),
                        'sha256': hashlib.sha256(body).hexdigest()}
                time.sleep(0.25)
            else:
                body = cached
            chart, bars = parse_chart(body, symbol, start, end, index=is_index)
            if not bars:
                raise ValueError('no bars in requested window')
            if not is_index and canonical_name(chart.get('name', '')) != canonical_name(security['name']):
                raise ValueError('provider name differs from DART name')
            if cached is None:
                bytes_save(path, body)
                json_save(meta_path, meta)
            snapshots[symbol] = {'security': security, 'is_index': is_index, 'source': SOURCE,
                                 'adjustment_status': 'not_applicable' if is_index else 'unverified',
                                 **meta, 'bars': bars}
            print('PRICE', symbol, len(bars), flush=True)
        except (ValueError, OSError, RuntimeError, KeyError, SyntaxError) as exc:
            failures[symbol] = type(exc).__name__ + ': ' + str(exc)
    return snapshots, failures


def returns(events, snapshots):
    for event in events:
        for role in ('supplier', 'buyer'):
            party = event[role]
            if not party:
                continue
            symbol = party['symbol']
            market = party['market']
            prices = {p['date']: p for p in snapshots.get(symbol, {}).get('bars', [])}
            index = {p['date']: p for p in snapshots.get(market, {}).get('bars', [])}
            days = sorted(day for day in index if day > event['receipt_date'])
            for horizon in (1, 5):
                entry = days[0] if days else None
                exit_day = days[horizon-1] if len(days) >= horizon else None
                result = dict(receipt_no=event['receipt_no'], role=role, symbol=symbol,
                              benchmark=market, horizon=horizon, entry_date=entry, exit_date=exit_day,
                              return_pct=None, benchmark_return_pct=None, excess_pct=None,
                              status='insufficient_future_bars')
                if not index or not prices:
                    result['status'] = 'missing_series'
                elif exit_day:
                    start_bar, end_bar = prices.get(entry), prices.get(exit_day)
                    if not (start_bar and end_bar and start_bar['is_tradable'] and end_bar['is_tradable']):
                        result['status'] = 'nontradable_or_missing'
                    elif index[entry]['open'] <= 0 or index[exit_day]['close'] <= 0:
                        result['status'] = 'invalid_benchmark'
                    else:
                        own = 100 * (end_bar['close'] / start_bar['open'] - 1)
                        base = 100 * (index[exit_day]['close'] / index[entry]['open'] - 1)
                        result.update(return_pct=round(own, 4), benchmark_return_pct=round(base, 4),
                                      excess_pct=round(own - base, 4), status='exploratory_adjustment_unverified')
                yield result


NEWS_COLUMNS = ('receipt_no', 'url', 'publisher', 'published_date', 'published_at', 'match_basis')


def news_references(path, events):
    dates = {e['receipt_no']: e['receipt_date'] for e in events}
    rows = []
    seen = set()
    counts = Counter()
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if not set(NEWS_COLUMNS) <= set(reader.fieldnames or ()):
            raise ValueError('news CSV requires columns: ' + ', '.join(NEWS_COLUMNS))
        for row in reader:
            receipt, url = row['receipt_no'].strip(), row['url'].strip()
            if receipt not in dates:
                continue
            parsed = urlsplit(url)
            if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError('news URL must be an HTTPS publisher reference')
            published = dt.date.fromisoformat(row['published_date']).isoformat()
            if row['published_at']:
                timestamp = dt.datetime.fromisoformat(row['published_at'])
                if timestamp.tzinfo is None or timestamp.astimezone(KST).date().isoformat() != published:
                    raise ValueError('published_at must have a timezone and agree with published_date in KST')
            if not row['publisher'].strip() or not row['match_basis'].strip():
                raise ValueError('news publisher and match_basis are required')
            if (receipt, url) in seen or counts[receipt] >= 5:
                continue
            seen.add((receipt, url))
            counts[receipt] += 1
            timing = ('before_filing_day' if published < dates[receipt] else
                      'after_filing_day' if published > dates[receipt] else 'same_day_order_unknown')
            rows.append({**{key: row[key] for key in NEWS_COLUMNS}, 'timing': timing})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', default='2026-01-01')
    parser.add_argument('--end', required=True, help='last closed KST date')
    parser.add_argument('--limit', type=int, choices=range(1, 21), default=10)
    parser.add_argument('--news-csv', type=Path)
    parser.add_argument('--with-prices', action='store_true')
    parser.add_argument('--refresh-prices', action='store_true')
    args = parser.parse_args()
    start, end = (dt.date.fromisoformat(x).isoformat() for x in (args.start, args.end))
    if end < start or end >= dt.datetime.now(KST).date().isoformat():
        parser.error('use an ordered date range ending before today in KST')
    paths = get_paths()
    collections = sorted((paths.raw / 'collections').glob('*_*'))
    out = paths.data / 'pilots' / 'shipbuilding_contracts' / (start + '_' + end)
    out.mkdir(parents=True, exist_ok=True)
    events, stats = select_events(collections, start, end, args.limit)
    json_save(out / 'contracts.json', events)
    csv_save(out / 'news_input_template.csv', NEWS_COLUMNS, [])
    print('CONTRACTS', stats, flush=True)
    if not events:
        raise RuntimeError('no eligible listed-supplier contracts found in local archives')
    snapshots, failures = ({}, {})
    if args.with_prices:
        snapshots, failures = collect_prices(events, end, out, args.refresh_prices)
        price_rows = [dict(symbol=symbol, source=dataset['source'], **bar)
                      for symbol, dataset in sorted(snapshots.items()) for bar in dataset['bars']]
        csv_save(out / 'prices.csv', ('symbol','source','date','open','high','low','close','volume','is_tradable'), price_rows)
        json_save(out / 'price_sources.json',
                  {symbol: {k: v for k, v in dataset.items() if k != 'bars'}
                   for symbol, dataset in snapshots.items()})
        event_rows = list(returns(events, snapshots))
        csv_save(out / 'event_returns.csv', tuple(event_rows[0]), event_rows)
    references = news_references(args.news_csv, events) if args.news_csv else []
    if args.news_csv:
        json_save(out / 'news_references.json', references)
    manifest = {
        'start': start, 'end': end, 'updated_at': dt.datetime.now(KST).isoformat(),
        'contract_scan': stats, 'contract_target': args.limit,
        'price_series': {symbol: len(dataset['bars']) for symbol, dataset in snapshots.items()},
        'price_failures': failures, 'price_collection_requested': args.with_prices,
        'news_reference_count': len(references), 'news_import_requested': bool(args.news_csv),
        'news_covered_receipts': len({r['receipt_no'] for r in references}),
        'filing_time_precision': 'date', 'industry_benchmark': 'pending',
        'financial_data': 'reported sales denominator only', 'validation_status': 'pilot_candidates',
    }
    json_save(out / 'manifest.json', manifest)
    print('OUTPUT', out, 'price_series', len(snapshots), 'news', len(references), 'failures', len(failures))
    if failures:
        raise RuntimeError('some price series failed; see manifest')


if __name__ == '__main__':
    main()
