import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from knowledge_graph.ingestion.trace_contracts import buyer_cell, collect


class TraceContractTests(unittest.TestCase):
    def test_buyer_identity_from_later_filing_is_not_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            collection = Path(tmp)
            receipt = "20260105000001"
            rows = [
                dict(rcept_no=receipt, rcept_dt="20260105", corp_cls="Y",
                     corp_code="00000001", corp_name="공급사", stock_code="123456",
                     report_nm="단일판매ㆍ공급계약체결"),
                dict(rcept_no="20260106000001", rcept_dt="20260106", corp_cls="Y",
                     corp_code="00000002", corp_name="구매사", stock_code="234567",
                     report_nm="참고 공시"),
            ]
            index = collection / "filings.json"
            index.write_text(json.dumps(rows))
            archive = collection / "documents" / "00000001" / f"{receipt}.zip"
            archive.parent.mkdir(parents=True)
            with ZipFile(archive, "w") as package:
                package.writestr(f"{receipt}.xml", """<table>
                  <tr><td>1. 판매ㆍ공급계약 내용</td><td>부품 공급</td></tr>
                  <tr><td>2. 계약상대방</td><td>구매사 주식회사</td></tr>
                </table>""")
            events, counts = collect([collection], "2026-01-01", "2026-01-31")
            self.assertEqual(counts["unresolved_buyer"], 1)
            self.assertIsNone(events[0]["buyer"])
            self.assertEqual(events[0]["buyer_evidence"]["line"], 3)

            rows[1].update(rcept_dt="20260102", rcept_no="20260102000001")
            index.write_text(json.dumps(rows))
            events, counts = collect([collection], "2026-01-01", "2026-01-31")
            self.assertEqual(counts["matched_by_filing_date"], 1)
            self.assertEqual(events[0]["buyer"]["receipt"], "20260102000001")

    def test_multiple_counterparty_cells_are_returned_for_review(self):
        xml = """<table>
        <tr><td>계약상대방</td><td>회사 A</td></tr>
        <tr><td>계약상대</td><td>회사 B</td></tr>
        </table>"""
        self.assertEqual(buyer_cell(xml), [("회사 A", 2), ("회사 B", 3)])
