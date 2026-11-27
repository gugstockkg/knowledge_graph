"""Extract an evidence-linked economic event snapshot from local OpenDART collections."""

import argparse
import json
import math
import re
import zipfile
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from ..config import get_paths
from .contract_pilot import TableRows, compact, date_iso, field, is_subsidiary_report, json_save, parse_contract, read_archive
from .trace_contracts import collect as collect_contracts

LISTED = {"Y", "K", "N"}
UNITS = {"원": 1, "천원": 1_000, "백만원": 1_000_000, "억원": 100_000_000, "조원": 1_000_000_000_000}
METRICS = {"매출액": "revenue", "영업이익": "operating_profit"}
CATEGORIES = (
    ("inspection", "검사·테스트 장비", r"검사장[비치]|검사시스템|Wafer\s+Inspection|Tester|프로브카드|Probe\s*Card"),
    ("semiconductor_equipment", "반도체 제조장비", r"반도체\s*(제조|세정|공정)\s*장비"),
    ("facility_construction", "시설공사", r"건축공사|건설공사|건축\s*및\s*통신공사|골조공사|마감공사|신축|FAB\s*건축"),
    ("maintenance", "유지보수", r"유지\s*보수|유지관리"),
    ("memory_products", "메모리 반도체", r"메모리\s*반도체\s*공급"),
)


def row_cells(document):
    parser = TableRows()
    parser.feed(document)
    return parser.rows


def compact_label(text):
    return compact(re.sub(r"^\s*\d+\.\s*", "", text))


def cells_after(rows, label):
    return [(row[i + 1][0], row[i + 1][1]) for row in rows
            for i, (text, _, _) in enumerate(row[:-1])
            if compact_label(text) == label and row[i + 1][0] not in ("", "-", "－")]


def unique(values):
    if len(values) != 1:
        raise ValueError("expected exactly one labelled value")
    return values[0]


def money(text, unit):
    try:
        amount = Decimal(text.replace(",", "").replace(" ", "")) * UNITS[unit]
        if amount.is_finite() and amount == amount.to_integral_value() and abs(amount) < 2**63:
            return int(amount)
    except InvalidOperation:
        pass
    raise ValueError("invalid monetary amount")


def facility_fields(rows):
    target, target_line = unique(cells_after(rows, "투자대상"))
    raw, amount_line = unique(cells_after(rows, "투자금액원"))
    amount = money(raw, "원")
    if amount < 0:
        raise ValueError("invalid investment amount")
    return dict(target=target, target_line=target_line, planned_amount_krw=amount,
                amount_raw=raw, amount_line=amount_line, status="announced_plan")


def financial_fields(rows):
    units = [m[1] for row in rows for text, _, _ in row
             if (m := re.fullmatch(r"단위\s*[:：]\s*(조\s*원|억\s*원|백만\s*원|천\s*원|원)\s*(?:,\s*%)?", text))]
    unit = unique(units).replace(" ", "")
    periods = [(row[1][0], row[3][0]) for row in rows if len(row) >= 4
               and row[0][0] == "당기실적" and row[2][0] == "~"]
    start, end = [date.fromisoformat(x).isoformat() for x in unique(periods)]
    if start > end:
        raise ValueError("financial period out of order")
    observations = []
    for label, metric in METRICS.items():
        cells = [(row[2][0], row[2][1]) for row in rows if len(row) > 2
                 and row[0][0] == label and row[1][0] == "당해실적"]
        if not cells or (len(cells) == 1 and cells[0][0] in ("-", "－", "—")):
            continue
        raw, line = unique(cells)
        observations.append(dict(metric=metric, period_start=start, period_end=end,
                                 value_krw=money(raw, unit), raw_value=raw,
                                 raw_unit=unit, value_line=line))
    if not observations:
        raise ValueError("no supported financial values")
    return observations


def contract_category(description):
    matches = [(code, name) for code, name, pattern in CATEGORIES if re.search(pattern, description, re.I)]
    return dict(zip(("category_id", "category_name"), matches[0])) if len(matches) == 1 else {}


