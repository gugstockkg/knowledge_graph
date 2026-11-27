// TRACE 공급계약 파일럿. 기준일자의 거래 마감 후 공개 정보가 포함된다.
// 같은 공시의 공급자와 구매자, 원문 근거, 구매사 식별 근거를 함께 조회한다.
WITH date('2026-11-05') AS cutoff
MATCH (s:Company)-[:SUPPLIED_IN]->(k:TraceSupplyContract)
      <-[r:PURCHASED_IN]-(b:Company),
      (k)-[:REPORTED_IN]->(f:Filing),
      (k)-[:SUPPORTED_BY]->(e:TraceContractEvidence),
      (b)<-[:IS_ABOUT]-(i:Filing {receipt: r.identity_receipt})
WHERE f.receipt_date <= cutoff AND i.receipt_date <= cutoff
RETURN s.name AS supplier, b.name AS buyer, f.receipt_date AS disclosed,
       f.receipt AS receipt, k.product AS product, e.buyer_text AS buyer_in_xml,
       e.xml_line AS buyer_xml_line, e.sha256 AS document_sha256,
       i.receipt AS identity_observation
ORDER BY disclosed, receipt;

// 같은 기업이 한 계약에서는 구매자, 다른 계약에서는 공급자로 등장하는 경로.
// 경로의 존재는 두 계약이 같은 거래를 이루거나 수익률에 영향을 줬음을 뜻하지 않는다.
WITH date('2026-11-05') AS cutoff
MATCH (supplier:Company)-[:SUPPLIED_IN]->(first:TraceSupplyContract)
      <-[:PURCHASED_IN]-(middle:Company)-[:SUPPLIED_IN]->(second:TraceSupplyContract)
      <-[:PURCHASED_IN]-(customer:Company),
      (first)-[:REPORTED_IN]->(first_filing:Filing),
      (second)-[:REPORTED_IN]->(second_filing:Filing)
WHERE first <> second AND supplier <> customer
  AND first_filing.receipt_date <= cutoff AND second_filing.receipt_date <= cutoff
RETURN supplier.name AS supplier, middle.name AS shared_company, customer.name AS customer,
       first_filing.receipt AS first_receipt, second_filing.receipt AS second_receipt
ORDER BY first_receipt, second_receipt;
