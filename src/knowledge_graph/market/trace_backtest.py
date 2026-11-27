"""Fit and evaluate point-in-time supply-contract stock-direction baselines."""

import argparse
import csv
import json
import math
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from pathlib import Path
from statistics import fmean, stdev

PRICE = 4
DIRECT = PRICE + 3
COSTS = (0, 20, 40)
MODELS = {"price": PRICE, "direct": DIRECT, "graph": DIRECT + 5}
FEATURES = (
    "momentum_1", "momentum_5", "momentum_20", "volume_ratio_20",
    "direct_filing_count", "log_direct_sales_pct_max", "direct_sales_pct_count",
    "buyer_exposure_count", "unique_counterparty_count", "counterparty_momentum_5",
    "counterparty_momentum_count", "previous_pair_count",
)
SPLITS = {
    "train": ("2026-01-01", "2026-06-30"),
    "validation": ("2026-07-01", "2026-08-31"),
    "test": ("2026-10-01", "2026-11-06"),
}


def load_json(path):
    with path.open(encoding="utf-8") as source:
        return json.load(source)


def partition(filing, entry):
    for split, (start, end) in SPLITS.items():
        if start <= filing <= entry <= end:
            return split
    return None


def get_series(root, symbol, code):
    if not symbol or not (path := root / f"{symbol}.json").is_file():
        return None
    data = load_json(path)
    if data["status"] != "name_match" or {x["corp_code"] for x in data["identities"]} != {code}:
        return None
    bars = {bar["date"]: bar for bar in data["bars"]}
    return bars


def price_features(bars, cutoff, market_days):
    last = bisect_right(market_days, cutoff) - 1
    if bars is None or last < 20:
        return None
    window = [bars.get(day) for day in market_days[last - 20 : last + 1]]
    if not all(bar and bar["is_tradable"] and bar["close"] > 0 for bar in window):
        return None
    recent = window[-1]
    return [
        *(recent["close"] / window[-1 - days]["close"] - 1 for days in (1, 5, 20)),
        math.log1p(recent["volume"]) - math.log1p(fmean(bar["volume"] for bar in window[:-1])),
    ]


def build_dataset(contracts, price_dir):
    events = load_json(contracts)["events"]
    indexes = [load_json(price_dir / f"{symbol}.json") for symbol in ("KOSPI", "KOSDAQ")]
    dates = [tuple(bar["date"] for bar in data["bars"]) for data in indexes]
    if dates[0] != dates[1] or dates[0] != tuple(sorted(set(dates[0]))):
        raise ValueError("Price index calendars do not agree")
    market_days = dates[0]
    cache = {}
    prior = defaultdict(list)
    by_entry = defaultdict(list)
    audit = Counter()
    for event in events:
        day = event["filing_date"]
        position = bisect_right(market_days, day)
        supplier, buyer = event["supplier"], event["buyer"]
        if buyer:
            prior[(supplier["corp_code"], buyer["corp_code"])].append(day)
        if position == len(market_days):
            audit["submission_with_no_next_price_day"] += 1
            continue
        entry = market_days[position]
        split = partition(day, entry)
        if not split:
            audit["outside_split_or_label_crosses_boundary"] += 1
            continue
        by_entry[entry, split].append(event)
    for ledger in prior.values():
        ledger.sort()

    def prices(party):
        key = party["symbol"], party["corp_code"]
        if key not in cache:
            cache[key] = get_series(price_dir, *key)
        return cache[key]

    rows = []
    for (entry, split), filings in sorted(by_entry.items()):
        # All calendar dates strictly before entry are available overnight.
        cutoff = market_days[bisect_left(market_days, entry) - 1]
        entities = defaultdict(list)
        for event in filings:
            for side in ("supplier", "buyer"):
                if event[side]:
                    entities[event[side]["corp_code"]].append((event, side))
        for observed in entities.values():
            first, side = observed[0]
            party = first[side]
            audit["candidate_stock_days"] += 1
            bars = prices(party)
            trailing = price_features(bars, cutoff, market_days)
            if trailing is None:
                audit["missing_history_or_identity"] += 1
                continue
            bar = bars.get(entry)
            if not bar or not bar["is_tradable"] or min(bar["open"], bar["close"]) <= 0:
                audit["missing_or_untradable_entry"] += 1
                continue
            direct = [event for event, role in observed if role == "supplier"]
            counterparties = {}
            previous_pairs = set()
            for event, role in observed:
                buyer = event["buyer"]
                if buyer:
                    supplier = event["supplier"]
                    other = buyer if role == "supplier" else supplier
                    counterparties[other["corp_code"]] = other
                    previous_pairs.add((supplier["corp_code"], buyer["corp_code"]))
            # Intraday release time is unknown. Use previous session closes for price features.
            partner_returns = [past[1] for p in counterparties.values()
                               if (past := price_features(prices(p), cutoff, market_days)) is not None]
            ratios = [pc["value"] for item in direct if (pc := item["reported_sales_pct"])
                      and pc["value"] is not None and math.isfinite(pc["value"])]
            first_filing = min(event["filing_date"] for event, _ in observed)
            history = sum(bisect_left(prior[pair], first_filing) for pair in previous_pairs)
            rows.append({
                "date": entry, "split": split, "symbol": party["symbol"],
                "sources": [e["receipt"] for e, _ in observed],
                "features": [*trailing, len(direct), math.log1p(max(0, max(ratios, default=0))),
                             len(ratios), sum(role == "buyer" for _, role in observed),
                             len(counterparties), fmean(partner_returns) if partner_returns else 0,
                             len(partner_returns), history],
                "return": bar["close"] / bar["open"] - 1,
            })
    return {
        "rows": rows, "market_days": market_days, "audit": dict(audit),
        "features": FEATURES, "splits": SPLITS,
        "benchmark": {symbol: {b["date"]: b["close"] / b["open"] - 1
                              for b in series["bars"]}
                      for symbol, series in zip(("KOSPI", "KOSDAQ"), indexes)},
    }


