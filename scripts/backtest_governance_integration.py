"""Replay seven point-in-time strategies over a frozen non-overlapping quarter."""

import argparse
import gzip
import json
import re
from bisect import bisect_right
from collections import defaultdict
from itertools import accumulate, pairwise
from pathlib import Path

from audit_governance_signal_overlap import graph_filings, literal, source_evidence
from backtest_trace_paper_opendart import index_filings, structured_validator
from backtest_trace_positions import (
    get_series,
    load,
    portfolio_metrics,
    returns,
    select_large_companies,
    signals,
)
from extract_ownership_inventory import family

from knowledge_graph.market.economic_backtest import graph_events
from knowledge_graph.market.trace_paper import mine_rules, predict

DEFAULT_START, DEFAULT_END = "2026-07-01", "2026-09-30"
NS = "urn:fintos:opendart:"
TRIPLE = re.compile(r"^<([^>]+)> <([^>]+)> (.+) \.$")
TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
FEE = 0.001


def read_rdf(path, filings):
    """Load RDF evidence and materialized types for candidate stocks only."""
    subjects = defaultdict(lambda: defaultdict(set))
    prefixes = tuple(
        NS + prefix
        for prefix in ("filing:", "assertion:", "event:", "evidence:", "xml:")
    )
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            match = TRIPLE.match(line.rstrip("\n"))
            if not match or not match[1].startswith(prefixes):
                continue
            subject, predicate, obj = match.groups()
            receipt = subject[len(NS) :].split(":")[1]
            key = predicate.removeprefix(NS)
            if receipt in filings and (
                key
                in {
                    "reportsAssertion",
                    "supportedBy",
                    "line",
                    "locatedIn",
                    "sha256",
                    "field",
                }
                or key == TYPE
            ):
                subjects[subject][key].add(obj)
    return subjects


def resource(token):
    return token.strip("<>")


def controller_candidates(filings, rdf, market, start, end):
    dates = {}
    candidates = defaultdict(list)
    for receipt, row in filings.items():
        if row.get("receiptDate"):
            dates[receipt] = literal(row["receiptDate"][0])
    for receipt, row in sorted(filings.items()):
        if receipt not in dates or not row.get("reportTitle"):
            continue
        title = literal(row["reportTitle"][0])
        category = family(title)
        if not category or dates[receipt] >= end:
            continue
        idx = bisect_right(market, dates[receipt])
        if (
            idx >= len(market)
            or market[idx] < start
            and idx + 4 < bisect_right(market, start) - 1
        ):
            continue
        proof = []
        for claim in rdf[NS + "filing:" + receipt]["reportsAssertion"]:
            for span in rdf[resource(claim)]["supportedBy"]:
                location = rdf[resource(span)]
                for xml in location["locatedIn"]:
                    if not resource(xml).startswith(NS + "xml:" + receipt + ":"):
                        continue
                    for digest in rdf[resource(xml)]["sha256"]:
                        proof.extend(
                            {
                                "field": literal(field),
                                "line": int(literal(line)),
                                "sha256": literal(digest),
                            }
                            for field in rdf[resource(claim)]["field"]
                            for line in location["line"]
                        )
        correction = sorted(
            {
                resource(target).rsplit(":", 1)[-1]
                for target in row.get("corrects", [])
                if dates.get(resource(target).rsplit(":", 1)[-1], "9999")
                <= dates[receipt]
            }
        )
        events = set()
        for key in ("reportsEvent",):
            for term in row.get(key, []):
                event = resource(term)
                original = event.rsplit(":", 1)[-1]
                if bisect_right(market, dates.get(original, "9999")) <= idx and (
                    "정정" not in title.split("]", 1)[0] or correction
                ):
                    events.add(event)
        accepted = sorted(
            {
                event
                for event in events
                if proof and f"<{NS}OwnershipEvent>" in rdf[event][TYPE]
            }
        )
        explicit = sorted(
            {
                event
                for event in events
                if proof and f"<{NS}ControllerChange>" in rdf[event][TYPE]
            }
        )
        candidates[row["symbol"]].append(
            {
                "symbol": row["symbol"],
                "receipt": receipt,
                "title": title,
                "family": category,
                "filed": dates[receipt],
                "session": market[idx],
                "i": idx,
                "events": accepted,
                "explicit_events": explicit,
                "corrects": correction,
                "evidence": sorted(proof, key=lambda r: (r["line"], r["field"])),
                "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}",
            }
        )
    return candidates


