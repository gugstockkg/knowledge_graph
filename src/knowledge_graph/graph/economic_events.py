"""Load the economic-event snapshot into the existing filing catalog."""

import argparse
import json
from pathlib import Path

from ..storage.manage import table

CONSTRAINTS = {
    "SupplyContract": ("economic_contract_receipt", "receipt"),
    "ContractTermsObservation": ("economic_contract_terms_id", "id"),
    "ProductCategory": ("economic_category_id", "id"),
    "FacilityInvestment": ("economic_investment_receipt", "receipt"),
    "FinancialObservation": ("economic_financial_id", "id"),
}

CONTRACT_MATCH = """
UNWIND $rows AS row
MATCH (f:Filing {receipt:row.receipt})-[:IS_ABOUT]->(s:Company {corp_code:row.supplier})
WHERE f.receipt_date=date(row.known_on)
OPTIONAL MATCH (i:Filing {receipt:row.buyer_identity_receipt})
      -[:IS_ABOUT]->(b:Company {corp_code:row.buyer})
WHERE i.receipt_date <= f.receipt_date
"""
CONTRACT = CONTRACT_MATCH + """
OPTIONAL MATCH (pilot:TraceSupplyContract {receipt:row.receipt})
FOREACH (_ IN CASE WHEN pilot IS NULL THEN [] ELSE [1] END | SET pilot:SupplyContract)
MERGE (k:SupplyContract {receipt:row.receipt})
SET k.product=row.product, k.buyer_status=row.buyer_status, k.economic_snapshot=$snapshot
MERGE (s)-[:SUPPLIED_IN]->(k)
MERGE (k)-[:REPORTED_IN]->(f)
MERGE (t:ContractTermsObservation {id:row.receipt})
SET t.known_on=date(row.known_on), t.contract_amount_krw=row.amount_krw,
    t.amount_raw=row.amount_raw, t.conditional_raw=row.conditional_raw,
    t.signed_date=date(row.signed_date), t.start_date=date(row.start_date),
    t.end_date=date(row.end_date),
    t.supplier_reported_sales_pct=row.reported_sales_pct,
    t.reported_sales_pct_raw=row.reported_sales_pct_raw, t.source_sha256=row.sha256,
    t.product_line=row.product_line, t.observation_type="original"
MERGE (k)-[:HAS_TERMS_OBSERVATION]->(t)
MERGE (t)-[:REPORTED_IN]->(f)
FOREACH (_ IN CASE WHEN b IS NULL THEN [] ELSE [1] END |
  MERGE (b)-[p:PURCHASED_IN]->(k) SET p.identity_receipt=row.buyer_identity_receipt)
FOREACH (_ IN CASE WHEN row.category_id IS NULL THEN [] ELSE [1] END |
  MERGE (pc:ProductCategory {id:row.category_id}) SET pc.name=row.category_name
  MERGE (k)-[:COVERS_PRODUCT]->(pc))
RETURN count(k) AS loaded, count(b) AS buyers
"""
ANNOUNCEMENT_MATCH = """
UNWIND $rows AS row
MATCH (f:Filing {receipt:row.receipt})-[:IS_ABOUT]->(c:Company {corp_code:row.corp_code})
WHERE f.receipt_date=date(row.known_on)
"""
AMENDMENT_VALIDATE = ANNOUNCEMENT_MATCH + """
MATCH (origin:Filing {receipt:row.contract_receipt})-[:IS_ABOUT]->(c)
MATCH (prior:Filing {receipt:row.preceding_receipt})-[:IS_ABOUT]->(c)
WHERE prior.receipt_date < f.receipt_date AND origin.receipt_date <= prior.receipt_date
"""
AMENDMENT = AMENDMENT_VALIDATE + """
MATCH (k:SupplyContract {receipt:row.contract_receipt})<-[:SUPPLIED_IN]-(c)
MERGE (t:ContractTermsObservation {id:row.receipt})
SET t.known_on=date(row.known_on), t.observation_type="amendment",
    t.preceding_receipt=row.preceding_receipt, t.changed_fields=row.changed_fields,
    t.change_evidence=row.change_evidence, t.source_sha256=row.sha256,
    t.contract_amount_krw=row.changes.contract_amount_krw,
    t.supplier_reported_sales_pct=row.changes.supplier_reported_sales_pct,
    t.start_date=date(row.changes.start_date), t.end_date=date(row.changes.end_date)
MERGE (k)-[:HAS_TERMS_OBSERVATION]->(t)
MERGE (t)-[:REPORTED_IN]->(f)
RETURN count(t) AS loaded
"""
FACILITY = ANNOUNCEMENT_MATCH + """
MERGE (k:FacilityInvestment {receipt:row.receipt})
SET k.known_on=date(row.known_on), k.target=row.target,
    k.planned_amount_krw=row.planned_amount_krw, k.amount_raw=row.amount_raw,
    k.target_line=row.target_line, k.amount_line=row.amount_line,
    k.source_sha256=row.sha256, k.status=row.status, k.economic_snapshot=$snapshot
MERGE (c)-[:ANNOUNCED_INVESTMENT]->(k)
MERGE (k)-[:REPORTED_IN]->(f)
RETURN count(k) AS loaded
"""
FINANCIAL = ANNOUNCEMENT_MATCH + """
MERGE (o:FinancialObservation {id:row.receipt + ':' + row.metric})
SET o.known_on=date(row.known_on), o.period_start=date(row.period_start),
    o.period_end=date(row.period_end), o.metric=row.metric,
    o.value_krw=row.value_krw, o.raw_value=row.raw_value, o.raw_unit=row.raw_unit,
    o.value_line=row.value_line, o.source_sha256=row.sha256,
    o.consolidation_scope=row.consolidation_scope, o.publication_stage=row.publication_stage,
    o.economic_snapshot=$snapshot
MERGE (c)-[:HAS_FINANCIAL_OBSERVATION]->(o)
MERGE (o)-[:REPORTED_IN]->(f)
RETURN count(o) AS loaded
"""


