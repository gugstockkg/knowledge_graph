"""Compare direct and graph-linked signals from the Neo4j economic-event snapshot."""
import argparse
import csv
import json
import math
import random
from bisect import bisect_left
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from statistics import fmean

from .trace_backtest import backtest, classification, get_series, load_json, portfolio_metrics, price_features, rank_one, train

ANCHORS = {"00126380": "005930", "00164779": "000660"}
TEST_START = "2026-10-01"
ARCHIVE_TEST_END = "2026-11-06"
TEST_END = "2026-11-26"
EVALUATION_PRICE_WINDOWS = (
    ("train", "2026-01-01", "2026-06-30", "archive"),
    ("validation", "2026-07-01", "2026-08-31", "archive"),
    ("test", TEST_START, ARCHIVE_TEST_END, "archive"),
    ("test", "2026-11-07", TEST_END, "later"),
)
FEATURES = {
    "price": ("return_1", "return_5", "return_20", "volume_ratio_20"),
    "direct": ("contract_count", "amendment_count", "facility_count", "earnings_filing_count",
               "log_max_reported_ratio", "log_planned_investment_billions"),
    "roles": ("buyer_notice_count", "same_notice_counterparties", "prior_active_counterparties"),
    "graph": ("partner_contracts", "partner_facilities", "partner_earnings"),
}
MODEL_WIDTHS = {name: sum(len(FEATURES[key]) for key in tuple(FEATURES)[:i + 1])
                for i, name in enumerate(FEATURES)}


def graph_events(graph):
    direct = defaultdict(dict)
    notices = defaultdict(list)
    histories = defaultdict(list)
    symbols = dict(ANCHORS)

    def add(party, record, kind):
        code = party["corp_code"]
        symbol = party["stock_code"]
        if symbol:
            if code in symbols and symbols[code] != symbol:
                raise ValueError(f"Inconsistent graph stock code for {code}")
            symbols[code] = symbol
        direct[record["day"]][code, record["receipt"]] = (kind, record)

    for record in graph["contract_terms"]:
        add(record["supplier"], record, record["kind"])
        notices[record["day"]].append(record)
        histories[record["contract"]].append(record)
        if buyer := record["buyer"]:
            if buyer["stock_code"]:
                symbols.setdefault(buyer["corp_code"], buyer["stock_code"])
    for key, kind in (("investments", "facility"), ("financials", "earnings")):
        for record in graph[key]:
            add(record["company"], record, kind)
    return direct, notices, histories, symbols


def active_contract(history, day):
    original = history[0]
    if original["kind"] != "original" or original["day"] >= day or not original["buyer"]:
        return False
    terms = {}
    for field in ("start", "end"):
        selected = None
        values = set()
        for item in history:
            if item["day"] >= day:
                break
            if item[field]:
                if selected != item["day"]:
                    selected, values = item["day"], set()
                values.add(item[field])
        if len(values) != 1:
            return False
        terms[field] = values.pop()
    return terms["start"] <= day <= terms["end"]


