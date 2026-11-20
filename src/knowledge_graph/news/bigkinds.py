"""Download BIG KINDS exports through its ordinary website without LLM calls."""
import argparse
import collections
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import sqlite3

from knowledge_graph.config import get_paths


CATEGORIES = ('정치', '경제', '국제')
CATEGORY_IDS = {'정치': '001000000', '경제': '002000000', '국제': '005000000'}
SEARCH_URL = 'https://www.bigkinds.or.kr/v2/news/search.do'


def split_interval(start, end):
    if start >= end:
        raise ValueError('A single day must be split by category instead')
    middle = start + (end - start) // 2
    return [(start, middle), (middle + dt.timedelta(days=1), end)]


class NewsStore:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.root / 'news.sqlite3')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS articles (
                source_id TEXT PRIMARY KEY, published_date TEXT NOT NULL, payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS batches (
                start_date TEXT NOT NULL, end_date TEXT NOT NULL, scope TEXT NOT NULL,
                expected INTEGER NOT NULL, filename TEXT, sha256 TEXT,
                PRIMARY KEY (start_date, end_date, scope)
            );
        ''')

    def close(self):
        self.db.close()

    def count(self):
        return self.db.execute('SELECT COUNT(*) FROM articles').fetchone()[0]

    def covered(self, start, end, categories=CATEGORIES):
        batches = self.db.execute('SELECT start_date,end_date,scope FROM batches ORDER BY start_date').fetchall()
        for category in categories:
            cursor = start
            for first, last, scope in batches:
                if category not in scope.split(','):
                    continue
                first, last = dt.date.fromisoformat(first), dt.date.fromisoformat(last)
                if first <= cursor <= last:
                    cursor = last + dt.timedelta(days=1)
            if cursor <= end:
                return False
        return True

    def import_legacy(self, paths):
        with self.db:
            for path in paths:
                with Path(path).open(encoding='utf-8') as stream:
                    for line in stream:
                        record = json.loads(line)
                        self.db.execute('INSERT OR IGNORE INTO articles VALUES (?,?,?)',
                                        (record['source_id'], record['published_date'], json.dumps(record, ensure_ascii=False)))

    def ingest(self, path, start, end, expected, categories=CATEGORIES):
        from openpyxl import load_workbook
        book = load_workbook(path, read_only=True, data_only=True)
        records = {}
        try:
            sheet = book.active
            sheet.reset_dimensions()
            rows = sheet.values
            header = {name: i for i, name in enumerate(next(rows))}
            required = ('뉴스 식별자', '일자', '언론사', '제목', '통합 분류1', '통합 분류2', '통합 분류3', 'URL')
            if any(name not in header for name in required):
                raise ValueError('Unexpected export columns')
            for row in rows:
                if not any(row):
                    continue
                values = {name: row[index] if index < len(row) else None for name, index in header.items()}
                source_id = values['뉴스 식별자']
                if not isinstance(source_id, str) or not source_id or source_id in records:
                    raise ValueError('Missing, imprecise or duplicate article identifier')
                value = values['일자']
                day = value.date() if isinstance(value, dt.datetime) else value
                if not isinstance(day, dt.date):
                    day = dt.datetime.strptime(str(day), '%Y%m%d').date()
                article_categories = [values[f'통합 분류{i}'] for i in (1, 2, 3) if values[f'통합 분류{i}']]
                if not start <= day <= end:
                    raise ValueError('Article date is outside the requested interval')
                if not any(re.split(r'[>／/]', category)[0].strip() in categories for category in article_categories):
                    raise ValueError('Article classification is outside the requested scope')
                records[source_id] = dict(source='BIG KINDS', source_id=source_id,
                    published_date=day.isoformat(), date_timezone='Asia/Seoul',
                    publisher=values['언론사'], title=values['제목'], url=values['URL'],
                    categories=article_categories,
                    organization_mentions=(values.get('기관') or '').split(',') if values.get('기관') else [])
        finally:
            book.close()
        if len(records) != expected:
            raise ValueError(f'Incomplete export: expected {expected}, found {len(records)}')
        digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        with self.db:
            for record in records.values():
                self.db.execute('INSERT OR IGNORE INTO articles VALUES (?,?,?)',
                                (record['source_id'], record['published_date'], json.dumps(record, ensure_ascii=False)))
            self.db.execute('INSERT OR REPLACE INTO batches VALUES (?,?,?,?,?,?)',
                            (start.isoformat(), end.isoformat(), ','.join(sorted(categories)), expected,
                             str(Path(path).resolve()), digest))
        return len(records)

    def mark_empty(self, start, end, categories):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO batches VALUES (?,?,?,?,?,?)',
                            (start.isoformat(), end.isoformat(), ','.join(sorted(categories)), 0, None, None))

    def export_jsonl(self):
        target = self.root / 'articles.jsonl'
        temporary = target.with_suffix('.jsonl.tmp')
        with temporary.open('w', encoding='utf-8') as stream:
            for payload, in self.db.execute('SELECT payload FROM articles ORDER BY published_date,source_id'):
                stream.write(payload + '\n')
        temporary.replace(target)


class Website:
    def __init__(self, page, status, timeout):
        self.page = page
        self.status = status
        self.timeout = timeout
        self.page.set_default_timeout(15000)
        self.page.set_default_navigation_timeout(90000)
        self.alerts = []
        self.page.on('dialog', self.dismiss_dialog)

    def dismiss_dialog(self, dialog):
        self.alerts.append(dialog.type)
        dialog.dismiss()

    def load(self, url):
        from playwright.sync_api import TimeoutError as BrowserTimeout
        for attempt in range(3):
            try:
                self.page.goto(url, wait_until='domcontentloaded')
                self.page.get_by_role('link', name='MEMBERSHIP', exact=True).wait_for(state='visible')
                # This legacy site binds controls after they become visible.
                self.page.wait_for_timeout(1500)
                return
            except BrowserTimeout:
                if self.page.get_by_role('link', name='MEMBERSHIP', exact=True).is_visible():
                    self.page.wait_for_timeout(1500)
                    return
                if attempt == 2:
                    raise
                self.status('navigation_retry', attempt=attempt + 1)

    def close_announcements(self):
        for _ in range(5):
            buttons = self.page.get_by_role('button', name='Close', exact=True)
            if not buttons.count():
                return
            buttons.last.click()

    def login(self):
        while True:
            if self.page.is_closed():
                raise RuntimeError('Collection browser was closed')
            if self.page.locator('#login-btn').is_visible():
                self.page.wait_for_timeout(3000)
                continue
            self.close_announcements()
            membership = self.page.get_by_role('link', name='MEMBERSHIP', exact=True)
            membership.click()
            if self.page.get_by_role('link', name='로그아웃', exact=True).is_visible():
                membership.click()
                return
            self.status('waiting_for_login', message='전용 Chrome 창에서 빅카인즈 로그인 필요')
            self.page.get_by_role('link', name='로그인', exact=True).click()
            self.page.wait_for_timeout(3000)

    def pick_date(self, field, day):
        element = self.page.locator('#' + field)
        element.fill(day.isoformat())
        element.press('Tab')
        element.click()
        self.page.locator(f'#ui-datepicker-div td[data-year="{day.year}"][data-month="{day.month - 1}"]').get_by_role(
            'link', name=str(day.day), exact=True).click()

    def search(self, start, end, categories):
        # A fresh document resets datepicker bounds retained by the site's reset button.
        self.load(SEARCH_URL)
        self.login()
        self.alerts.clear()
        section = self.page.locator('#collapse-step-1-body')
        if not section.is_visible():
            self.page.locator('#collapse-step-1').click()
        if not self.page.locator('#search-begin-date').is_visible():
            section.get_by_role('button', name='기간', exact=True).click()
        self.pick_date('search-begin-date', start)
        self.pick_date('search-end-date', end)
        section.get_by_role('button', name='통합 분류', exact=True).click()
        for category in categories:
            self.page.locator('#srch-tab3').get_by_text(category, exact=True).click()
        for category in categories:
            if not self.page.locator('#category_' + CATEGORY_IDS[category]).count():
                raise ValueError('Required category was not selected')
        actual = [self.page.locator('#' + name).input_value() for name in ('search-begin-date', 'search-end-date')]
        if actual != [start.isoformat(), end.isoformat()]:
            raise ValueError('Date selection changed unexpectedly')
        section.get_by_role('button', name='적용하기', exact=True).click()
        results = self.page.locator('#collapse-step-2-body')
        results.wait_for(state='visible', timeout=30000)
        results.get_by_text('뉴스 데이터를 검색하고 있습니다.', exact=True).wait_for(state='hidden', timeout=120000)
        actual = [self.page.locator('#' + name).input_value() for name in ('search-begin-date', 'search-end-date')]
        if self.alerts or actual != [start.isoformat(), end.isoformat()]:
            raise ValueError('The website did not retain the requested dates')
        text = results.get_by_role('heading', name=re.compile(r'뉴스 검색 결과.*건입니다')).inner_text()
        count = re.search(r'([\d,]+)\s*건', text)
        if count is None:
            raise ValueError('Search result count is missing')
        return int(count.group(1).replace(',', ''))

    def download(self, target):
        self.page.locator('#collapse-step-3').click()
        button = self.page.get_by_role('button', name='엑셀 다운로드', exact=True)
        with self.page.expect_download(timeout=self.timeout * 1000) as event:
            button.click()
        download = event.value
        temporary = target.with_suffix('.xlsx.part')
        download.save_as(temporary)
        temporary.replace(target)


def collect(args):
    from playwright.sync_api import sync_playwright, TimeoutError as BrowserTimeout
    paths = get_paths()
    root = paths.data / 'news' / 'bigkinds' / f'{args.start}_{args.end}_politics_economy_international'
    runtime = paths.runtime / 'bigkinds'
    runtime.mkdir(parents=True, exist_ok=True)
    runtime.chmod(0o700)
    root.mkdir(parents=True, exist_ok=True)
    (root / 'raw').mkdir(exist_ok=True)
    status_path = paths.artifacts / 'ingestion' / 'bigkinds_status.json'
    status_path.parent.mkdir(parents=True, exist_ok=True)
    store = NewsStore(root)

    def status(state, **details):
        payload = dict(state=state, pid=os.getpid(), updated_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                       start=args.start, end=args.end, categories=list(CATEGORIES),
                       verified_unique_articles=store.count(), data_dir=str(root), **details)
        temp = status_path.with_suffix('.json.tmp')
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
        temp.replace(status_path)
        print(json.dumps(payload, ensure_ascii=False), flush=True)

    with (runtime / 'collector.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            store.close()
            raise RuntimeError('A BIG KINDS collector is already running')
        try:
            for old in sorted((paths.data / 'news' / 'bigkinds').glob('*/monthly_export_plan.json')):
                manifest = json.loads(old.read_text())
                for export in manifest.get('verified_exports', []):
                    raw = old.parent / export['raw']
                    expected_hash = export.get('sha256')
                    if raw.exists() and hashlib.sha256(raw.read_bytes()).hexdigest() == expected_hash:
                        try:
                            store.ingest(raw, dt.date.fromisoformat(export['start']), dt.date.fromisoformat(export['end']),
                                         export['verified_rows'], tuple(export.get('search_categories', ['경제'])))
                        except ValueError:
                            store.import_legacy([old.parent / export['metadata']])
            status('starting')
            with sync_playwright() as playwright:
                context = playwright.chromium.launch_persistent_context(str(runtime / 'profile'), channel='chrome',
                    headless=args.headless, accept_downloads=True, viewport={'width': 1280, 'height': 900})
                try:
                    page = context.pages[0] if context.pages else context.new_page()
                    if not args.headless:
                        page.bring_to_front()
                    site = Website(page, status, args.download_timeout)
                    status('loading_website')
                    site.load('https://www.bigkinds.or.kr/')
                    site.login()
                    queue = collections.deque()
                    first = dt.date.fromisoformat(args.start)
                    end = dt.date.fromisoformat(args.end)
                    while first <= end:
                        next_month = (first.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
                        last = min(end, next_month - dt.timedelta(days=1))
                        queue.append((first, last, CATEGORIES))
                        first = last + dt.timedelta(days=1)
                    verified_batches = 0
                    while queue:
                        start, end, categories = queue.popleft()
                        if store.covered(start, end, categories):
                            continue
                        for attempt in range(1, 4):
                            try:
                                status('searching', current_start=start.isoformat(), current_end=end.isoformat(),
                                       current_categories=list(categories), attempt=attempt, queued_intervals=len(queue))
                                expected = site.search(start, end, categories)
                                if expected > 20000:
                                    raise OverflowError('Split at the 20,000 article limit')
                                if expected == 0:
                                    store.mark_empty(start, end, categories)
                                else:
                                    status('downloading', current_start=start.isoformat(), current_end=end.isoformat(),
                                           current_categories=list(categories), expected_articles=expected)
                                    suffix = '-'.join(CATEGORY_IDS[c] for c in categories)
                                    target = root / 'raw' / f'{start}_{end}_{suffix}.xlsx'
                                    if target.exists():
                                        try:
                                            store.ingest(target, start, end, expected, categories)
                                        except (ValueError, OSError):
                                            site.download(target)
                                            store.ingest(target, start, end, expected, categories)
                                    else:
                                        site.download(target)
                                        store.ingest(target, start, end, expected, categories)
                                verified_batches += 1
                                status('batch_verified', current_start=start.isoformat(), current_end=end.isoformat(),
                                       current_categories=list(categories), expected_articles=expected,
                                       verified_batches_this_run=verified_batches)
                                break
                            except (OverflowError, BrowserTimeout):
                                if start < end:
                                    queue.extendleft(reversed([(a, b, categories) for a, b in split_interval(start, end)]))
                                    break
                                if len(categories) > 1:
                                    queue.extendleft(reversed([(start, end, (c,)) for c in categories]))
                                    break
                                if attempt == 3:
                                    raise RuntimeError('A one-day, one-category export repeatedly failed') from None
                                page.wait_for_timeout(10000)
                            except ValueError:
                                if attempt == 3:
                                    raise
                                page.wait_for_timeout(5000)
                    store.export_jsonl()
                    status('complete', output=str(root / 'articles.jsonl'))
                finally:
                    context.close()
        except KeyboardInterrupt:
            status('stopped')
        except Exception as error:
            status('needs_attention', error_type=type(error).__name__)
            raise RuntimeError('News collector needs attention: ' + type(error).__name__) from None
        finally:
            store.close()


def main():
    parser = argparse.ArgumentParser(description='Resumable BIG KINDS website exports without LLM calls')
    parser.add_argument('--start', required=True)
    parser.add_argument('--end', required=True)
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--download-timeout', type=int, default=180)
    args = parser.parse_args()
    start, end = dt.date.fromisoformat(args.start), dt.date.fromisoformat(args.end)
    if start > end or args.download_timeout < 1:
        parser.error('Invalid interval or timeout')
    os.umask(0o077)
    def stop(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    collect(args)


if __name__ == '__main__':
    main()
