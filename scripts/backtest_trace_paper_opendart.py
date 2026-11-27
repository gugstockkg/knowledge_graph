"""EC2 comparison of TRACE-style inference with OpenDART structured evidence."""

import argparse
import json
from bisect import bisect_right
from collections import defaultdict
from math import prod
from pathlib import Path

from backtest_trace_positions import (
    TEST_END,
    TEST_START,
    get_series,
    load,
    portfolio_metrics,
    returns,
    select_large_companies,
    signals,
)
from knowledge_graph.market.economic_backtest import active_contract, graph_events
from knowledge_graph.market.trace_paper import Edge, TemporalGraph, mine_rules, predict


def index_filings(graph):
    """Make two-edge direct and three-edge counterparty paths to dated sources."""
    edges = set()
    texts = set()
    _, notices, histories, _ = graph_events(graph)
    histories = [
        sorted(terms, key=lambda item: (item["day"], item["kind"] != "original", item["receipt"]))
        for terms in histories.values()
    ]
    touched = defaultdict(set)

    def link(source, relation, target, day):
        edges.add(Edge(source, relation, target, day, day, day))

    for day, records in sorted(notices.items()):
        authors = set()
        for record in records:
            event = "event:" + record["receipt"]
            text = "dart:" + record["receipt"]
            texts.add(text)
            link(event, "EXTRACTED_FROM", text, day)
            for role in ("supplier", "buyer"):
                party = record[role]
                if party:
                    corp = party["corp_code"]
                    link(corp, f"{role.upper()}_{record['kind'].upper()}", event, day)
                    touched[day].add(corp)
                    if role == "supplier":
                        authors.add(corp)
        for terms in histories:
            if not active_contract(terms, day):
                continue
            seller = terms[0]["supplier"]["corp_code"]
            buyer = terms[0]["buyer"]["corp_code"]
            if seller in authors and seller != buyer:
                link(buyer, "BUYS_FROM", seller, day)
                touched[day].add(buyer)
            if buyer in authors and seller != buyer:
                link(seller, "SELLS_TO", buyer, day)
                touched[day].add(seller)
    return TemporalGraph(edges, texts), touched


def index_clear_filings(graph, market):
    """Ground TRACE paths only in disclosures accepted by CLEAR for the buyer."""
    accepted = signals(graph, market)["explicit_buyer_path"]
    records = {record["receipt"]: record for record in graph["contract_terms"]}
    edges, texts = set(), set()
    touched = defaultdict(set)
    for code, filings in accepted.items():
        for (release, receipt), _ in filings.items():
            record = records[receipt]
            if release >= len(market):
                continue
            day = record["day"]
            event, text = "event:" + receipt, "dart:" + receipt
            texts.add(text)
            touched[day].add(code)
            relation = "CLEAR_BUYER_" + record["kind"].upper()
            edges.add(Edge(code, relation, event, day, day, day))
            edges.add(Edge(event, "EXTRACTED_FROM", text, day, day, day))
    return TemporalGraph(edges, texts), touched


def structured_validator(path, rule):
    # A binary check against the graph's extracted filing fields. It does not
    # independently infer sentiment or verify the extraction against XML.
    grounded = path[-1].relation == "EXTRACTED_FROM"
    return rule.label, float(grounded)