def build_rows(graph, archived_prices, later_prices):
    direct, notices, histories, symbols = graph_events(graph)
    histories = [sorted(history, key=lambda item: (item["day"], item["kind"] != "original", item["receipt"]))
                 for history in histories.values()]
    event_days = sorted(set(direct) | set(notices))
    prices_for = lru_cache(maxsize=None)(get_series)
    all_rows, calendars, risk_benchmarks = {}, {}, {}
    audit = {}

    for split, start, end, source in EVALUATION_PRICE_WINDOWS:
        root = later_prices if source == "later" else archived_prices
        indexes = {name: load_json(root / f"{name}.json")["bars"] for name in ("KOSPI", "KOSDAQ")}
        market = tuple(bar["date"] for bar in indexes["KOSPI"])
        if market != tuple(bar["date"] for bar in indexes["KOSDAQ"]) or market != tuple(sorted(set(market))):
            raise ValueError(f"Index calendars disagree: {split}")
        calendar = [day for day in market if start <= day <= end]
        if len(calendar) < 2:
            raise ValueError(f"Missing market dates: {split}")
        calendars.setdefault(split, []).extend(calendar)
        benchmark = risk_benchmarks.setdefault(split, defaultdict(list))
        for name, bars in indexes.items():
            benchmark[name].extend(bar["close"] / bar["open"] - 1 for bar in bars if bar["date"] in calendar)
        all_rows.setdefault(split, [])
        stats = audit.setdefault(split, Counter())
        for entry in calendar:
            pos = bisect_left(market, entry)
            if pos == 0:
                continue
            cutoff = market[pos - 1]
            floor = TEST_START if split == "test" else start
            candidates = set(ANCHORS)
            own = defaultdict(dict)
            observed_buyers = Counter()
            present = defaultdict(set)
            old_partners = defaultdict(set)
            partner_events = defaultdict(set)
            for release in event_days[bisect_left(event_days, max(cutoff, floor)):bisect_left(event_days, entry)]:
                all_direct = defaultdict(dict)
                for (company, receipt), fact in direct[release].items():
                    own[company][receipt] = fact
                    all_direct[company][receipt] = fact
                    candidates.add(company)
                for item in notices[release]:
                    if buyer := item["buyer"]:
                        b, s = buyer["corp_code"], item["supplier"]["corp_code"]
                        observed_buyers[b] += 1
                        present[b].add(s)
                        present[s].add(b)
                        candidates.add(b)
                for history in histories:
                    if active_contract(history, release):
                        origin = history[0]
                        s, b = origin["supplier"]["corp_code"], origin["buyer"]["corp_code"]
                        for company, partner in ((s, b), (b, s)):
                            old_partners[company].add(partner)
                            partner_events[company].update(
                                (partner, receipt, kind) for receipt, (kind, _) in all_direct[partner].items()
                            )
            for code in sorted(candidates):
                symbol = symbols.get(code)
                stats["candidate_stock_days"] += 1
                bars = prices_for(root, symbol, code)
                trailing = price_features(bars, cutoff, market)
                if trailing is None:
                    stats["prices_or_history_unavailable"] += 1
                    continue
                bar = bars.get(entry)
                if not bar or not bar["is_tradable"] or min(bar["open"], bar["close"]) <= 0:
                    stats["entry_prices_unavailable"] += 1
                    continue
                counts = Counter(kind for kind, _ in own[code].values())
                ratios = [item["ratio"] for _, item in own[code].values()
                          if item.get("ratio") is not None]
                facility = sum(item["value"] for kind, item in own[code].values() if kind == "facility")
                partner_counts = Counter(kind for _, _, kind in partner_events[code])
                all_rows[split].append({
                    "date": entry, "symbol": symbol, "code": code, "return": bar["close"] / bar["open"] - 1,
                    "source_counts": [sum(counts.values()), observed_buyers[code], sum(partner_counts.values())],
                    "features": [*trailing, *(counts[kind] for kind in ("original", "amendment", "facility", "earnings")),
                                 math.log1p(max([0, *ratios])), math.log1p(facility / 1_000_000_000),
                                 observed_buyers[code], len(present[code]), len(old_partners[code]),
                                 partner_counts["original"] + partner_counts["amendment"],
                                 partner_counts["facility"], partner_counts["earnings"]],
                })
    return all_rows, calendars, audit, risk_benchmarks


def summarize(scored, days):
    return {**classification(scored), "portfolios": {str(cost): backtest(scored, days, cost) for cost in (0, 20, 40)},
            "top_one_20bp": rank_one(scored, days)}


