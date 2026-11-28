"""Replay CLEAR and TRACE in windows around source-linked controller corrections."""

import argparse
import json
from bisect import bisect_right
from pathlib import Path

from backtest_governance_integration import (
    base_signals, controller_candidates, graph_filings, read_rdf, replay, resource,
    source_evidence, FEE,
)
from backtest_trace_positions import get_series, load
from knowledge_graph.market.economic_backtest import graph_events


def run(graph, archive, later, rdf, inventory, bucket):
    records = {}
    with inventory.open() as stream:
        for line in stream:
            row = json.loads(line)
            if row["kind"] == "controller":
                records[row["receipt"]] = row
    _, _, _, symbols = graph_events(graph)
    companies = {row["corp_code"]: row["corp_code"] for row in records.values()}
    filings = graph_filings(rdf, companies)
    pairs = sorted(
        (receipt, original, row["symbol"])
        for receipt, row in filings.items() if receipt in records
        for target in row.get("corrects", [])
        if (original := resource(target).rsplit(":", 1)[-1]) in records
        and records[original]["corp_code"] == row["symbol"]
    )
    market = sorted({
        bar["date"] for root in (archive, later)
        for bar in load(root / "KOSPI.json")["bars"]
    })
    # Allow price-trend candidates outside the supply graph only when the
    # existing price archive identifies the same OpenDART company code.
    price_symbols = {}
    for root in (archive, later):
        for path in root.glob("*.json"):
            series = load(path)
            if series.get("status") != "name_match":
                continue
            for identity in series.get("identities", []):
                code = identity["corp_code"]
                if code in companies:
                    price_symbols.setdefault(code, set()).add(path.stem)
    target_symbols = {**symbols, **{
        code: next(iter(matches)) for code, matches in price_symbols.items()
        if code not in symbols and len(matches) == 1
    }}
    bars = {
        code: {**(get_series(archive, symbol, code) or {}),
               **(get_series(later, symbol, code) or {})}
        for code, symbol in target_symbols.items()
    }
    for row in filings.values():
        row["symbol"] = target_symbols.get(row["symbol"])
    candidates = controller_candidates(filings, read_rdf(rdf, filings), market,
                                       market[0], market[-1])
    screened, results, evidence, model = [], [], {}, {}
    for correction, original, code in pairs:
        endpoints = {correction, original}
        symbol = target_symbols.get(code)
        eligible = {row["receipt"]: row for row in candidates[symbol]
                    if row["receipt"] in endpoints and row["events"]}
        for anchor in (original, correction):
            entry = {"receipt": anchor, "original": original, "correction": correction,
                     "symbol": symbol, "filed": records[anchor]["filed"]}
            screened.append(entry)
            entry["supply_graph_company"] = code in symbols
            if symbol is None:
                entry["status"] = "no_identified_price_series"
                continue
            if anchor not in eligible:
                entry["status"] = "no_eligible_event"
                continue
            i = eligible[anchor]["i"]
            # Two-week observation window around each filing with 20-session warmup.
            if i < 26 or i + 10 >= len(market) or not all(
                bars.get(code, {}).get(day, {}).get("is_tradable")
                for day in market[i-26:i+11]
            ):
                entry["status"] = "incomplete_prices"
                continue
            dates = market[i-5:i+11]
            start, end = dates[0], dates[-1]
            if start not in model:
                model[start] = base_signals(graph, market, symbols, bars, start, market[-1])
            clear, trace, _, training, cutoff = model[start]
            entry.update(status="tested", training=training, training_cutoff=cutoff,
                         window=[start, end])
            for strategy in ("CLEAR", "TRACE"):
                decisions = []
                for j in range(i-5, i+11):
                    window = range(j-4, j+1)
                    items = (
                        [(sign, {r}) for (release, r), sign in clear[code].items()
                         if release in window]
                        if strategy == "CLEAR"
                        else [trace[code][k] for k in window if k in trace[code]]
                    )
                    net = sum(sign for sign, _ in items)
                    receipts = sorted({r for _, refs in items for r in refs})
                    trend = bars[code][market[j-1]]["close"] > bars[code][market[j-21]]["close"]
                    decisions.append((market[j], j, net > 0 if net else trend, net, receipts))
                outcomes = {}
                for condition in ("base", "explicit", "integrated"):
                    curve, _, fills, delays = replay(symbol, strategy, condition,
                                                   decisions, list(eligible.values()),
                                                   dates, bars[code])
                    outcomes[condition] = {"return": curve[-1]-1, "orders": fills,
                                           "delays": delays}
                buys = [order for order in outcomes["base"]["orders"]
                        if order["side"] == "buy" and market[i] <= order["date"] <= market[i+4]]
                changed = [delay for delay in outcomes["integrated"]["delays"]
                           if anchor in delay["governance_receipts"]]
                if buys or changed:
                    results.append({**entry, "strategy": strategy, "baseline_overlap": buys,
                                    "anchor_interventions": changed, "conditions": outcomes,
                                    "buy_hold": (bars[code][end]["close"] / bars[code][start]["open"]
                                                 * (1-FEE)/(1+FEE) - 1)})
                    for receipt in sorted(endpoints - evidence.keys()):
                        record = records[receipt]
                        title = eligible[receipt]["title"] if receipt in eligible else (
                            "[정정]" if receipt == correction else "최대주주변경")
                        evidence[receipt] = source_evidence(receipt, record, title, bucket)
    return {"controller_filings": len(records), "pairs": len(pairs),
            "screened": screened, "results": results, "evidence": evidence}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("graph", "archive", "later", "rdf", "inventory"):
        parser.add_argument(name, type=Path)
    parser.add_argument("bucket")
    args = parser.parse_args()
    inputs = vars(args)
    inputs["graph"] = load(args.graph)
    print(json.dumps(run(**inputs), ensure_ascii=False, indent=2))
