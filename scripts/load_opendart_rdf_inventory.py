"""Build a dated OpenDART RDF export and load its property graph projection."""

import argparse
import base64
import csv
import gzip
import json
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from urllib.request import Request, urlopen

from audit_opendart_inventory import read_metadata, title
from controller_graph_benchmark import TYPES
from extract_ownership_inventory import family, inventory_sources
from extract_ownership_inventory import run as extract
from link_ownership_inventory import run as link_extended
from rdflib import OWL, RDF, RDFS, XSD, Graph, Literal, Namespace, URIRef
from rdflib.plugins.serializers.nt import _quoteLiteral

from knowledge_graph.ingestion.control_ownership import correction_target, reconcile

NS = Namespace("urn:fintos:opendart:")
START, END = "20260101", "20261127"
DATASET = f"opendart-{START}-{END}-v1"
CLASSES = {
    "controller": "ControllerChange",
    "holding": "LargeHoldingReport",
    "share_transfer": "ShareTransferDisclosure",
    "officer": "OfficerHoldingReport",
    "periodic": "PeriodicOwnershipReport",
}
SUPERS = {
    "ControllerChange": "OwnershipEvent",
    "OwnershipEvent": "DisclosureEvent",
    "ShareTransferDisclosure": "DisclosureEvent",
    "LargeHoldingReport": "OwnershipObservation",
    "OfficerHoldingReport": "OwnershipObservation",
    "PeriodicOwnershipReport": "OwnershipObservation",
    **{leaf: parent for leaf, (_, parent) in TYPES.items()},
}
OWNERSHIP_META = {
    "corrected_title",
    "corrected_date",
    "correction_item",
    "related_filing",
}


def filing(receipt):
    return NS[f"filing:{receipt}"]


def event(receipt):
    return NS[f"event:{receipt}"]


def source(uri):
    return URIRef("s3://fintos-dev-data-gugst5ck/" + uri)


def dated(value):
    day = value.replace("-", "")
    return Literal(f"{day[:4]}-{day[4:6]}-{day[6:8]}", datatype=XSD.date)


def rows_jsonl(path):
    with path.open() as handle:
        yield from map(json.loads, handle)


def read_inputs(root, inventory):
    paths = sorted(
        p
        for base in (inventory / "metadata/legacy", root / "metadata")
        for p in base.rglob("*")
        if p.name in {"filings.json", "filings.jsonl"}
    )
    objects = root / "objects.txt"
    sources = inventory_sources(objects)
    metadata = {
        row["rcept_no"]: row
        for row in read_metadata(paths)
        if row.get("rcept_no") in sources
    }
    selected = {
        receipt: metadata.get(receipt, {})
        for receipt in sources
        if START <= (metadata.get(receipt, {}).get("rcept_dt") or receipt[:8]) <= END
    }
    ownership = {}
    for path in sorted((inventory / "extraction").glob("*/ownership.jsonl")):
        ownership.update(
            (row["receipt"], row)
            for row in rows_jsonl(path)
            if row["receipt"] in selected
        )
    delta = {
        r
        for r, row in selected.items()
        if family(row.get("report_nm", ""))
        and (
            r not in ownership
            or sources[r][-1] != ownership[r]["s3_key"]
            or ownership[r].get("error")
        )
    }
    if delta:
        listing = root / "delta-objects.txt"
        with listing.open("w") as handle:
            for receipt in sorted(delta):
                handle.write(f"2000-01-01 00:00:00 0 {sources[receipt][-1]}\n")
        extract(
            listing,
            paths,
            "fintos-dev-data-gugst5ck",
            "ap-southeast-2",
            root / "delta",
            12,
        )
        ownership.update(
            (row["receipt"], row) for row in rows_jsonl(root / "delta/ownership.jsonl")
        )
    return sources, selected, ownership, paths


def ownership_model(root, selected, ownership, paths):
    groups = defaultdict(list)
    for receipt, row in ownership.items():
        if not row.get("facts"):
            continue
        metadata = selected[receipt]
        doc = dict(
            row,
            filed=str(dated(row["filed"])),
            company=metadata.get("corp_name", ""),
            submitter=metadata.get("flr_nm", ""),
            title=metadata.get("report_nm", ""),
            correction="정정" in metadata.get("report_nm", "").split("]", 1)[0],
        )
        groups[doc["corp_code"], doc["kind"]].append(doc)
    controller_docs = [
        doc
        for (_, kind), docs in groups.items()
        if kind in {"controller", "holding"}
        for doc in docs
    ]
    model = reconcile(controller_docs, {}, {"start": START, "end": END}, [], 35)
    for (_, kind), docs in groups.items():
        if kind in {"controller", "holding"}:
            continue
        for doc in docs:
            if doc["correction"]:
                model["corrections"].append(
                    dict(kind=kind, **correction_target(doc, docs))
                )

    extended = root / "link-input" / "all"
    extended.mkdir(parents=True, exist_ok=True)
    with (extended / "ownership.jsonl").open("w") as handle:
        for record in ownership.values():
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    extra = link_extended(model, extended.parent, paths)
    return model, extra