def paired_day_bootstrap(left, right, days):
    daily = defaultdict(list)
    for (row, l), (other, r) in zip(left, right):
        if row is not other:
            raise ValueError("Comparison must use matched rows")
        up = row["return"] > 0
        daily[row["date"]].append(int((l >= .5) == up) - int((r >= .5) == up))
    groups = [(sum(daily[day]), len(daily[day])) for day in days]
    rng = random.Random(27)
    draws = []
    for _ in range(2000):
        sample = rng.choices(groups, k=len(groups))
        size = sum(count for _, count in sample)
        if size:
            draws.append(sum(value for value, _ in sample) / size)
    draws.sort()
    return [draws[int((len(draws) - 1) * q)] for q in (.025, .975)]


def compare_legacy(path, scores, days):
    legacy = {}
    with path.open(encoding="utf-8", newline="") as source:
        for row in csv.DictReader(source):
            if row["model"] == "graph":
                legacy[row["session"], row["symbol"]] = (float(row["realized_return"]), float(row["score"]))
    old_scored, new_scored = [], []
    for row, score in scores:
        key = row["date"], row["symbol"]
        if key in legacy:
            realized, old_probability = legacy[key]
            if not math.isclose(realized, row["return"], abs_tol=1e-12):
                raise ValueError(f"Historical label changed for {key}")
            old_scored.append((row, old_probability))
            new_scored.append((row, score))
    return {"rows": len(old_scored), "symbols": len({row["symbol"] for row, _ in old_scored}),
            "old": summarize(old_scored, days), "revised": summarize(new_scored, days)}


def run(graph, archive, later, legacy_scores=None):
    rows, days, audit, index = build_rows(graph, archive, later)
    models, params = {}, {}
    for name, columns in MODEL_WIDTHS.items():
        variants = []
        for penalty in (.01, .1, 1.):
            predict = train(rows["train"], columns, penalty)
            validated = classification([(row, predict(row)) for row in rows["validation"]])
            variants.append((validated["balanced_accuracy"], penalty))
        validation_score, penalty = max(variants)
        params[name] = dict(penalty=penalty, validation_balanced_accuracy=validation_score)
        models[name] = train(rows["train"] + rows["validation"], columns, penalty)
    result = {"snapshot": graph["snapshot"], "audit": audit, "model_parameters": params,
              "splits": {name: dict(rows=len(part), symbols=len({r["symbol"] for r in part}),
                                    ups=sum(r["return"] > 0 for r in part), days=days[name])
                         for name, part in rows.items()},
              "evaluations": {}}
    split = "test"
    sample = rows[split]
    scores = {k: [(r, m(r)) for r in sample] for k, m in models.items()}
    outcomes = {"models": {k: summarize(scored, days[split]) for k, scored in scores.items()},
                "always_non_up_accuracy": fmean(r["return"] <= 0 for r in sample),
                "accuracy_graph_minus_direct_ci": paired_day_bootstrap(scores["graph"], scores["direct"], days[split]),
                "index_intraday": {name: portfolio_metrics(returns) for name, returns in index[split].items()},
                "anchors": {}}
    for code, symbol in ANCHORS.items():
        part = [r for r in sample if r["code"] == code]
        if not part:
            continue
        risks = {}
        for name, predict in models.items():
            scored = [(r, predict(r)) for r in part]
            risks[name] = {"correct": sum((p >= .5) == (r["return"] > 0) for r, p in scored),
                           "portfolio": backtest(scored, days[split], 20)}
        outcomes["anchors"][symbol] = dict(rows=len(part), ups=sum(r["return"] > 0 for r in part),
            source_days=[sum(r["source_counts"][i] > 0 for r in part) for i in range(3)],
            models=risks)
    if legacy_scores:
        legacy_days = [day for day in days[split] if day <= ARCHIVE_TEST_END]
        outcomes["legacy_common_rows"] = compare_legacy(legacy_scores, scores["graph"], legacy_days)
    result["evaluations"][split] = outcomes
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--later", type=Path, required=True)
    parser.add_argument("--legacy-scores", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(load_json(args.graph), args.archive, args.later, args.legacy_scores)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
