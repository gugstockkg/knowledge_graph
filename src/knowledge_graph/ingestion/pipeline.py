"""OpenDART collection workflow; raw responses remain available for reprocessing."""

from __future__ import annotations

import json
import hashlib
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .client import DartClient, DartApiError
from .normalize import (
    REPORT_CODES,
    company_record,
    executive_records,
    filing_records,
    shareholder_change_records,
    shareholder_records,
)

REPORT_ENDPOINTS = {
    "exctvSttus.json": executive_records,
    "hyslrSttus.json": shareholder_records,
    "hyslrChgSttus.json": shareholder_change_records,
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def stamp() -> str:
    return utc_now().strftime("%Y%m%dT%H%M%SZ")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    if not records:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


class OpenDartPipeline:
    def __init__(self, output_dir: Path, *, client: DartClient | None = None, download_documents: bool = True):
        self.output_dir = output_dir
        self.client = client or DartClient()
        self.download_documents = download_documents
        self.run_id = stamp()
        self.run_dir = output_dir / "runs" / self.run_id
        self.raw_dir = self.run_dir / "raw"
        self.document_dir = self.run_dir / "documents"
        self.graph_file = self.run_dir / "kg_records.jsonl"
        self.manifest: dict[str, Any] = {
            "run_id": self.run_id,
            "started_at": utc_now().isoformat(),
            "source": "OpenDART",
            "companies": [],
            "years": [],
            "download_documents": download_documents,
            "api_key_saved": False,
        }

    def download_company_catalog(self) -> Path:
        archive, companies = self.client.download_company_codes()
        self.run_dir.mkdir(parents=True, exist_ok=True)
        archive_path = self.raw_dir / "corpCode.zip"
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        archive_path.write_bytes(archive)
        csv_path = self.run_dir / "corp_codes.csv"
        import csv

        fields = ["corp_code", "corp_name", "stock_code", "modify_date"]
        with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(companies)
        write_json(self.run_dir / "catalog_manifest.json", {
            "source": "OpenDART corpCode.xml",
            "retrieved_at": utc_now().isoformat(),
            "company_count": len(companies),
            "listed_company_count": sum(bool(item.get("stock_code")) for item in companies),
            "raw_archive": str(archive_path.relative_to(self.run_dir)),
        })
        return csv_path

    def _save_response(self, endpoint: str, params: dict[str, Any], response: dict[str, Any]) -> str:
        retrieved_at = utc_now().isoformat()
        safe_endpoint = re.sub(r"[^a-zA-Z0-9_.-]", "_", endpoint)
        identity = "_".join(
            str(params.get(k, ""))
            for k in ("corp_code", "bsns_year", "reprt_code", "pblntf_ty", "pblntf_detail_ty", "bgn_de", "end_de", "page_no")
            if params.get(k) is not None
        )
        param_hash = hashlib.sha256(json.dumps(params, sort_keys=True).encode("utf-8")).hexdigest()[:10]
        path = self.raw_dir / safe_endpoint / f"{identity or 'global'}_{param_hash}_{stamp()}.json"
        write_json(path, {
            "endpoint": endpoint,
            "parameters": params,
            "retrieved_at": retrieved_at,
            "payload": response,
        })
        return retrieved_at

    def _get(self, endpoint: str, params: dict[str, Any], *, required: bool = False) -> dict[str, Any] | None:
        response = self.client.get_json(endpoint, params)
        self._save_response(endpoint, params, response)
        if response.get("status") == "013":
            if required:
                raise DartApiError(f"{endpoint}: 조회 결과가 없습니다.", status="013")
            return None
        return response

    @staticmethod
    def _rows(response: dict[str, Any] | None) -> list[dict[str, Any]]:
        if not response:
            return []
        rows = response.get("list", [])
        if isinstance(rows, dict):
            return [rows]
        if not isinstance(rows, list):
            return []
        return [row for row in rows if isinstance(row, dict)]

    def _collect_filings(self, corp_code: str, year: str, filing_type: str, detail_type: str | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        page_no = 1
        while True:
            params: dict[str, Any] = {
                "corp_code": corp_code,
                "bgn_de": f"{year}0101",
                "end_de": f"{year}1231",
                "last_reprt_at": "N",
                "pblntf_ty": filing_type,
                "page_no": page_no,
                "page_count": 100,
                "sort": "date",
                "sort_mth": "asc",
            }
            if detail_type:
                params["pblntf_detail_ty"] = detail_type
            response = self._get("list.json", params)
            if response is None:
                break
            page_rows = self._rows(response)
            rows.extend(page_rows)
            total_page = int(response.get("total_page") or page_no)
            if page_no >= total_page or not page_rows:
                break
            page_no += 1
        return rows

    def _collect_filings_for_date(self, date: str) -> list[dict[str, Any]]:
        """Collect every filing listed by OpenDART for one calendar date."""
        rows: list[dict[str, Any]] = []
        page_no = 1
        while True:
            params: dict[str, Any] = {
                "bgn_de": date,
                "end_de": date,
                "last_reprt_at": "N",
                "page_no": page_no,
                "page_count": 100,
                "sort": "date",
                "sort_mth": "asc",
            }
            response = self._get("list.json", params)
            if response is None:
                break
            page_rows = self._rows(response)
            rows.extend(page_rows)
            total_page = int(response.get("total_page") or page_no)
            if page_no >= total_page or not page_rows:
                break
            page_no += 1
        return rows

    def sync_date(self, date: str) -> dict[str, Any]:
        if not re.fullmatch(r"\d{8}", date):
            raise ValueError("날짜는 YYYYMMDD 형식이어야 합니다.")
        # Reject impossible dates (for example, 20260231) before making API calls.
        datetime.strptime(date, "%Y%m%d")
        rows = self._collect_filings_for_date(date)
        retrieved_at = utc_now().isoformat()
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            corp_code = str(row.get("corp_code") or "").strip()
            if corp_code:
                grouped.setdefault(corp_code, []).append(row)
        records = []
        for corp_code, company_rows in grouped.items():
            records.extend(filing_records(
                company_rows,
                corp_code=corp_code,
                retrieved_at=retrieved_at,
                list_query={"date": date, "last_reprt_at": "N"},
            ))
            if self.download_documents:
                for row in company_rows:
                    self._download_filing(corp_code, row)
        append_jsonl(self.graph_file, records)
        self.manifest.update({
            "date": date,
            "filing_count": len(rows),
            "company_count": len(grouped),
            "kg_records_written": len(records),
            "finished_at": utc_now().isoformat(),
        })
        self.run_dir.mkdir(parents=True, exist_ok=True)
        write_json(self.run_dir / "manifest.json", self.manifest)
        return {"run_dir": str(self.run_dir), "date": date, "filing_count": len(rows), "company_count": len(grouped), "kg_records_written": len(records)}

    def _download_filing(self, corp_code: str, row: dict[str, Any]) -> str | None:
        receipt = str(row.get("rcept_no") or "").strip()
        if not receipt:
            return None
        archive_path = self.document_dir / corp_code / f"{receipt}.zip"
        xml_dir = self.document_dir / corp_code / receipt
        if archive_path.exists():
            return str(archive_path.relative_to(self.run_dir))
        try:
            body = self.client.download_document(receipt)
        except DartApiError as exc:
            write_json(self.document_dir / corp_code / f"{receipt}.error.json", {
                "receipt_no": receipt, "error": str(exc), "retrieved_at": utc_now().isoformat()
            })
            return None
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        archive_path.write_bytes(body)
        if body.startswith(b"PK\x03\x04"):
            xml_dir.mkdir(parents=True, exist_ok=True)
            try:
                with zipfile.ZipFile(archive_path) as archive:
                    for member in archive.infolist():
                        if member.is_dir() or not member.filename.lower().endswith(".xml"):
                            continue
                        target_name = Path(member.filename).name
                        target = xml_dir / target_name
                        target.write_bytes(archive.read(member))
            except (zipfile.BadZipFile, OSError) as exc:
                write_json(self.document_dir / corp_code / f"{receipt}.error.json", {
                    "receipt_no": receipt, "error": f"원문 ZIP 처리 실패: {exc}", "retrieved_at": utc_now().isoformat()
                })
        return str(archive_path.relative_to(self.run_dir))

    def sync_company(self, corp_code: str, years: list[str]) -> dict[str, Any]:
        corp_code = corp_code.strip()
        if not re.fullmatch(r"\d{8}", corp_code):
            raise ValueError(f"DART 고유번호는 8자리 숫자여야 합니다: {corp_code}")
        company = self._get("company.json", {"corp_code": corp_code}, required=True)
        assert company is not None
        company_payload = company_record(company, retrieved_at=utc_now().isoformat())
        if company_payload:
            append_jsonl(self.graph_file, [company_payload])

        filing_counts: dict[str, int] = {}
        records_written = 1 if company_payload else 0
        for year in years:
            if not re.fullmatch(r"20\d{2}", year):
                raise ValueError(f"연도 형식이 올바르지 않습니다: {year}")
            for report_code in REPORT_CODES:
                params = {"corp_code": corp_code, "bsns_year": year, "reprt_code": report_code}
                for endpoint, converter in REPORT_ENDPOINTS.items():
                    response = self._get(endpoint, params)
                    rows = self._rows(response)
                    retrieved_at = utc_now().isoformat()
                    if endpoint == "exctvSttus.json":
                        records = converter(rows, corp_code=corp_code, year=year, report_code=report_code, retrieved_at=retrieved_at)
                    elif endpoint == "hyslrSttus.json":
                        records = converter(rows, corp_code=corp_code, year=year, report_code=report_code, retrieved_at=retrieved_at)
                    else:
                        records = converter(rows, corp_code=corp_code, year=year, report_code=report_code, retrieved_at=retrieved_at)
                    append_jsonl(self.graph_file, records)
                    records_written += len(records)

            for filing_type, detail_type, label in (("A", None, "periodic"), ("B", "B001", "major_event")):
                rows = self._collect_filings(corp_code, year, filing_type, detail_type)
                filing_counts[f"{year}:{label}"] = len(rows)
                filing_retrieved_at = utc_now().isoformat()
                records = filing_records(
                    rows,
                    corp_code=corp_code,
                    retrieved_at=filing_retrieved_at,
                    list_query={"fiscal_year": year, "pblntf_ty": filing_type, "pblntf_detail_ty": detail_type},
                )
                append_jsonl(self.graph_file, records)
                records_written += len(records)
                if self.download_documents:
                    for row in rows:
                        self._download_filing(corp_code, row)

        return {
            "corp_code": corp_code,
            "company_name": company.get("corp_name"),
            "years": years,
            "filing_counts": filing_counts,
            "kg_records_written": records_written,
        }

    def sync(self, corp_codes: list[str], years: list[str]) -> dict[str, Any]:
        results = []
        for corp_code in corp_codes:
            results.append(self.sync_company(corp_code, years))
        self.manifest["companies"] = results
        self.manifest["years"] = years
        self.manifest["finished_at"] = utc_now().isoformat()
        self.run_dir.mkdir(parents=True, exist_ok=True)
        write_json(self.run_dir / "manifest.json", self.manifest)
        return {"run_dir": str(self.run_dir), "results": results}