def logistic(value):
    return 1 / (1 + math.exp(-max(-35, min(35, value))))


def train(records, columns, penalty):
    # Mean and scale come only from the training sample. The intercept is unpenalized.
    means = [fmean(row["features"][i] for row in records) for i in range(columns)]
    scales = [math.sqrt(fmean((row["features"][i] - means[i]) ** 2 for row in records)) or 1
              for i in range(columns)]

    def transform(row):
        return [1, *((value - mean) / scale
                     for value, mean, scale in zip(row["features"], means, scales))]

    data = [(transform(row), row["return"] > 0) for row in records]
    weights = [0.] * (columns + 1)
    for _ in range(450):
        gradient = [0.] * len(weights)
        for vector, actual in data:
            error = logistic(sum(weight * value for weight, value in zip(weights, vector))) - actual
            for i, value in enumerate(vector):
                gradient[i] += error * value
        for i, g in enumerate(gradient):
            weights[i] -= .15 * (g / len(data) + (penalty * weights[i] if i else 0))

    def predict(row):
        return logistic(sum(weight * value for weight, value in zip(weights, transform(row))))

    return predict


def classification(scored):
    tp = tn = fp = fn = 0
    for row, score in scored:
        up, predicted = row["return"] > 0, score >= .5
        tp += up and predicted
        tn += not up and not predicted
        fp += not up and predicted
        fn += up and not predicted
    if min(tp + fn, tn + fp) == 0:
        raise ValueError("Both classes required for balanced accuracy")
    return {
        "accuracy": (tp + tn) / len(scored),
        "balanced_accuracy": (tp / (tp + fn) + tn / (tn + fp)) / 2,
        "f1_up": (2 * tp / (2 * tp + fp + fn)) if tp else 0.,
        "confusion": [tp, tn, fp, fn],
    }


def portfolio_metrics(daily):
    values = list(daily)
    equity = peak = 1.
    drawdown = 0.
    for value in values:
        equity *= 1 + value
        peak = max(equity, peak)
        drawdown = min(drawdown, equity / peak - 1)
    volatility = stdev(values)
    return {
        "total_return": equity - 1,
        "sharpe": math.sqrt(252) * fmean(values) / volatility if volatility else None,
        "annualized_volatility": volatility * math.sqrt(252),
        "max_drawdown": drawdown,
    }


def backtest(scored, days, cost_bps):
    selected = defaultdict(list)
    for row, probability in scored:
        if probability >= .5:
            selected[row["date"]].append(row["return"])
    cost = cost_bps / 10_000
    daily = [(fmean(selected[day]) - cost) if day in selected else 0. for day in days]
    return {
        **portfolio_metrics(daily),
        "stock_entries": sum(map(len, selected.values())),
        "active_days": len(selected),
        "daily": daily,
    }


def rank_one(scored, days):
    daily = defaultdict(list)
    for row, probability in scored:
        daily[row["date"]].append((row, probability))
    selected = [min(group, key=lambda item: (-item[1], item[0]["symbol"]))[0]
                for group in daily.values()]
    return backtest([(row, 1.) for row in selected], days, cost_bps=20)


def run(data):
    rows = {split: [row for row in data["rows"] if row["split"] == split] for split in SPLITS}
    start, end = SPLITS["test"]
    days = [day for day in data["market_days"] if start <= day <= end]
    report = {
        "splits": {name: {"rows": len(part), "symbols": len({r["symbol"] for r in part}),
                         "up": sum(r["return"] > 0 for r in part),
                         "first": min(r["date"] for r in part), "last": max(r["date"] for r in part)}
                   for name, part in rows.items()},
        "test_days": days, "models": {}, "benchmarks": {}, "audit": data["audit"],
        "exploratory_top_one": {},
    }
    scores = {}
    for name, columns in MODELS.items():
        variants = []
        for penalty in (.01, .1, 1.):
            model = train(rows["train"], columns, penalty)
            metrics = classification([(row, model(row)) for row in rows["validation"]])
            variants.append((metrics["balanced_accuracy"], penalty))
        validation_ba, penalty = max(variants)
        model = train(rows["train"] + rows["validation"], columns, penalty)
        scored = [(row, model(row)) for row in rows["test"]]
        scores[name] = scored
        report["models"][name] = {
            "selected_penalty": penalty, "validation_balanced_accuracy": validation_ba,
            **classification(scored),
            "portfolios": {str(cost): backtest(scored, days, cost) for cost in COSTS},
        }
        report["exploratory_top_one"][name] = rank_one(scored, days)
    always = [(row, 1) for row in rows["test"]]
    report["benchmarks"]["all_candidates"] = {str(cost): backtest(always, days, cost) for cost in COSTS}
    for index, by_day in data["benchmark"].items():
        report["benchmarks"][index] = portfolio_metrics([by_day[day] for day in days])
    return report, scores


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--contracts", type=Path, required=True)
    prepare.add_argument("--prices", type=Path, required=True)
    fit = sub.add_parser("run")
    fit.add_argument("--dataset", type=Path, required=True)
    for command in (prepare, fit):
        command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.command == "prepare":
        result = build_dataset(args.contracts, args.prices)
    else:
        result, scores = run(load_json(args.dataset))
        with args.output.with_suffix(".scores.csv").open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["model", "session", "symbol", "realized_return", "score", "receipts"])
            for name, scored in scores.items():
                writer.writerows((name, r["date"], r["symbol"], r["return"], p, " ".join(r["sources"]))
                                 for r, p in scored)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
