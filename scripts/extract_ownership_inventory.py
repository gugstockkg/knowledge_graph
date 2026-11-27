"""Extract ownership observations from every dated OpenDART source in an S3 inventory."""

import argparse
import hashlib
import io
import json
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from audit_opendart_inventory import RECEIPT_FILE, read_metadata, title

from knowledge_graph.extraction.tagged import FieldParser
from knowledge_graph.ingestion.contract_pilot import compact
from knowledge_graph.ingestion.control_ownership import (
    LocatedRows,
    fact,
    fields_from_rows,
    filing_type,
)

OFFICER_FIELDS = {
    "IFR_NM",
    "STF_PSM",
    "STF_RYN",
    "AFR_RPT_DT",
    "AFR_UN_CNT",
    "AFR_UN_RT",
    "AFR_PS_CPT_CNT",
    "AFR_PS_CPT_RT",
    "BFR_UN_CNT",
    "BFR_PS_CPT_CNT",
    "MDF_UN_CNT",
    "MDF_PS_CPT_CNT",
}
DEAL_FIELDS = {
    "양도인",
    "양수인",
    "양도인명",
    "양수인명",
    "계약당사자",
    "양수도주식수",
    "양수도대금",
    "양수도계약체결일",
    "계약체결일",
    "거래종결일",
    "대금지급일정및조건",
    "대금지급일",
    "양수도내역",
    "계약내용",
    "변경예정최대주주",
    "변경예정일자",
    "양수도계약의주요내용",
    "세부변경내역",
}


def family(report_title):
    base = title(report_title)
    if base.startswith("임원ㆍ주요주주특정증권등소유상황보고서") or compact(
        base
    ).startswith("임원주요주주특정증권등소유상황보고서"):
        return "officer"
    if re.match(r"^(?:사업|반기|분기)보고서(?:\(|$)", base):
        return "periodic"
    normalized = compact(base)
    if normalized.startswith(
        ("최대주주변경을수반하는주식양수도계약", "주요사항보고서주식양수도")
    ):
        return "share_transfer"
    existing = filing_type(report_title)
    return existing[0] if existing else None


def inventory_sources(listing):
    sources = {}
    with listing.open() as source:
        for line in source:
            parts = line.split(maxsplit=3)
            if len(parts) != 4 or "/documents/" not in parts[3]:
                continue
            key = parts[3].strip()
            match = RECEIPT_FILE.fullmatch(key.rsplit("/", 1)[-1])
            if match:
                receipt, fmt = match.groups()
                priority = (
                    fmt.lower() != "zip",
                    "/documents/partition_day=" not in key,
                    key,
                )
                if receipt not in sources or priority < sources[receipt]:
                    sources[receipt] = priority
    return sources


def periodic_facts(document):
    starts = list(
        re.finditer(
            r"최대주주\s*및\s*특수관계인(?:의)?\s*(?:주식\s*)?소유\s*현황", document
        )
    )
    facts = []
    seen = set()
    for start in starts:
        parser = LocatedRows()
        newline_count = document.count("\n", 0, start.start())
        # Read the first nearby tables, then require the standard ownership header.
        excerpt = document[start.end() : start.end() + 100_000]
        parser.feed(excerpt)
        tables = {}
        for table, row in zip(parser.row_tables, parser.rows):
            tables.setdefault(table, []).append(row)
        for rows in list(tables.values())[:4]:
            header = compact(" ".join(c[0] for row in rows[:3] for c in row))
            if not all(label in header for label in ("관계", "주식수", "지분율")):
                continue
            for row in rows:
                if len(row) not in (7, 8):
                    continue
                cells = [cell[0] for cell in row]
                numeric = all(
                    re.fullmatch(r"[\d,.%\-]+", value) for value in cells[3:7]
                )
                line = row[0][1] + newline_count
                if numeric and cells[0] and line not in seen:
                    seen.add(line)
                    facts.append(
                        {
                            "field": "reported_shareholder_position",
                            "line": line,
                            "holder": cells[0],
                            "role": cells[1],
                            "security": cells[2],
                            "opening_shares": cells[3],
                            "opening_ratio": cells[4],
                            "closing_shares": cells[5],
                            "closing_ratio": cells[6],
                        }
                    )
    return facts


