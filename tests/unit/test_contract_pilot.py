import unittest

from knowledge_graph.ingestion.contract_pilot import (
    buyer_lookup_name, is_marine_contract, is_subsidiary_report, parse_contract,
)


class ContractPilotTests(unittest.TestCase):
    def test_supplier_revenue_is_not_replaced_by_buyer_revenue(self):
        document = """<table>
        <tr><td>1. 판매ㆍ공급계약 내용</td><td>LNG 보냉재 공급</td></tr>
        <tr><td>2. 계약내역</td><td>계약금액 총액(원)</td><td>100,000</td></tr>
        <tr><td>최근 매출액(원)</td><td>250,000</td></tr>
        <tr><td>3. 계약상대방</td><td>구매사 주식회사</td></tr>
        <tr><td>- 최근 매출액(원)</td><td>1,000,000</td></tr>
        <tr><td>5. 계약기간</td><td>시작일</td><td>2026-02-01</td></tr>
        <tr><td>종료일</td><td>-</td></tr>
        </table>"""
        fields = parse_contract(document)
        self.assertEqual(fields['amount_krw']['value'], 100000)
        self.assertEqual(fields['supplier_sales_krw']['value'], 250000)
        self.assertEqual(fields['buyer']['value'], '구매사 주식회사')
        self.assertEqual(fields['start_date']['value'], '2026-02-01')
        self.assertIsNone(fields['end_date']['value'])

    def test_form_with_separate_contract_title(self):
        document = """<table>
        <tr><td>1. 판매ㆍ공급계약 구분</td><td>공사수주</td></tr>
        <tr><td>- 체결계약명</td><td>LNG운반선 2척</td></tr>
        <tr><td>2. 계약내역</td><td>계약금액(원)</td><td>500</td></tr>
        <tr><td>3. 계약상대</td><td>오세아니아 지역 선주</td></tr>
        </table>"""
        fields = parse_contract(document)
        self.assertEqual(fields['description']['value'], 'LNG운반선 2척')
        self.assertEqual(fields['amount_krw']['value'], 500)
        self.assertEqual(fields['buyer']['value'], '오세아니아 지역 선주')

    def test_parent_report_is_recognized_even_without_title_suffix(self):
        document = '<table><tr><td>자회사인</td><td>공급사</td><td>의 주요경영사항신고</td></tr></table>'
        self.assertTrue(is_subsidiary_report('단일판매ㆍ공급계약체결', parse_contract(document)))
        self.assertTrue(is_subsidiary_report('단일판매ㆍ공급계약체결(자회사의 주요경영사항)', {}))
        self.assertFalse(is_subsidiary_report('단일판매ㆍ공급계약체결', {}))

    def test_filters_nonmarine_contracts_from_diversified_issuers(self):
        self.assertTrue(is_marine_contract('LNG운반선의 초저온 보냉자재 공급계약'))
        self.assertFalse(is_marine_contract('부산 거제동 가로주택정비사업'))

    def test_bilingual_counterparty_can_match_korean_legal_name(self):
        self.assertEqual(buyer_lookup_name('한화오션(주) (Hanwha Ocean co.,Ltd.)'), '한화오션')
