"""Operational, resumable collection for the user-approved date interval."""
import concurrent.futures
import datetime as dt
import io
import json
import os
from pathlib import Path
import re
import sys
import threading
import time
import zipfile
import xml.etree.ElementTree as ET

from ..config import get_paths, require_api_key
from .client import DartClient, DartApiError
from .normalize import filing_records
PATHS = get_paths()
ROOT = PATHS.collection
DEV = PATHS.raw
KEY = None
START = dt.date(2026, 10, 1)
END = dt.date(2026, 11, 5)

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(path)

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def log(message):
    print(now(), message, flush=True)

gate = threading.Lock()
last_call = [0.0]
request_count = [0]
halt = threading.Event()

def request(endpoint, params):
    for attempt in range(4):
        if halt.is_set():
            raise RuntimeError('collection_stopped')
        with gate:
            wait = .22 - (time.monotonic() - last_call[0])
            if wait > 0:
                time.sleep(wait)
            last_call[0] = time.monotonic()
            request_count[0] += 1
        try:
            return DartClient(KEY, timeout=45, delay=0)._request(endpoint, params)
        except Exception:
            if attempt == 3:
                raise RuntimeError('network_request_failed_after_retries')
            time.sleep(2 ** attempt)

def check_status(status):
    if status in {'010', '011', '012', '020', '021', '800', '901'}:
        halt.set()
        raise RuntimeError('OpenDART_stop_status_' + status)

def list_day(day):
    cache = ROOT / 'daily_indexes' / (day + '.json')
    if cache.exists():
        return json.loads(cache.read_text())['filings']
    rows = []
    expected = None
    page = 1
    while True:
        params = dict(bgn_de=day, end_de=day, last_reprt_at='N', page_no=page,
                      page_count=100, sort='date', sort_mth='asc')
        body = request('list.json', params)
        payload = json.loads(body.decode('utf-8-sig'))
        status = str(payload.get('status', ''))
        check_status(status)
        save(ROOT / 'raw' / 'list.json' / (day + '_page_' + str(page) + '.json'),
             dict(parameters=params, retrieved_at=now(), payload=payload))
        if status == '013':
            expected = 0
            break
        if status != '000':
            raise RuntimeError('OpenDART_list_status_' + status)
        if expected is None:
            expected = int(payload['total_count'])
        rows.extend(payload.get('list', []))
        if page >= int(payload['total_page']):
            break
        page += 1
    unique = {str(r['rcept_no']): r for r in rows}
    if len(rows) != expected or len(unique) != expected:
        raise RuntimeError('pagination_count_mismatch_' + day)
    save(cache, dict(date=day, count=len(rows), retrieved_at=now(), filings=rows))
    log('INDEX ' + day + ' filings=' + str(len(rows)))
    return rows

def error_xml(body):
    try:
        root = ET.fromstring(body)
        return root.findtext('.//status'), root.findtext('.//message')
    except ET.ParseError:
        try:
            obj = json.loads(body.decode('utf-8-sig'))
            return str(obj.get('status', '')), str(obj.get('message', ''))
        except Exception:
            return None, None

def validate_archive(body):
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        if archive.testzip() is not None:
            raise ValueError('corrupt_zip')
        members = [(Path(x.filename).name, archive.read(x)) for x in archive.infolist()
                   if not x.is_dir() and x.filename.lower().endswith('.xml')]
        if not members:
            raise ValueError('zip_without_xml')
        return members

def document(row):
    receipt = str(row['rcept_no'])
    corp = str(row.get('corp_code') or 'unknown')
    folder = ROOT / 'documents' / corp
    archive_path = folder / (receipt + '.zip')
    state_path = folder / (receipt + '.status.json')
    if state_path.exists():
        prev = json.loads(state_path.read_text())
        if prev.get('state') == 'unavailable':
            return prev
    members = None
    origin = 'downloaded'
    if archive_path.exists():
        try:
            members = validate_archive(archive_path.read_bytes())
            origin = 'cached'
        except Exception:
            pass
    if members is None:
        # Reuse only valid ZIPs from the previous October 29 collection.
        old = DEV / 'runs/20261030T091922Z/documents' / corp / (receipt + '.zip')
        if old.exists():
            try:
                body = old.read_bytes()
                members = validate_archive(body)
                folder.mkdir(parents=True, exist_ok=True)
                archive_path.write_bytes(body)
                origin = 'reused_previous_run'
            except Exception:
                members = None
    if members is None:
        body = request('document.xml', {'rcept_no': receipt})
        if not body.startswith(b'PK'):
            status, message = error_xml(body)
            check_status(status)
            result = dict(receipt_no=receipt, corp_code=corp, checked_at=now(),
                          state='unavailable' if status in {'013', '014'} else 'error',
                          api_status=status, message=message or 'non_zip_response')
            save(state_path, result)
            return result
        try:
            members = validate_archive(body)
        except Exception:
            result = dict(receipt_no=receipt, state='error', reason='invalid_zip_or_missing_xml')
            save(state_path, result)
            return result
        folder.mkdir(parents=True, exist_ok=True)
        tmp = archive_path.with_suffix('.zip.tmp')
        tmp.write_bytes(body)
        tmp.replace(archive_path)
    xml_dir = folder / receipt
    xml_dir.mkdir(parents=True, exist_ok=True)
    for name, content in members:
        (xml_dir / name).write_bytes(content)
    result = dict(receipt_no=receipt, corp_code=corp, state='downloaded', origin=origin,
                  xml_count=len(members), bytes=archive_path.stat().st_size, checked_at=now())
    save(state_path, result)
    return result

