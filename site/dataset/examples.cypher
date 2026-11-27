// 스키마와 제약 확인
CALL dbms.components() YIELD versions,edition RETURN versions[0] AS version,edition;
CALL db.schema.nodeTypeProperties() YIELD nodeType,propertyName,propertyTypes,mandatory RETURN nodeType,propertyName,propertyTypes,mandatory ORDER BY nodeType,propertyName;
CALL db.schema.relTypeProperties() YIELD relType,propertyName RETURN relType,propertyName ORDER BY relType;
SHOW CONSTRAINTS YIELD name,labelsOrTypes,properties RETURN name,labelsOrTypes,properties ORDER BY name;
MATCH (n) UNWIND labels(n) AS label RETURN label,count(*) AS nodes ORDER BY label;
MATCH ()-[r]->() RETURN type(r) AS relationship,count(*) AS relationships ORDER BY relationship;
MATCH (f:Filing) RETURN min(f.receipt_date) AS first_receipt,max(f.receipt_date) AS last_receipt,count(f) AS filings;

// 금호에이치티 공시 및 원문 객체
MATCH (f:Filing)-[:IS_ABOUT]->(c:Company {corp_code:'00105606'})
WHERE f.receipt IN ['20261028800611','20261029800490']
OPTIONAL MATCH (f)-[:HAS_SOURCE_DOCUMENT]->(d:SourceDocument)
RETURN c.name AS company,f.receipt_date AS receipt_date,f.receipt AS receipt,f.title AS title,count(d) AS source_objects
ORDER BY receipt_date,receipt;

// 공시별 원문 상태 집계
MATCH (f:Filing)
RETURN f.source_state AS source_state,count(*) AS filings
ORDER BY filings DESC,source_state;

// 최근 최대주주 변경 제목 후보
MATCH (f:Filing)-[:IS_ABOUT]->(c:Company)
WHERE f.receipt_date >= date('2026-11-24')
  AND f.receipt_date <= date('2026-11-26')
  AND replace(f.title,' ','') CONTAINS '최대주주변경'
RETURN f.receipt_date AS receipt_date,c.name AS company,f.title AS title,f.receipt AS receipt,f.source_state AS source_state
ORDER BY receipt_date DESC,receipt LIMIT 5;

// 월별 원문 연결 수
MATCH (f:Filing)
WITH substring(toString(f.receipt_date),0,7) AS month, f
RETURN month,count(*) AS filings,count(CASE WHEN f.source_state='available' THEN 1 END) AS linked
ORDER BY month;

// 샘플 정정 공시의 원문 객체 형식
MATCH (f:Filing {receipt:'20261029800490'})-[:HAS_SOURCE_DOCUMENT]->(d:SourceDocument)
RETURN d.format AS format,count(*) AS files ORDER BY format;

// Graph sample: catalog
MATCH company_path = (c:Company {corp_code:'00105606'})
      <-[:IS_ABOUT]-(f:Filing)
MATCH source_path = (f)-[:HAS_SOURCE_DOCUMENT]->(:SourceDocument)
WHERE f.receipt IN ['20261028800611', '20261029800490']
RETURN company_path, source_path;

// Graph sample: TRACE contract
MATCH supplier_path = (:Company)-[:SUPPLIED_IN]->
      (k:TraceSupplyContract {receipt:'20261105900115'})
MATCH buyer_path = (:Company)-[:PURCHASED_IN]->(k)
MATCH filing_path = (k)-[:REPORTED_IN]->(:Filing)
MATCH evidence_path = (k)-[:SUPPORTED_BY]->(:TraceContractEvidence)
RETURN supplier_path, buyer_path, filing_path, evidence_path;

// 넥스틴의 공급계약을 품목과 구매자까지 조회
MATCH path = (supplier:Company)-[:SUPPLIED_IN]->(contract:SupplyContract {receipt:'20261006900146'})
             <-[:PURCHASED_IN]-(buyer:Company)
MATCH product_path = (contract)-[:COVERS_PRODUCT]->(:ProductCategory)
MATCH (contract)-[:HAS_TERMS_OBSERVATION]->(terms:ContractTermsObservation {observation_type:'original'})
RETURN path, product_path, terms.contract_amount_krw AS amount_krw,
       terms.supplier_reported_sales_pct AS sales_pct, terms.start_date AS starts_on,
       terms.end_date AS ends_on;

// 개별 계약의 원래 조건과 공시별 변경값을 당시 공개 정보로 조회
// 기준일을 변경해 예정 종료일 등 변경 전후를 확인
MATCH (:SupplyContract {receipt:'20260119900439'})-[:HAS_TERMS_OBSERVATION]->
      (terms:ContractTermsObservation)-[:REPORTED_IN]->(filing:Filing)
WHERE terms.known_on <= date('2026-02-24')
RETURN terms.known_on AS known_on, terms.observation_type AS type,
       terms.changed_fields AS changed_fields, terms.end_date AS disclosed_end_date,
       filing.receipt AS receipt
ORDER BY known_on, receipt;
