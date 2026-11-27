"""Run four graph configurations against the reviewed controller-change event."""

import argparse
import json
import time
from pathlib import Path
from urllib.request import Request, urlopen

from owlrl import DeductiveClosure, OWLRL_Semantics
from rdflib import RDF, RDFS, Graph, Namespace, URIRef

EVENT = "controller:20261028800611"
EX = Namespace("urn:fintos:controller:")
CYPHER = """
MATCH (a:ControllerExperimentAssertion {event:$event})
WHERE a.filed <= $cutoff AND NOT EXISTS {
  MATCH (newer:ControllerExperimentAssertion)-[:SUPERSEDES]->(a)
  WHERE newer.filed <= $cutoff
}
RETURN a.field, a.value, a.receipt, a.line
ORDER BY a.field
"""
SEMANTIC_CYPHER = """
MATCH (e:ControllerExperimentEvent {id:$event})-[:CLASSIFIED_AS]->(t)
MATCH (t)-[:SUBCLASS_OF*0..]->(:ControllerExperimentType {id:'CorporateRestructuring'})
WITH DISTINCT e
"""


def cypher(url, statement, parameters=None):
    request = Request(
        url.rstrip("/") + "/db/neo4j/tx/commit",
        headers={"Content-Type": "application/json"},
        data=json.dumps(
            {"statements": [{"statement": statement, "parameters": parameters or {}}]}
        ).encode(),
    )
    with urlopen(request, timeout=20) as response:
        data = json.load(response)
    if data["errors"]:
        raise RuntimeError(data["errors"])
    return [row["row"] for row in data["results"][0]["data"]]


def records(snapshot):
    docs = {d["receipt"]: d for d in snapshot["documents"]}
    original, correction = (docs[r] for r in ("20261028800611", "20261029800490"))
    relevant = []
    for document, field in [
        (original, "change_date"),
        (original, "ratio"),
        (correction, "ratio"),
    ]:
        (fact,) = [
            f
            for f in document["facts"]
            if f["field"] == field
            and (
                field != "ratio"
                or (f.get("phase"), f.get("scope")) == ("after", "group")
            )
        ]
        relevant.append(
            {
                "event": EVENT,
                "filed": document["filed"],
                "receipt": document["receipt"],
                "field": field,
                "value": fact["value"],
                "line": fact["line"],
            }
        )
    (change_reason,) = [f for f in original["facts"] if f["field"] == "change_reason"]
    if "합병" not in change_reason["value"]:
        raise ValueError("Reviewed merger evidence changed")
    return relevant, [original["receipt"], change_reason["line"]]


def semantic_graph(evidence):
    graph = Graph()
    event = URIRef(EX[EVENT])
    merger = EX.Merger
    graph.add((event, RDF.type, merger))
    graph.add((merger, RDFS.subClassOf, EX.CorporateRestructuring))
    graph.add((event, EX.evidence, URIRef(EX[f"{evidence[0]}:{evidence[1]}"])))
    DeductiveClosure(OWLRL_Semantics).expand(graph)
    return graph


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("isolated_neo4j_url")
    args = parser.parse_args()
    url = args.isolated_neo4j_url
    rows, evidence = records(json.loads(args.snapshot.read_text()))
    graph = semantic_graph(evidence)
    query = f"ASK {{ <{EX[EVENT]}> a <{EX.CorporateRestructuring}> . }}"
    cypher(
        url,
        """
    UNWIND $rows AS row
    MERGE (a:ControllerExperimentAssertion {event: row.event, receipt: row.receipt, field: row.field})
    SET a += row
    """,
        {"rows": rows},
    )
    cypher(
        url,
        """
    MATCH (a:ControllerExperimentAssertion {receipt:'20261028800611', field:'ratio'}),
          (b:ControllerExperimentAssertion {receipt:'20261029800490', field:'ratio'})
    MERGE (b)-[:SUPERSEDES]->(a)
    """,
    )
    results = []
    for cutoff, ratio, receipt in [
        ("2026-10-28", "52.25", "20261028800611"),
        ("2026-10-29", "52.39", "20261029800490"),
    ]:
        started = time.perf_counter()
        args = {"event": EVENT, "cutoff": cutoff}
        temporal = cypher(url, CYPHER, args)
        rdf = bool(graph.query(query).askAnswer)
        hybrid = (
            {
                "type": "CorporateRestructuring",
                "assertions": temporal,
                "type_evidence": evidence,
            }
            if rdf
            else None
        )
        # The integrated graph gets the same asserted fact and subclass axiom.
        cypher(
            url,
            """
        MERGE (e:ControllerExperimentEvent {id:$event})
        SET e.receipt=$receipt, e.line=$line
        MERGE (m:ControllerExperimentType {id:'Merger'})
        MERGE (c:ControllerExperimentType {id:'CorporateRestructuring'})
        MERGE (e)-[:CLASSIFIED_AS]->(m)
        MERGE (m)-[:SUBCLASS_OF]->(c)
        """,
            {"event": EVENT, "receipt": evidence[0], "line": evidence[1]},
        )
        integrated_rows = cypher(
            url,
            SEMANTIC_CYPHER
            + CYPHER.replace(
                "RETURN a.field, a.value, a.receipt, a.line",
                "RETURN a.field, a.value, a.receipt, a.line, e.receipt, e.line",
            ),
            args,
        )
        integrated = (
            {
                "type": "CorporateRestructuring",
                "assertions": [r[:4] for r in integrated_rows],
                "type_evidence": integrated_rows[0][4:],
            }
            if integrated_rows
            else None
        )
        assert hybrid == integrated
        assert [(a[0], a[1], a[2]) for a in temporal] == [
            ("change_date", "2026-10-27", "20261028800611"),
            ("ratio", ratio, receipt),
        ]
        results.append(
            {
                "cutoff": cutoff,
                "LPG": temporal,
                "OWL": {"type": rdf, "evidence": evidence},
                "hybrid": hybrid,
                "single_graph": integrated,
                "smoke_wall_ms": round((time.perf_counter() - started) * 1000, 2),
            }
        )
    print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
