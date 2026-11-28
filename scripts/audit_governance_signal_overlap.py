"""Audit overlap between recorded CLEAR/TRACE decisions and point-in-time DART filings."""

import argparse
import csv
import gzip
import hashlib
import io
import json
import re
import subprocess
from bisect import bisect_right
from collections import Counter, defaultdict
from pathlib import Path
from zipfile import ZipFile

from extract_ownership_inventory import extract_fields, family

FILINGS = re.compile(
    rb"<urn:fintos:opendart:filing:(\d{14})> <urn:fintos:opendart:([^>]+)> (.+) \."
)
COMPANIES = re.compile(rb"<urn:fintos:opendart:company:(\d+)>")
SYMBOLS = {
    "005930": "삼성전자",
    "000660": "SK하이닉스",
    "010140": "삼성중공업",
    "329180": "HD현대중공업",
    "000720": "현대건설",
    "028260": "삼성물산",
    "009150": "삼성전기",
}
MAIN = {"explicit_buyer_path": "CLEAR", "trace": "TRACE"}
PREDICATES = {
    "receiptDate",
    "reportTitle",
    "aboutCompany",
    "corrects",
    "reportsEvent",
    "reportsSameTransaction",
    "supportsEvent",
}


def csv_rows(path, compressed=False):
    opener = gzip.open if compressed else open
    with opener(path, "rt", encoding="utf-8-sig", newline="") as handle:
        yield from csv.DictReader(handle)


def company_codes(path):
    codes = {}
    for row in csv_rows(path, compressed=True):
        if "Company" in json.loads(row["LABELS_JSON"]):
            props = json.loads(row["PROPERTIES_JSON"])
            symbol = props.get("stock_code")
            if symbol in SYMBOLS:
                if symbol in codes and codes[symbol] != props["corp_code"]:
                    raise ValueError(f"Ambiguous company for {symbol}")
                codes[symbol] = props["corp_code"]
    if codes.keys() != SYMBOLS.keys():
        raise ValueError("Missing a sample company in the LPG snapshot")
    return {corp: symbol for symbol, corp in codes.items()}


def graph_filings(rdf, codes):
    receipts = {}
    with gzip.open(rdf, "rb") as handle:
        for line in handle:
            if b"> <urn:fintos:opendart:aboutCompany> " not in line:
                continue
            match = FILINGS.match(line)
            if match:
                corp = COMPANIES.fullmatch(match[3])
                if corp and corp[1].decode() in codes:
                    receipts[match[1]] = {"symbol": codes[corp[1].decode()]}
    with gzip.open(rdf, "rb") as handle:
        for line in handle:
            match = FILINGS.match(line)
            if not match or match[1] not in receipts:
                continue
            predicate = match[2].decode()
            if predicate in PREDICATES - {"aboutCompany"}:
                receipts[match[1]].setdefault(predicate, []).append(match[3].decode())
    return {key.decode(): value for key, value in receipts.items()}


def literal(value):
    return json.JSONDecoder().raw_decode(value)[0]


def source_evidence(receipt, record, title, bucket):
    key = record["s3_key"]
    payload = subprocess.check_output(
        ["aws", "s3", "cp", f"s3://{bucket}/{key}", "-", "--only-show-errors"]
    )
    if key.lower().endswith(".zip"):
        with ZipFile(io.BytesIO(payload)) as archive:
            (member,) = [
                n
                for n in archive.namelist()
                if n.rsplit("/", 1)[-1] == receipt + ".xml"
            ]
            payload = archive.read(member)
    digest = hashlib.sha256(payload).hexdigest()
    if digest != record["sha256"]:
        raise ValueError(f"XML hash mismatch: {receipt}")
    try:
        source = payload.decode("utf-8-sig")
    except UnicodeDecodeError:
        source = payload.decode("cp949")
    replay = extract_fields(source, record["kind"], "정정" in title.split("]", 1)[0])
    if replay != record["facts"]:
        raise ValueError(f"Extracted fields do not match the snapshot: {receipt}")
    xml_lines = source.splitlines()
    facts = [fact for fact in record["facts"] if fact.get("line")]
    for fact in facts:
        if not 1 <= fact["line"] <= len(xml_lines):
            raise ValueError(f"Invalid line for {receipt}")
    return {
        "sha256": digest,
        "fields": [{"field": fact["field"], "line": fact["line"]} for fact in facts],
    }


