"""Convert OpenDART responses into evidence-linked, graph-shaped JSON records.

Names without a stable public identifier are deliberately scoped to the filing
company. This avoids incorrectly merging same-name people or shareholders.
"""

from __future__ import annotations

import hashlib
from typing import Any, Iterable

REPORT_CODES = {
    "11013": "Q1",
    "11012": "HALF_YEAR",
    "11014": "Q3",
    "11011": "ANNUAL",
}


def company_id(corp_code: str) -> str:
    return f"dart-company:{corp_code}"


def _candidate_id(kind: str, corp_code: str, name: str) -> str:
    canonical = " ".join(name.split()).casefold()
    digest = hashlib.sha256(f"{corp_code}|{canonical}".encode("utf-8")).hexdigest()[:16]
    return f"candidate-{kind}:{corp_code}:{digest}"


def company_record(payload: dict[str, Any], *, retrieved_at: str) -> dict[str, Any] | None:
    corp_code = str(payload.get("corp_code") or "").strip()
    name = str(payload.get("corp_name") or "").strip()
    if not corp_code or not name:
        return None
    return {
        "record_type": "entity",
        "entity_type": "Company",
        "id": company_id(corp_code),
        "name": name,
        "aliases": [x for x in [payload.get("corp_name_eng"), payload.get("stock_name")] if x],
        "attributes": {
            key: payload.get(key)
            for key in (
                "stock_code", "corp_cls", "jurir_no", "bizr_no", "ceo_nm",
                "induty_code", "est_dt", "acc_mt", "adres", "hm_url",
            )
            if payload.get(key) not in (None, "")
        },
        "provenance": {"endpoint": "company.json", "retrieved_at": retrieved_at},
    }


def filing_records(
    rows: Iterable[dict[str, Any]], *, corp_code: str, retrieved_at: str, list_query: dict[str, Any]
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in rows:
        receipt = str(row.get("rcept_no") or "").strip()
        if not receipt:
            continue
        records.append({
            "record_type": "relation",
            "subject": company_id(corp_code),
            "predicate": "SUBMITTED_FILING",
            "object": f"dart-filing:{receipt}",
            "object_entity": {"entity_type": "Filing", "id": f"dart-filing:{receipt}", "name": row.get("report_nm")},
            "attributes": {
                "report_name": row.get("report_nm"),
                "filing_date": row.get("rcept_dt"),
                "submitter": row.get("flr_nm"),
                "market": row.get("corp_cls"),
                "remarks": row.get("rm"),
                "query": list_query,
            },
            "provenance": {
                "endpoint": "list.json",
                "receipt_no": receipt,
                "retrieved_at": retrieved_at,
                "original_document": f"documents/{corp_code}/{receipt}.zip",
            },
        })
    return records


def executive_records(
    rows: Iterable[dict[str, Any]], *, corp_code: str, year: str, report_code: str, retrieved_at: str
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in rows:
        name = str(row.get("nm") or "").strip()
        if not name:
            continue
        person_id = _candidate_id("person", corp_code, name)
        records.append({
            "record_type": "relation",
            "subject": company_id(corp_code),
            "predicate": "HAS_EXECUTIVE_CANDIDATE",
            "object": person_id,
            "object_entity": {
                "entity_type": "PersonCandidate", "id": person_id, "name": name,
                "resolution_status": "unresolved_name_only",
            },
            "attributes": dict(row),
            "reporting_period": {"fiscal_year": year, "report_code": report_code, "report_type": REPORT_CODES[report_code]},
            "provenance": {
                "endpoint": "exctvSttus.json",
                "receipt_no": row.get("rcept_no"),
                "retrieved_at": retrieved_at,
                "temporal_note": "보고서에 기재된 임원 현황이며 재직 유효기간으로 자동 해석하지 않음",
            },
        })
    return records


def shareholder_records(
    rows: Iterable[dict[str, Any]], *, corp_code: str, year: str, report_code: str, retrieved_at: str
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in rows:
        name = str(row.get("nm") or row.get("mxmm_shrholdr_nm") or "").strip()
        if not name:
            continue
        holder_id = _candidate_id("shareholder", corp_code, name)
        records.append({
            "record_type": "relation",
            "subject": company_id(corp_code),
            "predicate": "HAS_SHAREHOLDER_CANDIDATE",
            "object": holder_id,
            "object_entity": {
                "entity_type": "ShareholderCandidate", "id": holder_id, "name": name,
                "resolution_status": "unresolved_name_only",
            },
            "attributes": dict(row),
            "reporting_period": {"fiscal_year": year, "report_code": report_code, "report_type": REPORT_CODES[report_code]},
            "provenance": {
                "endpoint": "hyslrSttus.json",
                "receipt_no": row.get("rcept_no"),
                "retrieved_at": retrieved_at,
                "temporal_note": "보고서상 주주 현황이며 유효시점은 원문 기준일 확인 후 별도 부여",
            },
        })
    return records


def shareholder_change_records(
    rows: Iterable[dict[str, Any]], *, corp_code: str, year: str, report_code: str, retrieved_at: str
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in rows:
        name = str(row.get("mxmm_shrholdr_nm") or row.get("nm") or "").strip()
        if not name:
            continue
        records.append({
            "record_type": "event",
            "event_type": "LARGEST_SHAREHOLDER_CHANGE",
            "company": company_id(corp_code),
            "actor_candidate": _candidate_id("shareholder", corp_code, name),
            "actor_name": name,
            "actor_entity": {
                "entity_type": "ShareholderCandidate",
                "id": _candidate_id("shareholder", corp_code, name),
                "name": name,
                "resolution_status": "unresolved_name_only",
            },
            "event_date": row.get("change_on"),
            "attributes": dict(row),
            "reporting_period": {"fiscal_year": year, "report_code": report_code, "report_type": REPORT_CODES[report_code]},
            "provenance": {
                "endpoint": "hyslrChgSttus.json",
                "receipt_no": row.get("rcept_no"),
                "retrieved_at": retrieved_at,
            },
        })
    return records