AMENDABLE_TERMS = {
    "계약내역계약금액원": "contract_amount_krw",
    "계약내역계약금액총액원": "contract_amount_krw",
    "계약내역매출액대비": "supplier_reported_sales_pct",
    "계약기간시작일": "start_date",
    "계약기간종료일": "end_date",
}


def amendment_fields(rows):
    """Read only explicit, individually labelled changes in the correction table."""
    fields = {}
    missing = {"", "-", "－", "—"}
    in_changes = False
    for row in rows:
        values = [cell[0] for cell in row]
        if values[:3] == ["정정항목", "정정전", "정정후"]:
            in_changes = True
            continue
        if not in_changes:
            continue
        if len(values) < 3:
            break
        label, before, after = values[:3]
        key = AMENDABLE_TERMS.get(compact_label(label))
        if not key or after in missing or before == after:
            continue
        if key in fields:
            raise ValueError("repeated field in amendment table")
        if key == "contract_amount_krw":
            value = money(after, "원")
            if value < 0:
                raise ValueError("negative contract amount")
        elif key == "supplier_reported_sales_pct":
            value = float(after.replace(",", "").replace("%", ""))
            if not math.isfinite(value):
                raise ValueError("non-finite sales ratio")
        else:
            value = date.fromisoformat(after).isoformat()
        fields[key] = dict(value=value, before=before, after=after, line=row[2][1])
    return fields


def contract_amendment(row, receipt, document, cells, lineage, by_signature):
    """Resolve an earlier version using receipt or issuer, filed date and contract signature."""
    contract_fields = parse_contract(document)
    if is_subsidiary_report(row["report_nm"], contract_fields):
        raise ValueError("contract amendment is a subsidiary disclosure")
    refs = field(contract_fields, "related_receipts") or []
    submitted = unique(cells_after(cells, "정정관련공시서류제출일"))[0]
    date_parts = re.findall(r"\d+", submitted)
    if len(date_parts) != 3:
        raise ValueError("missing or ambiguous prior filing date")
    reference_day = date(*map(int, date_parts)).isoformat()
    known_on = date_iso(row["rcept_dt"])
    if reference_day >= known_on:
        raise ValueError("prior publication order is unavailable")
    corp = row["corp_code"]
    description = field(contract_fields, "description")
    signed_date = field(contract_fields, "signed_date")
    signature = (compact(description).casefold(), signed_date) if description and signed_date else None
    candidates = [ref for ref in refs if ref in lineage and lineage[ref][:2] == (corp, reference_day)]
    if not candidates and signature:
        candidates = by_signature.get((corp, reference_day, signature), [])
    prior = unique(candidates)
    original = lineage[prior][2]
    fields = amendment_fields(cells)
    if not fields:
        raise ValueError("no supported changed terms")
    result = dict(receipt=receipt, contract_receipt=original, preceding_receipt=prior,
                  corp_code=corp, known_on=known_on, changes={key: field["value"] for key, field in fields.items()},
                  changed_fields=sorted(fields), change_evidence=json.dumps(fields, ensure_ascii=False))
    return result, signature


