"""Export the bounded economic-event snapshot needed for the TRACE-style research run."""
import argparse
import json
from pathlib import Path

from knowledge_graph.storage.manage import table

CONTRACTS = """
MATCH (supplier:Company)-[:SUPPLIED_IN]->(contract:SupplyContract {economic_snapshot:$snapshot})
MATCH (contract)-[:HAS_TERMS_OBSERVATION]->(terms:ContractTermsObservation)
OPTIONAL MATCH (buyer:Company)-[:PURCHASED_IN]->(contract)
OPTIONAL MATCH (contract)-[:COVERS_PRODUCT]->(product:ProductCategory)
RETURN contract.receipt AS contract, contract.product AS product, product.id AS category,
       terms.id AS receipt, toString(terms.known_on) AS day, terms.observation_type AS kind,
       toString(terms.start_date) AS start, toString(terms.end_date) AS end,
       terms.changed_fields AS changed, terms.contract_amount_krw AS amount,
       terms.supplier_reported_sales_pct AS ratio,
       supplier{.corp_code,.stock_code,.name} AS supplier,
       buyer{.corp_code,.stock_code,.name} AS buyer
ORDER BY day, receipt
"""
INVESTMENTS = """
MATCH (c:Company)-[:ANNOUNCED_INVESTMENT]->(i:FacilityInvestment {economic_snapshot:$snapshot})
RETURN i.receipt AS receipt, toString(i.known_on) AS day, c{.corp_code,.stock_code,.name} AS company,
       i.planned_amount_krw AS value
ORDER BY day, receipt
"""
FINANCIALS = """
MATCH (c:Company)-[:HAS_FINANCIAL_OBSERVATION]->(o:FinancialObservation {economic_snapshot:$snapshot})
      -[:REPORTED_IN]->(f:Filing)
RETURN f.receipt AS receipt, toString(o.known_on) AS day, c{.corp_code,.stock_code,.name} AS company,
       o.metric AS metric, o.value_krw AS value, o.consolidation_scope AS scope
ORDER BY day, receipt, metric
"""

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = {"snapshot": args.snapshot}
    for key, query in {"contract_terms": CONTRACTS, "investments": INVESTMENTS, "financials": FINANCIALS}.items():
        result[key] = table(query, {"snapshot": args.snapshot})
        if not result[key]:
            raise ValueError(f"No {key} rows for snapshot {args.snapshot}")
    args.output.write_text(json.dumps(result, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: len(result[key]) for key in ("contract_terms", "investments", "financials")}))