def run(graph, archive, later, min_support, *, clear_filter=False):
    market = sorted({
        bar["date"] for root in (archive, later) for bar in load(root / "KOSPI.json")["bars"]
    })
    dates = [day for day in market if TEST_START <= day <= TEST_END]
    selected, selection = select_large_companies(graph, archive, later, market, dates)
    bars = {
        code: {**(get_series(archive, symbol, code) or {}), **(get_series(later, symbol, code) or {})}
        for code, symbol in selected.items()
    }
    kg, touched = index_clear_filings(graph, market) if clear_filter else index_filings(graph)
    observations = {}
    evaluation = defaultdict(set)
    for filing_day, codes in sorted(touched.items()):
        release = bisect_right(market, filing_day)
        if not 0 < release < len(market):
            continue
        prev, nxt = market[release - 1], market[release]
        for code in codes & selected.keys():
            if nxt < TEST_START:
                before = bars[code].get(prev)
                after = bars[code].get(nxt)
                if before and after and before["is_tradable"] and after["is_tradable"]:
                    label = "UP" if after["close"] > before["close"] else "DOWN"
                    # Several calendar-day filings may map to the same stock-session.
                    # Use the latest filing-day snapshot and count the stock-day once.
                    observations[code, prev] = (code, filing_day, nxt, code, label)
            elif nxt <= TEST_END:
                evaluation[code, release].add(filing_day)
    rules = mine_rules(kg, observations.values(), max(day for day in market if day < TEST_START),
                       min_support=min_support)
    daily_signs = defaultdict(dict)
    audit = []
    for (code, release), filing_days in sorted(evaluation.items()):
        day = max(filing_days)
        label, conf, evidence = predict(
            kg, code, day, rules, select=lambda paths: paths,
            validate=structured_validator, alpha=0.5,
        )
        if evidence:
            daily_signs[code][release] = 1 if label == "UP" else -1
        audit.append({
            "symbol": selected[code], "filing_day": day, "session": market[release],
            "label": label, "confidence": conf, "adopted": bool(evidence),
            "receipts": sorted({path[-1].target.removeprefix("dart:") for _, path, _ in evidence}),
        })

    curves = []
    stock_returns, stock_orders, signal_days = {}, {}, {}
    exposure = 0
    active_signal_days = {}
    order_records = []
    receipts_by_session = {(row["symbol"], row["session"]): row["receipts"] for row in audit}
    for code, symbol in selected.items():
        targets = []
        prior = 0
        active_signal_days[symbol] = 0
        for day in dates:
            i = market.index(day)
            signal = sum(daily_signs[code].get(j, 0) for j in range(i - 4, i + 1))
            active_signal_days[symbol] += bool(signal)
            trend = bars[code][market[i - 1]]["close"] > bars[code][market[i - 21]]["close"]
            target = int(signal > 0) if signal else int(trend)
            targets.append(target)
            if target != prior:
                receipts = {
                    receipt for j in range(i - 4, i + 1)
                    for receipt in receipts_by_session.get((symbol, market[j]), ())
                }
                order_records.append({
                    "date": day, "symbol": symbol, "strategy": "trace",
                    "side": "buy" if target else "sell", "session": "open",
                    "price": bars[code][day]["open"],
                    "reason": "net_trace_signal" if signal else "20_session_price_trend",
                    "trend_target": int(trend), "net_signal": signal,
                    "signal_receipts": "|".join(sorted(receipts)),
                })
            prior = target
        if prior:
            order_records.append({
                "date": dates[-1], "symbol": symbol, "strategy": "trace",
                "side": "sell", "session": "close", "price": bars[code][dates[-1]]["close"],
                "reason": "end_of_evaluation",
            })
        daily, orders = returns(dates, bars[code], targets, 0.001)
        curves.append([prod(1 + r for r in daily[:n]) for n in range(len(dates) + 1)])
        stock_returns[symbol] = curves[-1][-1] - 1
        stock_orders[symbol] = orders
        signal_days[symbol] = len(daily_signs[code])
        exposure += sum(targets)
    equity = [sum(values) for values in zip(*curves)]
    summary = portfolio_metrics([next_value / value - 1 for value, next_value in zip(equity, equity[1:])])
    return {
        **summary, "stock_returns": stock_returns, "orders": sum(stock_orders.values()),
        "invested_stock_days": exposure, "signal_days": signal_days, "selection": selection,
        "training_stock_days": len(observations), "evaluation_stock_days": len(audit),
        "rules": [vars(rule) for rule in rules], "predictions": audit,
        "clear_filter": clear_filter, "min_support": min_support,
        "order_records": order_records, "active_signal_days": active_signal_days,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("graph", "archive", "later", "output"):
        parser.add_argument(key, type=Path)
    parser.add_argument("--min-support", type=int, default=5)
    parser.add_argument("--clear-filter", action="store_true")
    args = parser.parse_args()
    result = run(load(args.graph), args.archive, args.later, args.min_support,
                 clear_filter=args.clear_filter)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
