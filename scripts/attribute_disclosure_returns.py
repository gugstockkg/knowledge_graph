"""Explain the CLEAR and TRACE backtest using matched positions and signal removals."""

import argparse
import json
from collections import defaultdict
from itertools import groupby
from math import prod
from pathlib import Path

import backtest_trace_paper_opendart as trace
import backtest_trace_positions as clear
from audit_disclosure_backtest import market_dates, write_csv


def trade_difference(left, right):
    def keys(rows):
        return {(r["date"], r["session"], r["side"]) for r in rows}
    a, b = keys(left), keys(right)
    return {"added": len(a - b), "removed": len(b - a)}


def positions(days, orders):
    opening = {r["date"]: r["side"] for r in orders if r["session"] == "open"}
    held = 0
    for day in days:
        if day in opening:
            held = int(opening[day] == "buy")
        yield held


def run(graph_path, archive, later, output):
    graph = clear.load(graph_path)
    market = market_dates(archive, later)
    dates = [day for day in market if clear.TEST_START <= day <= clear.TEST_END]
    selected, selection = clear.select_large_companies(graph, archive, later, market, dates)
    base = clear.run(graph, archive, later, price_controls=True, large_companies=True)
    tracing = trace.run(graph, archive, later, 5)
    accepted = clear.signals(graph, market)["explicit_buyer_path"]
    orders = defaultdict(list)
    for row in base["orders"] + tracing["order_records"]:
        orders[row["symbol"], row["strategy"]].append(row)
    decisions = defaultdict(dict)
    for row in tracing["predictions"]:
        if row["adopted"]:
            decisions[row["symbol"]][market.index(row["session"])] = (
                1 if row["label"] == "UP" else -1, frozenset(row["receipts"])
            )
    daily, results = [], []
    day_indices = [market.index(day) for day in dates]
    for code, symbol in selected.items():
        bars = {
            **(clear.get_series(archive, symbol, code) or {}),
            **(clear.get_series(later, symbol, code) or {}),
        }
        price = list(positions(dates, orders[symbol, "price_trend"]))
        clear_by_day = defaultdict(list)
        for (i, receipt), sign in accepted[code].items():
            clear_by_day[i].append((frozenset([receipt]), sign))
        trace_by_day = {i: [(receipts, sign)] for i, (sign, receipts) in decisions[symbol].items()}

        def targets(signals, removed=frozenset()):
            nets, refs, held = [], [], []
            for i, fallback in zip(day_indices, price):
                remaining = [
                    (receipts - removed, sign)
                    for j in range(i - 4, i + 1) for receipts, sign in signals.get(j, ())
                    if receipts - removed
                ]
                net = sum(sign for _, sign in remaining)
                nets.append(net)
                refs.append(sorted({r for receipts, _ in remaining for r in receipts}))
                held.append(int(net > 0) if net else fallback)
            return held, nets, refs

        def replay(target):
            moves, count = clear.returns(dates, bars, target, 0.001)
            return prod(1 + change for change in moves) - 1, moves, count

        baseline, baseline_daily, _ = replay(price)
        row = {"symbol": symbol, "price_trend": baseline}
        for name, signals, strategy, expected in (
            ("clear", clear_by_day, "explicit_buyer_path",
             base["positions"]["20"]["explicit_buyer_path"]["stock_returns"][symbol]),
            ("trace", trace_by_day, "trace", tracing["stock_returns"][symbol]),
        ):
            holding, nets, refs = targets(signals)
            actual, moves, order_count = replay(holding)
            actual_orders = orders[symbol, strategy]
            assert holding == list(positions(dates, actual_orders))
            assert abs(actual - expected) < 1e-10 and order_count == len(actual_orders)
            exec_orders = {(o["date"], o["session"]): o for o in actual_orders}
            prior_equity = prior_base = 1.0
            for j, day in enumerate(dates):
                prior_equity *= 1 + moves[j]
                prior_base *= 1 + baseline_daily[j]
                day_orders = [exec_orders[day, session] for session in ("open", "close")
                              if (day, session) in exec_orders]
                daily.append(dict(
                    symbol=symbol, strategy=name.upper(), date=day, trend_target=price[j],
                    net_signal=nets[j], target=holding[j], receipts="|".join(refs[j]),
                    orders="|".join(f'{o["session"]}:{o["side"]}@{o["price"]}' for o in day_orders),
                    equity=prior_equity, price_equity=prior_base,
                ))
            episodes = []
            different = [i for i, (actual_target, baseline_target) in enumerate(zip(holding, price))
                         if actual_target != baseline_target]
            for _, group in groupby(enumerate(different), key=lambda pair: pair[1] - pair[0]):
                indices = [i for _, i in group]
                alternative = holding[:]
                for j in indices:
                    alternative[j] = price[j]
                episodes.append(dict(
                    start=dates[indices[0]], end=dates[indices[-1]], days=len(indices),
                    receipts=sorted({r for j in indices for r in refs[j]}),
                    sleeve_effect=actual - replay(alternative)[0],
                ))
            used = sorted({r for receipts in refs for r in receipts})
            removals = []
            for group in dict.fromkeys([(receipt,) for receipt in used] + [tuple(used)]):
                if not group:
                    continue
                alternative = targets(signals, frozenset(group))[0]
                alternate_return, _, alt_order_count = replay(alternative)
                removals.append(dict(
                    receipts=group, return_without=alternate_return,
                    sleeve_effect=actual - alternate_return,
                    changed_days=sum(a != b for a, b in zip(holding, alternative)),
                    orders_without=alt_order_count,
                ))
            row[name] = dict(return_net=actual, delta_vs_price=actual - baseline,
                             different_days=len(different), episodes=episodes, removals=removals,
                             orders_vs_price=trade_difference(actual_orders, orders[symbol, "price_trend"]))
        row["trace_minus_clear_contribution"] = (
            row["trace"]["return_net"] - row["clear"]["return_net"]
        ) / len(selected)
        results.append(row)
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "daily-decisions.csv", daily, list(daily[0]))
    (output / "stock-attribution.json").write_text(json.dumps({
        "selection": selection, "days": len(dates), "round_trip_bp": 20, "stocks": results,
        "portfolio_trace_minus_clear": sum(r["trace_minus_clear_contribution"] for r in results),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("graph", "archive", "later", "output"):
        parser.add_argument(key, type=Path)
    args = parser.parse_args()
    run(args.graph, args.archive, args.later, args.output)
