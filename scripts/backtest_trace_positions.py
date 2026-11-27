"""Compare long/flat TRACE trading rules with continuous buy-and-hold."""

import argparse
import json
from bisect import bisect_right
from collections import defaultdict
from pathlib import Path
from statistics import mean

from knowledge_graph.market.economic_backtest import (
    ANCHORS,
    TEST_END,
    TEST_START,
    active_contract,
    graph_events,
)
from knowledge_graph.market.trace_backtest import get_series, portfolio_metrics


def load(path):
    return json.loads(path.read_text())


def returns(days, bars, targets, fee):
    cash, units, previous, trades = 1.0, 0.0, 1.0, 0
    daily = []
    for i, day in enumerate(days):
        bar = bars[day]
        if targets[i] and not units:
            units, cash = cash / (bar["open"] * (1 + fee)), 0
            trades += 1
        if not targets[i] and units:
            cash, units = units * bar["open"] * (1 - fee), 0
            trades += 1
        if i == len(days) - 1 and units:
            cash, units = units * bar["close"] * (1 - fee), 0
            trades += 1
        equity = cash + units * bar["close"]
        daily.append(equity / previous - 1)
        previous = equity
    return daily, trades


def signals(graph, market):
    _, notices, raw_histories, _ = graph_events(graph)
    histories = [
        sorted(h, key=lambda d: (d["day"], d["kind"] != "original", d["receipt"]))
        for h in raw_histories.values()
    ]
    by_receipt = {}
    for h in histories:
        for item in h:
            earlier = [
                prior
                for prior in h
                if prior["day"] < item["day"] and prior["amount"] is not None
            ]
            if item["kind"] == "original":
                by_receipt[item["receipt"]] = 1
            elif earlier and item["amount"] is not None:
                prior = {x["amount"] for x in earlier if x["day"] == earlier[-1]["day"]}
                if len(prior) == 1:
                    old = prior.pop()
                    by_receipt[item["receipt"]] = (item["amount"] > old) - (
                        item["amount"] < old
                    )
    result = {
        name: defaultdict(dict)
        for name in (
            "legacy_path",
            "filtered_path",
            "explicit_buyer_path",
            "named_buyer_only",
        )
    }
    for published, records in notices.items():
        release = bisect_right(market, published)
        for item in records:
            buyer = item["buyer"]
            sign = by_receipt.get(item["receipt"], 0)
            if buyer and sign:
                result["named_buyer_only"][buyer["corp_code"]][
                    release, item["receipt"]
                ] = sign
        for h in histories:
            if not active_contract(h, published):
                continue
            origin = h[0]
            seller, buyer = (origin[key]["corp_code"] for key in ("supplier", "buyer"))
            for item in records:
                source = item["supplier"]["corp_code"]
                sign = by_receipt.get(item["receipt"], 0)
                if not sign or source not in (seller, buyer):
                    continue
                target = buyer if source == seller else seller
                result["legacy_path"][target][release, item["receipt"]] = sign
                if (
                    target == buyer
                    and origin["category"]
                    and origin["category"] == item["category"]
                    and (origin["amount"] or 0) > 0
                    and origin["receipt"] != item["receipt"]
                ):
                    result["filtered_path"][target][release, item["receipt"]] = sign
                    if item["buyer"] and item["buyer"]["corp_code"] == target:
                        result["explicit_buyer_path"][target][
                            release, item["receipt"]
                        ] = sign
    return result


