import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from knowledge_graph.news.bigkinds import NewsStore, split_interval


def workbook(path, rows):
    """Minimal source workbook with the incorrect dimensions used by BIG KINDS."""
    from openpyxl import Workbook
    book = Workbook()
    sheet = book.active
    sheet.append(['뉴스 식별자', '일자', '언론사', '제목', '통합 분류1', '통합 분류2', '통합 분류3', '기관', 'URL', '본문'])
    for row in rows:
        sheet.append(row)
    book.save(path)
    with zipfile.ZipFile(path) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    import re
    files['xl/worksheets/sheet1.xml'] = re.sub(
        rb'<dimension ref="[^"]+"', b'<dimension ref="A1"', files['xl/worksheets/sheet1.xml'])
    with zipfile.ZipFile(path, 'w') as archive:
        for name, content in files.items():
            archive.writestr(name, content)


class BigKindsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = NewsStore(self.root)
        self.addCleanup(self.store.close)
        self.start = dt.date(2026, 1, 1)
        self.end = dt.date(2026, 1, 2)
        self.rows = [
            ['001.202601010001', '20260101', '언론사', '기사1', '정치>정치일반', None, None, '기관1', 'https://example.org/1', '본문 제외'],
            ['001.202601020001', '20260102', '언론사', '기사2', '경제>증권_증시', '국제>미국', None, None, 'https://example.org/2', '본문 제외'],
        ]

    def test_split_has_no_missing_or_overlapping_days(self):
        self.assertEqual(split_interval(self.start, self.end), [(self.start, self.start), (self.end, self.end)])
        with self.assertRaises(ValueError):
            split_interval(self.start, self.start)

    def test_exact_count_dates_and_categories_required_before_checkpoint(self):
        path = self.root / 'source.xlsx'
        workbook(path, self.rows)
        with self.assertRaises(ValueError):
            self.store.ingest(path, self.start, self.end, 3)
        self.assertFalse(self.store.covered(self.start, self.end))
        self.assertEqual(self.store.count(), 0)
        wrong = [list(self.rows[0])]
        wrong[0][4] = '스포츠>축구'
        workbook(path, wrong)
        with self.assertRaises(ValueError):
            self.store.ingest(path, self.start, self.end, 1)
        self.assertEqual(self.store.count(), 0)

    def test_replay_deduplicates_and_preserves_ids_without_body(self):
        path = self.root / 'source.xlsx'
        workbook(path, self.rows)
        self.store.ingest(path, self.start, self.end, 2)
        self.store.ingest(path, self.start, self.end, 2)
        self.assertTrue(self.store.covered(self.start, self.end))
        self.assertEqual(self.store.count(), 2)
        self.store.export_jsonl()
        records = [json.loads(line) for line in (self.root / 'articles.jsonl').read_text().splitlines()]
        self.assertEqual(records[0]['source_id'], self.rows[0][0])
        self.assertNotIn('본문 제외', json.dumps(records, ensure_ascii=False))

    def test_legacy_economic_import_does_not_complete_three_category_scope(self):
        source = self.root / 'legacy.jsonl'
        source.write_text(json.dumps({'source_id': '001.1', 'published_date': '2026-01-01', 'categories': ['경제>증권']}) + '\n')
        self.store.import_legacy([source])
        self.store.import_legacy([source])
        self.assertEqual(self.store.count(), 1)
        self.assertFalse(self.store.covered(self.start, self.end))

    def test_out_of_range_date_never_creates_a_checkpoint(self):
        path = self.root / 'wrong-date.xlsx'
        workbook(path, self.rows)
        with self.assertRaises(ValueError):
            self.store.ingest(path, self.start, self.start, 2)
        self.assertEqual(self.store.count(), 0)
        self.assertFalse(self.store.covered(self.start, self.start))

    def test_separate_category_exports_complete_scope_without_double_counting(self):
        path = self.root / 'scope.xlsx'
        for category in ('정치', '경제', '국제'):
            row = list(self.rows[0])
            row[4] = category + '>일반'
            workbook(path, [row])
            self.store.ingest(path, self.start, self.start, 1, (category,))
        self.assertEqual(self.store.count(), 1)
        self.assertTrue(self.store.covered(self.start, self.start))
        self.assertFalse(self.store.covered(self.start, self.end))


if __name__ == '__main__':
    unittest.main()
