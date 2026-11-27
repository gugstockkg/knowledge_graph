"""Compare a loaded economic-event snapshot with the extracted counts and as-of dates."""
import argparse
import json
from datetime import date, timedelta
from pathlib import Path

from knowledge_graph.storage.manage import table

COUNTS = {
    "contracts": "MATCH (n:SupplyContract {economic_snapshot:$snapshot}) RETURN count(n) AS count",
    "facility": "MATCH (n:FacilityInvestment {economic_snapshot:$snapshot}) RETURN count(n) AS count",
    "financial": "MATCH (n:FinancialObservation {economic_snapshot:$snapshot}) RETURN count(n) AS count",
    "contract_amendment": """MATCH (:SupplyContract {economic_snapshot:$snapshot})-[:HAS_TERMS_OBSERVATION]->
                              (n:ContractTermsObservation {observation_type:'amendment'})
                              RETURN count(n) AS count""",
    "buyers": """MATCH (:Company)-[p:PURCHASED_IN]->(:SupplyContract {economic_snapshot:$snapshot})
                 RETURN count(p) AS count""",
    "suppliers": """MATCH (:Company)-[p:SUPPLIED_IN]->(:SupplyContract {economic_snapshot:$snapshot})
                    RETURN count(p) AS count""",
    "products": """MATCH (:SupplyContract {economic_snapshot:$snapshot})-[p:COVERS_PRODUCT]->(:ProductCategory)
                   RETURN count(p) AS count""",
    "original_terms": """MATCH (:SupplyContract {economic_snapshot:$snapshot})-[:HAS_TERMS_OBSERVATION]->
                           (n:ContractTermsObservation {observation_type:'original'})
                           RETURN count(n) AS count""",
}
CASE = """
MATCH (supplier:Company)-[:SUPPLIED_IN]->(k:SupplyContract {receipt:$receipt})
OPTIONAL MATCH (buyer:Company)-[:PURCHASED_IN]->(k)
MATCH (k)-[:HAS_TERMS_OBSERVATION]->(t:ContractTermsObservation)
MATCH (t)-[:REPORTED_IN]->(f:Filing)
WHERE t.known_on <= date($cutoff)
RETURN supplier.name AS supplier, buyer.name AS buyer, k.product AS product, f.receipt AS receipt,
       toString(t.known_on) AS known_on, t.contract_amount_krw AS amount_krw,
       t.supplier_reported_sales_pct AS sales_pct, toString(t.end_date) AS end_date,
       t.changed_fields AS changed_fields
ORDER BY known_on, receipt
"""


def verify(data):
    snapshot = data["start"] + "_" + data["end"]
    args = {"snapshot": snapshot}
    actual = {key: table(statement, args)[0]["count"] for key, statement in COUNTS.items()}
    expected = {
        **data["rows"],
        "buyers": sum(row["buyer"] is not None for row in data["contracts"]),
        "products": sum("category_id" in row for row in data["contracts"]),
        "suppliers": len(data["contracts"]),
        "original_terms": len(data["contracts"]),
    }
    if actual != expected:
        raise ValueError(f"Snapshot counts differ: {actual} != {expected}")
    invalid = table("""
        MATCH (k:SupplyContract {economic_snapshot:$snapshot})-[:HAS_TERMS_OBSERVATION]->
              (t:ContractTermsObservation)
        OPTIONAL MATCH (t)-[:REPORTED_IN]->(f:Filing)
        WITH t, collect(f.receipt_date) AS dates
        WHERE size(dates) <> 1 OR dates[0] <> t.known_on
        RETURN count(t) AS count
    """, args)[0]["count"]
    if invalid:
        raise ValueError(f"{invalid} term observations are missing a unique filing with a matching date")
    results = {"snapshot": snapshot, "counts": actual}
    nextin = next((r for r in data["contracts"] if r["receipt"] == "20261006900146"), None)
    if nextin:
        values = table(CASE, {"receipt": nextin["receipt"], "cutoff": nextin["known_on"]})
        if len(values) != 1 or values[0]["amount_krw"] != nextin["amount_krw"] or not values[0]["buyer"]:
            raise ValueError("Nextin case differs from the expected disclosed contract")
        results["contract_example"] = values[0]
    if data["contract_amendment"]:
        sample = data["contract_amendment"][0]
        args = {"receipt": sample["contract_receipt"], "cutoff": sample["known_on"]}
        after = table(CASE, args)
        args["cutoff"] = (date.fromisoformat(sample["known_on"]) - timedelta(days=1)).isoformat()
        before = table(CASE, args)
        if not before or any(row["receipt"] == sample["receipt"] for row in before):
            raise ValueError("Amendment leaked into a cutoff before publication")
        if not any(row["receipt"] == sample["receipt"] for row in after):
            raise ValueError("Published amendment is missing in the as-of query")
        results["amendment_example"] = {"before": before, "after": after}
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    args = parser.parse_args()
    with args.dataset.open(encoding="utf-8") as source:
        print(json.dumps(verify(json.load(source)), ensure_ascii=False))
