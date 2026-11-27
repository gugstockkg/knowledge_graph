import unittest

from knowledge_graph.ingestion.economic_events import contract_amendment, row_cells


class ContractAmendmentTests(unittest.TestCase):
    def setUp(self):
        self.raw = """<table>
        <tr><td>2. 정정관련 공시서류제출일</td><td>2026.01.19</td></tr>
        <tr><td>정정항목</td><td>정정전</td><td>정정후</td></tr>
        <tr><td>5. 계약기간 - 종료일</td><td>2026-03-01</td><td>2026-07-15</td></tr>
        <tr><td>-</td></tr>
        <tr><td>1. 판매ㆍ공급계약 내용</td><td>검사장비 공급계약</td></tr>
        <tr><td>2. 계약내역</td><td>계약금액(원)</td><td>1000</td></tr>
        <tr><td>계약(수주)일자</td><td>2026-01-16</td></tr>
        </table>"""
        self.row = dict(rcept_dt="20260224", corp_code="12345678", report_nm="[기재정정]단일판매ㆍ공급계약체결")
        self.origin = "20260119900439"
        self.receipt = "20260224900460"
        self.lineage = {self.origin: ("12345678", "2026-01-19", self.origin)}
        self.signature = ("12345678", "2026-01-19", ("검사장비공급계약", "2026-01-16"))

    def test_partial_amendment_preserves_only_the_changed_field(self):
        amendment, _ = contract_amendment(
            self.row, self.receipt, self.raw, row_cells(self.raw),
            self.lineage, {self.signature: [self.origin]},
        )
        self.assertEqual(amendment["contract_receipt"], self.origin)
        self.assertEqual(amendment["known_on"], "2026-02-24")
        self.assertEqual(amendment["changes"], {"end_date": "2026-07-15"})

    def test_ambiguous_or_same_day_versions_cannot_be_linked(self):
        for row, candidates in [
            (self.row, [self.origin, "20260119900440"]),
            (dict(self.row, rcept_dt="20260119"), [self.origin]),
        ]:
            with self.subTest(row=row, candidates=candidates), self.assertRaises(ValueError):
                contract_amendment(row, self.receipt, self.raw, row_cells(self.raw),
                                   self.lineage, {self.signature: candidates})
