"""Compare entry policies around published periodic ownership observations."""

import argparse
import json
from bisect import bisect_right
from collections import Counter
from pathlib import Path

from backtest_governance_integration import FEE, base_signals, replay, source_evidence
from backtest_trace_positions import get_series, load
from knowledge_graph.market.economic_backtest import graph_events


def run(graph, archive, later, pairs, inventory, bucket):
    market = sorted({row["date"] for root in (archive, later)
                     for row in load(root / "KOSPI.json")["bars"]})
    _, _, _, symbols = graph_events(graph)
    target_symbols = {code: {symbol} for code, symbol in symbols.items()}
    companies = {row["current"]["corp"] for row in pairs}
    for root in (archive, later):
        for path in root.glob("*.json"):
            series = load(path)
            if series.get("status") != "name_match":
                continue
            for identity in series["identities"]:
                code = identity["corp_code"]
                if code in companies:
                    target_symbols.setdefault(code, set()).add(path.stem)
    bars = {}
    for code, matches in target_symbols.items():
        if len(matches) == 1:
            symbol = next(iter(matches))
            bars[code] = {**(get_series(archive, symbol, code) or {}),
                          **(get_series(later, symbol, code) or {})}
    screening = Counter()
    fits, output = {}, []
    verified, replacement_example = {}, None
    with inventory.open() as stream:
        index = {row["receipt"]: row for row in map(json.loads, stream)
                 if row["kind"] == "periodic"}
    for pair in pairs:
        kind, current = pair["kind"], pair["current"]
        if kind == "same_holder":
            continue
        code = current["corp"]
        filed = current["filed"]
        filed = f"{filed[:4]}-{filed[4:6]}-{filed[6:]}"
        i = bisect_right(market, filed)
        series = bars.get(code, {})
        # Retain late filings with a full entry window and one reevaluation day.
        stop = min(i + 11, len(market))
        if i < 26 or i + 5 >= stop or not all(
            series.get(d, {}).get("is_tradable") for d in market[i-26:stop]
        ):
            screening[kind, "incomplete"] += 1
            continue
        screening[kind, "evaluated"] += 1
        dates = market[i-5:stop]
        start, end = dates[0], dates[-1]
        if start not in fits:
            fits[start] = base_signals(graph, market,
                                      {c: s for c, s in symbols.items() if c in bars},
                                      bars, start, market[-1])
        clear, trace, _, training, cutoff = fits[start]
        candidate = {"i": i, "receipt": current["receipt"]}
        symbol = next(iter(target_symbols[code]))
        for strategy in ("CLEAR", "TRACE"):
            decisions = []
            for j in range(i-5, stop):
                window = range(j-4, j+1)
                items = (
                    [(sign, {receipt}) for (release, receipt), sign in clear[code].items()
                     if release in window]
                    if strategy == "CLEAR"
                    else [trace[code][release] for release in window if release in trace[code]]
                )
                net = sum(sign for sign, _ in items)
                refs = sorted({receipt for _, receipts in items for receipt in receipts})
                trend = series[market[j-1]]["close"] > series[market[j-21]]["close"]
                decisions.append((market[j], j, net > 0 if net else trend, net, refs))
            policies = {}
            for policy, candidates in (
                ("base", []), ("any_change", [candidate]),
                ("replacement_only", [candidate] if kind == "holder_replacement" else []),
            ):
                curve, _, fills, delays = replay(symbol, strategy,
                                               "title" if candidates else "base",
                                               decisions, candidates, dates, series)
                policies[policy] = {"return": curve[-1]-1, "orders": fills, "delays": delays}
            overlap = bool(policies["any_change"]["delays"])
            if overlap:
                screening[kind, strategy] += 1
            output.append({**pair, "symbol": symbol, "strategy": strategy,
                           "policies": policies, "window": [start, end], "cutoff": cutoff,
                           "overlap": overlap,
                           "training": training,
                           "buy_hold": series[end]["close"]/series[start]["open"]
                                       * (1-FEE)/(1+FEE)-1})
            if kind == "holder_replacement" and replacement_example is None:
                replacement_example = current["receipt"]
            if not overlap and current["receipt"] != replacement_example:
                continue
            for report in (pair["previous"], current):
                receipt = report["receipt"]
                if receipt not in verified:
                    verified[receipt] = source_evidence(receipt, index[receipt],
                                                       report["title"], bucket)
    return {"classified": dict(Counter(row["kind"] for row in pairs)),
            "screening": {f"{k}:{s}": n for (k,s),n in screening.items()},
            "results": output, "evidence": verified}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("graph", "archive", "later", "pairs", "inventory"):
        parser.add_argument(name, type=Path)
    parser.add_argument("bucket")
    args = vars(parser.parse_args())
    args["graph"] = load(args["graph"])
    args["pairs"] = load(args["pairs"])
    print(json.dumps(run(**args), ensure_ascii=False, indent=2))
