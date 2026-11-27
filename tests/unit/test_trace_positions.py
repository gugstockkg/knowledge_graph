import unittest

from scripts.backtest_trace_positions import returns, signals


class TracePositionsTest(unittest.TestCase):
    def test_continuous_hold_carries_overnight_gap_and_charges_two_orders(self):
        days = ["2026-10-01", "2026-10-02"]
        bars = {days[0]: {"open": 100, "close": 90}, days[1]: {"open": 80, "close": 70}}
        daily, orders = returns(days, bars, [1, 1], 0.001)
        self.assertEqual(orders, 2)
        self.assertAlmostEqual(
            (1 + daily[0]) * (1 + daily[1]), 70 / 100 * 0.999 / 1.001
        )

    def test_exit_occurs_at_next_open_and_preserves_overnight_loss(self):
        days = ["2026-10-01", "2026-10-02"]
        bars = {days[0]: {"open": 100, "close": 90}, days[1]: {"open": 80, "close": 70}}
        daily, orders = returns(days, bars, [1, 0], 0.0)
        self.assertEqual(orders, 2)
        self.assertAlmostEqual((1 + daily[0]) * (1 + daily[1]), 0.8)

    def test_path_uses_next_session_and_filters_scrambled_category(self):
        buyer = {"corp_code": "buyer", "stock_code": "000001"}
        supplier = {"corp_code": "supplier", "stock_code": "000002"}
        origin = {
            "day": "2026-09-28",
            "receipt": "a",
            "contract": "a",
            "kind": "original",
            "start": "2026-09-28",
            "end": "2026-10-31",
            "amount": 100,
            "buyer": buyer,
            "supplier": supplier,
            "category": "equipment",
        }
        notice = dict(
            origin,
            day="2026-10-01",
            receipt="b",
            contract="b",
            category="other",
            buyer=None,
        )
        dates = ["2026-10-01", "2026-10-02"]
        graph = {
            "contract_terms": [origin, notice],
            "investments": [],
            "financials": [],
        }
        self.assertEqual(signals(graph, dates)["legacy_path"]["buyer"], {(1, "b"): 1})
        self.assertEqual(signals(graph, dates)["filtered_path"]["buyer"], {})
        notice["category"] = "equipment"
        self.assertEqual(signals(graph, dates)["filtered_path"]["buyer"], {(1, "b"): 1})

    def test_named_buyer_baseline_does_not_require_prior_contract(self):
        buyer = {"corp_code": "buyer", "stock_code": "000001"}
        supplier = {"corp_code": "supplier", "stock_code": "000002"}
        notice = {
            "day": "2026-10-01",
            "receipt": "new",
            "contract": "new",
            "kind": "original",
            "start": "2026-10-01",
            "end": "2026-12-31",
            "amount": 100,
            "buyer": buyer,
            "supplier": supplier,
            "category": "equipment",
        }
        result = signals(
            {"contract_terms": [notice], "investments": [], "financials": []},
            ["2026-10-01", "2026-10-02"],
        )
        self.assertEqual(result["named_buyer_only"]["buyer"], {(1, "new"): 1})
        self.assertEqual(result["explicit_buyer_path"]["buyer"], {})
