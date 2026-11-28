"""Load the audited controller-change RDF sample into EC2 Neo4j."""
import argparse
import base64
import json
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen

from owlrl import DeductiveClosure, OWLRL_Semantics
from pyshacl import validate
from rdflib import OWL, RDF, RDFS, XSD, Graph, Literal, URIRef

from controller_graph_benchmark import EX, SHAPES, put_types, source_cells, temporal_rows

CORRECTION = "20261029800490"
ORIGINAL = "20261028800611"


def build_graph(snapshot, audit):
    docs = {doc["receipt"]: doc for doc in snapshot["documents"]}
    graph = Graph()
    graph.add((EX.ControllerChangeOntology, RDF.type, OWL.Ontology))
    rows = []
    for case in audit["cases"]:
        receipt = case["receipt"]
        doc = docs[receipt]
        cells = source_cells(doc)
        if doc["sha256"] != case["sha256"] or list(cells["reason"]) != case["reason"]:
            raise ValueError(f"Benchmark source differs for {receipt}")
        leaf, parent = case["leaf"], case["parent"]
        for kind in (leaf, parent):
            graph.add((EX[kind], RDF.type, OWL.Class))
        put_types(graph, "bench:" + receipt, leaf, parent,
                  f"{receipt}:{cells['reason'][1]}", doc["filed"])
        rows.extend(temporal_rows(doc, cells))

    corrected = docs[CORRECTION]
    ratio, line = source_cells(corrected)["ratio"]
    rows.append(dict(event="bench:" + ORIGINAL, filed=corrected["filed"],
                     receipt=CORRECTION, field="ratio", value=ratio, line=line))

    def assertion(receipt, field):
        return EX[f"assertion:{receipt}:{field}"]

    for row in rows:
        receipt = row["receipt"]
        node = assertion(receipt, row["field"])
        source = EX[receipt]
        graph.add((node, RDF.type, EX.Assertion))
        graph.add((node, EX.aboutEvent, EX[row["event"]]))
        graph.add((node, EX.source, source))
        graph.add((node, EX.published, Literal(row["filed"], datatype=XSD.date)))
        graph.add((node, EX.field, Literal(row["field"])))
        graph.add((node, EX.value, Literal(row["value"])))
        graph.add((node, EX.line, Literal(row["line"])))
        graph.add((source, EX.sha256, Literal(docs[receipt]["sha256"])))
        graph.add((source, EX.documentUrl, URIRef(
            f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}"
        )))
    graph.add((EX[CORRECTION], EX.corrects, EX[ORIGINAL]))
    graph.add((assertion(CORRECTION, "ratio"), EX.supersedes, assertion(ORIGINAL, "ratio")))
    valid, _, report = validate(graph, shacl_graph=Graph().parse(data=SHAPES, format="turtle"))
    if not valid:
        raise ValueError(report)
    return graph


