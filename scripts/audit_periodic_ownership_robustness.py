"""Compare periodic ownership definitions and a filing-blind entry delay."""

import argparse
import json
import random
from collections import Counter
from decimal import Decimal
from pathlib import Path
from statistics import mean
from unittest.mock import patch

import backtest_periodic_ownership as backtest
from backtest_governance_integration import replay


def end_to_end(pair):
    if pair["kind"] == "holder_replacement":
        return pair["kind"]
    previous = pair["previous"].get("closing_ratio")
    current = pair["current"].get("closing_ratio")
    if previous is None or current is None:
        return "missing"
    return "same_holder_ratio_change" if Decimal(previous) != Decimal(current) else "same_holder"


def run(graph, archive, later, pairs, inventory, bucket):
    changed = []
    original_ratio = set()
    end_ratio = set()
    for row in pairs:
        receipt = row["current"]["receipt"]
        alternative = end_to_end(row)
        if row["kind"] == "same_holder_ratio_change":
            original_ratio.add(receipt)
        if alternative == "same_holder_ratio_change":
            end_ratio.add(receipt)
        if row["kind"] != "same_holder" or alternative == "same_holder_ratio_change":
            changed.append({**row, "kind": "holder_replacement"
                            if row["kind"] == "holder_replacement"
                            else "same_holder_ratio_change"})
    contexts = {}

    def record(symbol, strategy, condition, decisions, candidates, dates, bars):
        if candidates:
            contexts[strategy, candidates[0]["receipt"]] = (
                symbol, strategy, decisions, dates, bars)
        return replay(symbol, strategy, condition, decisions, candidates, dates, bars)

    # Case XML checks are performed separately for the seven holder-name changes.
    with patch.object(backtest, "replay", record), patch.object(
        backtest, "source_evidence", return_value={}
    ):
        data = backtest.run(graph, archive, later, changed, inventory, bucket)
    result = {"defined": {"opening_closing": len(original_ratio),
                         "closing_closing": len(end_ratio),
                         "both": len(original_ratio & end_ratio)}, "strategies": {}}
    ledger = []
    for strategy in ("CLEAR", "TRACE"):
        available = [r for r in data["results"] if r["strategy"] == strategy
                     and r["kind"] != "holder_replacement"]
        summary, placebo_pool = {}, []
        for r in available:
            receipt = r["current"]["receipt"]
            base, gated = (r["policies"][k] for k in ("base", "any_change"))
            row = {"receipt": receipt, "symbol": r["symbol"], "strategy": strategy,
                   "window": r["window"], "training_cutoff": r["cutoff"],
                   "opening_closing": receipt in original_ratio,
                   "closing_closing": receipt in end_ratio,
                   "baseline_return": base["return"], "delayed_return": gated["return"],
                   "delay": gated["delays"]}
            ledger.append(row)
            if receipt not in original_ratio:
                continue
            symbol, name, decisions, dates, bars = contexts[strategy, receipt]
            day_index = {day: i for day, i, *_ in decisions}
            alternatives = []
            for order in base["orders"]:
                day = order["date"]
                if order["side"] != "buy" or day == dates[-1]:
                    continue
                curve, _, _, delays = replay(symbol, name, "title", decisions,
                    [{"receipt": "placebo", "i": day_index[day]}], dates, bars)
                if delays:
                    alternatives.append(curve[-1] - 1 - base["return"])
            if alternatives:
                placebo_pool.append((receipt, alternatives))
                row["placebo_deltas"] = alternatives
        for label, receipts in (("opening_closing", original_ratio),
                                ("closing_closing", end_ratio),
                                ("common", original_ratio & end_ratio)):
            sample = [r for r in available if r["current"]["receipt"] in receipts]
            summary[label] = {
                "windows": len(sample),
                "orders": sum(r["overlap"] for r in sample),
                "outcomes": dict(Counter(d["outcome"] for r in sample
                    for d in r["policies"]["any_change"]["delays"])),
                "mean_delta": mean(r["policies"]["any_change"]["return"] -
                                    r["policies"]["base"]["return"] for r in sample),
            }
        n = summary["opening_closing"]["orders"]
        rng = random.Random(20261128)
        normalizer = summary["opening_closing"]["windows"]
        draws = sorted(sum(rng.choice(options) for _, options in rng.sample(placebo_pool, n))
                       / normalizer for _ in range(2000))
        summary["placebo"] = {"eligible_windows": len(placebo_pool), "delays": n,
            "seed": 20261128, "draws": len(draws), "mean": mean(draws),
            "p025": draws[49], "p975": draws[1949]}
        result["strategies"][strategy] = summary
    return {"summary": result, "ledger": ledger}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("graph", "archive", "later", "pairs", "inventory"):
        parser.add_argument(name, type=Path)
    parser.add_argument("bucket")
    args = vars(parser.parse_args())
    for name in ("graph", "pairs"):
        args[name] = json.loads(args[name].read_text())
    print(json.dumps(run(**args), ensure_ascii=False, indent=2))
