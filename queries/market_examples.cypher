// 1. 기업 → 증권 → 특정 일자의 주가를 그래프로 봅니다.
MATCH path=(c:Company {name:'금호에이치티'})<-[:ISSUED_BY]-(s:MarketPilot:Security)<-[:PRICE_OF]-(p:PriceObservation)
WHERE p.active=true AND p.trade_date IN [date('2026-10-19'),date('2026-10-20'),date('2026-10-26'),date('2026-10-27')]
RETURN path;

// 2. 공시 다음 관측 거래일 시가 → 1/5/20번째 일봉 종가 수익률.
// 수정주가 여부는 미검증; 시간 정보 없는 공시를 당일 체결로 가정하지 않습니다.
MATCH (f:Filing)-[:IS_ABOUT]->(c:Company {name:'금호에이치티'})
MATCH (c)<-[:ISSUED_BY]-(:MarketPilot:Security)<-[:PRICE_OF]-(p:PriceObservation)
WHERE p.active=true AND p.trade_date>f.receipt_date
WITH f,c,p ORDER BY f.entity_id,p.trade_date
WITH f,c,collect(p) AS bars
UNWIND [1,5,20] AS horizon
WITH f,c,bars[0] AS entry,bars[horizon-1] AS exit,size(bars) AS available,horizon
RETURN f.entity_id AS 공시,c.name AS 기업,f.receipt_date AS 접수일,
       entry.trade_date AS 진입일,entry.open AS 진입시가,horizon AS 관측일봉수,
       exit.trade_date AS 청산일,exit.close AS 청산종가,
       CASE WHEN available<horizon THEN null
            WHEN entry.open<=0 OR entry.volume<=0 OR exit.close<=0 OR exit.volume<=0 THEN null
            ELSE round(100*(toFloat(exit.close)/entry.open-1),2) END AS `구간수익률(%)`,
       CASE WHEN available<horizon THEN '미성숙/관측부족'
            WHEN entry.open<=0 OR entry.volume<=0 OR exit.close<=0 OR exit.volume<=0 THEN '거래불가 확인 필요'
            ELSE '탐색용 관측 수익률' END AS 상태
ORDER BY 접수일,공시,관측일봉수;

// 3. 공시·지분 변화·그 이후 가격을 한 화면에 연결합니다.
MATCH evidence=(f:Filing {entity_id:'filing:20261019000237'})-[:HAS_DOCUMENT]->(d:DocumentVersion)<-[:LOCATED_IN]-(:EvidenceSpan)<-[:SUPPORTED_BY]-(a:Assertion)-[:HAS_SUBJECT]->(h:HoldingSnapshot)-[:HOLDING_IN_COMPANY]->(c:Company)
MATCH market=(c)<-[:ISSUED_BY]-(s:MarketPilot:Security)<-[:PRICE_OF]-(p:PriceObservation)
WHERE a.predicate='shares' AND h.category='shares_etc' AND p.active=true
  AND p.trade_date IN [date('2026-10-20'),date('2026-10-26')]
RETURN evidence,market LIMIT 5;