def term(node):
    return dict(key=node.n3(), value=str(node), kind="IRI" if isinstance(node, URIRef) else "LITERAL",
                datatype=str(node.datatype) if isinstance(node, Literal) and node.datatype else "",
                language=node.language or "" if isinstance(node, Literal) else "")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("audit", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--container", default="fintos-disclosure-kg")
    parser.add_argument("--port", type=int, default=27474)
    args = parser.parse_args()
    audit = json.loads(args.audit.read_text())
    if len({case["receipt"] for case in audit["cases"]}) != 30:
        raise ValueError("Expected 30 audited events")
    graph = build_graph(json.loads(args.snapshot.read_text()), audit)
    graph.serialize(destination=str(args.output), format="turtle")
    closure = Graph()
    closure += graph
    DeductiveClosure(OWLRL_Semantics).expand(closure)
    inferred = {
        (s, RDF.type, o) for s, _, o in closure.triples((None, RDF.type, None))
        if str(s).startswith(str(EX["bench:"])) and (o, RDF.type, OWL.Class) in graph
        and (s, RDF.type, o) not in graph
    }
    if len(inferred) != 30:
        raise ValueError("Expected 30 inferred event types")

    config = json.loads(subprocess.check_output(["docker", "inspect", args.container]))[0]
    env = dict(item.split("=", 1) for item in config["Config"]["Env"])
    auth = base64.b64encode(env["NEO4J_AUTH"].replace("/", ":", 1).encode()).decode()

    def query(statement, **parameters):
        request = Request(
            f"http://127.0.0.1:{args.port}/db/neo4j/tx/commit",
            headers={"Content-Type": "application/json", "Authorization": "Basic " + auth},
            data=json.dumps({"statements": [dict(statement=statement, parameters=parameters)]}).encode(),
        )
        with urlopen(request, timeout=60) as response:
            result = json.load(response)
        if result["errors"]:
            raise RuntimeError(result["errors"])
        return [item["row"] for item in result["results"][0]["data"]]

    dataset = "controller-audit-v1"
    records = [
        dict(subject=term(s), predicate=str(p), object=term(o), inferred=(s, p, o) in inferred)
        for s, p, o in set(graph) | inferred
    ]
    query("""CREATE CONSTRAINT controller_rdf_term_key IF NOT EXISTS
             FOR (n:ControllerRdfTerm) REQUIRE (n.dataset, n.key) IS UNIQUE""")
    query("""
    UNWIND $records AS row
    MERGE (s:ControllerRdfTerm {dataset:$dataset, key:row.subject.key})
    SET s += row.subject
    MERGE (o:ControllerRdfTerm {dataset:$dataset, key:row.object.key})
    SET o += row.object
    MERGE (s)-[r:CONTROLLER_RDF_TRIPLE {predicate:row.predicate}]->(o)
    SET r.inferred = row.inferred
    """, dataset=dataset, records=records)

    counts = query("""
    MATCH (s:ControllerRdfTerm {dataset:$dataset})-[r:CONTROLLER_RDF_TRIPLE]->()
    RETURN r.inferred, count(*) ORDER BY r.inferred
    """, dataset=dataset)
    assert counts == [[False, len(graph)], [True, len(inferred)]], counts
    for cutoff, expected_ratio, ratio_receipt in [
        ("2026-10-28", "52.25", ORIGINAL), ("2026-10-29", "52.39", CORRECTION)
    ]:
        rows = query("""
        MATCH (event:ControllerRdfTerm {dataset:$dataset, value:$event})
              -[:CONTROLLER_RDF_TRIPLE {predicate:$type, inferred:true}]->
              (:ControllerRdfTerm {value:$parent})
        MATCH (event)<-[:CONTROLLER_RDF_TRIPLE {predicate:$about}]-(a)
              -[:CONTROLLER_RDF_TRIPLE {predicate:$published}]->(d)
        WHERE d.value <= $cutoff AND NOT EXISTS {
          MATCH (a)<-[:CONTROLLER_RDF_TRIPLE {predicate:$supersedes}]-(b)
                -[:CONTROLLER_RDF_TRIPLE {predicate:$published}]->(newDate)
          WHERE newDate.value <= $cutoff
        }
        MATCH (a)-[:CONTROLLER_RDF_TRIPLE {predicate:$field}]->(f),
              (a)-[:CONTROLLER_RDF_TRIPLE {predicate:$value}]->(v),
              (a)-[:CONTROLLER_RDF_TRIPLE {predicate:$source}]->(s)
        RETURN f.value, v.value, s.value ORDER BY f.value
        """, dataset=dataset, event=str(EX["bench:" + ORIGINAL]), type=str(RDF.type),
             parent=str(EX.CorporateRestructuring), about=str(EX.aboutEvent),
             published=str(EX.published), cutoff=cutoff, supersedes=str(EX.supersedes),
             field=str(EX.field), value=str(EX.value), source=str(EX.source))
        assert rows == [["change_date", "2026-10-27", str(EX[ORIGINAL])],
                        ["ratio", expected_ratio, str(EX[ratio_receipt])]], rows
        print(cutoff, rows)
    print(json.dumps(dict(dataset=dataset, asserted=len(graph), inferred=len(inferred))))


if __name__ == "__main__":
    main()