def exposure_timing_placebo(dates, per_stock, fee):
    """Rotate each stock's observed position, preserving its exposure and order count."""
    from itertools import product
    from math import prod

    comparable = []
    actual = []
    for bars, positions, _ in per_stock.values():
        target = positions["explicit_buyer_path"]
        daily, trade_count = returns(dates, bars, target, fee)
        actual.append(prod(1 + r for r in daily) - 1)
        alternatives = []
        for shift in range(1, len(target)):
            rotated = target[shift:] + target[:shift]
            if rotated == target:
                continue
            shifted, orders = returns(dates, bars, rotated, fee)
            if orders == trade_count:
                alternatives.append(prod(1 + r for r in shifted) - 1)
        comparable.append(alternatives)
    actual_return = sum(actual) / len(actual)
    controls = sorted(sum(p) / len(p) for p in product(*comparable))
    if not controls:
        return {"alternatives": 0, "actual_return": actual_return}
    return {
        "alternatives": len(controls),
        "actual_return": actual_return,
        "median": controls[len(controls) // 2],
        "share_below_actual": sum(v < actual_return for v in controls) / len(controls),
    }


def run(graph, archive, later, *, price_controls=False):
    indexes = {}
    for index in ("KOSPI", "KOSDAQ"):
        indexes[index] = {
            b["date"]: b
            for root in (archive, later)
            for b in load(root / f"{index}.json")["bars"]
        }
    market = sorted(indexes["KOSPI"])
    dates = [day for day in market if TEST_START <= day <= TEST_END]
    path_signals = signals(graph, market)
    per_stock = {}
    decision = {}
    for code, symbol in ANCHORS.items():
        bars = {
            **(get_series(archive, symbol, code) or {}),
            **(get_series(later, symbol, code) or {}),
        }
        if not all(bars.get(day, {}).get("is_tradable") for day in dates):
            raise ValueError(f"Missing tradable session for {symbol}")
        positions = {
            "buy_hold": [],
            "price_trend": [],
            "legacy_path": [],
            "filtered_path": [],
            "explicit_buyer_path": [],
            "named_buyer_only": [],
        }
        if price_controls:
            positions.update(sma20=[], reversion5=[])
        signal_days = defaultdict(int)
        for day in dates:
            i = market.index(day)
            price = int(bars[market[i - 1]]["close"] > bars[market[i - 21]]["close"])
            positions["buy_hold"].append(1)
            positions["price_trend"].append(price)
            if price_controls:
                prior_closes = [bars[day]["close"] for day in market[i - 20 : i]]
                positions["sma20"].append(int(prior_closes[-1] > mean(prior_closes)))
                positions["reversion5"].append(int(prior_closes[-1] < prior_closes[-6]))
                decision[symbol, day, "sma20"] = {"reason": "20_session_moving_average"}
                decision[symbol, day, "reversion5"] = {"reason": "5_session_mean_reversion"}
            decision[symbol, day, "buy_hold"] = {"reason": "continuous_equity_exposure"}
            decision[symbol, day, "price_trend"] = {
                "reason": "20_session_price_trend",
                "trend_target": price,
            }
            for name, data in path_signals.items():
                eligible = [
                    (receipt, sign)
                    for (release, receipt), sign in data[code].items()
                    if i - 4 <= release <= i
                ]
                net = sum(sign for _, sign in eligible)
                decision[symbol, day, name] = {
                    "reason": "net_contract_signal"
                    if net
                    else "20_session_price_trend",
                    "net_signal": net,
                    "trend_target": price,
                    "signal_receipts": "|".join(
                        receipt for receipt, _ in sorted(eligible)
                    ),
                }
                signal_days[name] += bool(net)
                positions[name].append(int(net > 0) if net else price)
        per_stock[symbol] = (bars, positions, dict(signal_days))
    orders = []
    for symbol, (bars, positions, _) in per_stock.items():
        for strategy, targets in positions.items():
            prior = 0
            for day, target in zip(dates, targets):
                if target != prior:
                    orders.append(
                        {
                            "date": day,
                            "symbol": symbol,
                            "strategy": strategy,
                            "side": "buy" if target else "sell",
                            "session": "open",
                            "price": bars[day]["open"],
                            **decision[symbol, day, strategy],
                        }
                    )
                prior = target
            if prior:
                orders.append(
                    {
                        "date": dates[-1],
                        "symbol": symbol,
                        "strategy": strategy,
                        "side": "sell",
                        "session": "close",
                        "price": bars[dates[-1]]["close"],
                        "reason": "end_of_evaluation",
                    }
                )
    summary = {}
    for bp in (0, 20, 40):
        for name in next(iter(per_stock.values()))[1]:
            portfolios = [
                returns(dates, bars, positions[name], bp / 20_000)
                for bars, positions, _ in per_stock.values()
            ]
            by_symbol = (
                {
                    "stock_returns": {
                        symbol: portfolio_metrics(portfolio[0])["total_return"]
                        for symbol, portfolio in zip(per_stock, portfolios)
                    }
                }
                if price_controls
                else {}
            )
            # Initial allocations are equal and each sleeve funds its own trades.
            values = [1.0] * len(portfolios)
            daily = []
            for day_returns in zip(*(p[0] for p in portfolios)):
                previous = sum(values)
                values = [v * (1 + r) for v, r in zip(values, day_returns)]
                daily.append(sum(values) / previous - 1)
            summary.setdefault(str(bp), {})[name] = {
                **portfolio_metrics(daily),
                **by_symbol,
                "order_count": sum(p[1] for p in portfolios),
                "invested_stock_days": sum(
                    sum(positions[name]) for _, positions, _ in per_stock.values()
                ),
            }
    return {
        "days": len(dates),
        "start": dates[0],
        "end": dates[-1],
        "benchmarks": {
            k: v[dates[-1]]["close"] / v[dates[0]]["open"] - 1
            for k, v in indexes.items()
        },
        "signal_days": {k: counts for k, (_, _, counts) in per_stock.items()},
        "buyer_control_position_differences": {
            symbol: sum(
                left != right
                for left, right in zip(
                    positions["explicit_buyer_path"], positions["named_buyer_only"]
                )
            )
            for symbol, (_, positions, _) in per_stock.items()
        },
        "exposure_timing_placebo": exposure_timing_placebo(dates, per_stock, 0.001),
        "positions": summary,
        "orders": orders,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("graph", "archive", "later", "output"):
        parser.add_argument(key, type=Path)
    parser.add_argument("--price-controls", action="store_true")
    a = parser.parse_args()
    result = run(load(a.graph), a.archive, a.later, price_controls=a.price_controls)
    a.output.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
