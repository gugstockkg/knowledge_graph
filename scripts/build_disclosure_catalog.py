"""Build Neo4j bulk-import CSVs from OpenDART metadata and an S3 object inventory."""
import argparse
import csv
import json
import re
from collections import Counter
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path, PurePosixPath

RECEIPT = re.compile(r"(?<!\d)\d{14}(?!\d)")
SCHEMAS = {
    "filings": ["receipt:ID(Filing)", "receipt_date:date", "title", "filer_name", "remarks",
                "source_state", "catalog_partition", ":LABEL"],
    "companies": ["corp_code:ID(Company)", "name", "stock_code", "corp_class", ":LABEL"],
    "documents": ["s3_key:ID(SourceDocument)", "format", "bytes:long", ":LABEL"],
    "subjects": [":START_ID(Filing)", ":END_ID(Company)", ":TYPE"],
    "sources": [":START_ID(Filing)", ":END_ID(SourceDocument)", ":TYPE"],
}


def metadata_files(root):
    legacy = sorted(root.glob("*.json"), key=lambda path: path.stem)
    yield from legacy
    yield from sorted((root / "daily").glob("partition_day=*/filings.jsonl"))


def read_rows(path):
    with path.open(encoding="utf-8-sig") as source:
        if path.suffix == ".json":
            yield from json.load(source)
        else:
            for line in source:
                if line.strip():
                    yield json.loads(line)


def catalog(root):
    filings = {}
    companies = {}
    stats = Counter()
    for path in metadata_files(root):
        partition = path.parent.name.removeprefix("partition_day=") if path.suffix == ".jsonl" else path.stem
        for row in read_rows(path):
            stats["metadata_rows"] += 1
            receipt = str(row.get("rcept_no", ""))
            if not RECEIPT.fullmatch(receipt):
                raise ValueError(f"Invalid receipt in {path}")
            receipt_date = datetime.strptime(row["rcept_dt"], "%Y%m%d").date().isoformat()
            corp = str(row.get("corp_code") or "")
            previous = filings.get(receipt)
            if previous is not None:
                stats["duplicate_metadata_rows"] += 1
                if previous[:2] != (receipt_date, corp):
                    raise ValueError(f"Conflicting receipt date or company for {receipt}")
            filings[receipt] = (receipt_date, corp, row["report_nm"].strip(), row.get("flr_nm", ""),
                                row.get("rm", ""), row.get("document_state", ""), partition)
            if corp:
                if not re.fullmatch(r"\d{8}", corp):
                    raise ValueError(f"Invalid company code for {receipt}")
                company_data = (row.get("corp_name", ""), row.get("stock_code", ""),
                                row.get("corp_cls", ""))
                if corp not in companies or receipt_date >= companies[corp][0]:
                    companies[corp] = (receipt_date, *company_data)
    if not filings:
        raise ValueError("No filing metadata found")
    return filings, companies, stats


def documents(root, filings, stats):
    for inventory in sorted(root.glob("*.tsv")):
        with inventory.open(encoding="utf-8") as source:
            for line in source:
                fields = line.rstrip("\r\n").split("\t")
                if fields == ["None"]:
                    continue
                key, size = fields
                stats["listed_objects"] += 1
                stats["listed_bytes"] += int(size)
                parts = PurePosixPath(key)
                extension = parts.suffix.lower().removeprefix(".")
                if extension not in {"zip", "xml", "html", "htm"}:
                    continue
                match = next((m for part in reversed(parts.parts) if (m := RECEIPT.search(part)) and m[0] in filings), None)
                if match is None:
                    stats["unmatched_source_objects"] += 1
                    continue
                receipt = match[0]
                stats["source_documents"] += 1
                yield receipt, key, extension, size


def build(root, output):
    filings, companies, stats = catalog(root)
    if not list(root.glob("*.tsv")):
        raise ValueError("No S3 object inventory found")
    output.mkdir()
    with ExitStack() as stack:
        writers = {}
        for name, columns in SCHEMAS.items():
            file = stack.enter_context((output / f"{name}.csv").open("w", encoding="utf-8", newline=""))
            writers[name] = csv.writer(file)
            writers[name].writerow(columns)
        linked = set()
        for receipt, key, extension, size in documents(root, filings, stats):
            linked.add(receipt)
            writers["documents"].writerow((key, extension, size, "SourceDocument"))
            writers["sources"].writerow((receipt, key, "HAS_SOURCE_DOCUMENT"))
        for corp, (_, name, stock_code, corp_class) in sorted(companies.items()):
            writers["companies"].writerow((corp, name, stock_code, corp_class, "Company"))
        for receipt, row in sorted(filings.items()):
            date, corp, title, filer, remarks, state, partition = row
            if receipt in linked:
                state = "available"
            elif not state or state == "downloaded":
                state = "not_in_object_inventory"
            stats[f"source_state_{state}"] += 1
            writers["filings"].writerow((receipt, date, title, filer, remarks, state, partition, "Filing"))
            if corp:
                writers["subjects"].writerow((receipt, corp, "IS_ABOUT"))
                stats["filing_company_links"] += 1
    report = dict(stats, filings=len(filings), companies=len(companies),
                  first_receipt_date=min(x[0] for x in filings.values()),
                  last_receipt_date=max(x[0] for x in filings.values()))
    (output / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path, help="A new output directory")
    args = parser.parse_args()
    print(json.dumps(build(args.input, args.output), ensure_ascii=False))