def announcements(collections, start, end, stats, lineage, by_signature):
    filed = {}
    for collection in collections:
        index = collection / "filings.json"
        if not index.is_file():
            continue
        with index.open(encoding="utf-8") as source:
            for row in json.load(source):
                if row["corp_cls"] not in LISTED or not start <= date_iso(row["rcept_dt"]) <= end:
                    continue
                raw_title = row["report_nm"].strip()
                title = compact(re.sub(r"^(?:\[[^]]+\]\s*)+", "", raw_title))
                correction = any(word in raw_title.split("]", 1)[0] for word in ("정정", "취소", "철회"))
                if title in ("신규시설투자등", "신규시설투자"):
                    kind = "facility"
                elif title in ("연결재무제표기준영업잠정실적공정공시", "개별재무제표기준영업잠정실적공정공시"):
                    kind = "financial"
                elif raw_title.startswith("[기재정정]") and title == "단일판매공급계약체결":
                    kind = "contract_amendment"
                else:
                    continue
                receipt = row["rcept_no"]
                archive = collection / "documents" / row["corp_code"] / (receipt + ".zip")
                if receipt not in filed or (archive.is_file() and not filed[receipt][1].is_file()):
                    filed[receipt] = (row, archive, title, kind, correction)

    for receipt, (row, archive, title, kind, correction) in sorted(filed.items()):
        stats[kind + "_candidates"] += 1
        if not archive.is_file():
            stats[kind + "_missing_zip"] += 1
            continue
        if kind == "facility" and correction:
            stats[kind + "_pending_version_link"] += 1
            continue
        try:
            raw, _, digest = read_archive(archive, receipt)
            cells = row_cells(raw)
            if kind == "contract_amendment":
                item, signature = contract_amendment(row, receipt, raw, cells, lineage, by_signature)
                fields = [item]
            elif kind == "facility":
                fields = [facility_fields(cells)]
            else:
                fields = financial_fields(cells)
        except (ValueError, OSError, zipfile.BadZipFile):
            stats[kind + "_unsupported_form"] += 1
            continue
        stats[kind + "_parsed_filings"] += 1
        for item in fields:
            if kind == "contract_amendment":
                lineage[receipt] = (row["corp_code"], item["known_on"], item["contract_receipt"])
                if signature:
                    by_signature[(row["corp_code"], item["known_on"], signature)].append(receipt)
            if kind == "financial":
                item.update(consolidation_scope="consolidated" if title.startswith("연결") else "separate",
                            publication_stage="correction_notice" if correction else "preliminary_notice")
            yield kind, dict(item, receipt=receipt, corp_code=row["corp_code"],
                             known_on=date_iso(row["rcept_dt"]), sha256=digest)


def collect(collections, start, end):
    raw_contracts, contract_counts = collect_contracts(collections, start, end, LISTED)
    stats = Counter({"contract_" + key: value for key, value in contract_counts.items()})
    result = {"contracts": [], "facility": [], "financial": [], "contract_amendment": []}
    for row in raw_contracts:
        description = row["description"]["value"]
        amount = row["amount_krw"] or {}
        ratio = row["reported_sales_pct"] or {}
        ratio_value = ratio.get("value")
        if ratio_value is not None and not math.isfinite(ratio_value):
            ratio_value = None
        buyer = row["buyer"] or {}
        result["contracts"].append(dict(
            receipt=row["receipt"], known_on=row["filing_date"], supplier=row["supplier"]["corp_code"],
            buyer=buyer.get("corp_code"), buyer_identity_receipt=buyer.get("receipt"),
            product=description, product_line=row["description"]["line"],
            sha256=row["document_sha256"], amount_krw=amount.get("value"), amount_raw=amount.get("text"),
            reported_sales_pct=ratio_value, reported_sales_pct_raw=ratio.get("text"),
            conditional_raw=(row["conditional"] or {}).get("text"),
            signed_date=row["signed_date"], start_date=row["start_date"], end_date=row["end_date"],
            buyer_status=row["buyer_status"], **contract_category(description)))
    lineage = {row["receipt"]: (row["supplier"], row["known_on"], row["receipt"])
               for row in result["contracts"]}
    by_signature = defaultdict(list)
    for row in result["contracts"]:
        if row["signed_date"]:
            signature = (compact(row["product"]).casefold(), row["signed_date"])
            by_signature[(row["supplier"], row["known_on"], signature)].append(row["receipt"])
    for kind, row in announcements(collections, start, end, stats, lineage, by_signature):
        result[kind].append(row)
    return dict(start=start, end=end, counts=dict(stats),
                rows={kind: len(rows) for kind, rows in result.items()}, **result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2026-01-01")
    parser.add_argument("--end", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    start, end = [date.fromisoformat(d).isoformat() for d in (args.start, args.end)]
    if start > end:
        parser.error("end must be on or after start")
    result = collect(sorted(get_paths().raw.glob("collections/*")), start, end)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    json_save(args.output, result)
    print(json.dumps({"rows": result["rows"], "counts": result["counts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
