// 수치 요약. 상세 자동 검증과 원본 대조는 verify.py를 실행합니다.
CALL dbms.components() YIELD name,versions,edition RETURN name,versions,edition;
MATCH (n:GUGPilot) RETURN n.entity_type AS type,count(n) AS count ORDER BY type;
MATCH (:GUGPilot)-[r]->(:GUGPilot) RETURN type(r) AS type,count(r) AS count ORDER BY type;
MATCH (a:Assertion)
WHERE NOT EXISTS { MATCH (a)-[:SUPPORTED_BY]->(:EvidenceSpan)-[:LOCATED_IN]->(:DocumentVersion) }
RETURN count(a) AS assertions_without_document_evidence;
MATCH (h:HoldingSnapshot {entity_id:'holding:20261021000306:shares_etc'})
RETURN h.shares,h.percentage,h.as_of_date,h.scope,h.denominator,
       valueType(h.shares),valueType(h.percentage),valueType(h.as_of_date);
