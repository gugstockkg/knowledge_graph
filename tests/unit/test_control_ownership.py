import json
import unittest

from knowledge_graph.config import get_paths
from knowledge_graph.ingestion.control_ownership import build, filing_type


class ControlOwnershipTest(unittest.TestCase):
    def test_titles(self):
        self.assertEqual(filing_type("[기재정정] 최대주주 변경"), ("controller", True))
        self.assertEqual(
            filing_type("주식등의대량보유상황보고서(약식)"), ("holding", False)
        )
        self.assertIsNone(filing_type("최대주주 변경을 수반하는 주식양수도 계약 체결"))
        self.assertIsNone(filing_type("[첨부정정] 주주총회 결과"))

    def test_reviewed_open_dart_cases(self):
        expected = {
            ("20260310902022", "20260310002731"): "same_transaction",
            ("20260310902022", "20260310002993"): "same_transaction",
            ("20260310902022", "20260311901202"): "unresolved",
            ("20260324901691", "20260325001437"): "same_transaction",
            ("20260324901691", "20260325001434"): "same_transaction",
            ("20260422900886", "20260422000596"): "same_transaction",
            ("20260422900886", "20260420000502"): "separate_event",
            ("20260527800891", "20260527000620"): "same_transaction",
            ("20260527800891", "20260626000489"): "separate_event",
            ("20261028800611", "20261029000387"): "quantity_support",
            ("20261028800611", "20261026000303"): "unresolved",
        }
        corrections = {
            "20260311901202",
            "20260325900570",
            "20260424900671",
            "20260528800324",
            "20261029800490",
        }
        collection = get_paths().raw / "collections" / "20260101_20261105"
        index = collection / "filings.json"
        if not index.is_file():
            self.skipTest("Local OpenDART collection is unavailable")
        receipts = {receipt for pair in expected for receipt in pair} | corrections
        rows = [r for r in json.loads(index.read_text()) if r["rcept_no"] in receipts]
        documents = [
            (r, collection / "documents" / r["corp_code"] / (r["rcept_no"] + ".zip"))
            for r in rows
        ]
        if len(documents) != len(receipts) or any(
            not path.is_file() for _, path in documents
        ):
            self.skipTest("Reviewed OpenDART archives are unavailable")
        result = build(documents, window_days=35)
        actual = {
            (r["event_receipt"], r["related_receipt"]): r["classification"]
            for r in result["links"]
        }
        for pair, label in expected.items():
            with self.subTest(pair=pair):
                self.assertEqual(actual[pair], label)
        self.assertEqual(len(result["events"]), 5)
        self.assertEqual(sum(r["status"] == "linked" for r in result["corrections"]), 5)
        self.assertTrue(all(link["evidence"] for link in result["links"]))

    def test_extracts_only_correction_table_and_reads_both_controller_phases(self):
        from knowledge_graph.ingestion.control_ownership import (
            LocatedRows,
            fields_from_rows,
        )

        parser = LocatedRows()
        parser.feed("""
        <table><tr><td>정정항목</td><td>정정 전</td><td>정정 후</td></tr>
        <tr><td>지분율</td><td>30</td><td>40</td></tr></table>
        <table><tr><td>1. 변경내용</td><td>변경전</td><td>최대주주등</td><td>A</td></tr>
        <tr><td>소유주식수(주)</td><td>3,000</td></tr>
        <tr><td>변경후</td><td>최대주주등</td><td>B</td></tr>
        <tr><td>소유주식수(주)</td><td>4,000</td></tr></table>""")
        facts = fields_from_rows(
            zip(parser.row_tables, parser.rows), "controller", True
        )
        self.assertEqual(
            [
                (f["before"], f["after"])
                for f in facts
                if f["field"] == "correction_item"
            ],
            [("30", "40")],
        )
        self.assertEqual(
            [(f["phase"], f["value"]) for f in facts if f["field"] == "shares"],
            [("before", "3,000"), ("after", "4,000")],
        )

    def test_detailed_rule_uses_trade_date_and_counterparty(self):
        from knowledge_graph.ingestion.control_ownership import classify_detailed

        event = {
            "receipt": "e",
            "facts": [
                {"field": "controller_name", "value": "매도회사", "line": 1},
                {"field": "controller_name", "value": "매수회사", "line": 2},
                {"field": "change_date", "value": "2026-08-05", "line": 3},
                {"field": "shares", "value": "1,752,362", "line": 4},
            ],
        }
        holding = {
            "receipt": "h",
            "submitter": "매수회사",
            "filed": "2026-08-17",
            "facts": [
                {"field": "report_trigger_date", "value": "2026-08-07", "line": 5},
                {
                    "field": "holding_movement",
                    "value": "장외매수",
                    "line": 6,
                    "party": "매수회사",
                    "note": "매매상대방: 매도회사",
                    "delta": "1,752,362",
                    "transaction_date": "2026-08-05",
                },
            ],
        }
        self.assertEqual(
            classify_detailed(event, holding)[1],
            "matching_transaction_row_parties_quantity_and_date",
        )
        holding["facts"][1]["transaction_date"] = "2026-08-07"
        self.assertIsNone(classify_detailed(event, holding))

    def test_reference_does_not_join_two_issuances_on_different_dates(self):
        from knowledge_graph.ingestion.control_ownership import classify_detailed

        event = {
            "receipt": "event",
            "facts": [
                {"field": "change_date", "value": "2026-08-12", "line": 1},
                {
                    "field": "change_reason",
                    "value": "제3자배정 유상증자 납입",
                    "line": 2,
                },
                {
                    "field": "related_filing",
                    "value": "주식등의대량보유상황보고서",
                    "references": ["holding"],
                    "line": 3,
                },
            ],
        }
        holding = {
            "receipt": "holding",
            "submitter": "발행대상자",
            "facts": [
                {"field": "report_trigger_date", "value": "2026-07-24", "line": 4},
                {
                    "field": "report_reason",
                    "value": "제3자배정 유상증자 납입",
                    "line": 5,
                },
            ],
        }
        self.assertIsNone(classify_detailed(event, holding))
        holding["facts"][0]["value"] = "2026-08-12"
        self.assertEqual(
            classify_detailed(event, holding)[1],
            "explicit_transaction_filing_reference",
        )
