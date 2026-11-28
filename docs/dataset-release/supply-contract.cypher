MATCH (supplier:Company)-[:SUPPLIED_IN]->(c:SupplyContract)
      <-[:PURCHASED_IN]-(buyer:Company)
MATCH (c)-[:REPORTED_IN]->(f:Filing)
RETURN supplier.name AS supplier, buyer.name AS buyer, f.receipt AS receipt,
       'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=' + f.receipt AS source
ORDER BY receipt
LIMIT 10;
