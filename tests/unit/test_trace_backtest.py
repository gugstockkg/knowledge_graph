import unittest

from knowledge_graph.market.trace_backtest import backtest, partition, price_features


class TraceBacktestTests(unittest.TestCase):
    def test_split_rejects_labels_crossing_boundary(self):
        self.assertEqual(partition("2026-06-29", "2026-06-30"), "train")
        self.assertIsNone(partition("2026-06-30", "2026-07-01"))
        self.assertIsNone(partition("2026-09-30", "2026-10-01"))

    def test_price_feature_ignores_entry_bar(self):
        dates = tuple(f"2026-03-{day:02}" for day in range(1, 23))
        bars = {day: {"close": 100, "volume": 200, "is_tradable": True} for day in dates}
        bars[dates[-1]]["close"] = 1000
        self.assertEqual(price_features(bars, dates[-2], dates), [0.0] * 4)

    def test_portfolio_cost_applies_once_per_allocated_day_and_cash_is_included(self):
        days = ["2026-10-01", "2026-10-02", "2026-10-03"]
        scores = [
            ({"date": days[0], "return": .02}, .7),
            ({"date": days[0], "return": -.01}, .8),
            ({"date": days[1], "return": .04}, .4),
        ]
        result = backtest(scores, days, cost_bps=20)
        self.assertEqual(result["stock_entries"], 2)
        self.assertEqual(result["active_days"], 1)
        self.assertEqual(result["daily"], [.003, 0, 0])
        self.assertAlmostEqual(result["total_return"], .003)
