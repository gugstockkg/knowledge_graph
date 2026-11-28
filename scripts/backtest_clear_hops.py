"""CLEAR: learn disclosure responses for issuers and direct buyers, then replay trades."""

import argparse
import json
from bisect import bisect_right
from collections import defaultdict
from pathlib import Path
from statistics import mean

from backtest_governance_integration import FEE, replay, summary
from backtest_trace_positions import get_series, load, signals
from knowledge_graph.market.economic_backtest import active_contract, graph_events

START = "2026-10-01"
END = "2026-11-26"

def run(graph, archive, later, start_date=START):
    market = sorted({r["date"] for root in (archive, later)
                     for r in load(root / "KOSPI.json")["bars"]})
    days = [d for d in market if start_date <= d <= END]
    start = market.index(days[0])
    if start < 21:
        raise ValueError("The test start must leave 21 prior trading sessions")
    _, _, histories, symbols = graph_events(graph)
    bars = {code: {**(get_series(archive, symbol, code) or {}),
                   **(get_series(later, symbol, code) or {})}
            for code, symbol in symbols.items()}
    panel = [c for c, series in bars.items() if all(
        series.get(d, {}).get("is_tradable") for d in market[start-21:start + len(days)])]
    existing = signals(graph, market)["explicit_buyer_path"]
    disclosures, own = {}, defaultdict(dict)
    for history in histories.values():
        history.sort(key=lambda r: (r["day"], r["kind"] != "original", r["receipt"]))
        before = []
        for row in history:
            release = bisect_right(market, row["day"])
            old = [x for x in before if x["day"] < row["day"] and x["amount"] is not None]
            change = row["kind"]
            if change != "original":
                change = "unknown"
                if old and row["amount"] is not None:
                    values = {x["amount"] for x in old if x["day"] == old[-1]["day"]}
                    if len(values) == 1:
                        last = values.pop()
                        change = ("increase" if row["amount"] > last else
                                  "decrease" if row["amount"] < last else "unchanged")
            ratio = row["ratio"]
            size = ("unknown" if ratio is None else "under_10" if ratio < 10
                    else "10_to_30" if ratio < 30 else "30_plus")
            disclosures[row["receipt"]] = (row, release, change, size)
            if release < len(market):
                own[row["supplier"]["corp_code"]][release, row["receipt"]] = 1
            before.append(row)
    training, pooled = defaultdict(list), defaultdict(list)
    for hop, source in enumerate((own, existing)):
        for code, items in source.items():
            seen = set()
            for j, receipt in sorted(items):
                if j + 4 >= start or j in seen:
                    continue
                series = bars.get(code, {})
                if not all(series.get(day, {}).get("is_tradable") for day in market[j:j+5]):
                    continue
                net = series[market[j+4]]["close"]/series[market[j]]["open"]*(1-FEE)/(1+FEE)-1
                _, _, kind, size = disclosures[receipt]
                training[hop, kind, size].append(net)
                pooled[hop].append(net)
                seen.add(j)

    def score(hop, receipt):
        _, _, kind, size = disclosures[receipt]
        sample = training[hop, kind, size]
        if len(sample) < 5:
            return None
        return (sum(sample) + 10 * mean(pooled[hop])) / (len(sample) + 10)

    def preferences(code, j, max_hop=1):
        scores = {}
        for hop, source in enumerate((own, existing)):
            if hop > max_hop:
                break
            for release, receipt in source[code]:
                if j-4 <= release <= j:
                    estimate = score(hop, receipt)
                    if estimate is not None:
                        scores.setdefault(receipt, (hop, release, estimate))
        return scores

    def order_key(row):
        return row["symbol"], row["date"], row["side"], row["session"]

    diagnostics = {symbols[code]: {"hops": [], "position_days_vs_trend": 0}
                   for code in panel}
    for code in panel:
        stats = diagnostics[symbols[code]]
        chosen = [preferences(code, j) for j in range(start, start + len(days))]
        for hop, source in enumerate((own, existing)):
            # Include carry-in disclosures whose five-session window reaches the test.
            candidates = {receipt for release, receipt in source[code]
                          if start-4 <= release < start + len(days)}
            kept = {receipt for scores in chosen for receipt, (h, _, _) in scores.items()
                    if h == hop}
            stats["hops"].append({
                "candidates": len(candidates),
                "accepted": len(kept),
                "new_signal_days": sum(any(h == hop and release == j and value
                                           for h, release, value in scores.values())
                                       for j, scores in enumerate(chosen, start)),
                "active_signal_days": sum(bool(sum(value for h, _, value in scores.values()
                                                  if h == hop)) for scores in chosen),
            })

    report, ledgers, changes_due_to_1hop = {}, {}, 0
    hop_decisions, hop_paths = [], {}
    for policy in ("hold", "trend", "CLEAR"):
        curves, orders, stock_results, exposure = [], [], [], 0
        for code in panel:
            symbol = symbols[code]
            positions, own_positions = [], []
            for j in range(start, start + len(days)):
                scored = preferences(code, j) if policy == "CLEAR" else {}
                net, refs = sum(v for _, _, v in scored.values()), sorted(scored)
                trend = bars[code][market[j-1]]["close"] > bars[code][market[j-21]]["close"]
                desired = policy == "hold" or (net > 0 if net else trend)
                positions.append((market[j], j, desired, net, refs))
                if policy == "CLEAR":
                    diagnostics[symbol]["position_days_vs_trend"] += desired != trend
                    first = preferences(code, j, max_hop=0)
                    net_0 = sum(v for _, _, v in first.values())
                    own_positions.append((market[j], j, net_0 > 0 if net_0 else trend,
                                          net_0, sorted(first)))
                    buyer_refs = [r for r, (hop, _, _) in scored.items() if hop == 1]
                    if buyer_refs:
                        for receipt in buyer_refs:
                            if receipt in hop_paths:
                                continue
                            item = disclosures[receipt][0]
                            paths = [h[0] for h in histories.values()
                                     if h[0]["receipt"] != receipt
                                     and h[0]["supplier"]["corp_code"] == item["supplier"]["corp_code"]
                                     and (h[0]["buyer"] or {}).get("corp_code") == code
                                     and h[0]["category"] == item["category"]
                                     and (h[0]["amount"] or 0) > 0
                                     and active_contract(h, item["day"])]
                            if not paths:
                                raise ValueError(f"Missing supporting contract for {receipt}")
                            hop_paths[receipt] = {
                                "disclosure": item,
                                "supporting_contracts": sorted(paths, key=lambda r: r["receipt"]),
                            }
                        hop_decisions.append({
                            "symbol": symbol, "date": market[j], "one_hop_receipts": buyer_refs,
                            "zero_hop_receipts": sorted(first), "score_0": net_0,
                            "score_1": sum(scored[r][2] for r in buyer_refs), "score": net,
                            "trend": trend,
                            "previous_close": bars[code][market[j-1]]["close"],
                            "trend_reference_close": bars[code][market[j-21]]["close"],
                            "prior_position": positions[-2][2] if len(positions) > 1 else False,
                            "prior_without_1hop": own_positions[-2][2] if len(own_positions) > 1 else False,
                            "target": desired, "target_without_1hop": own_positions[-1][2],
                        })

            equity, exposed, fills, _ = replay(symbol, policy, "base", positions, [], days, bars[code])
            if policy == "CLEAR":
                _, _, without_hop, _ = replay(symbol, policy, "base", own_positions,
                                               [], days, bars[code])
                changes_due_to_1hop += len({order_key(r) for r in fills}
                                           ^ {order_key(r) for r in without_hop})
            curves.append(equity)
            exposure += exposed
            orders.extend(fills)
            stock_results.append({"symbol": symbol, "return": equity[-1]-1, "orders": len(fills)})
        ledgers[policy] = orders
        report[policy] = {**summary(curves, exposure, orders, [], days), "stocks": stock_results}
    baseline = {order_key(row): row for row in ledgers["trend"]}
    clear = {order_key(row): row for row in ledgers["CLEAR"]}
    changes = {"removed": [baseline[k] for k in sorted(baseline.keys()-clear.keys())],
               "added": [clear[k] for k in sorted(clear.keys()-baseline.keys())]}
    for symbol, _, _, _ in baseline.keys()-clear.keys():
        stats = diagnostics[symbol]
        stats["removed"] = stats.get("removed", 0) + 1
    for symbol, _, _, _ in clear.keys()-baseline.keys():
        stats = diagnostics[symbol]
        stats["added"] = stats.get("added", 0) + 1
    return {"one_hop_trace": {"paths": hop_paths, "decisions": hop_decisions},
            "diagnostics": diagnostics, "changed_fills_due_to_hop_1": changes_due_to_1hop,
            "period": [days[0], days[-1]], "sessions": len(days),
            "panel": sorted(symbols[c] for c in panel), "training": {k: len(v) for k,v in pooled.items()},
            "training_cutoff": market[start-1],
            "patterns": [{"hop": h, "kind": k, "size": s, "n": len(v),
                          "score": (sum(v)+10*mean(pooled[h]))/(len(v)+10)}
                         for (h,k,s),v in sorted(training.items()) if len(v)>=5],
            "performance": report, "orders": ledgers, "changes_vs_trend": changes}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("graph", "archive", "later"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--start", default=START)
    args = parser.parse_args()
    print(json.dumps(run(load(args.graph), args.archive, args.later, args.start), ensure_ascii=False))