def base_signals(graph, market, stocks, bars, start, end):
    clear = signals(graph, market)["explicit_buyer_path"]
    kg, touched = index_filings(graph)
    training, evaluation = {}, defaultdict(set)
    cutoff = market[bisect_right(market, start) - 2]
    for day, codes in sorted(touched.items()):
        release = bisect_right(market, day)
        if not 0 < release < len(market):
            continue
        prev, nxt = market[release - 1], market[release]
        for code in codes & stocks.keys():
            if nxt < start and all(
                bars[code].get(d, {}).get("is_tradable") for d in (prev, nxt)
            ):
                label = (
                    "UP"
                    if bars[code][nxt]["close"] > bars[code][prev]["close"]
                    else "DOWN"
                )
                training[code, prev] = (code, day, nxt, code, label)
            if start <= nxt <= end:
                evaluation[code, release].add(day)
    rules = mine_rules(kg, training.values(), cutoff, min_support=5)
    trace = defaultdict(dict)
    for (code, release), days in sorted(evaluation.items()):
        label, _, evidence = predict(
            kg,
            code,
            max(days),
            rules,
            select=lambda p: p,
            validate=structured_validator,
            alpha=0.5,
        )
        receipts = set()
        for _, path, _ in evidence:
            terminal = path[-1].target
            if terminal in kg.text_sources:
                receipts.add(terminal.removeprefix("dart:"))
            else:
                receipts.update(
                    edge.target.removeprefix("dart:")
                    for edge in kg.edges[terminal]
                    if edge.visible(max(days))
                    and edge.relation == "EXTRACTED_FROM"
                    and edge.target in kg.text_sources
                )
        if receipts:
            trace[code][release] = (1 if label == "UP" else -1, receipts)
    return clear, trace, rules, len(training), cutoff


def replay(symbol, strategy, condition, decisions, candidates, dates, bars):
    consumed, targets, orders, interventions = set(), [], [], []
    prior, pending = 0, None
    for day, idx, desired, net, receipts in decisions:
        target = desired
        detail = None
        if pending:
            detail = pending
            pending["next_session"] = day
            pending["outcome"] = "executed" if desired else "cancelled"
            pending["next_open"] = bars[day]["open"]
            pending = None
        elif desired and not prior and condition != "base":
            key = {
                "title": "receipt",
                "integrated": "events",
                "explicit": "explicit_events",
            }[condition]
            matches = []
            for row in candidates:
                if idx - 4 <= row["i"] <= idx:
                    keys = {row["receipt"]} if key == "receipt" else set(row[key])
                    if keys - consumed:
                        matches.append((row, keys))
            if matches:
                consumed.update(k for _, keys in matches for k in keys)
                target = 0
                pending = {
                    "symbol": symbol,
                    "strategy": strategy,
                    "condition": condition,
                    "date": day,
                    "open": bars[day]["open"],
                    "supply_receipts": receipts,
                    "signal": net,
                    "governance_receipts": [row["receipt"] for row, _ in matches],
                    "events": sorted({k for _, keys in matches for k in keys})
                    if key != "receipt"
                    else [],
                }
                interventions.append(pending)
        if target != prior:
            orders.append(
                {
                    "date": day,
                    "symbol": symbol,
                    "strategy": strategy,
                    "condition": condition,
                    "side": "buy" if target else "sell",
                    "session": "open",
                    "price": bars[day]["open"],
                    "signal": net,
                    "supply_receipts": receipts,
                    "governance_receipts": detail["governance_receipts"]
                    if detail
                    else [],
                    "reason": "reevaluated_after_delay"
                    if detail
                    else "base_signal"
                    if net
                    else "price_trend",
                }
            )
        targets.append(target)
        prior = target
    if pending:
        pending["outcome"] = "evaluation_ended"
    if prior:
        orders.append(
            {
                "date": dates[-1],
                "symbol": symbol,
                "strategy": strategy,
                "condition": condition,
                "side": "sell",
                "session": "close",
                "price": bars[dates[-1]]["close"],
                "reason": "terminal_liquidation",
            }
        )
    daily, trade_count = returns(dates, bars, targets, FEE)
    if len(orders) != trade_count:
        raise ValueError("Order ledger does not match simulated fills")
    return (
        list(accumulate([1.0] + [1 + r for r in daily], lambda a, b: a * b)),
        sum(targets),
        orders,
        interventions,
    )


def summary(curves, exposed, orders, interventions, dates):
    equity = [sum(values) / len(curves) for values in zip(*curves)]
    daily = [b / a - 1 for a, b in pairwise(equity)]
    return {
        **portfolio_metrics(daily),
        "exposure": exposed / (len(curves) * len(dates)),
        "orders": len(orders),
        "delays": len(interventions),
    }


