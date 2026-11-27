"""Reproduce the nine-strategy comparison and export its public audit artifacts."""

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from subprocess import check_output

import backtest_trace_paper_opendart as trace
import backtest_trace_positions as clear


def write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def market_dates(archive, later):
    return sorted({
        bar["date"] for folder in (archive, later)
        for bar in clear.load(folder / "KOSPI.json")["bars"]
    })


def evidence_candidates(kg, code, day):
    frontier = [()]
    receipts = set()
    for _ in range(3):
        frontier = [path for prefix in frontier for path in kg.expand(code, prefix, day)]
        receipts.update(
            path[-1].target.removeprefix("dart:")
            for path in frontier if path[-1].target in kg.text_sources
        )
    return receipts


def run(graph_path, archive, later, output, revision):
    graph = clear.load(graph_path)
    market = market_dates(archive, later)
    dates = [day for day in market if clear.TEST_START <= day <= clear.TEST_END]
    selection, _ = clear.select_large_companies(graph, archive, later, market, dates)
    base = clear.run(graph, archive, later, price_controls=True, large_companies=True)
    trace_result = trace.run(graph, archive, later, 5)
    orders = sorted(base["orders"] + trace_result["order_records"],
                    key=lambda row: (row["strategy"], row["symbol"], row["date"], row["session"] != "open"))
    trace_result["order_count"] = trace_result["orders"]
    metrics = {**base["positions"]["20"], "trace": trace_result}
    for strategy, result in metrics.items():
        assert sum(order["strategy"] == strategy for order in orders) == result["order_count"]
    signals = clear.signals(graph, market)
    kg, _ = trace.index_filings(graph)
    groups = defaultdict(list)
    for order in orders:
        groups[order["symbol"], order["strategy"]].append(order)
    rows, evidence = [], []
    for code, symbol in selection.items():
        trend = groups[symbol, "price_trend"]
        buyer = groups[symbol, "named_buyer_only"]
        trace_days = [row for row in trace_result["predictions"] if row["symbol"] == symbol]
        for name, candidates, adopted, signal_count, reference in (
            ("CLEAR", signals["named_buyer_only"][code],
             signals["explicit_buyer_path"][code],
             base["signal_days"][symbol].get("explicit_buyer_path", 0), buyer),
            ("TRACE", {(market.index(row["session"]), r): None
                       for row in trace_days for r in evidence_candidates(kg, code, row["filing_day"])},
             {(market.index(row["session"]), r): None for row in trace_days for r in row["receipts"]},
             trace_result["signal_days"][symbol], trend),
        ):
            strategy = "trace" if name == "TRACE" else "explicit_buyer_path"
            order_set = {(r["date"], r["session"], r["side"]) for r in groups[symbol, strategy]}
            ref_set = {(r["date"], r["session"], r["side"]) for r in reference}
            eligible = lambda items: {(i, r) for i, r in items if i < len(market) and market[i] in dates}
            candidates, adopted = eligible(candidates), eligible(adopted)
            assert adopted <= candidates
            receipt_dates = {i for i, _ in adopted}
            rows.append(dict(
                strategy=name, symbol=symbol, candidate_receipt_sessions=len(candidates),
                adopted_receipt_sessions=len(adopted), new_signal_days=len(receipt_dates),
                active_signal_days=(trace_result["active_signal_days"][symbol]
                                    if name == "TRACE" else signal_count),
                orders_added=len(order_set - ref_set), orders_removed=len(ref_set - order_set),
            ))
            for i, receipt in sorted(candidates):
                evidence.append(dict(strategy=name, symbol=symbol, date=market[i],
                                     receipt=receipt, adopted=int((i, receipt) in adopted)))
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "main-orders.csv", orders,
              ["date", "symbol", "strategy", "side", "session", "price", "reason",
               "trend_target", "net_signal", "signal_receipts"])
    write_csv(output / "filing-audit.csv", evidence,
              ["strategy", "symbol", "date", "receipt", "adopted"])
    (output / "audit-summary.json").write_text(json.dumps({
        "revision": revision,
        "source_sha256": {p.name: digest(p) for p in (
            Path(__file__), Path(clear.__file__), Path(trace.__file__),
            Path(trace.predict.__code__.co_filename),
        )},
        "graph_sha256": digest(graph_path),
        "prices_sha256": {f"{folder.name}/{p.name}": digest(p) for folder in (archive, later)
                          for p in sorted(folder.glob("*.json")) if p.stem in set(selection.values()) | {"KOSPI", "KOSDAQ"}},
        "period": [dates[0], dates[-1]], "days": len(dates), "round_trip_bp": 20,
        "selection": base["selection"], "audit": rows, "trace_predictions": trace_result["predictions"],
        "trace_rules": trace_result["rules"],
        "metrics": {key: {field: result[field] for field in
                          ("total_return", "sharpe", "annualized_volatility", "max_drawdown",
                           "stock_returns", "order_count", "invested_stock_days")}
                    for key, result in metrics.items()},
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("graph", "archive", "later", "output"):
        parser.add_argument(arg, type=Path)
    parser.add_argument("--revision", help="Source revision if running from an exported bundle")
    args = parser.parse_args()
    revision = args.revision or check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    run(args.graph, args.archive, args.later, args.output, revision)
