"""Daily/backfill OpenDART ingestion. No LLM calls or third-party Python packages.

API contract: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019001
S3 checksum: https://docs.aws.amazon.com/cli/latest/reference/s3/cp.html
Run with: python -m knowledge_graph.ingestion.batch --help
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import datetime as dt
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import time
import zipfile
from zoneinfo import ZoneInfo

from .client import DartClient, DartApiError

KST = ZoneInfo('Asia/Seoul')


class BatchError(RuntimeError):
    pass


class Paused(BatchError):
    """Temporary stop; systemd retries without declaring the date complete."""


class AuthFailure(BatchError):
    """Requires operator intervention; never retry an invalid API key forever."""


def now_kst():
    return dt.datetime.now(KST)


def atomic_write(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_bytes(body)
    tmp.replace(path)


def write_json(path, value):
    atomic_write(path, (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode())


def valid_zip(path):
    try:
        with zipfile.ZipFile(path) as z:
            return z.testzip() is None and any(n.lower().endswith('.xml') for n in z.namelist())
    except (OSError, zipfile.BadZipFile, EOFError):
        return False


@contextmanager
def collection_lock(root):
    root.mkdir(parents=True, exist_ok=True)
    with (root/'collector.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Paused('collector_busy') from None
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def daily_start(today, last_success):
    lookback = today - dt.timedelta(days=3)
    return min(lookback, dt.date.fromisoformat(last_success) + dt.timedelta(days=1)) if last_success else lookback


class S3Sink:
    def __init__(self, prefix, region):
        if not re.fullmatch(r's3://[a-z0-9][a-z0-9.-]+/[A-Za-z0-9/_=-]*/?', prefix):
            raise BatchError('invalid_s3_prefix')
        self.prefix = prefix.rstrip('/')
        self.region = region

    def put(self, path, key):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        # CLI computes/sends checksum; S3 verifies it. ETag is not assumed to be MD5.
        result = subprocess.run(['aws', 's3', 'cp', str(path), self.prefix+'/'+key,
                                 '--region', self.region, '--only-show-errors',
                                 '--checksum-algorithm', 'SHA256', '--metadata', 'sha256='+digest],
                                capture_output=True, timeout=180)
        if result.returncode:
            raise BatchError('S3_upload_failed')


class Collector:
    def __init__(self, root, client, sink=None, *, now=now_kst, daily_limit=12000,
                 run_limit=1000, max_seconds=1200):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.client, self.sink, self.now = client, sink, now
        self.daily_limit, self.run_limit = daily_limit, run_limit
        self.calls = 0
        self.deadline = time.monotonic() + max_seconds
        self.db = sqlite3.connect(self.root/'state.sqlite3')
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS usage (day TEXT PRIMARY KEY, requests INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS days (day TEXT PRIMARY KEY, state TEXT NOT NULL,
              count INTEGER NOT NULL, checked TEXT NOT NULL, next_review TEXT);
            CREATE TABLE IF NOT EXISTS docs (receipt TEXT PRIMARY KEY, day TEXT NOT NULL,
              state TEXT NOT NULL, sha256 TEXT, bytes INTEGER, checked TEXT NOT NULL,
              first_seen TEXT NOT NULL, uploaded INTEGER NOT NULL DEFAULT 0);
        ''')
        self.db.commit()

    def get(self, key):
        row = self.db.execute('SELECT value FROM kv WHERE key=?', (key,)).fetchone()
        return row['value'] if row else None

    def set(self, key, value):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO kv VALUES (?,?)', (key, value))

    def check_time(self):
        if time.monotonic() >= self.deadline:
            raise Paused('run_time_budget')

    def call(self, method, *args):
        for attempt in range(3):
            self.check_time()
            stamp = self.now()
            cooldown = self.get('cooldown_until')
            if cooldown and stamp < dt.datetime.fromisoformat(cooldown):
                raise Paused('API_cooldown_until_'+cooldown)
            day = stamp.date().isoformat()
            used = self.db.execute('SELECT requests FROM usage WHERE day=?', (day,)).fetchone()
            if (used and used[0] >= self.daily_limit) or self.calls >= self.run_limit:
                raise Paused('request_budget')
            with self.db:
                self.db.execute('INSERT INTO usage VALUES (?,1) ON CONFLICT(day) DO UPDATE SET requests=requests+1', (day,))
            self.calls += 1
            try:
                return method(*args)
            except DartApiError as exc:
                if exc.status == '020':
                    tomorrow = stamp.date() + dt.timedelta(days=1)
                    self.set('cooldown_until', dt.datetime.combine(tomorrow, dt.time(0, 5), KST).isoformat())
                    raise Paused('OpenDART_020_quota') from None
                if exc.status in {'010', '011', '012', '901'}:
                    raise AuthFailure('OpenDART_auth_'+exc.status) from None
                if exc.status is not None:
                    raise
            except (OSError, TimeoutError):
                pass
            if attempt < 2:
                time.sleep(2**attempt)
        raise BatchError('OpenDART_network_failed_after_retries')

    def index(self, day, refresh):
        compact = day.strftime('%Y%m%d')
        path = self.root/'indexes'/f'partition_day={day.isoformat()}'/'index.json'
        if path.exists() and not refresh:
            return json.loads(path.read_text())['filings']
        rows, page, expected = [], 1, None
        while True:
            data = self.call(self.client.get_json, 'list.json', dict(bgn_de=compact, end_de=compact,
                             last_reprt_at='N', page_no=page, page_count=100, sort='date', sort_mth='asc'))
            if data.get('status') == '013':
                if page != 1:
                    raise BatchError('unexpected_empty_pagination')
                expected = 0
                break
            if expected is None:
                expected = int(data['total_count'])
            elif int(data['total_count']) != expected:
                raise BatchError('index_changed_during_pagination')
            rows.extend(data.get('list', []))
            if page >= int(data['total_page']):
                break
            page += 1
        if len(rows) != expected or len({r.get('rcept_no') for r in rows}) != expected:
            raise BatchError('pagination_count_mismatch')
        for row in rows:
            if not re.fullmatch(r'\d{14}', str(row.get('rcept_no', ''))) or row.get('rcept_dt') != compact:
                raise BatchError('invalid_receipt_identity_or_date')
            if not re.fullmatch(r'\d{8}', str(row.get('corp_code', ''))):
                raise BatchError('invalid_corp_code')
        write_json(path, dict(receipt_date=day.isoformat(), retrieved_at=self.now().isoformat(), filings=rows))
        return rows

    def document(self, row, day):
        receipt = row['rcept_no']
        key = f'documents/partition_day={day.isoformat()}/{receipt}.zip'
        path = self.root/key
        prev = self.db.execute('SELECT * FROM docs WHERE receipt=?', (receipt,)).fetchone()
        stamp = self.now().isoformat()
        if prev and prev['day'] != day.isoformat():
            raise BatchError('receipt_date_conflict')
        first_seen = prev['first_seen'] if prev else stamp
        if prev and prev['state'] == 'unavailable' and self.now()-dt.datetime.fromisoformat(prev['checked']) < dt.timedelta(days=7):
            return dict(row, document_state='unavailable', first_seen_at=first_seen, time_precision='date')
        if not valid_zip(path):
            if shutil.disk_usage(self.root).free < 1024**3:
                raise BatchError('disk_free_below_1GiB')
            try:
                body = self.call(self.client.download_document, receipt)
            except DartApiError as exc:
                if exc.status not in {'013', '014'}:
                    raise BatchError('OpenDART_document_error_'+str(exc.status or 'network')) from None
                with self.db:
                    self.db.execute('INSERT OR REPLACE INTO docs VALUES (?,?,?,?,?,?,?,?)',
                                    (receipt, day.isoformat(), 'unavailable', None, 0, stamp, first_seen, 0,))
                return dict(row, document_state='unavailable', first_seen_at=first_seen, time_precision='date')
            if not valid_zip(io.BytesIO(body)):
                raise BatchError('invalid_document_zip')
            atomic_write(path, body)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        uploaded = bool(prev and prev['uploaded'] and prev['sha256'] == digest)
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO docs VALUES (?,?,?,?,?,?,?,?)',
                            (receipt, day.isoformat(), 'downloaded', digest, path.stat().st_size,
                             stamp, first_seen, int(uploaded)))
        if self.sink and not uploaded:
            try:
                self.sink.put(path, key)
            except Exception:
                raise BatchError('S3_document_upload_failed') from None
            with self.db:
                self.db.execute('UPDATE docs SET uploaded=1 WHERE receipt=?', (receipt,))
        return dict(row, document_state='downloaded', document_key=key, sha256=digest,
                    bytes=path.stat().st_size, first_seen_at=first_seen, time_precision='date')

    def collect_day(self, day, refresh=False):
        self.check_time()
        if day >= self.now().date():
            raise BatchError('only_closed_KST_dates_allowed')
        old = self.db.execute('SELECT * FROM days WHERE day=?', (day.isoformat(),)).fetchone()
        if old and old['state'] == 'complete' and not refresh:
            if not old['next_review'] or self.now() < dt.datetime.fromisoformat(old['next_review']):
                return True
        # Demote before refreshing; a failed refresh must not retain a complete marker.
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO days VALUES (?,?,?,?,?)',
                            (day.isoformat(), 'pending', 0, self.now().isoformat(), None))
        rows = self.index(day, refresh)
        results = []
        for row in rows:
            self.check_time()
            results.append(self.document(row, day))
        key = f'filings/partition_day={day.isoformat()}/filings.jsonl'
        path = self.root/key
        atomic_write(path, ''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in results).encode())
        if self.sink:
            try:
                self.sink.put(path, key)
            except Exception:
                raise BatchError('S3_index_upload_failed') from None
        counts = {s: sum(r['document_state'] == s for r in results) for s in ['downloaded', 'unavailable']}
        review = (self.now()+dt.timedelta(days=7)).isoformat() if counts['unavailable'] else None
        manifest = dict(receipt_date=day.isoformat(), state='complete', filing_count=len(rows),
                        counts=counts, checked_at=self.now().isoformat(), next_review=review,
                        s3_upload_enabled=self.sink is not None)
        mkey = f'_manifests/partition_day={day.isoformat()}/manifest.json'
        write_json(self.root/mkey, manifest)
        if self.sink:
            try:
                self.sink.put(self.root/mkey, mkey)
            except Exception:
                raise BatchError('S3_manifest_upload_failed') from None
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO days VALUES (?,?,?,?,?)',
                            (day.isoformat(), 'complete', len(rows), self.now().isoformat(), review))
        print(json.dumps(manifest, ensure_ascii=False), flush=True)
        return True

    def daily(self):
        today = self.now().date()
        day = daily_start(today, self.get('last_daily_success'))
        while day < today:
            self.collect_day(day, refresh=day >= today-dt.timedelta(days=3))
            last = self.get('last_daily_success')
            if last is None or day.isoformat() > last:
                self.set('last_daily_success', day.isoformat())
            day += dt.timedelta(days=1)

    def backfill(self, start, end):
        if end < start or end >= self.now().date():
            raise BatchError('invalid_closed_date_range')
        day = start
        while day <= end:
            self.collect_day(day)
            day += dt.timedelta(days=1)

    def summary(self):
        return dict(days=[dict(r) for r in self.db.execute('SELECT state,COUNT(*) AS count FROM days GROUP BY state')],
                    documents=[dict(r) for r in self.db.execute('SELECT state,COUNT(*) AS count,SUM(bytes) AS bytes FROM docs GROUP BY state')],
                    usage=[dict(r) for r in self.db.execute('SELECT * FROM usage ORDER BY day DESC LIMIT 7')],
                    last_daily_success=self.get('last_daily_success'), cooldown_until=self.get('cooldown_until'))


def entry(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['daily', 'backfill', 'status'])
    parser.add_argument('--root', type=Path, default=Path(os.environ.get('OPENDART_DATA_DIR', '/var/lib/opendart')))
    parser.add_argument('--start', type=dt.date.fromisoformat)
    parser.add_argument('--end', type=dt.date.fromisoformat)
    parser.add_argument('--window', help='systemd instance: YYYY-MM-DD_YYYY-MM-DD')
    parser.add_argument('--prioritize-daily', action='store_true')
    parser.add_argument('--s3-prefix', default=os.environ.get('OPENDART_S3_PREFIX'))
    parser.add_argument('--region', default=os.environ.get('AWS_DEFAULT_REGION', 'ap-southeast-2'))
    parser.add_argument('--max-requests', type=int, default=1000)
    parser.add_argument('--daily-limit', type=int, default=12000)
    parser.add_argument('--max-seconds', type=int, default=1200)
    args = parser.parse_args(argv)
    if args.window:
        try:
            if args.start or args.end or not re.fullmatch(r'\d{4}-\d{2}-\d{2}_\d{4}-\d{2}-\d{2}', args.window):
                raise ValueError
            args.start, args.end = map(dt.date.fromisoformat, args.window.split('_'))
        except ValueError:
            parser.error('invalid window; use YYYY-MM-DD_YYYY-MM-DD without --start/--end')
    if args.mode == 'backfill' and (not args.start or not args.end):
        parser.error('backfill requires --start and --end')
    if min(args.max_requests, args.daily_limit, args.max_seconds) < 1:
        parser.error('budgets must be positive')
    try:
        with collection_lock(args.root):
            key = os.environ.get('OPENDART_API_KEY', '').strip()
            if args.mode != 'status' and not re.fullmatch('[a-fA-F0-9]{40}', key):
                raise AuthFailure('OPENDART_API_KEY_missing_or_invalid_format')
            sink = S3Sink(args.s3_prefix, args.region) if args.s3_prefix else None
            worker = Collector(args.root, DartClient(key, timeout=30, delay=.3) if key else None, sink,
                               daily_limit=args.daily_limit, run_limit=args.max_requests, max_seconds=args.max_seconds)
            if args.mode == 'daily':
                worker.daily()
            elif args.mode == 'backfill':
                if args.prioritize_daily:
                    worker.daily()
                worker.backfill(args.start, args.end)
            print(json.dumps(dict(state='complete', summary=worker.summary()), ensure_ascii=False), flush=True)
            worker.db.close()
            return 0
    except AuthFailure as exc:
        print(json.dumps(dict(state='auth_error', reason=str(exc))), flush=True)
        return 78
    except Paused as exc:
        print(json.dumps(dict(state='paused', reason=str(exc))), flush=True)
        return 75
    except Exception as exc:
        # Deliberately omit exception text: upstream URL errors may contain secrets.
        print(json.dumps(dict(state='failed', reason=type(exc).__name__)), flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(entry())
