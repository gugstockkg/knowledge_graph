"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .client import DartApiError, DartClient
from .pipeline import OpenDartPipeline
from ..config import get_paths


def _corp_codes(args: argparse.Namespace) -> list[str]:
    values = list(args.corp_code or [])
    if args.corp_code_file:
        for line in Path(args.corp_code_file).read_text(encoding="utf-8-sig").splitlines():
            value = line.strip().split(",", 1)[0].strip()
            if value and not value.lower().startswith("corp_code") and not value.startswith("#"):
                values.append(value)
    unique = list(dict.fromkeys(values))
    if not unique:
        raise ValueError("--corp-code 또는 --corp-code-file을 지정하세요.")
    return unique


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="opendart-kg", description="OpenDART 원천자료를 출처와 함께 수집합니다.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    catalog = subparsers.add_parser("catalog", help="전체 DART 고유번호 파일을 받고 회사 선택용 CSV를 만듭니다.")
    catalog.add_argument("--output", default=str(get_paths().raw), help="로컬 수집 산출물 경로 (기본값: data).")
    catalog.add_argument("--delay", type=float, default=0.15, help="API 요청 대기 초.")
    sync_date = subparsers.add_parser("sync-date", help="특정 날짜의 전체 공시 목록과 원문을 수집합니다.")
    sync_date.add_argument("--date", required=True, help="공시 접수일 YYYYMMDD.")
    sync_date.add_argument("--output", default=str(get_paths().raw), help="로컬 수집 산출물 경로 (기본값: data).")
    sync_date.add_argument("--skip-documents", action="store_true", help="목록만 수집하고 원문 ZIP은 내려받지 않습니다.")
    sync_date.add_argument("--delay", type=float, default=0.15, help="API 요청 사이 최소 대기 초 (기본값: 0.15).")
    sync = subparsers.add_parser("sync", help="기업·임원·최대주주·공시 및 원문을 수집합니다.")
    sync.add_argument("--corp-code", action="append", help="DART 고유번호 8자리. 여러 번 지정할 수 있습니다.")
    sync.add_argument("--corp-code-file", help="한 줄에 하나씩 DART 고유번호를 적은 UTF-8 파일.")
    sync.add_argument("--year", action="append", required=True, help="사업연도. 여러 번 지정할 수 있습니다.")
    sync.add_argument("--output", default=str(get_paths().raw), help="로컬 수집 산출물 경로 (기본값: data).")
    sync.add_argument("--skip-documents", action="store_true", help="공시 목록만 수집하고 원문 ZIP은 내려받지 않습니다.")
    sync.add_argument("--delay", type=float, default=0.15, help="API 요청 사이 최소 대기 초 (기본값: 0.15).")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "catalog":
            pipeline = OpenDartPipeline(Path(args.output), client=DartClient(delay=args.delay), download_documents=False)
            path = pipeline.download_company_catalog()
            print(json.dumps({"catalog_csv": str(path)}, ensure_ascii=False, indent=2))
            return 0
        if args.command == "sync-date":
            client = DartClient(delay=args.delay)
            pipeline = OpenDartPipeline(Path(args.output), client=client, download_documents=not args.skip_documents)
            result = pipeline.sync_date(args.date)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        corp_codes = _corp_codes(args)
        client = DartClient(delay=args.delay)
        pipeline = OpenDartPipeline(Path(args.output), client=client, download_documents=not args.skip_documents)
        result = pipeline.sync(corp_codes, list(dict.fromkeys(args.year)))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (DartApiError, OSError, ValueError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
