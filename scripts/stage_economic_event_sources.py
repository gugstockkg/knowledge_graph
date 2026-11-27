"""Stage only ZIPs for economic event filings from an existing catalog inventory."""
import argparse
import json
import os
import re
import shutil
import subprocess
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
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


def sdk_downloader(bucket, region, workers):
    try:
        from botocore.config import Config
        from botocore.exceptions import BotoCoreError, ClientError
        from botocore.session import get_session
    except ImportError:
        from awscli.botocore.config import Config
        from awscli.botocore.exceptions import BotoCoreError, ClientError
        from awscli.botocore.session import get_session

    client = get_session().create_client("s3", region_name=region,
                                         config=Config(max_pool_connections=workers))

    def download(key, path):
        try:
            with closing(client.get_object(Bucket=bucket, Key=key)["Body"]) as source, path.open("wb") as sink:
                shutil.copyfileobj(source, sink)
        except (BotoCoreError, ClientError):
            return False
        return True

    return download


def stage(catalog, output, bucket, region, end, workers, use_sdk=False, *, ownership=False):
    from knowledge_graph.ingestion.control_ownership import filing_type
    filings = {}
    for path in metadata_files(catalog):
        for row in read_rows(path):
            if (ownership or row.get("corp_cls") in LISTED) and row["rcept_dt"] <= end:
                filings[row["rcept_no"]] = row
    if not filings:
        raise ValueError("No listed-company filing metadata found")
    output.mkdir(parents=True, exist_ok=True)
    index = output / f"filings.{os.getpid()}.part"
    index.write_text(json.dumps(list(filings.values()), ensure_ascii=False), encoding="utf-8")
    index.replace(output / "filings.json")
    candidates = {
        receipt for receipt, row in filings.items()
        if (filing_type(row["report_nm"]) if ownership else
            compact(re.sub(r"^(?:\[[^]]+\]\s*)+", "", row["report_nm"].strip())) in FORMS)
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

    download_with_sdk = sdk_downloader(bucket, region, workers) if use_sdk else None

    def download(receipt):
        corp = filings[receipt]["corp_code"]
        if not re.fullmatch(r"\d{8}", corp):
            raise ValueError(f"Invalid company code for {receipt}")
        path = output / "documents" / corp / f"{receipt}.zip"
        if path.is_file():
            return "cached"
        path.parent.mkdir(exist_ok=True, parents=True)
        temporary = path.with_suffix(f".zip.{os.getpid()}.part")
        keys = sorted(sources[receipt], key=lambda key: ("/documents/partition_day=" not in key, key))
        for key in keys:
            if download_with_sdk:
                success = download_with_sdk(key, temporary)
            else:
                result = subprocess.run(
                    ["aws", "s3", "cp", f"s3://{bucket}/{key}", str(temporary),
                     "--region", region, "--only-show-errors"], capture_output=True, check=False,
                )
                success = result.returncode == 0
            if success:
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
    parser.add_argument("--ownership", action="store_true", help="Stage controller and large-holding reports across all markets")
    parser.add_argument("--sdk", action="store_true", help="Reuse a botocore client for S3 downloads")
    args = parser.parse_args()
    print(json.dumps(stage(args.catalog, args.output, args.bucket, args.region,
                           args.end.strftime("%Y%m%d"), args.workers, args.sdk, ownership=args.ownership)))
