"""Link audited ownership observations to existing OpenDART controller events."""

import argparse
import calendar
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

from audit_opendart_inventory import read_metadata

from knowledge_graph.ingestion.control_ownership import name_key, parse_date

GROUP = re.compile(r"\s*[외外]\s*(?:특수관계인\s*)?\d+")


def party(value):
    return name_key(GROUP.split(value)[0])


def shares(value):
    value = value.replace(",", "").strip()
    return int(value) if value.isdecimal() else None


def as_of(title):
    match = re.search(r"\((\d{4})\.(\d{2})\)", title)
    if not match:
        return None
    year, month = map(int, match.groups())
    return date(year, month, calendar.monthrange(year, month)[1]).isoformat()


def facts(document, *fields):
    return [f for f in document["facts"] if f["field"] in fields]


def event_view(document, correction=None):
    after = [f for f in facts(document, "controller_name") if f.get("phase") == "after"]
    after_names = {party(f["value"]) for f in after} - {""}
    before_names = {
        party(f["value"])
        for f in facts(document, "controller_name")
        if f.get("phase") == "before"
    } - {""}
    change_day = next(
        (parse_date(f["value"]) for f in facts(document, "change_date")), None
    )
    reference = {}
    contract_dates = {}
    for ref in facts(document, "related_filing") + (
        facts(correction, "related_filing") if correction else []
    ):
        for match in re.finditer(
            r"(\d{4}-\d{2}-\d{2})\s+최대주주\s*변경을\s*수반하는\s*주식양수도\s*계약",
            ref["value"],
        ):
            contract_dates[match[1]] = ref
        for receipt in ref.get("references", []):
            reference[receipt] = ref
    quantity_doc = correction or document
    group = any(GROUP.search(f["value"]) for f in after)
    scoped = [
        f
        for f in facts(quantity_doc, "shares")
        if f.get("phase") == "after" and (f.get("scope") == "individual" or not group)
    ]
    quantities = {shares(f["value"]) for f in scoped} - {None, 0}
    return {
        "document": document,
        "after": after_names,
        "before": before_names,
        "date": change_day,
        "references": reference,
        "contract_dates": contract_dates,
        "quantities": quantities,
    }


def match_record(record, candidates, title):
    kind = record["kind"]
    if kind == "periodic":
        cutoff = as_of(title)
        if (
            not cutoff
            or cutoff
            > record["filed"][:4]
            + "-"
            + record["filed"][4:6]
            + "-"
            + record["filed"][6:]
        ):
            return None
        eligible = [
            e
            for e in candidates
            if e["date"]
            and e["date"] <= cutoff
            and (date.fromisoformat(cutoff) - date.fromisoformat(e["date"])).days <= 366
        ]
        if not eligible:
            return None
        latest = max(e["date"] for e in eligible)
        candidates = [e for e in eligible if e["date"] == latest]
    hits = []
    filed = datetime.strptime(record["filed"], "%Y%m%d").date().isoformat()
    for e in candidates:
        matched = []
        basis = None
        if kind == "share_transfer":
            buyer = [
                f
                for f in facts(record, "양수인", "양수인명")
                if party(f["value"]) in e["after"]
            ]
            seller = [
                f
                for f in facts(record, "양도인", "양도인명")
                if party(f["value"]) in e["before"]
            ]
            if record["receipt"] in e["references"] and buyer:
                matched, basis = buyer, "explicit_contract_reference"
            elif filed in e["contract_dates"] and buyer and seller:
                matched, basis = buyer + seller, "cited_contract_date_and_parties"
        elif kind == "officer":
            names = {party(f["value"]) for f in facts(record, "IFR_NM")} - {""}
            days = {parse_date(f["value"]) for f in facts(record, "AFR_RPT_DT")} - {
                None
            }
            if len(names) == 1 and names <= e["after"] and days == {e["date"]}:
                matched = [
                    f
                    for f in facts(record, "AFR_PS_CPT_CNT")
                    if shares(f["value"]) in e["quantities"]
                ]
            basis = "same_day_individual_holding"
        elif kind == "periodic":
            matched = [
                f
                for f in facts(record, "reported_shareholder_position")
                if party(f["holder"]) in e["after"]
                and re.fullmatch(r"최대주주|본인", f["role"].strip())
                and shares(f["closing_shares"]) not in (None, 0)
            ]
            basis = "period_end_controller_position"
        if matched:
            hits.append((e, basis, matched))
    if len(hits) != 1:
        return None
    event, basis, matched = hits[0]
    evidence = [f["line"] for f in matched]
    reference = event["references"].get(record["receipt"]) or event[
        "contract_dates"
    ].get(filed)
    return {
        "event_reference_line": reference["line"]
        if kind == "share_transfer" and reference
        else None,
        "event_receipt": event["document"]["receipt"],
        "related_receipt": record["receipt"],
        "company": event["document"]["company"],
        "family": kind,
        "basis": basis,
        "event_date": event["date"],
        "observation_date": cutoff if kind == "periodic" else None,
        "source_lines": evidence,
        "sha256": record["sha256"],
    }


def run(snapshot, extraction, metadata):
    docs = {d["receipt"]: d for d in snapshot["documents"]}
    corrections = defaultdict(list)
    for correction in snapshot["corrections"]:
        if correction["kind"] == "controller" and correction["status"] == "linked":
            corrections[correction["target"]].append(docs[correction["receipt"]])
    groups = defaultdict(list)
    for e in snapshot["events"]:
        original = docs[e["receipt"]]
        revised = max(
            corrections[e["receipt"]],
            key=lambda d: (d["filed"], d["receipt"]),
            default=None,
        )
        groups[e["corp_code"]].append(event_view(original, revised))
    titles = {
        r["rcept_no"]: r["report_nm"]
        for r in read_metadata(metadata)
        if r.get("corp_code") in groups
    }
    links, scanned = [], Counter()
    for jsonl in sorted(extraction.glob("*/ownership.jsonl")):
        with jsonl.open() as source:
            for line in source:
                record = json.loads(line)
                kind = record["kind"]
                if kind not in (
                    "share_transfer",
                    "officer",
                    "periodic",
                ) or not record.get("facts"):
                    continue
                scanned[kind] += 1
                if record["corp_code"] in groups:
                    match = match_record(
                        record,
                        groups[record["corp_code"]],
                        titles.get(record["receipt"], ""),
                    )
                    if match:
                        links.append(match)
    summary = {
        kind: {
            "field_detected": count,
            "links": sum(x["family"] == kind for x in links),
            "events": len({x["event_receipt"] for x in links if x["family"] == kind}),
        }
        for kind, count in sorted(scanned.items())
    }
    return {"summary": summary, "links": links}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("extraction", type=Path)
    parser.add_argument("metadata", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    paths = sorted(
        p
        for p in args.metadata.rglob("*")
        if p.name in {"filings.json", "filings.jsonl"}
    )
    result = run(json.loads(args.snapshot.read_text()), args.extraction, paths)
    temporary = args.output.with_suffix(".part")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    temporary.replace(args.output)
    print(json.dumps(result["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
