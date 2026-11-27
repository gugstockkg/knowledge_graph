"""Run paired controller-event queries and guardrail checks on an isolated Neo4j."""

import argparse
import html
import json
import random
import re
import statistics
import time
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from compare_controller_graphs import CYPHER, cypher
from owlrl import DeductiveClosure, OWLRL_Semantics
from pyshacl import validate
from rdflib import RDF, RDFS, XSD, Graph, Literal, Namespace

from knowledge_graph.ingestion.contract_pilot import read_archive

EX = Namespace("urn:fintos:benchmark:")
FEATURED = (
    "20261028800611",
    "20260803800771",
    "20260803800817",
    "20260810800801",
    "20260811800737",
    "20260630800535",
)
TYPES = {
    "Merger": (r"합병", "CorporateRestructuring"),
    "Split": (r"인적분할|물적분할", "CorporateRestructuring"),
    "Gift": (r"증여|수증", "OwnershipTransfer"),
    "Inheritance": (r"상속|유고|사망|별세", "OwnershipTransfer"),
    "Issuance": (r"유상증자|신주취득", "EquityFinancing"),
    "Acquisition": (r"양수도|취득완료|매매계약", "OwnershipTransfer"),
}
SHAPES = """
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix ex: <urn:fintos:benchmark:> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex:AssertionShape a sh:NodeShape ; sh:targetClass ex:Assertion ;
 sh:property [ sh:path ex:source ; sh:minCount 1 ; sh:nodeKind sh:IRI ] ;
 sh:property [ sh:path ex:published ; sh:minCount 1 ; sh:datatype xsd:date ] .
"""
SEMANTIC = """
MATCH (e:BenchmarkEvent {id:$event})-[:CLASSIFIED_AS]->(t)
MATCH (t)-[:SUBCLASS_OF*0..]->(:BenchmarkType {id:$parent})
WHERE e.filed <= $cutoff
WITH DISTINCT e
"""


def cleaned(text):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", text)).split())


def source_cells(document):
    raw, _, digest = read_archive(Path(document["archive"]), document["receipt"])
    if digest != document["sha256"]:
        raise ValueError("source hash mismatch")
    after = False
    result = {}
    for row in re.finditer(r"<tr\b[^>]*>.*?</tr>", raw, re.IGNORECASE | re.DOTALL):
        cells = list(
            re.finditer(
                r"<t[deh]\b[^>]*>(.*?)</t[deh]>", row[0], re.IGNORECASE | re.DOTALL
            )
        )
        texts = [cleaned(c[1]) for c in cells]
        if len(texts) < 2:
            continue
        key = None
        if texts[0] == "변경후" and texts[1] == "최대주주등":
            after = True
        if after and len(texts) == 2 and "소유비율" in texts[0]:
            key = "ratio"
            after = False
        elif re.fullmatch(r"(?:\d+[.]\s*)?변경일자", texts[0]):
            key = "change_date"
        elif re.fullmatch(r"(?:\d+[.]\s*)?변경사유", texts[0]):
            key = "reason"
        if key:
            line = raw.count("\n", 0, row.start() + cells[-1].start()) + 1
            result[key] = (texts[-1], line)
    return result


def sample(snapshot, metadata, count):
    docs = {d["receipt"]: d for d in snapshot["documents"]}
    candidates = []
    for event in snapshot["events"]:
        d = docs[event["receipt"]]
        if not Path(d["archive"]).is_file():
            continue
        cells = source_cells(d)
        if not {"ratio", "reason", "change_date"} <= cells.keys():
            continue
        category = next(
            (
                (leaf, parent)
                for leaf, (pattern, parent) in TYPES.items()
                if re.search(pattern, re.sub(r"\s+", "", cells["reason"][0]))
            ),
            None,
        )
        if category is None or not re.fullmatch(r"\d+(?:\.\d+)?", cells["ratio"][0]):
            continue
        fields = [
            f
            for f in d["facts"]
            if f["field"] == "change_date"
            or (
                f["field"] == "ratio"
                and f.get("phase") == "after"
                and f.get("scope") == "group"
            )
        ]
        if sorted((f["field"], f["value"], f["line"]) for f in fields) != sorted(
            (k, v, line) for k, (v, line) in cells.items() if k != "reason"
        ):
            continue
        candidates.append((d, cells, category))
    candidates.sort(
        key=lambda c: (
            FEATURED.index(c[0]["receipt"])
            if c[0]["receipt"] in FEATURED
            else len(FEATURED),
            metadata.get(c[0]["receipt"]) != "Y",
            c[0]["receipt"],
        )
    )
    chosen, companies = [], set()
    for candidate in candidates:
        d, _, _ = candidate
        if d["corp_code"] not in companies:
            chosen.append(candidate)
            companies.add(d["corp_code"])
        if len(chosen) == count:
            break
    return chosen, docs