def import_snapshot(data):
    snapshot = data["start"] + "_" + data["end"]
    specs = {
        "contracts": (CONTRACT_MATCH + "RETURN count(f) AS loaded,count(b) AS buyers", CONTRACT),
        "facility": (ANNOUNCEMENT_MATCH + "RETURN count(f) AS loaded", FACILITY),
        "financial": (ANNOUNCEMENT_MATCH + "RETURN count(f) AS loaded", FINANCIAL),
        "contract_amendment": (AMENDMENT_VALIDATE + "RETURN count(f) AS loaded", AMENDMENT),
    }

    def batch(statement, key):
        counts = {"loaded": 0}
        if key == "contracts":
            counts["buyers"] = 0
        rows = data.get(key, [])
        for start in range(0, len(rows), 200):
            response = table(statement, {"rows": rows[start:start + 200], "snapshot": snapshot})
            for name, value in response[0].items():
                counts[name] = counts.get(name, 0) + value
        return counts

    preflight = {}
    for key, (match, _) in specs.items():
        expected = {"loaded": len(data.get(key, []))}
        if key == "contracts":
            expected["buyers"] = sum(row.get("buyer") is not None for row in data[key])
        preflight[key] = batch(match, key)
        if preflight[key] != expected:
            raise ValueError(f"{key}: catalog matches {preflight[key]}, expected {expected}")
    for label, (name, key) in CONSTRAINTS.items():
        table(f"CREATE CONSTRAINT {name} IF NOT EXISTS FOR (n:{label}) REQUIRE n.{key} IS UNIQUE")
    results = {key: batch(load, key) for key, (_, load) in specs.items()}
    if results != preflight:
        raise RuntimeError(f"Unexpected load result: {results}")
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    args = parser.parse_args()
    with args.dataset.open(encoding="utf-8") as source:
        data = json.load(source)
    print(json.dumps(import_snapshot(data), ensure_ascii=False))


if __name__ == "__main__":
    main()