def main():
    started = now()
    manifest = dict(start_date=START.isoformat(), end_date=END.isoformat(), started_at=started,
                    source='OpenDART', api_key_saved=False, state='indexing')
    save(ROOT / 'manifest.json', manifest)
    all_rows = []
    daily = {}
    day = START
    while day <= END:
        key = day.strftime('%Y%m%d')
        rows = list_day(key)
        all_rows.extend(rows)
        daily[key] = len(rows)
        day += dt.timedelta(days=1)
    unique = {str(r['rcept_no']): r for r in all_rows}
    if len(unique) != len(all_rows):
        raise RuntimeError('cross_date_duplicate_receipt')
    save(ROOT / 'filings.json', list(unique.values()))
    graph = ROOT / 'kg_records.jsonl'
    with graph.open('w') as stream:
        for row in unique.values():
            for record in filing_records([row], corp_code=str(row.get('corp_code') or ''),
                    retrieved_at=now(), list_query={'start_date':START.strftime('%Y%m%d'),'end_date':END.strftime('%Y%m%d'),'last_reprt_at':'N'}):
                stream.write(json.dumps(record, ensure_ascii=False) + '\n')
    manifest.update(state='downloading', daily_counts=daily, filing_count=len(unique),
                    company_count=len({r.get('corp_code') for r in all_rows}), updated_at=now())
    save(ROOT / 'manifest.json', manifest)
    log('ALL_INDEXES_COMPLETE filings=' + str(len(unique)))
    counts = {'downloaded':0, 'unavailable':0, 'error':0, 'reused_previous_run':0}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(document, row): row['rcept_no'] for row in unique.values()}
        for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
            try:
                result = future.result()
                counts[result['state']] += 1
                if result.get('origin') == 'reused_previous_run':
                    counts['reused_previous_run'] += 1
            except Exception as exc:
                if halt.is_set():
                    for f in futures:
                        f.cancel()
                    manifest.update(state='stopped_api_limit_or_auth', counts=counts, updated_at=now())
                    save(ROOT / 'manifest.json', manifest)
                    log('STOPPED ' + str(exc).replace(KEY, '[REDACTED]'))
                    return 2
                counts['error'] += 1
                save(ROOT / 'failures' / (str(futures[future]) + '.json'),
                     dict(receipt_no=futures[future], reason='request_or_write_failed', updated_at=now()))
            if i % 100 == 0 or i == len(futures):
                manifest.update(counts=counts, processed=i, requests_this_run=request_count[0], updated_at=now())
                save(ROOT / 'manifest.json', manifest)
                log('PROGRESS ' + str(i) + '/' + str(len(futures)) + ' ' + str(counts))
    manifest.update(state='complete' if counts['error'] == 0 else 'complete_with_errors',
                    counts=counts, finished_at=now())
    save(ROOT / 'manifest.json', manifest)
    log('FINISHED ' + str(counts))
    return 0 if counts['error'] == 0 else 2

def entry(argv=None):
    import argparse
    global ROOT, KEY, START, END
    parser=argparse.ArgumentParser(description='Resume cached date-range OpenDART collection')
    parser.add_argument('--start',required=True,help='YYYY-MM-DD')
    parser.add_argument('--end',required=True,help='YYYY-MM-DD')
    args=parser.parse_args(argv)
    START=dt.date.fromisoformat(args.start);END=dt.date.fromisoformat(args.end)
    if END<START:parser.error('end must not precede start')
    KEY=require_api_key()
    ROOT=PATHS.raw/'collections'/(START.strftime('%Y%m%d')+'_'+END.strftime('%Y%m%d'))
    try:
        return main()
    except Exception as exc:
        reason=str(exc).replace(KEY,'[REDACTED]')
        save(ROOT/'fatal_error.json',dict(state='stopped',reason=reason,at=now()))
        log('FATAL '+reason)
        return 1
    return 0

if __name__=='__main__':
    raise SystemExit(entry())
