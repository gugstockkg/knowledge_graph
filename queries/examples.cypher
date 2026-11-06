// 1. 에이루트 공시 한 건의 보유현황 그래프: 숫자는 노드를 클릭하면 표시됩니다.
MATCH (h:HoldingSnapshot)-[r:HOLDING_IN_COMPANY]->(c:Company {corp_code:'00608839'})
MATCH (h)-[s:HELD_BY]->(g)
WHERE h.entity_id STARTS WITH 'holding:20261021000306:'
RETURN c,h,g,r,s;

// 2. 주식등 5% 이상 후보. 개인/합산과 검토상태를 함께 조회합니다.
MATCH (h:HoldingSnapshot)-[:HOLDING_IN_COMPANY]->(c:Company)
MATCH (h)-[:HELD_BY]->(g)
WHERE h.category='shares_etc' AND h.percentage >= 5
RETURN c.name AS company,g.name AS reported_holder,h.shares AS quantity,h.percentage AS percentage,
       h.as_of_date AS as_of_date,h.scope AS scope,h.verification_status AS status
ORDER BY company,as_of_date;

// 3. 수량에서 원문 근거까지 추적합니다.
MATCH (a:Assertion {predicate:'shares'})-[:HAS_SUBJECT]->(h:HoldingSnapshot)
MATCH (a)-[:SUPPORTED_BY]->(e:EvidenceSpan)-[:LOCATED_IN]->(d:DocumentVersion)
MATCH (f:Filing)-[:HAS_DOCUMENT]->(d)
WHERE h.entity_id='holding:20261021000306:shares_etc'
RETURN h.shares AS quantity,h.percentage AS percentage,h.as_of_date AS as_of_date,
       e.quote AS original_text,e.line AS source_line,e.path AS source_locator,
       d.source_path AS local_source,f.source_url AS official_source;

// 4. 정정 공시 접수일과 현황 기준일 차이.
MATCH (f:Filing)-[:HAS_DOCUMENT]->(d:DocumentVersion)<-[:LOCATED_IN]-(e:EvidenceSpan)<-[:SUPPORTED_BY]-(a:Assertion)-[:HAS_SUBJECT]->(h:HoldingSnapshot)
WHERE f.entity_id='filing:20261021000238' AND a.predicate='shares'
RETURN DISTINCT f.name AS filing,f.receipt_date AS receipt_date,h.as_of_date AS as_of_date,h.category AS category,h.verification_status AS status;

// 5. 여러 공시에서 같은 이름이 등장해도 식별자는 자동 병합하지 않았습니다.
MATCH (f:Filing)-[:SUBMITTED_BY]->(p)
WITH p.name AS name,collect(p.entity_id) AS provisional_ids,collect(f.entity_id) AS filings
WHERE size(provisional_ids)>1
RETURN name,provisional_ids,filings;

// 6. 근거 경로를 그래프로 표시합니다.
MATCH p=(f:Filing {entity_id:'filing:20261021000306'})-[:HAS_DOCUMENT]->(d:DocumentVersion)<-[:LOCATED_IN]-(e:EvidenceSpan)<-[:SUPPORTED_BY]-(a:Assertion)-[:HAS_SUBJECT]->(h:HoldingSnapshot)-[:HOLDING_IN_COMPANY]->(c:Company)
MATCH q=(h)-[:HELD_BY]->(g)
WHERE a.predicate='shares'
RETURN p,q LIMIT 5;
