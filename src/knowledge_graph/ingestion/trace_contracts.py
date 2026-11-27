"""Build an offline, evidence-linked supply-contract cohort for TRACE-style research."""

import argparse
import json
import re
import zipfile
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from ..config import get_paths
from ..market.prices import canonical_name
from .contract_pilot import (
    MARKETS, TableRows, buyer_lookup_name, compact, date_iso, field,
    is_subsidiary_report, json_save, parse_contract, read_archive,
)

ORIGINAL_TITLE = "단일판매공급계약체결"
ROLE_LABELS = {"계약상대", "계약상대방"}


def read_index(collections, start, end, listed_markets=MARKETS):
    """Use filing observations available by the contract date for party identity."""
    filings = {}
    observations = defaultdict(dict)
    for collection in collections:
        path = collection / "filings.json"
        if not path.is_file():
            continue
        with path.open(encoding="utf-8") as source:
            for row in json.load(source):
                observed = date_iso(row["rcept_dt"])
                if observed > end:
                    continue
                company = row.get("corp_code", "")
                receipt = row["rcept_no"]
                symbol = row.get("stock_code", "")
                name = canonical_name(row["corp_name"])
                if (row.get("corp_cls") in listed_markets and re.fullmatch(r"\d{8}", company)
                        and re.fullmatch(r"\d{6}", symbol) and symbol != "000000"):
                    key = (company, symbol)
                    previous = observations[name].get(key)
                    if previous is None or (observed, receipt) < (previous["date"], previous["receipt"]):
                        observations[name][key] = {"corp_code": company, "symbol": symbol,
                                                   "date": observed, "receipt": receipt}
                if not start <= observed or compact(row["report_nm"]) != ORIGINAL_TITLE:
                    continue
                if row.get("corp_cls") not in listed_markets or not re.fullmatch(r"\d{8}", company):
                    continue
                archive = collection / "documents" / company / (receipt + ".zip")
                if receipt not in filings or (archive.is_file() and not filings[receipt][1].is_file()):
                    filings[receipt] = row, archive
    return filings, observations


def buyer_cell(document):
    parser = TableRows()
    parser.feed(document)
    cells = []
    for row in parser.rows:
        for index, (label, _, _) in enumerate(row[:-1]):
            label = re.sub(r"^\d+\.\s*", "", label)
            if compact(label) in ROLE_LABELS:
                text, line, _ = row[index + 1]
                if text.strip(" -–—－"):
                    cells.append((text, line))
    return cells


def collect(collections, start, end, listed_markets=MARKETS):
    filings, observed = read_index(collections, start, end, listed_markets)
    counts = Counter(title_candidates=len(filings))
    events = []
    for receipt, (row, archive) in sorted(filings.items()):
        if not archive.is_file():
            counts["no_zip"] += 1
            continue
        try:
            document, member, digest = read_archive(archive, receipt)
            fields = parse_contract(document)
        except (ValueError, OSError, zipfile.BadZipFile):
            counts["unreadable_zip"] += 1
            continue
        if is_subsidiary_report(row["report_nm"], fields):
            counts["subsidiary_or_proxy"] += 1
            continue
        if not field(fields, "description"):
            counts["missing_contract_description"] += 1
            continue
        filing_date = date_iso(row["rcept_dt"])
        cells = buyer_cell(document)
        buyer = None
        evidence = None
        if len(cells) == 1:
            text, line = cells[0]
            evidence = {"text": text, "line": line}
            candidates = [match for match in observed.get(buyer_lookup_name(text), {}).values()
                          if match["date"] <= filing_date]
            # Reject aliases reused by more than one issuer or security.
            if len(candidates) == 1 and candidates[0]["corp_code"] != row["corp_code"]:
                buyer = candidates[0]
        state = ("matched_by_filing_date" if buyer else
                 "ambiguous_buyer_cell" if len(cells) > 1 else
                 "unresolved_buyer" if evidence else "no_buyer_cell")
        counts[state] += 1
        events.append({
            "receipt": receipt, "filing_date": filing_date,
            "supplier": {"corp_code": row["corp_code"], "name": row["corp_name"],
                         "symbol": row.get("stock_code") or ""},
            "document_member": member, "document_sha256": digest,
            "description": fields["description"], "amount_krw": fields.get("amount_krw"),
            "reported_sales_pct": fields.get("reported_sales_pct"),
            "conditional": fields.get("conditional"),
            "buyer_evidence": evidence, "buyer": buyer, "buyer_status": state,
        })
    counts["events"] = len(events)
    return events, dict(counts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2026-01-01")
    parser.add_argument("--end", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    start, end = date.fromisoformat(args.start).isoformat(), date.fromisoformat(args.end).isoformat()
    if end < start:
        parser.error("end must be on or after start")
    collections = sorted(get_paths().raw.glob("collections/*"))
    events, counts = collect(collections, start, end)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    json_save(args.output, {"start": start, "end": end, "counts": counts, "events": events})
    print(json.dumps(counts, ensure_ascii=False))


if __name__ == "__main__":
    main()
