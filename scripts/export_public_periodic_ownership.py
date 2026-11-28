"""Export an allowlisted periodic ownership supplement for the public v1 graph."""

import argparse
import gzip
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

NS = "urn:fintos:opendart:"
TRIPLE = re.compile(r"^<([^>]+)> <([^>]+)> (.+) \.$")
ASSERTION = re.compile(NS + r"assertion:(\d{14}):\d+")
NUMERIC_TYPES = {
    "openingShareCount": "integer",
    "closingShareCount": "integer",
    "openingOwnershipPercent": "decimal",
    "closingOwnershipPercent": "decimal",
}
ROLES = {"최대주주", "특수관계인", "본인", "임원"}
PUBLIC_EXAMPLE = (NS + "assertion:20261116001715:0", "SK스퀘어(주)")


def export(base, delta, output):
    anchors = set()
    with gzip.open(base, "rt", encoding="utf-8") as stream:
        for line in stream:
            if f"> <{NS}field> \"reported_shareholder_position\" ." in line:
                anchors.add(line.split(">", 1)[0][1:])
    counts = Counter()
    subjects = set()
    receipts = set()
    output.mkdir(parents=True, exist_ok=True)
    graph = output / "rdf-periodic-ownership.nt.gz"
    with gzip.open(delta, "rt", encoding="utf-8") as source, graph.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as dest:
            for line in source:
                subject, predicate, value = TRIPLE.fullmatch(line.rstrip()).groups()
                anchor = ASSERTION.fullmatch(subject)
                if subject not in anchors or not anchor:
                    raise ValueError(f"No public v1 assertion for {subject}")
                field = predicate.removeprefix(NS)
                literal = json.JSONDecoder().raw_decode(value)[0]
                if field in NUMERIC_TYPES:
                    if not value.endswith(f"^^<http://www.w3.org/2001/XMLSchema#{NUMERIC_TYPES[field]}>"):
                        raise ValueError(f"Unexpected datatype for {field}")
                elif field == "reportedHolderRole" and literal in ROLES:
                    pass
                elif field == "reportedHolderName" and (subject, literal) == PUBLIC_EXAMPLE:
                    pass
                else:
                    counts["excluded:" + field] += 1
                    continue
                counts[field] += 1
                subjects.add(subject)
                receipts.add(anchor[1])
                dest.write(line.encode("utf-8"))
    if counts["reportedHolderName"] != 1:
        raise ValueError("The verified corporate example was not exported")
    return {"version": "20261128-v1.1", "requires": "fintos-opendart-20261127-v1",
            "periodic_filings": len(receipts), "assertions": len(subjects),
            "asserted_triples": sum(n for field, n in counts.items()
                                    if not field.startswith("excluded:")),
            "predicates": dict(counts)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "delta", "output"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    report = export(args.base, args.delta, args.output)
    report["files"] = {file.name: {"bytes": file.stat().st_size,
                                    "sha256": hashlib.sha256(file.read_bytes()).hexdigest()}
                       for file in sorted(args.output.iterdir()) if file.is_file()
                       and file.name != "manifest.json"}
    (args.output / "manifest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