def filing_graphs(selected, sources, counts):
    for receipt, row in sorted(selected.items()):
        node = filing(receipt)
        report_type = title(row.get("report_nm", "")) or "(metadata unavailable)"
        counts[report_type] += 1
        triples = {
            (node, RDF.type, NS.Filing),
            (node, NS.receipt, Literal(receipt)),
            (node, NS.receiptDate, dated(row.get("rcept_dt") or receipt[:8])),
            (node, NS.sourceObject, source(sources[receipt][-1])),
            (node, NS.reportType, Literal(report_type)),
            (
                node,
                NS.documentUrl,
                URIRef(f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}"),
            ),
        }
        if not row.get("rcept_dt"):
            triples.add((node, NS.dateBasis, Literal("receipt_prefix")))
        if row.get("report_nm"):
            triples.add((node, NS.reportTitle, Literal(row["report_nm"])))
        if row.get("corp_code"):
            company = NS[f"company:{row['corp_code']}"]
            triples.add((node, NS.aboutCompany, company))
            triples.add((company, RDF.type, NS.Company))
        yield triples


def ownership_graph(selected, ownership, model, extra):
    graph = Graph()
    graph.add((NS.Ontology, RDF.type, OWL.Ontology))
    for child, parent in SUPERS.items():
        graph.add((NS[child], RDF.type, OWL.Class))
        graph.add((NS[parent], RDF.type, OWL.Class))
        graph.add((NS[child], RDFS.subClassOf, NS[parent]))
    correction_counts, link_counts, by_family = (
        Counter(),
        Counter(),
        defaultdict(Counter),
    )
    controller_events = {x["receipt"] for x in model["events"]}
    targets = {}

    def evidence_at(receipt, line):
        evidence = NS[f"evidence:{receipt}:{line}"]
        record = ownership.get(receipt)
        graph.add((evidence, NS.line, Literal(line)))
        if record and record.get("sha256"):
            document = NS[f"xml:{receipt}:{record['sha256']}"]
            graph.add((evidence, NS.locatedIn, document))
        return evidence

    for correction in model["corrections"]:
        receipt, target = correction["receipt"], correction["target"]
        correction_counts[correction["kind"], correction["status"]] += 1
        assessment = NS[f"correction:{receipt}"]
        graph.add((filing(receipt), NS.correctionAssessment, assessment))
        graph.add((assessment, NS.status, Literal(correction["status"])))
        graph.add((assessment, NS.reason, Literal(correction["reason"])))
        for fact in correction["evidence"]:
            if fact.get("line"):
                evidence = evidence_at(receipt, fact["line"])
                graph.add((assessment, NS.supportedBy, evidence))
        if target and target in selected:
            graph.add((filing(receipt), NS.corrects, filing(target)))
            targets[receipt] = target

    for receipt, record in ownership.items():
        kind = record["kind"]
        by_family[kind]["candidate"] += 1
        facts = record.get("facts", [])
        if not facts:
            by_family[kind]["error" if record.get("error") else "no_fields"] += 1
            continue
        by_family[kind]["with_fields"] += 1
        observation = event(receipt)
        filing_node = filing(receipt)
        title_value = selected[receipt].get("report_nm", "")
        is_correction = "정정" in title_value.split("]", 1)[0]
        is_event = receipt in controller_events or (
            kind != "controller" and not is_correction
        )
        target = targets.get(receipt)
        existing_event = target and (
            target in controller_events
            or (
                kind != "controller"
                and target in ownership
                and ownership[target].get("facts")
                and "정정" not in selected[target].get("report_nm", "").split("]", 1)[0]
            )
        )
        if existing_event:
            observation = event(target)
            graph.add((filing_node, NS.reportsEvent, observation))
        if is_event:
            graph.add((filing_node, NS.reportsEvent, observation))
            graph.add((observation, RDF.type, NS[CLASSES[kind]]))
            by_family[kind]["classified"] += 1
        document = NS[f"xml:{receipt}:{record['sha256']}"]
        graph.add((document, NS.sha256, Literal(record["sha256"])))
        graph.add((document, NS.sourceObject, source(record["s3_key"])))
        graph.add((filing_node, NS.documentVersion, document))
        for index, fact in enumerate(facts):
            assertion = NS[f"assertion:{receipt}:{index}"]
            field = fact["field"]
            graph.add((filing_node, NS.reportsAssertion, assertion))
            graph.add((assertion, NS.field, Literal(field)))
            if (is_event or existing_event) and field not in OWNERSHIP_META:
                graph.add((assertion, NS.aboutEvent, observation))
            for attr in ("value", "before", "after", "scope", "phase", "security"):
                if fact.get(attr) is not None:
                    graph.add((assertion, NS[attr], Literal(str(fact[attr]))))
            if fact.get("line"):
                evidence = evidence_at(receipt, fact["line"])
                graph.add((assertion, NS.supportedBy, evidence))
            if receipt in controller_events and field in {"reason", "change_reason"}:
                value = str(fact.get("value", ""))
                matches = [
                    leaf
                    for leaf, (pattern, _) in TYPES.items()
                    if re.search(pattern, value)
                ]
                if len(matches) == 1:
                    graph.add((observation, RDF.type, NS[matches[0]]))
                    graph.add((observation, NS.classificationEvidence, assertion))

    for kind, items in (("holding", model["links"]), ("extended", extra["links"])):
        for index, link in enumerate(items):
            original, related = link["event_receipt"], link["related_receipt"]
            if original not in controller_events or related not in selected:
                continue
            status = link.get("classification") or link["basis"]
            family_name = link.get("family", kind)
            link_counts[family_name, status] += 1
            assessment = NS[f"link:{kind}:{index}"]
            graph.add((assessment, NS.status, Literal(status)))
            graph.add((assessment, NS.candidateEvent, event(original)))
            graph.add((filing(related), NS.linkAssessment, assessment))
            if status in {"same_transaction", "quantity_support"} or kind == "extended":
                predicate = {"same_transaction": NS.reportsSameTransaction}.get(
                    status, NS.supportsEvent
                )
                graph.add((filing(related), predicate, event(original)))
            locations = link.get("evidence", []) + [
                {"receipt": related, "line": line}
                for line in link.get("source_lines", [])
            ]
            for place in locations:
                if place.get("receipt") and place.get("line"):
                    addr = evidence_at(place["receipt"], place["line"])
                    graph.add((assessment, NS.supportedBy, addr))

    inferred = set()
    for subject, _, cls in graph.triples((None, RDF.type, None)):
        current = str(cls).removeprefix(str(NS))
        while current in SUPERS:
            current = SUPERS[current]
            triple = (subject, RDF.type, NS[current])
            if triple not in graph:
                inferred.add(triple)
    stats = {
        "ownership": {k: dict(v) for k, v in sorted(by_family.items())},
        "corrections": {
            f"{k}/{v}": n for (k, v), n in sorted(correction_counts.items())
        },
        "links": {f"{k}/{v}": n for (k, v), n in sorted(link_counts.items())},
        "inferred_types": dict(
            Counter(str(obj).removeprefix(str(NS)) for _, _, obj in inferred)
        ),
    }
    return graph, inferred, stats