def put_types(graph, event, leaf, parent, evidence, filed):
    graph.add((EX[event], RDF.type, EX[leaf]))
    graph.add((EX[leaf], RDFS.subClassOf, EX[parent]))
    graph.add((EX[event], EX.source, EX[evidence]))
    graph.add((EX[event], EX.published, Literal(filed, datatype=XSD.date)))


def temporal_rows(d, cells):
    return [
        {
            "event": "bench:" + d["receipt"],
            "filed": d["filed"],
            "receipt": d["receipt"],
            "field": k,
            "value": value,
            "line": line,
        }
        for k, (value, line) in cells.items()
        if k != "reason"
    ]


def rdf_answers(graph, event, parent, cutoff):
    return [
        str(row.source).removeprefix(str(EX))
        for row in graph.query(
            f"""SELECT DISTINCT ?source WHERE {{
        <{EX[event]}> a <{EX[parent]}> ; <{EX.source}> ?source ; <{EX.published}> ?published .
        FILTER (?published <= "{cutoff}"^^<{XSD.date}>)
        }}"""
        )
    ]


def score(answer, expected):
    return sorted(answer) == sorted(expected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("listing", type=Path)
    parser.add_argument("url")
    parser.add_argument("output", type=Path)
    parser.add_argument("--count", type=int, default=30)
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text())
    metadata = {
        r["rcept_no"]: r.get("corp_cls") for r in json.loads(args.listing.read_text())
    }
    chosen, docs = sample(snapshot, metadata, args.count)
    if len(chosen) != args.count or not set(FEATURED) <= {
        d["receipt"] for d, _, _ in chosen
    }:
        raise ValueError("missing target sample or featured event")
    graph, evidence_graph = Graph(), Graph()
    shapes = Graph().parse(data=SHAPES, format="turtle")
    rows, types, questions, cases = [], [], [], []
    for d, cells, (leaf, parent) in chosen:
        event = "bench:" + d["receipt"]
        source = f"{d['receipt']}:{cells['reason'][1]}"
        same_day = temporal_rows(d, cells)
        rows.extend(same_day)
        cases.append(
            {
                "receipt": d["receipt"],
                "company": d["company"],
                "market": metadata.get(d["receipt"]),
                "leaf": leaf,
                "parent": parent,
                "reason": cells["reason"],
                "sha256": d["sha256"],
            }
        )
        put_types(graph, event, leaf, parent, source, d["filed"])
        types.append(
            {
                "event": event,
                "leaf": leaf,
                "parent": parent,
                "source": source,
                "filed": d["filed"],
            }
        )
        exact = [[r["field"], r["value"], r["receipt"], r["line"]] for r in same_day]
        for kind in ("temporal", "semantic", "combined"):
            questions.append((event, d["filed"], parent, kind, exact, [source]))
    correction = docs["20261029800490"]
    correction_cells = source_cells(correction)
    (change,) = [
        r
        for r in rows
        if r["event"] == "bench:20261028800611" and r["field"] == "change_date"
    ]
    change = [change[k] for k in ("field", "value", "receipt", "line")]
    ratio, line = correction_cells["ratio"]
    assert ratio == "52.39"
    rows.append(
        {
            "event": "bench:20261028800611",
            "filed": correction["filed"],
            "receipt": correction["receipt"],
            "field": "ratio",
            "value": ratio,
            "line": line,
        }
    )
    gold = [change, ["ratio", ratio, correction["receipt"], line]]
    gold_event = next(t for t in types if t["event"] == "bench:20261028800611")
    questions.append(
        (
            gold_event["event"],
            correction["filed"],
            gold_event["parent"],
            "combined",
            gold,
            [gold_event["source"]],
        )
    )
    for t in types:
        earlier = (date.fromisoformat(t["filed"]) - timedelta(days=1)).isoformat()
        questions.append(
            (t["event"], earlier, t["parent"], "before_publication", [], [])
        )
        questions.append(
            (t["event"], t["filed"], "NonMatchingType", "different_type", [], [])
        )
    for r in rows:
        node = EX[f"{r['receipt']}:{r['line']}"]
        evidence_graph.add((node, RDF.type, EX.Assertion))
        evidence_graph.add((node, EX.source, EX[r["receipt"]]))
        evidence_graph.add((node, EX.published, Literal(r["filed"], datatype=XSD.date)))
    assert validate(evidence_graph, shacl_graph=shapes)[0]
    guard = Graph()
    for triple in evidence_graph:
        guard.add(triple)
    missing = next(guard.triples((None, EX.source, None)))
    guard.remove(missing)
    assert not validate(guard, shacl_graph=shapes)[0]
    guard.add(missing)
    assert validate(guard, shacl_graph=shapes)[0]
    DeductiveClosure(OWLRL_Semantics).expand(graph)
    cypher(
        args.url,
        """UNWIND $rows AS r
        MERGE (a:ControllerExperimentAssertion {event:r.event, receipt:r.receipt, field:r.field})
        SET a += r""",
        {"rows": rows},
    )
    cypher(
        args.url,
        """MATCH (a:ControllerExperimentAssertion {receipt:'20261028800611', field:'ratio'}),
        (b:ControllerExperimentAssertion {receipt:'20261029800490', field:'ratio'}) MERGE (b)-[:SUPERSEDES]->(a)""",
    )
    cypher(
        args.url,
        """UNWIND $types AS r
        MERGE (e:BenchmarkEvent {id:r.event}) SET e += r
        MERGE (t:BenchmarkType {id:r.leaf})
        MERGE (p:BenchmarkType {id:r.parent})
        MERGE (e)-[:CLASSIFIED_AS]->(t) MERGE (t)-[:SUBCLASS_OF]->(p)""",
        {"types": types},
    )
    integrated = SEMANTIC + CYPHER.replace(
        "RETURN a.field, a.value, a.receipt, a.line",
        "RETURN a.field, a.value, a.receipt, a.line, e.source",
    )
    scores = Counter()
    outcomes = []
    for event, cutoff, parent, kind, result, source in questions:
        params = {"event": event, "cutoff": cutoff, "parent": parent}
        times = {}
        begin = time.perf_counter()
        lpg = cypher(args.url, CYPHER, params)
        times["lpg"] = (time.perf_counter() - begin) * 1000
        begin = time.perf_counter()
        owl = rdf_answers(graph, event, parent, cutoff)
        times["owl"] = (time.perf_counter() - begin) * 1000
        begin = time.perf_counter()
        single = cypher(args.url, integrated, params)
        times["single"] = (time.perf_counter() - begin) * 1000
        hybrid = [lpg, owl] if owl and lpg else [[], []]
        unified = [[r[:4] for r in single], sorted({r[4] for r in single})]
        if kind == "temporal":
            expected = [result, []]
            answers = ([lpg, []], [[], []], [lpg, []], [unified[0], []])
        elif kind == "semantic":
            expected = [[], source]
            answers = ([[], []], [[], owl], [[], owl], [[], unified[1]])
        else:
            expected = [result, source]
            answers = ([lpg, []], [[], owl], hybrid, unified)
        for name, answer in zip(("lpg", "owl", "hybrid", "single"), answers):
            scores[kind, name] += all(score(a, b) for a, b in zip(answer, expected))
        assert answers[2] == answers[3], (event, cutoff, kind, answers)
        outcomes.append(
            {
                "event": event,
                "cutoff": cutoff,
                "type": kind,
                "gold": expected,
                "answers": answers,
                "times_ms": times,
            }
        )
    # Remove the asserted axiom and recompute from asserted triples, not the closure.
    t = types[0]
    root = Graph()
    put_types(root, t["event"], t["leaf"], t["parent"], t["source"], t["filed"])
    root.remove((EX[t["leaf"]], RDFS.subClassOf, EX[t["parent"]]))
    DeductiveClosure(OWLRL_Semantics).expand(root)
    assert not rdf_answers(root, t["event"], t["parent"], t["filed"])
    assert rdf_answers(graph, t["event"], t["parent"], t["filed"])
    restored = Graph()
    put_types(restored, t["event"], t["leaf"], t["parent"], t["source"], t["filed"])
    roundtrip = Graph().parse(data=restored.serialize(format="turtle"), format="turtle")
    assert set(roundtrip) == set(restored)
    DeductiveClosure(OWLRL_Semantics).expand(roundtrip)
    assert rdf_answers(roundtrip, t["event"], t["parent"], t["filed"])
    # Time complete paired queries after warm-up, with randomized condition order.
    rng = random.Random(27)
    latency = {"hybrid": [], "single": []}
    for event, cutoff, parent, kind, _, _ in questions:
        if kind != "combined":
            continue
        params = {"event": event, "cutoff": cutoff, "parent": parent}

        def hybrid_query(event=event, parent=parent, cutoff=cutoff, params=params):
            owl = rdf_answers(graph, event, parent, cutoff)
            return (cypher(args.url, CYPHER, params), owl)

        def single_query(params=params):
            return cypher(args.url, integrated, params)

        routines = [("hybrid", hybrid_query), ("single", single_query)]
        for _, query in routines:
            query()
        for _ in range(5):
            rng.shuffle(routines)
            for arm, query in routines:
                begin = time.perf_counter()
                query()
                latency[arm].append((time.perf_counter() - begin) * 1000)

    # An unknown asserted type must survive export but must not entail a known parent.
    unknown = Graph()
    unknown_event = EX["unmapped-fixture"]
    unknown.add((unknown_event, RDF.type, EX.UnmappedRelation))
    DeductiveClosure(OWLRL_Semantics).expand(unknown)
    assert (unknown_event, RDF.type, EX.UnmappedRelation) in unknown
    assert all(
        (unknown_event, RDF.type, EX[parent]) not in unknown
        for _, parent in TYPES.values()
    )

    def quantile(values, fraction):
        values = sorted(values)
        return values[round((len(values) - 1) * fraction)]

    summary = {
        "cases": len(cases),
        "markets": dict(Counter(x["market"] for x in cases)),
        "type_counts": dict(Counter(x["leaf"] for x in cases)),
        "questions": dict(Counter(q["type"] for q in outcomes)),
        "correct": {f"{k}/{a}": v for (k, a), v in sorted(scores.items())},
        "median_query_ms": {
            k: statistics.median(q["times_ms"][k] for q in outcomes)
            for k in ("lpg", "owl", "single")
        },
        "companies": [x["company"] for x in cases],
        "paired_latency_ms": {
            name: {
                "repetitions": len(v),
                "p50": statistics.median(v),
                "p95": quantile(v, 0.95),
            }
            for name, v in latency.items()
        },
        "guardrails": [
            "unmapped type preserved without known-parent inference",
            "SHACL missing-source rejection and restoration",
            "prepublication cutoff",
            "ontology deletion/recalculation/restoration",
            "RDF roundtrip identifier preservation",
            "correction as-of and hybrid/single parity",
        ],
    }
    args.output.write_text(
        json.dumps(
            {"summary": summary, "cases": cases, "outcomes": outcomes},
            ensure_ascii=False,
            indent=2,
        )
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
