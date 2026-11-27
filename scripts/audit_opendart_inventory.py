"""Count S3 OpenDART documents by unique receipt, year and normalized report title."""

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

RECEIPT_FILE = re.compile(r"(\d{14})\.(zip|xml)$", re.IGNORECASE)


def title(value):
    return re.sub(r"^(?:\s*\[[^]]+\])*\s*", "", value).replace(" ", "").strip()


def read_metadata(paths):
    for path in paths:
        with path.open(encoding="utf-8-sig") as source:
            if path.suffix == ".jsonl":
                yield from (json.loads(line) for line in source if line.strip())
            else:
                yield from json.load(source)


def audit(listing, paths):
    documents = defaultdict(set)
    files = Counter()
    with listing.open() as source:
        for line in source:
            parts = line.split(maxsplit=3)
            if len(parts) != 4 or "/documents/" not in parts[3]:
                continue
            match = RECEIPT_FILE.fullmatch(parts[3].strip().rsplit("/", 1)[-1])
            if match:
                receipt, ext = match.groups()
                files[ext.lower()] += 1
                documents[receipt].add(ext.lower())
    metadata = {}
    for row in read_metadata(paths):
        receipt = row.get("rcept_no")
        if receipt in documents:
            metadata[receipt] = row
    years = defaultdict(Counter)
    types = Counter()
    for receipt, formats in documents.items():
        row = metadata.get(receipt)
        year = (row.get("rcept_dt") or receipt)[:4] if row else receipt[:4]
        years[year]["receipts"] += 1
        years[year]["zip"] += "zip" in formats
        years[year]["xml_only"] += formats == {"xml"}
        years[year]["metadata_unmatched"] += row is None
        types[
            year, title(row.get("report_nm") or "") if row else "(metadata unavailable)"
        ] += 1
    return {
        "objects": dict(files),
        "unique_receipts": len(documents),
        "years": dict(sorted(years.items())),
        "metadata_joined": len(metadata),
    }, types


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("listing", type=Path)
    parser.add_argument("metadata", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    paths = sorted(
        p
        for p in args.metadata.rglob("*")
        if (
            p.name in {"filings.json", "filings.jsonl"}
            or re.fullmatch(r"\d{8}_\d{8}\.json", p.name)
        )
    )
    summary, types = audit(args.listing, paths)
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / "by_year_title.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as file:
        writer = csv.writer(file)
        writer.writerow(["year", "normalized_title", "unique_receipts"])
        writer.writerows(
            (year, name, count) for (year, name), count in sorted(types.items())
        )
    (args.output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2)
    )
    print(json.dumps(summary, ensure_ascii=False))
    for year in summary["years"]:
        print(
            year,
            Counter(
                {name: count for (y, name), count in types.items() if y == year}
            ).most_common(15),
        )


if __name__ == "__main__":
    main()
