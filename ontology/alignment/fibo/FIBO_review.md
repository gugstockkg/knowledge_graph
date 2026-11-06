# FIBO 정합성 검토 결과

검토일: 2026-11-06. 대상: 기존 v0.1 개념 25개·관계 33개. 결과는 의미·구조 검토이며 OWL 논리적 일관성 인증이 아닙니다.

## 핵심 결론
기업·증권·인물·계약을 구분한 방향은 유지할 수 있습니다. 그러나 이름이 같거나 비슷하다고 owl:equivalentClass / owl:equivalentProperty를 선언하면 안 됩니다. 현재 선언한 동치 공리는 없습니다. 이 검토에서도 실행 가능한 매핑 공리를 추가하지 않았습니다.

25개 개념과 33개 관계 모두에 검토 상태를 기록했고, 그중 14개 항목은 실제 표준 항목을 확인해 정의·주요 제약·방향을 대조했습니다. 나머지 44개는 이번 검토에서 매핑을 확정하지 않았습니다. 전체 FIBO에 대응 항목이 없다고 판단한 것은 아닙니다. 검토 완료율과 표준 일치율을 동일시하지 마세요.

## 주요 발견
1. Organization은 FIBO가 가져오는 OMG Commons Organization과 비교해야 합니다. 이전 FIBO 경로를 추정해서 URI를 만들면 안 됩니다.
2. Company에는 BusinessEntity가 더 넓은 참고 개념입니다. Corporation은 소유자와 구별되는 법적 실체인 조직입니다. 법적 형태를 확인한 경우만 적용하세요. 특히 확인한 JointStockCompany는 unincorporated business로 정의되어 있어 한국의 주식회사와 명칭만으로 동일시할 수 없습니다.
3. Person은 자연인 의미가 부합합니다. 공시 인물은 그 제한된 적용 범위입니다. 이름 표기는 인물 식별과 다릅니다.
4. Security는 금융상품 범위와 관할 제약을 확인해야 합니다. FIBO의 주식은 Share라는 금융상품입니다. 개별 증권·종목코드·발행수량을 같은 객체로 혼합하면 안 됩니다.
5. HoldingSnapshot은 관측 기록, Ownership은 법적 소유 상황입니다. Ownership, Shareholding(권리·자산), Shareholder(소유 역할)를 구분해야 합니다. 한국 공시 보유를 자동으로 법적 소유/실질소유로 변환하지 마세요.
6. ExecutiveTenure는 재임 기간 관측, FIBO Executive는 관리 권한 역할입니다. 사외이사나 후보를 Executive로 자동 분류할 수 없습니다.
7. SupplyContract는 실제 법적 합의가 확인된 경우 Contract 하위유형 후보입니다. 계약 공시문은 계약 자체도 계약서 원본도 아닙니다.
8. ContractParty는 조직/인물 자체가 아니라 역할입니다. Contract -> hasContractParty -> 역할 -> isPlayedBy -> 법적 주체 패턴을 검토하세요. isPlayedBy는 OMG Commons의 속성이며 FIBO ContractParty의 제한식에서 확인했습니다. 미식별 자리표시자는 실제 법적 주체와 구분합니다.
9. FIBO Listing은 거래소가 관리하는 SecuritiesOffering의 등재 항목입니다. lists는 Offering을 대상으로 하고 정확히 1개 제약이 있습니다. 상장일 정확히 1개, 통화 존재 등 추가 제약도 있습니다. 현재 ListingRecord -> Security 연결을 lists와 동치로 매핑하면 대상 유형이 다릅니다.
10. FIBO Issuer는 주체가 수행하는 역할입니다. 우리 ISSUED_BY는 증권에서 기업으로 연결하는 간략 관계입니다. 일반 isIssuedBy와 방향은 맞지만 표준 역할 모델을 전부 표현하지 않습니다.

## 기준 소스와 재현
FIBO 공식 edmcouncil/fibo 저장소 master 커밋: 33a92cd34285d532c158da97bb42add089f135d3. 정식 릴리스 전체를 가져온 검토가 아니라 이 커밋의 관련 모듈 16개와 OMG Commons Organizations 1개를 확인했습니다. 각 원본의 라이선스·주석을 포함한 파일을 sources에 보존했습니다. source_manifest.json에는 파일 해시와 모듈별 versionIRI를 기록했습니다. master는 이후 바뀔 수 있으므로 CSV의 커밋 고정 링크를 사용하세요.

fibo_alignment_review.csv의 '매핑 수준'은 검토자의 자연어 판정이며 SKOS/OWL 공리를 선언한 것이 아닙니다. source_index.json은 검색을 위한 정의 요약 인덱스이므로 전체 제한식은 원본 RDF에서 확인해야 합니다. source 위치는 선언 시작 위치이며 관계 공리 전체는 뒤에 이어집니다.

## 범위와 미실시 사항
공식 RDF의 정의, 주요 상위 유형, 관련 제한식, 관계 방향과 폐기 여부를 검토했습니다. 전체 imports closure 다운로드, Protégé/HermiT 등의 추론기 실행, 모든 상속·비연결(disjointness) 제약 대조, 한국 법령과 국가별 증권 정의의 법적 동치 판단은 수행하지 않았습니다. OWL의 열린 세계에서는 값 누락이 즉시 모순을 뜻하지 않으므로 FIBO 제약을 충족하려고 미확인 사실을 만들어 넣으면 안 됩니다. 필수값·업무 데이터 완전성 검사는 별도 검증 규칙으로 구현해야 합니다.

## 권장 반영 순서
1. definition_change_proposals.csv의 7개 변경안을 팀 검토.
2. 조직/법적 실체와 역할의 분리, 관측/실재의 구분을 v0.2에 반영.
3. 계약 10건·지분 10건·임원 10건에서 주체-역할-관측-근거 모델을 수작업 검증.
4. 선택한 FIBO 및 Commons 버전과 의존성을 고정하고 제한된 매핑 모듈 작성.
5. 추론기 일관성 검사와 데이터 제약 검사, 역량 질문 검증 수행.

기존 v0.1은 변경하지 않았습니다. 이번 결과물은 매핑 검토와 정의 수정 제안이며 팀의 승인된 정의 변경은 아닙니다.

이전 참고: 원본 RDF·검색 인덱스는 artifacts/reference_sources/fibo_review/에 로컬 보존하며 Git에는 소스 버전·해시만 포함합니다.
