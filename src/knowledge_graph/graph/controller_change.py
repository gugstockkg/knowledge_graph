"""Build a bounded controller-change demo from a reviewed pair of OpenDART ZIPs."""
import argparse
import hashlib
import json
import re
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from zipfile import ZipFile


class Tables(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self.tables.append([])
        elif tag == 'tr' and self.tables:
            self.row = []
        elif tag in ('td', 'th', 'te', 'tu') and self.row is not None:
            self.cell = []
        elif tag == 'br' and self.cell is not None:
            self.cell.append(' ')

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ('td', 'th', 'te', 'tu') and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split()))
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            self.tables[-1].append(self.row)
            self.row = None


def facts(html):
    parser = Tables()
    parser.feed(html)
    candidates = {'after_group_ratio': [], 'change_date': []}
    for table_no, rows in enumerate(parser.tables, 1):
        if not any(len(row) == 2 and re.fullmatch(r'(?:\d+\.\s*)?변경일자', row[0]) for row in rows):
            continue
        after_group = False
        for row_no, row in enumerate(rows, 1):
            if '최대주주등' in row:
                after_group = '변경후' in row
            if len(row) != 2:
                continue
            label, value = row
            locator = f'table/{table_no}/row/{row_no}/cell/2'
            if re.fullmatch(r'(?:\d+\.\s*)?변경일자', label):
                candidates['change_date'].append((date.fromisoformat(value).isoformat(), locator))
            if after_group and re.fullmatch(r'소유비율\s*\(\s*%\s*\)', label) and re.fullmatch(r'\d+(?:\.\d+)?', value):
                if not 0 <= float(value) <= 100:
                    raise ValueError('after_group_ratio out of range')
                candidates['after_group_ratio'].append((value, locator))
    for field, matches in candidates.items():
        if len(matches) != 1:
            raise ValueError(f'{field}: expected exactly one matching cell, found {len(matches)}')
    return {field: matches[0] for field, matches in candidates.items()}


def document(path, receipt, receipt_date):
    if not re.fullmatch(r'\d{14}', receipt):
        raise ValueError('invalid filing receipt number')
    date.fromisoformat(receipt_date)
    with ZipFile(path) as package:
        members = [m for m in package.infolist() if Path(m.filename).name == f'{receipt}.xml']
        if len(members) != 1 or members[0].file_size > 10_000_000:
            raise ValueError(f'{receipt}: expected one bounded primary XML member')
        raw = package.read(members[0])
    try:
        html = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        html = raw.decode('cp949')
    return {'receipt': receipt, 'receipt_date': receipt_date, 'sha256': hashlib.sha256(raw).hexdigest(), 'cells': facts(html)}


LOAD = '''
MERGE (c:ControllerDemoCompany {corp_code:$corp})
MERGE (e:ControllerDemoEvent {id:$event})
MERGE (e)-[:CONCERNS]->(c)
WITH e,c
UNWIND $documents AS d
MERGE (f:ControllerDemoFiling {receipt:d.receipt})
SET f.receipt_date=date(d.receipt_date)
MERGE (f)-[:IS_ABOUT]->(c)
MERGE (f)-[:REPORTS_EVENT]->(e)
MERGE (v:ControllerDemoDocument {id:d.receipt+':'+d.sha256})
SET v.sha256=d.sha256
MERGE (f)-[:HAS_DOCUMENT]->(v)
WITH e,f,v,d
UNWIND d.assertions AS item
MERGE (a:ControllerDemoAssertion {id:v.id+':'+item.field})
SET a.field=item.field,a.value=item.value,a.scope=item.scope
MERGE (a)-[:ASSERTED_IN]->(f)
MERGE (a)-[:ABOUT_EVENT]->(e)
MERGE (s:ControllerDemoEvidence {id:v.id+':'+item.locator})
SET s.locator=item.locator
MERGE (s)-[:LOCATED_IN]->(v)
MERGE (a)-[:SUPPORTED_BY]->(s)
WITH e,count(a) AS assertions
MATCH (old:ControllerDemoFiling {receipt:$original})-[:REPORTS_EVENT]->(e)<-[:REPORTS_EVENT]-(new:ControllerDemoFiling {receipt:$correction})
MERGE (new)-[:CORRECTS]->(old)
WITH old,new,assertions
MATCH (before:ControllerDemoAssertion {field:'after_group_ratio'})-[:ASSERTED_IN]->(old),
      (after:ControllerDemoAssertion {field:'after_group_ratio'})-[:ASSERTED_IN]->(new)
MERGE (after)-[:SUPERSEDES]->(before)
RETURN assertions
'''

AS_OF = '''
MATCH (a:ControllerDemoAssertion)-[:ABOUT_EVENT]->(:ControllerDemoEvent {id:$event}),
      (a)-[:ASSERTED_IN]->(f:ControllerDemoFiling),
      (a)-[:SUPPORTED_BY]->(s:ControllerDemoEvidence)-[:LOCATED_IN]->(v:ControllerDemoDocument)
WHERE f.receipt_date <= date($cutoff)
  AND NOT EXISTS {
    MATCH (a)<-[:SUPERSEDES]-(:ControllerDemoAssertion)-[:ASSERTED_IN]->(r:ControllerDemoFiling)
    WHERE r.receipt_date <= date($cutoff)
  }
RETURN a.field AS field,a.value AS value,a.scope AS scope,f.receipt AS receipt,s.locator AS locator,v.sha256 AS sha256
ORDER BY field
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('original', type=Path)
    parser.add_argument('correction', type=Path)
    parser.add_argument('--load', action='store_true', help='Write to the configured Neo4j and check both dates')
    args = parser.parse_args()
    old = document(args.original, '20261028800611', '2026-10-28')
    new = document(args.correction, '20261029800490', '2026-10-29')
    if (old['cells']['after_group_ratio'][0], new['cells']['after_group_ratio'][0]) != ('52.25', '52.39'):
        raise ValueError('source differs from the reviewed demo ratios')
    if any(d['cells']['change_date'][0] != '2026-10-27' for d in (old, new)):
        raise ValueError('source differs from the reviewed demo change date')
    for d in (old, new):
        d['assertions'] = [dict(field=field, value=value, locator=locator,
                                scope='controller_group' if field == 'after_group_ratio' else 'event')
                           for field, (value, locator) in d.pop('cells').items()
                           if d is old or field == 'after_group_ratio']
    payload = dict(corp='00105606', event='demo:' + old['receipt'], original=old['receipt'],
                   correction=new['receipt'], documents=[old, new])
    if not args.load:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    from ..storage.manage import table
    table('CREATE CONSTRAINT controller_demo_assertion_id IF NOT EXISTS FOR (a:ControllerDemoAssertion) REQUIRE a.id IS UNIQUE')
    if table(LOAD, payload) != [{'assertions': 3}]:
        raise RuntimeError('expected three source-backed assertions')
    for d, rate in ((old, '52.25'), (new, '52.39')):
        rows = table(AS_OF, dict(event=payload['event'], cutoff=d['receipt_date']))
        if {r['field']: r['value'] for r in rows} != {'after_group_ratio': rate, 'change_date': '2026-10-27'} or len(rows) != 2:
            raise RuntimeError(f'wrong as-of result for {d["receipt_date"]}: {rows}')
        print(json.dumps({'cutoff': d['receipt_date'], 'rows': rows}, ensure_ascii=False))


if __name__ == '__main__':
    main()
