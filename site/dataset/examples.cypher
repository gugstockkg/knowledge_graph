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
