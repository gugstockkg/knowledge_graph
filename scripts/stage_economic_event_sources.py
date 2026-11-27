"""Stage only ZIPs for economic event filings from an existing catalog inventory."""
import argparse
import json
import re
import subprocess
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

from build_disclosure_catalog import RECEIPT, metadata_files, read_rows

from knowledge_graph.ingestion.contract_pilot import compact
from knowledge_graph.ingestion.economic_events import LISTED

FORMS = {
    "단일판매공급계약체결",
    "신규시설투자등",
    "신규시설투자",
    "연결재무제표기준영업잠정실적공정공시",
    "개별재무제표기준영업잠정실적공정공시",
}


def stage(catalog, output, bucket, region, end, workers):
    filings = {}
    for path in metadata_files(catalog):
        for row in read_rows(path):
            if row.get("corp_cls") in LISTED and row["rcept_dt"] <= end:
                filings[row["rcept_no"]] = row
    if not filings:
        raise ValueError("No listed-company filing metadata found")
    output.mkdir(parents=True, exist_ok=True)
    (output / "filings.json").write_text(json.dumps(list(filings.values()), ensure_ascii=False), encoding="utf-8")
    candidates = {
        receipt for receipt, row in filings.items()
        if compact(re.sub(r"^(?:\[[^]]+\]\s*)+", "", row["report_nm"].strip())) in FORMS
    }
    sources = defaultdict(set)
    for inventory in sorted(catalog.glob("*.tsv")):
        with inventory.open(encoding="utf-8") as source:
            for line in source:
                key = line.split("\t", 1)[0].strip()
                if not key.lower().endswith(".zip"):
                    continue
                match = RECEIPT.search(key.rsplit("/", 1)[-1])
                if match and match[0] in candidates:
                    sources[match[0]].add(key)

    def download(receipt):
        corp = filings[receipt]["corp_code"]
        if not re.fullmatch(r"\d{8}", corp):
            raise ValueError(f"Invalid company code for {receipt}")
        path = output / "documents" / corp / f"{receipt}.zip"
        if path.is_file():
            return "cached"
        path.parent.mkdir(exist_ok=True, parents=True)
        temporary = path.with_suffix(".zip.part")
        keys = sorted(sources[receipt], key=lambda key: ("/documents/partition_day=" not in key, key))
        for key in keys:
            result = subprocess.run(
                ["aws", "s3", "cp", f"s3://{bucket}/{key}", str(temporary),
                 "--region", region, "--only-show-errors"], capture_output=True, check=False,
            )
            if result.returncode == 0:
                temporary.replace(path)
                return "downloaded"
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"Unable to retrieve a cataloged source ZIP for receipt {receipt}")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        stats = Counter(pool.map(download, sorted(sources)))
    return dict(stats, listed_filings=len(filings), event_candidates=len(candidates),
                candidates_without_zip=len(candidates - sources.keys()),
                listed_by_market=dict(Counter(row["corp_cls"] for row in filings.values())))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--end", required=True, type=date.fromisoformat)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    print(json.dumps(stage(args.catalog, args.output, args.bucket, args.region,
                           args.end.strftime("%Y%m%d"), args.workers)))
