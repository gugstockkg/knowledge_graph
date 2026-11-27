import unittest

from knowledge_graph.market.economic_backtest import active_contract, graph_events


class EconomicBacktestTests(unittest.TestCase):
    def test_only_previously_public_terms_control_an_active_edge(self):
        original = {"kind": "original", "day": "2026-01-19", "buyer": {"corp_code": "buyer"},
                    "start": "2026-01-19", "end": "2026-03-01"}
        extended = {"kind": "amendment", "day": "2026-03-02", "start": None, "end": "2026-07-15"}
        self.assertFalse(active_contract([original, extended], "2026-01-19"))
        self.assertTrue(active_contract([original, extended], "2026-02-01"))
        self.assertFalse(active_contract([original, extended], "2026-03-02"))
        self.assertTrue(active_contract([original, extended], "2026-03-03"))
        self.assertFalse(active_contract([original, extended, dict(extended, end="2026-08-15")], "2026-03-03"))

    def test_earnings_metrics_are_one_filing(self):
        party = {"corp_code": "company", "stock_code": "012345"}
        filing = {"receipt": "receipt", "day": "2026-06-01", "company": party}
        direct, _, _, _ = graph_events({"contract_terms": [], "investments": [],
                                       "financials": [dict(filing, metric="revenue"),
                                                      dict(filing, metric="operating_profit")]})
        self.assertEqual(len(direct["2026-06-01"]), 1)