def run(graph, archive, later, rdf_path, start, end, original_panel=False):
    index = {
        bar["date"]: bar
        for root in (archive, later)
        for bar in load(root / "KOSPI.json")["bars"]
    }
    market = sorted(index)
    dates = [d for d in market if start <= d <= end]
    i = market.index(dates[0])
    _, notices, _, symbols = graph_events(graph)
    seen = {
        p["corp_code"]
        for day, rows in notices.items()
        if day < start
        for row in rows
        for p in (row["supplier"], row["buyer"])
        if p
    }
    stocks, bars, missing, prior_ineligible = {}, {}, [], []
    for code, symbol in sorted(symbols.items()):
        if code not in seen:
            continue
        series = {
            **(get_series(archive, symbol, code) or {}),
            **(get_series(later, symbol, code) or {}),
        }
        if not all(series.get(d, {}).get("is_tradable") for d in market[i - 21 : i]):
            prior_ineligible.append(symbol)
            continue
        if not all(series.get(d, {}).get("is_tradable") for d in dates):
            missing.append(symbol)
            continue
        stocks[code] = symbol
        bars[code] = series
    if len(set(stocks.values())) != len(stocks):
        raise ValueError("Company identification is ambiguous")
    if original_panel:
        selected, _ = select_large_companies(graph, archive, later, market, dates)
        bars = {
            code: {
                **(get_series(archive, symbol, code) or {}),
                **(get_series(later, symbol, code) or {}),
            }
            for code, symbol in selected.items()
        }
        seven = {"005930", "000660", "010140", "329180", "000720", "028260", "009150"}
        stocks = {code: symbol for code, symbol in selected.items() if symbol in seven}
        if set(stocks.values()) != seven:
            raise ValueError("The seven published symbols must be present")
        missing, prior_ineligible = [], []
    else:
        selected = stocks
    filings = graph_filings(rdf_path, stocks)
    governance = controller_candidates(
        filings, read_rdf(rdf_path, filings), market, start, end
    )
    clear, trace, rules, training, cutoff = base_signals(
        graph, market, selected, bars, start, end
    )
    report, stock_report, all_orders, all_delays = {}, [], [], []
    for strategy in ("BUY_HOLD", "CLEAR", "TRACE"):
        for condition in (
            ("base",)
            if strategy == "BUY_HOLD"
            else ("base", "title", "integrated", "explicit")
        ):
            curves, orders, delays, exposed = [], [], [], 0
            key = f"{strategy}_{condition}"
            for code, symbol in stocks.items():
                positions = []
                for j, day in enumerate(market):
                    if not start <= day <= end:
                        continue
                    window = range(j - 4, j + 1)
                    if strategy == "CLEAR":
                        items = [
                            (sign, {r})
                            for (release, r), sign in clear[code].items()
                            if release in window
                        ]
                    elif strategy == "TRACE":
                        items = [trace[code][k] for k in window if k in trace[code]]
                    else:
                        items = []
                    net = sum(sign for sign, _ in items)
                    receipts = sorted({r for _, rs in items for r in rs})
                    trend = (
                        bars[code][market[j - 1]]["close"]
                        > bars[code][market[j - 21]]["close"]
                    )
                    desired = strategy == "BUY_HOLD" or (net > 0 if net else trend)
                    positions.append((day, j, desired, net, receipts))
                curve, exposure, fills, blocked = replay(
                    symbol,
                    strategy,
                    condition,
                    positions,
                    governance[symbol],
                    dates,
                    bars[code],
                )
                curves.append(curve)
                orders.extend(fills)
                delays.extend(blocked)
                exposed += exposure
                stock_report.append(
                    {
                        "symbol": symbol,
                        "strategy": strategy,
                        "condition": condition,
                        "return": curve[-1] - 1,
                        "orders": len(fills),
                        "delays": len(blocked),
                    }
                )
            report[key] = summary(curves, exposed, orders, delays, dates)
            all_orders.extend(orders)
            all_delays.extend(delays)
    eligible = [r for rows in governance.values() for r in rows if r["events"]]
    return {
        "period": [start, end],
        "sessions": len(dates),
        "stocks": stocks,
        "missing": missing,
        "prior_ineligible": prior_ineligible,
        "training": training,
        "training_cutoff": cutoff,
        "rules": [vars(r) for r in rules],
        "training_symbols": sorted(selected.values()),
        "validation_split": None,
        "metrics": report,
        "stocks_results": stock_report,
        "orders": all_orders,
        "delays": all_delays,
        "eligible": eligible,
        "governance": [r for rows in governance.values() for r in rows],
        "benchmark_index_return": index[dates[-1]]["close"] / index[dates[0]]["open"]
        - 1,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("graph", "archive", "later", "rdf", "output"):
        parser.add_argument(arg, type=Path)
    parser.add_argument("--ownership", type=Path)
    parser.add_argument("--bucket")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--original-panel", action="store_true")
    args = parser.parse_args()
    result = run(
        load(args.graph),
        args.archive,
        args.later,
        args.rdf,
        args.start,
        args.end,
        args.original_panel,
    )
    if args.ownership and args.bucket:
        verify = {r["receipt"]: r for r in result["eligible"]}
        with args.ownership.open() as handle:
            records = {
                r["receipt"]: r
                for r in map(json.loads, handle)
                if r["receipt"] in verify
            }
        for receipt, doc in verify.items():
            record = records.get(receipt)
            if record and record.get("sha256"):
                doc["verified_xml"] = source_evidence(
                    receipt, record, doc["title"], args.bucket
                )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                key: result[key]
                for key in ("sessions", "training", "metrics", "benchmark_index_return")
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