def compare(ledgers, filings):
    decisions = {
        (r["strategy"], r["symbol"], r["date"]): int(r["net_signal"])
        for r in csv_rows(ledgers / "daily-decisions.csv")
        if r["symbol"] in SYMBOLS and r["strategy"] in MAIN.values()
    }
    sessions = sorted({date for _, _, date in decisions})
    if len(sessions) != 39 or len(decisions) != 2 * 7 * 39:
        raise ValueError("Unexpected decision panel")
    new = {
        (r["strategy"], r["symbol"], r["date"])
        for r in csv_rows(ledgers / "filing-audit.csv")
        if r["adopted"] == "1" and r["symbol"] in SYMBOLS
    }
    order_rows = {
        (MAIN[r["strategy"]], r["symbol"], r["date"]): r
        for r in csv_rows(ledgers / "main-orders.csv")
        if r["strategy"] in MAIN
        and r["symbol"] in SYMBOLS
        and r["side"] == "buy"
        and r["session"] == "open"
    }
    documents, same_day = [], defaultdict(list)
    for receipt, row in filings.items():
        if not row.get("reportTitle") or not row.get("receiptDate"):
            continue
        title = literal(row["reportTitle"][0])
        kind = family(title)
        filed = literal(row["receiptDate"][0])
        if not kind or not sessions[0] <= filed < sessions[-1]:
            continue
        date = sessions[bisect_right(sessions, filed)]
        edges = {
            k: [v.strip("<>").rsplit(":", 1)[-1] for v in row[k]]
            for k in (
                "corrects",
                "reportsEvent",
                "reportsSameTransaction",
                "supportsEvent",
            )
            if row.get(k)
        }
        doc = {
            "receipt": receipt,
            "symbol": row["symbol"],
            "title": title,
            "family": kind,
            "filed": filed,
            "effective": date,
            "links": edges,
            "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}",
        }
        documents.append(doc)
        same_day[row["symbol"], date].append(doc)
    results, overlaps = [], []
    for strategy in MAIN.values():
        for symbol, name in SYMBOLS.items():
            counts = Counter()
            for index, date in enumerate(sessions):
                key = strategy, symbol, date
                items = same_day[symbol, date]
                recent = [
                    d
                    for day in sessions[max(0, index - 4) : index + 1]
                    for d in same_day[symbol, day]
                ]
                counts["signal_days"] += decisions[key] != 0
                counts["new_signal_days"] += key in new
                counts["buy_orders"] += key in order_rows
                hits = {
                    "new_overlap": items if key in new else [],
                    "active_overlap": items if decisions[key] else [],
                    "buy_overlap": recent if key in order_rows else [],
                    "buy_with_active_signal_overlap": recent
                    if key in order_rows and decisions[key]
                    else [],
                }
                for mode, matched in hits.items():
                    if matched:
                        counts[mode] += 1
                        overlaps.append(
                            {
                                "mode": mode,
                                "strategy": strategy,
                                "symbol": symbol,
                                "date": date,
                                "signal": decisions[key],
                                "order": order_rows.get(key),
                                "receipts": sorted({doc["receipt"] for doc in matched}),
                            }
                        )
            results.append(
                {
                    "strategy": strategy,
                    "symbol": symbol,
                    "name": name,
                    **counts,
                }
            )
    return {
        "sessions": len(sessions),
        "stock_days": len(sessions) * len(SYMBOLS),
        "counts": results,
        "documents": sorted(documents, key=lambda d: d["receipt"]),
        "overlaps": overlaps,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledgers", type=Path)
    parser.add_argument("lpg_nodes", type=Path)
    parser.add_argument("rdf", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--ownership", type=Path)
    parser.add_argument("--bucket")
    args = parser.parse_args()
    result = compare(
        args.ledgers, graph_filings(args.rdf, company_codes(args.lpg_nodes))
    )
    if args.ownership and args.bucket:
        with args.ownership.open() as handle:
            ids = {receipt for row in result["overlaps"] for receipt in row["receipts"]}
            evidence = {
                r["receipt"]: r for r in map(json.loads, handle) if r["receipt"] in ids
            }
        for doc in result["documents"]:
            receipt = doc["receipt"]
            if receipt in evidence and evidence[receipt].get("sha256"):
                doc["verified_xml"] = source_evidence(
                    receipt, evidence[receipt], doc["title"], args.bucket
                )
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "documents": len(result["documents"]),
                "overlaps": len(result["overlaps"]),
                "families": Counter(d["family"] for d in result["documents"]),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
