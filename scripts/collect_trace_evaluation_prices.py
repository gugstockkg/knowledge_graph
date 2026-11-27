"""Fetch later TRACE evaluation bars for the event universe and two anchor stocks."""
import argparse
import hashlib
import json
import time
from collections import defaultdict, Counter
from pathlib import Path
from urllib.error import HTTPError

from knowledge_graph.market.prices import canonical_name, fetch_chart, parse_chart

def collect(graph_path, old, out, start, end, release_floor):
    graph = json.loads(graph_path.read_text())
    out.mkdir(parents=True, exist_ok=True)
    symbols = defaultdict(dict)
    def add(party):
        if party and party["stock_code"]:
            symbols[party["stock_code"]][party["corp_code"]] = party["name"]
    for row in graph["contract_terms"]:
        if release_floor <= row["day"] <= end:
            add(row["supplier"])
            add(row["buyer"])
    for key in ("financials", "investments"):
        for row in graph[key]:
            if release_floor <= row["day"] <= end:
                add(row["company"])
    for symbol in ("005930", "000660"):
        for i in json.loads((old / f"{symbol}.json").read_text())["identities"]:
            symbols[symbol][i["corp_code"]] = i["name"]
    counts = Counter()
    errors = {}
    for symbol in ("KOSPI", "KOSDAQ", *sorted(symbols)):
        path = out / f"{symbol}.json"
        if path.is_file():
            counts["cached"] += 1
            continue
        try:
            body, url = fetch_chart(symbol, count=180)
            chart, bars = parse_chart(body, symbol, start, end, index=symbol not in symbols)
            identities = [{"corp_code": code, "name": name} for code, name in symbols.get(symbol, {}).items()]
            confirmed = len(identities) == 1 and canonical_name(identities[0]["name"]) == canonical_name(chart.get("name", ""))
            status = "index" if symbol not in symbols else "name_match" if confirmed else "identity_review"
            if not bars:
                status = "no_bars"
            path.write_text(json.dumps(dict(symbol=symbol, identities=identities, status=status, bars=bars,
                                            source_url=url, sha256=hashlib.sha256(body).hexdigest()), ensure_ascii=False))
            counts[status] += 1
        except (ValueError, OSError) as exc:
            errors[symbol] = str(exc)[:175]
            if symbol in ("KOSPI", "KOSDAQ") or isinstance(exc, HTTPError) and exc.code in (403, 429):
                break
        finally:
            time.sleep(.82)
        if sum(counts.values()) % 25 == 0:
            print(dict(counts), flush=True)
    (out / "manifest.json").write_text(json.dumps(dict(requested=len(symbols)+2, counts=counts, errors=errors)))
    print(dict(counts), len(errors), flush=True)
    return bool(errors)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start", default="2026-09-01")
    parser.add_argument("--end", default="2026-11-26")
    parser.add_argument("--release-floor", default="2026-11-06")
    args = parser.parse_args()
    raise SystemExit(collect(args.graph, args.archive, args.output, args.start, args.end, args.release_floor))
