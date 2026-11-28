"""Add typed periodic ownership values to the existing RDF assertions."""

import argparse
import gzip
import json
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from unicodedata import normalize

from load_opendart_rdf_inventory import NS, Literal, XSD, database, load_triples, rows_jsonl
from rdflib.plugins.serializers.nt import _quoteLiteral

FIELDS = {
    "holder": (NS.reportedHolderName, str, None),
    "role": (NS.reportedHolderRole, str, None),
    "opening_shares": (NS.openingShareCount, int, XSD.integer),
    "closing_shares": (NS.closingShareCount, int, XSD.integer),
    "opening_ratio": (NS.openingOwnershipPercent, Decimal, XSD.decimal),
    "closing_ratio": (NS.closingOwnershipPercent, Decimal, XSD.decimal),
}


def observations(inventory):
    for filing in rows_jsonl(inventory):
        if filing["kind"] != "periodic":
            continue
        for index, fact in enumerate(filing.get("facts", [])):
            yield filing, NS[f"assertion:{filing['receipt']}:{index}"], fact


def typed_fields(fact):
    if re.sub(r"\s+", "", fact["holder"]) in {"계", "합계", "소계", "총계"}:
        return None
    typed = {}
    for key, (predicate, convert, datatype) in FIELDS.items():
        value = fact[key]
        if datatype:
            value = value.replace(",", "").rstrip("%")
            if value == "-":
                continue
        try:
            number = convert(value)
        except (ValueError, InvalidOperation):
            return None
        if datatype == XSD.decimal and (not number.is_finite() or not 0 <= number <= 100):
            return None
        if datatype == XSD.integer and number < 0:
            return None
        typed[predicate] = Literal(number, datatype=datatype)
    return typed


def triples(inventory):
    for _, assertion, fact in observations(inventory):
        for predicate, value in (typed_fields(fact) or {}).items():
            yield assertion, predicate, value


def classify(rdf, delta, inventory):
    filings, values = {}, defaultdict(dict)
    for filing, assertion, fact in observations(inventory):
        if fact["role"].strip() == "최대주주":
            filings.setdefault(filing["receipt"], (filing, []))[1].append(
                (str(assertion), fact["line"])
            )
    receipts = set(filings)
    titles = {}
    with gzip.open(rdf, "rt") as handle:
        for line in handle:
            if "> <urn:fintos:opendart:reportTitle> " not in line:
                continue
            subject, _, value = line.rstrip().split(" ", 2)
            receipt = subject.strip("<>").rsplit(":", 1)[-1]
            if receipt in receipts:
                titles[receipt] = json.JSONDecoder().raw_decode(value)[0]
    predicates = {str(predicate): key for key, (predicate, _, _) in FIELDS.items()}
    with gzip.open(delta, "rt") as handle:
        for line in handle:
            subject, predicate, value = line.rstrip().split(" ", 2)
            values[subject.strip("<>")][predicates[predicate.strip("<>")]] = (
                json.JSONDecoder().raw_decode(value)[0]
            )
    reports = []
    for receipt, (filing, rows) in filings.items():
        title = titles.get(receipt, "")
        periods = re.findall(r"\((\d{4})[.](\d{2})\)", title)
        if not periods:
            continue
        year, month = map(int, periods[-1])
        candidates = []
        for assertion, line in rows:
            data = values[assertion]
            if not FIELDS.keys() <= data.keys() or data["role"].strip() != "최대주주":
                continue
            name = data["holder"]
            identity = re.sub(r"\(주\)|주식회사|\s+", "", normalize("NFKC", name))
            candidates.append({"identity": identity, "line": line, **data})
        if len({row["identity"] for row in candidates}) != 1:
            continue
        comparable = {tuple(row.get(k) for k in FIELDS) for row in candidates}
        selected = candidates[0]
        observation = {
            "receipt": receipt, "filed": filing["filed"], "corp": filing["corp_code"],
            "period": f"{year:04d}-{month:02d}", "title": title,
            "holder": selected["holder"], "identity": selected["identity"],
            "line": selected["line"],
        }
        if len(comparable) == 1:
            observation.update(selected)
        reports.append(observation)
    history = defaultdict(dict)
    outcomes = []
    by_day = defaultdict(list)
    for report in reports:
        by_day[(report["filed"], report["corp"])].append(report)
    for (_, corp), reports_today in sorted(by_day.items()):
        known = history[corp]
        # With date-only metadata, conflicting versions on one day are ambiguous.
        periods = defaultdict(list)
        for report in reports_today:
            periods[report["period"]].append(report)
        for period, versions in periods.items():
            if len(versions) != 1:
                continue
            current = versions[0]
            if known and period < max(known):
                known[period] = current
                continue
            previous = next((known[p] for p in sorted(known, reverse=True) if p < period), None)
            old_version = known.get(period)
            known[period] = current
            if old_version or not previous:
                continue
            py, pm = map(int, previous["period"].split("-"))
            cy, cm = map(int, period.split("-"))
            if (cy-py)*12 + cm-pm != 3:
                continue
            change = "same_holder"
            if current["identity"] != previous["identity"]:
                change = "holder_replacement"
            elif all(key in current for key in ("opening_ratio", "closing_ratio")) and Decimal(
                current["opening_ratio"]
            ) != Decimal(current["closing_ratio"]):
                change = "same_holder_ratio_change"
            outcomes.append({"kind": change, "previous": previous, "current": current})
    return outcomes


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("inventory", "rdf", "delta", "outcomes"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--load", action="store_true")
    args = parser.parse_args()
    if args.load:
        query = database("fintos-disclosure-kg", 27474)
        counts = load_triples(query,
                              triples(args.inventory), set(), args.delta,
                              predicates=[str(v[0]) for v in FIELDS.values()])
        print(dict(counts), flush=True)
    else:
        with gzip.open(args.delta, "wt") as handle:
            for subject, predicate, obj in triples(args.inventory):
                handle.write(f"{subject.n3()} {predicate.n3()} {_quoteLiteral(obj)} .\n")
    args.outcomes.write_text(json.dumps(classify(args.rdf, args.delta, args.inventory),
                                        ensure_ascii=False, indent=2))
