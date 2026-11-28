"""Export the two public OpenDART graph snapshots on EC2."""

import argparse
import csv
import gzip
import hashlib
import json
import re
from collections import Counter
from contextlib import ExitStack
from pathlib import Path

from load_opendart_rdf_inventory import NS, database

NODE_FIELDS = {
    "Filing": "receipt receipt_date title source_state",
    "Company": "corp_code stock_code corp_class name",
    "SourceDocument": "bytes format",
    "SupplyContract": "receipt buyer_status",
    "TraceSupplyContract": "receipt buyer_status",
    "TraceContractEvidence": "xml_line sha256",
    "ContractTermsObservation": "observation_type supplier_reported_sales_pct start_date end_date signed_date contract_amount_krw known_on source_sha256",
    "ProductCategory": "id name",
    "FacilityInvestment": "receipt planned_amount_krw amount_line target_line known_on source_sha256 status",
    "FinancialObservation": "value_krw value_line period_end period_start metric consolidation_scope publication_stage known_on source_sha256",
}
RDF_LINE = re.compile(r"^(<[^>]+>) <([^>]+)> (.+) \.$")
NUMERIC = re.compile(r"[+\-]?[\d,.]+\s*%?|\d{4}-\d{2}-\d{2}")
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
SUBCLASS = "http://www.w3.org/2000/01/rdf-schema#subClassOf"


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def pages(query, statement, *, step=20000):
    cursor = -1
    while True:
        rows = query(statement, cursor=cursor, size=step)
        if not rows:
            return
        yield from rows
        cursor = rows[-1][0]


def export_lpg(query, out):
    nodes, relationships = Counter(), Counter()
    node_count = 0
    internal_labels = ["OpenDartRdfTerm", "ControllerRdfTerm"]
    with gzip.open(
        out / "lpg-nodes.csv.gz", "wt", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(["NODE_ID", "LABELS_JSON", "PROPERTIES_JSON"])
        for node_id, labels, props in pages(
            query,
            """
            MATCH (n) WHERE id(n) > $cursor
              AND NOT n:OpenDartRdfTerm AND NOT n:ControllerRdfTerm
            RETURN id(n), labels(n), properties(n)
            ORDER BY id(n) LIMIT $size
        """,
        ):
            allowed = set()
            for label in labels:
                if label in internal_labels:
                    raise ValueError(label)
                allowed.update(NODE_FIELDS[label].split())
            result = {k: v for k, v in props.items() if k in allowed}
            if "SourceDocument" in labels:
                receipt = re.search(
                    r"(\d{14})\.(?:zip|xml)$", props.get("s3_key", ""), re.IGNORECASE
                )
                if receipt:
                    result["document_url"] = dart_url(receipt[1])
            nodes.update(labels)
            node_count += 1
            writer.writerow([node_id, encode(sorted(labels)), encode(result)])
    with gzip.open(
        out / "lpg-relationships.csv.gz", "wt", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["RELATIONSHIP_ID", "SOURCE_ID", "TARGET_ID", "TYPE", "PROPERTIES_JSON"]
        )
        for rel_id, source, target, kind, props in pages(
            query,
            """
            MATCH (s)-[r]->(t) WHERE id(r) > $cursor
              AND NOT type(r) IN ['OPENDART_RDF_TRIPLE', 'CONTROLLER_RDF_TRIPLE']
              AND NOT s:OpenDartRdfTerm AND NOT s:ControllerRdfTerm
              AND NOT t:OpenDartRdfTerm AND NOT t:ControllerRdfTerm
            RETURN id(r), id(s), id(t), type(r), properties(r)
            ORDER BY id(r) LIMIT $size
        """,
        ):
            relationships[kind] += 1
            writer.writerow(
                [
                    rel_id,
                    source,
                    target,
                    kind,
                    encode(
                        {
                            key: props[key]
                            for key in ("identity_receipt",)
                            if key in props
                        }
                    ),
                ]
            )
    return {
        "nodes": node_count,
        "relationships": sum(relationships.values()),
        "node_labels": dict(nodes),
        "relationship_types": dict(relationships),
    }


def dart_url(receipt):
    return f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}"


def export_rdf(data, source_summary, out):
    inferred = {f"<{NS[name]}>" for name in source_summary["inferred_types"]}
    counts = Counter()
    with ExitStack() as stack:
        original = stack.enter_context(gzip.open(data, "rt", encoding="utf-8"))
        asserted = stack.enter_context(
            gzip.open(out / "rdf-asserted.nt.gz", "wt", encoding="utf-8")
        )
        derived = stack.enter_context(
            gzip.open(out / "rdf-inferred.nt.gz", "wt", encoding="utf-8")
        )
        ontology = stack.enter_context(
            (out / "ontology.ttl").open("w", encoding="utf-8")
        )
        for line in original:
            match = RDF_LINE.fullmatch(line.rstrip("\n"))
            if not match:
                raise ValueError("Invalid N-Triples line")
            subject, predicate, obj = match.groups()
            name = predicate.removeprefix(str(NS))
            if name == "sourceObject":
                if subject.startswith(f"<{NS}xml:"):
                    receipt = subject.removeprefix(f"<{NS}xml:")[:14]
                    asserted.write(
                        f"{subject} <{NS.documentUrl}> <{dart_url(receipt)}> .\n"
                    )
                    counts["asserted"] += 1
                else:
                    counts["omitted_internal_path"] += 1
                continue
            if name in {"value", "before", "after"} and not (
                obj.startswith('"')
                and obj.endswith('"')
                and NUMERIC.fullmatch(obj[1:-1])
            ):
                counts["omitted_free_text"] += 1
                continue
            if predicate == RDF_TYPE and obj in inferred:
                derived.write(line)
                counts["inferred"] += 1
            else:
                asserted.write(line)
                counts["asserted"] += 1
                if predicate == SUBCLASS or (
                    predicate == RDF_TYPE
                    and obj.startswith("<http://www.w3.org/2002/07/owl#")
                ):
                    ontology.write(line)
    if counts["inferred"] != source_summary["inferred_triples"]:
        raise ValueError(f"Unexpected inferred count {counts}")
    return dict(counts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    source_summary = json.loads((args.input / "summary.json").read_text())
    stats = {
        "lpg": export_lpg(database("fintos-disclosure-kg", 27474), args.output),
        "rdf": export_rdf(args.input / "opendart.nt.gz", source_summary, args.output),
        "rdf_source_summary": source_summary,
    }
    assets = {}
    for file in sorted(args.output.iterdir()):
        if file.is_file() and file.name != "manifest.json":
            with file.open("rb") as handle:
                digest = hashlib.sha256()
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            assets[file.name] = {
                "bytes": file.stat().st_size,
                "sha256": digest.hexdigest(),
            }
    stats["files"] = assets
    (args.output / "manifest.json").write_text(encode(stats) + "\n", encoding="utf-8")
    print(encode(stats))


if __name__ == "__main__":
    main()