def extract_fields(document, kind, correction):
    if kind == "officer":
        parser = FieldParser()
        parser.feed(document)
        return [
            {
                "field": f["key"],
                "value": f["text"],
                "line": f["line"],
                "path": f["path"],
            }
            for f in parser.fields
            if f["key"] in OFFICER_FIELDS
        ]
    if kind == "periodic":
        return periodic_facts(document)
    parser = LocatedRows()
    parser.feed(document)
    facts = fields_from_rows(zip(parser.row_tables, parser.rows), kind, correction)
    if kind == "share_transfer":
        for row in parser.rows:
            for index, cell in enumerate(row[:-1]):
                label = compact(re.sub(r"^\s*\d+\.\s*", "", cell[0]))
                if label in DEAL_FIELDS and row[index + 1][0] not in ("", "-", "－"):
                    facts.append(fact(label, row[index + 1]))
    return facts


def run(listing, paths, bucket, region, output, workers, shard=0, shards=1):
    sources = inventory_sources(listing)
    filings = {
        row["rcept_no"]: row
        for row in read_metadata(paths)
        if row.get("rcept_no") in sources and family(row.get("report_nm", ""))
    }
    try:
        from botocore.config import Config
        from botocore.session import get_session
    except ImportError:
        from awscli.botocore.config import Config
        from awscli.botocore.session import get_session

    s3 = get_session().create_client(
        "s3", region_name=region, config=Config(max_pool_connections=workers)
    )

    def read_one(receipt):
        row = filings[receipt]
        kind = family(row["report_nm"])
        key = sources[receipt][-1]
        record = {
            "receipt": receipt,
            "kind": kind,
            "filed": row["rcept_dt"],
            "corp_code": row["corp_code"],
            "s3_key": key,
        }
        try:
            with closing(s3.get_object(Bucket=bucket, Key=key)["Body"]) as response:
                raw = response.read()
            if key.lower().endswith(".zip"):
                with ZipFile(io.BytesIO(raw)) as archive:
                    member = next(
                        (
                            n
                            for n in archive.namelist()
                            if n.rsplit("/", 1)[-1] == receipt + ".xml"
                        ),
                        None,
                    )
                    if member is None:
                        raise ValueError("primary XML missing")
                    raw = archive.read(member)
            try:
                text = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = raw.decode("cp949")
            record["facts"] = extract_fields(
                text, kind, "정정" in row["report_nm"].split("]")[0]
            )
            record["sha256"] = hashlib.sha256(raw).hexdigest()
        except (ValueError, OSError, BadZipFile, s3.exceptions.ClientError) as error:
            record["error"] = str(error)
        return record

    counts = Counter()
    identifiers = sorted(filings)[shard::shards]
    output.mkdir(parents=True, exist_ok=True)
    temporary = output / "ownership.jsonl.part"
    with ThreadPoolExecutor(max_workers=workers) as pool, temporary.open("w") as file:
        for start in range(0, len(identifiers), workers * 2):
            for record in pool.map(read_one, identifiers[start : start + workers * 2]):
                state = (
                    "error"
                    if "error" in record
                    else "fields"
                    if record["facts"]
                    else "no_fields"
                )
                counts[record["filed"][:4], record["kind"], state] += 1
                file.write(json.dumps(record, ensure_ascii=False) + "\n")
    temporary.replace(output / "ownership.jsonl")
    summary = [
        {"year": y, "family": k, "status": s, "count": n}
        for (y, k, s), n in sorted(counts.items())
    ]
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2)
    )
    print(json.dumps(summary, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("listing", type=Path)
    parser.add_argument("metadata", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--shards", type=int, default=1)
    args = parser.parse_args()
    if not 0 <= args.shard < args.shards:
        parser.error("--shard must be in the range [0, --shards)")
    paths = sorted(
        p
        for p in args.metadata.rglob("*")
        if p.name in {"filings.json", "filings.jsonl"}
    )
    run(
        args.listing,
        paths,
        args.bucket,
        args.region,
        args.output,
        args.workers,
        args.shard,
        args.shards,
    )


if __name__ == "__main__":
    main()
