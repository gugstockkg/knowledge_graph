"""Train disclosure response patterns and replay nested CLEAR hop conditions."""

import argparse
import json
from bisect import bisect_right
from collections import defaultdict
from pathlib import Path
from statistics import mean

from backtest_governance_integration import FEE, replay, summary
from backtest_trace_positions import get_series, load, signals
from knowledge_graph.market.economic_backtest import active_contract, graph_events

START = "2026-05-01"
END = "2026-11-26"
PROJECT_PAIRS = (
    ("20260515800319", "20260324800684"),
    ("20260710900482", "20260707900767"),
    ("20260312901296", "20260326800003"),
)


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

    projects, indirect = [], defaultdict(dict)
    for upstream, downstream in PROJECT_PAIRS:
        a, j, _, _ = disclosures[upstream]
        b = disclosures[downstream][0]
        code = b["buyer"]["corp_code"]
        valid = j < len(market) and active_contract(histories[a["contract"]], market[j]) and active_contract(
            histories[b["contract"]], market[j])
        estimate = score(1, upstream)
        day = market[j] if j < len(market) else None
        projects.append({"upstream": upstream, "downstream": downstream, "symbol": symbols.get(code),
                         "session": day, "active": valid, "in_panel": code in panel,
                         "proxy_score": estimate})
        if valid and code in panel and estimate is not None:
            indirect[code][j, upstream] = estimate

    def preferences(code, j, policy):
        sources = {"existing": [(existing, None)], "learn_0": [(own, 0)],
                   "learn_01": [(own, 0), (existing, 1)],
                   "learn_012": [(own, 0), (existing, 1), (indirect, 2)]}
        scores = {}
        for source, hop in sources.get(policy, []):
            for (i, receipt), value in source[code].items():
                if not j-4 <= i <= j:
                    continue
                value = score(hop, receipt) if hop in (0, 1) else value
                if value is not None:
                    # Prefer the shortest observed path for each disclosure.
                    scores.setdefault(receipt, value)
        return sum(scores.values()), sorted(scores)

    probe = []
    for project in projects:
        if not project["active"] or project["session"] < days[0]:
            continue
        upstream = project["upstream"]
        b = disclosures[project["downstream"]][0]
        code = b["buyer"]["corp_code"]
        series = bars[code]
        j = market.index(project["session"])
        window = market[j-5:j+11]
        if len(window) != 16 or not all(
            series.get(day, {}).get("is_tradable") for day in market[j-26:j+11]
        ):
            continue
        output = {}
        for label in ("learn_01", "project_positive"):
            positions = []
            for k in range(j-5, j+11):
                net, refs = preferences(code, k, "learn_01")
                trend = series[market[k-1]]["close"] > series[market[k-21]]["close"]
                if label == "project_positive" and j <= k <= j+4 and upstream not in refs:
                    net += 1
                    refs = sorted([*refs, upstream])
                positions.append((market[k], k, net > 0 if net else trend, net, refs))
            curve, _, fills, _ = replay(symbols[code], label, "base", positions,
                                        [], window, series)
            output[label] = {"return": curve[-1]-1, "orders": fills}
        probe.append({**project, "period": [window[0], window[-1]], "results": output})

    report, ledgers = {}, {}
    for policy in ("hold", "trend", "existing", "learn_0", "learn_01", "learn_012"):
        curves, orders, stock_results, exposure = [], [], [], 0
        for code in panel:
            symbol = symbols[code]
            positions = []
            for j in range(start, start + len(days)):
                net, refs = preferences(code, j, policy)
                trend = bars[code][market[j-1]]["close"] > bars[code][market[j-21]]["close"]
                desired = policy == "hold" or (net > 0 if net else trend)
                positions.append((market[j], j, desired, net, refs))
            equity, exposed, fills, _ = replay(symbol, policy, "base", positions, [], days, bars[code])
            curves.append(equity)
            exposure += exposed
            orders.extend(fills)
            stock_results.append({"symbol": symbol, "return": equity[-1]-1, "orders": len(fills)})
        ledgers[policy] = orders
        report[policy] = {**summary(curves, exposure, orders, [], days), "stocks": stock_results}
    diffs = {}
    for x, y in (("trend", "learn_0"), ("learn_0", "learn_01"), ("learn_01", "learn_012"),
                 ("existing", "learn_01")):
        def key(row):
            return row["symbol"], row["date"], row["side"], row["session"]
        before = {key(r): r for r in ledgers[x]}
        after = {key(r): r for r in ledgers[y]}
        diffs[f"{x}:{y}"] = {"removed": [before[k] for k in sorted(before.keys()-after.keys())],
                             "added": [after[k] for k in sorted(after.keys()-before.keys())]}
    return {"period": [days[0], days[-1]], "sessions": len(days),
            "panel": sorted(symbols[c] for c in panel), "training": {k: len(v) for k,v in pooled.items()},
            "training_cutoff": market[start-1],
            "patterns": [{"hop": h, "kind": k, "size": s, "n": len(v),
                          "score": (sum(v)+10*mean(pooled[h]))/(len(v)+10)}
                         for (h,k,s),v in sorted(training.items()) if len(v)>=5],
            "performance": report, "projects": projects, "project_probe": probe, "orders": ledgers, "diffs": diffs}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("graph", "archive", "later"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--start", default=START)
    args = parser.parse_args()
    print(json.dumps(run(load(args.graph), args.archive, args.later, args.start), ensure_ascii=False))