def database(container, port):
    config = json.loads(subprocess.check_output(["docker", "inspect", container]))[0]
    env = dict(item.split("=", 1) for item in config["Config"]["Env"])
    auth = base64.b64encode(env["NEO4J_AUTH"].replace("/", ":", 1).encode()).decode()

    def query(statement, **parameters):
        request = Request(
            f"http://127.0.0.1:{port}/db/neo4j/tx/commit",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Basic " + auth,
            },
            data=json.dumps(
                {"statements": [{"statement": statement, "parameters": parameters}]}
            ).encode(),
        )
        with urlopen(request, timeout=180) as response:
            reply = json.load(response)
        if reply["errors"]:
            raise RuntimeError(reply["errors"])
        return [entry["row"] for entry in reply["results"][0]["data"]]

    return query


def load_triples(query, triples, inferred, output, predicates=None):
    query("""CREATE CONSTRAINT opendart_rdf_term IF NOT EXISTS
             FOR (n:OpenDartRdfTerm) REQUIRE (n.dataset, n.key) IS UNIQUE""")
    edges = []
    counts = Counter()

    def flush():
        query(
            """
        UNWIND $edges AS row
        MERGE (s:OpenDartRdfTerm {dataset:$dataset, key:row.s})
        ON CREATE SET s.value = row.sv, s.kind = 'IRI'
        MERGE (o:OpenDartRdfTerm {dataset:$dataset, key:row.o})
        ON CREATE SET o.value = row.ov, o.kind = row.kind,
                      o.datatype = row.datatype, o.language = row.language
        MERGE (s)-[r:OPENDART_RDF_TRIPLE {predicate:row.p}]->(o)
        SET r.inferred = row.inferred
        """,
            dataset=DATASET,
            edges=edges,
        )
        edges.clear()

    with gzip.open(output, "wt", encoding="utf-8") as handle:
        for subject, predicate, obj in triples:
            triple = (subject, predicate, obj)
            derived = triple in inferred
            is_literal = isinstance(obj, Literal)
            key = _quoteLiteral(obj) if is_literal else obj.n3()
            handle.write(f"{subject.n3()} {predicate.n3()} {key} .\n")
            edges.append(
                {
                    "s": subject.n3(),
                    "sv": str(subject),
                    "p": str(predicate),
                    "o": key,
                    "ov": str(obj),
                    "kind": "LITERAL" if is_literal else "IRI",
                    "datatype": str(obj.datatype or "") if is_literal else "",
                    "language": (obj.language or "") if is_literal else "",
                    "inferred": derived,
                }
            )
            counts[derived] += 1
            if len(edges) >= 2500:
                flush()
                if sum(counts.values()) % 100000 == 0:
                    print(f"Loaded {sum(counts.values()):,} RDF triples", flush=True)
        if edges:
            flush()
    actual = query(
        """
    MATCH (:OpenDartRdfTerm {dataset:$dataset})-[r:OPENDART_RDF_TRIPLE]->()
    WHERE $predicates IS NULL OR r.predicate IN $predicates
    RETURN r.inferred, count(*)
    """,
        dataset=DATASET, predicates=predicates,
    )
    if dict(actual) != dict(counts):
        raise ValueError(
            f"Neo4j triple count mismatch: expected {counts}, got {actual}"
        )
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("--container", default="fintos-disclosure-kg")
    parser.add_argument("--port", type=int, default=27474)
    args = parser.parse_args()
    sources, selected, ownership, paths = read_inputs(args.root, args.inventory)
    print(
        f"Source receipts: {len(selected):,}; ownership candidates: {len(ownership):,}",
        flush=True,
    )
    model, extra = ownership_model(args.root, selected, ownership, paths)
    graph, inferred, stats = ownership_graph(selected, ownership, model, extra)
    print(
        f"Ownership triples: {len(graph):,}; inferred types: {len(inferred):,}",
        flush=True,
    )
    type_counts = Counter()

    def triples():
        companies = set()
        for packet in filing_graphs(selected, sources, type_counts):
            for subject, predicate, obj in packet:
                if obj == NS.Company and predicate == RDF.type:
                    if subject in companies:
                        continue
                    companies.add(subject)
                yield subject, predicate, obj
        yield from graph
        yield from inferred

    query = database(args.container, args.port)
    temp = args.root / "opendart.nt.gz.part"
    counts = load_triples(query, triples(), inferred, temp)
    actual_types = dict(
        query(
            """
    MATCH (:OpenDartRdfTerm {dataset:$dataset})
          -[:OPENDART_RDF_TRIPLE {predicate:$predicate}]->(t)
    RETURN t.value, count(*)
    """,
            dataset=DATASET,
            predicate=str(NS.reportType),
        )
    )
    if actual_types != type_counts or sum(actual_types.values()) != len(selected):
        raise ValueError("Neo4j filing type counts differ from source inventory")
    actual_inferred = dict(
        query(
            """
    MATCH (:OpenDartRdfTerm {dataset:$dataset})-[:OPENDART_RDF_TRIPLE {inferred:true}]->(t)
    RETURN t.value, count(*)
    """,
            dataset=DATASET,
        )
    )
    if actual_inferred != {str(NS[k]): v for k, v in stats["inferred_types"].items()}:
        raise ValueError("Neo4j inferred type counts differ from the computed closure")
    dates = dict(
        query(
            """
    MATCH (:OpenDartRdfTerm {dataset:$dataset})
          -[:OPENDART_RDF_TRIPLE {predicate:$predicate}]->(t)
    RETURN t.value, count(*)
    """,
            dataset=DATASET,
            predicate=str(NS.receiptDate),
        )
    )
    temp.replace(args.root / "opendart.nt.gz")
    with (args.root / "by_report_type.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(["REPORT_TYPE", "LOADED_FILINGS"])
        writer.writerows(type_counts.most_common())
    stats.update(
        dataset=DATASET,
        filings=len(selected),
        distinct_report_types=len(type_counts),
        asserted_triples=counts[False],
        inferred_triples=counts[True],
        november_27=dates.get("2026-11-27", 0),
        controller_events=len(model["events"]),
        metadata_missing=sum(not row for row in selected.values()),
    )
    (args.root / "summary.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
