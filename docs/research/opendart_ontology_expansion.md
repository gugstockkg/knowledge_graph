# 공시 원문에서 확장할 관계와 TRACE 후속 연구 설계

2026년 11월 27일 · 원문 표본 및 FIBO 대조

## 현재 실험에서 확인한 문제

기존 테스트 659개 종목·거래일에서 가격 모형 정확도는 56.90%, 직접 공시 모형은 56.30%, 거래 경로 모형은 56.15%였다. 거래 경로 모형과 직접 공시 모형의 정확도 차이의 95% 재표집 구간은 −1.66~+1.71%p였다. 파이프라인에서 입력을 다시 집계하면 구매자 공시가 들어간 관측은 48개, 거래 상대의 공시 건수가 양수인 관측은 39개였다. 후자는 전체 테스트의 5.9%에 해당한다. 원문에서 연결한 경제 사건 그래프에서는 공급계약 1,294건 중 구매자 매칭이 226건이었다. [기존 백테스트](trace_economic_revision_2026.md) · [특성 생성 코드](../../src/knowledge_graph/market/economic_backtest.py)

현재 거래 경로 특성은 상대 기업의 계약·정정·시설투자·실적 공시 건수를 합산한다. 상대의 사건이 기존 계약과 품목이나 프로젝트를 공유하는지, 공급사 매출에서 얼마나 큰지, 새 계약인지 일부 해지인지, 두 회사 중 어느 방향의 노출인지에 따라 효과가 달라질 수 있다. 이는 추가로 검증할 가설이다. 현재 성과표는 모든 종류의 공시 그래프가 무효라는 판단을 뒷받침하지 않는다.

## 원문 표본에서 확인한 확장 후보

로컬 수집분 2026-01-01~11-08의 코스피·코스닥·코넥스 접수 목록을 접수번호로 중복 제거했다. 아래 수치는 공시 제목 패턴에 들어온 문서 수와 ZIP이 있는 수이며, 정정 포함이다. 각 유형에서 선택한 ZIP 내부 XML의 표·문단을 확인했다. 기업 매칭률이나 추출 정확도는 아직 산정하지 않았다.

| 우선순위 | 공시 원문에서 확인한 정보 | 추가할 사건·관계 | 제목 후보 / ZIP |
| --- | --- | --- | ---: |
| 1. 계약 상태와 경제적 중요도 | 유니테스트의 HBM4 검사장비 공급계약은 구매자 SK하이닉스, 계약액 291.6억 원, 공급사 매출 대비 26.46%, 최근 3년 동종 계약 이행 여부를 명시한다. 엠플러스 공시는 블루오벌 SK 계약 해지와 원화 환산 기준을 보고한다. | `ContractRevision → MODIFIES → SupplyContract`, `ContractTermination → TERMINATES → SupplyContract`. 명시적 대상 계약을 확인한 경우에 연결한다. 전체·부분 해지, 확정·조건부 금액, 기준 통화와 선수금 차감 여부를 구분한다. [유니테스트 공시](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260512900186) · [엠플러스 공시](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260504900632) | 체결 3,193 / 2,680, 해지 계열 84 / 74 |
| 1. 프로젝트·제품 관계 | 네이블 공시에서 계약상대방은 SK텔레콤이며 계약 내용에는 하나금융그룹 5G 특화망 프로젝트가 등장한다. SK하이닉스는 청주 M17 건설에 19.1조 원을 계획했다. | `SupplyContract → FOR_PROJECT → Project`, `FacilityInvestment → INVESTS_IN → FacilityProject`, `SupplyContract → COVERS_PRODUCT → Product`. 프로젝트 언급과 계약 상대를 함께 보존하고, 계약이 특정 공장에 귀속된다는 근거는 별도로 확인한다. [네이블 공시](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260615900301) · [M17 투자 공시](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260807800602) | 시설투자 214 / 178 |
| 1. 고객 의존도·수주잔고 | 삼성전자는 2026년 반기 주요 매출처 명칭을 공시했다. SK하이닉스는 익명 고객 (가) 13.35%, (나) 13.03%를 보고했다. 넥스틴은 품목별 기초 수주잔고, 당반기 수주, 납품, 기말 잔고를 표로 공개했다. | `Company/Segment → HAS_CUSTOMER_EXPOSURE → CustomerExposure`와 `Company → HAS_BACKLOG_OBSERVATION → BacklogObservation`. 명시 식별에만 기업 연결을 만들고 익명 고객은 문서·기간 범위의 관측값으로 보존한다. 공시 간 (가), (나)의 동일성은 확인 근거가 있어야 부여한다. [삼성전자 반기보고서](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260814003699) · [SK하이닉스 반기보고서](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260814003509) · [넥스틴 반기보고서](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260814003931) | 정기보고서 전체 9,220 / 8,899 |
| 2. 기대와 실적의 차이 | 두산에너빌리티는 2026년 연결 매출 73,811억 원, 영업이익 3,959억 원, 수주 133,214억 원을 회사 전망으로 발표했다. | `Company → ISSUED_GUIDANCE → GuidanceObservation`. 기업·지표·회계기간·연결범위가 같을 때 공개된 실제 실적과 비교한다. 발표 전 회사 전망 대비 차이와 시장 컨센서스 대비 차이는 별도 변수다. [두산에너빌리티 공시](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260212800739) | 124 / 120 |
| 2. 보증·자금조달 | HS효성첨단소재 공시에는 해외 채무자와 채권자, 채무액 302.26억 원과 보증액 362.712억 원이 따로 나온다. KCC건설 공시에는 PF 프로젝트와 책임준공 조건이 나온다. 파인엠텍 CB는 자금 목적, 전환 조건 및 조기상환 옵션을 명시한다. | 보증자·채무자·채권자를 하나의 `Guarantee`와 `DebtObligation`에 역할별로 연결한다. CB는 발행 결정, 발행/납입, 조건 변경, 전환 청구를 같은 증권의 별도 사건으로 둔다. [HS효성첨단소재](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260602800629) · [KCC건설](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260529901876) · [파인엠텍](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260521000737) | 보증 891 / 717, CB 발행 결정 1,078 / 884 |
| 3. 지배권과 자본배분 | 베노티앤알은 지배주주 변경을 수반하는 주식 양수도 계약과 별도의 변경 확정 공시 가능성을 명시했다. 세아제강의 계열사 추가 출자에는 취득 후 지분율 39.49%가 나온다. 바이오비쥬 취득결과에는 주문과 실제 체결 수가 따로 나온다. | `EquityTransfer`의 양도인·양수인·대상 증권, `OwnershipObservation`의 보유량·분모·관측일, `BuybackDecision → IMPLEMENTED_BY → BuybackExecution`. 지배권은 명시적 의결권·지배 근거와 이행 상태를 확인한 뒤 부여한다. [베노티앤알](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260703900890) · [세아제강](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260610800812) · [바이오비쥬](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260701000292) | 지배주주 변경 수반 양수도 156 / 132, 타법인 주식 취득·양수 939 / 785, 자사주 결정·결과 표본군 574 / 496 |

정기보고서 표본은 이름이 나오는 경우와 비공개인 경우를 모두 보여준다. IFRS 8은 주요 고객 의존도를 공시하도록 하지만, 고객 식별은 별도로 다룬다. 명시된 고객 이름 목록에 개별 매출 비중이 없으면 비중도 미확인으로 둔다. [IFRS 8](https://www.ifrs.org/issued-standards/list-of-standards/ifrs-8-operating-segments/) · [IFRS 8 문단 34 자료](https://www.ifrs.org/content/dam/ifrs/meetings/2018/june/cmac-and-gpf/ap2a-appendix-disclosure-requirements.pdf)

## FIBO 원본 대조

공식 GitHub의 커밋 `33a92cd34285d532c158da97bb42add089f135d3` 원본을 로컬 `artifacts/fibo_gap_review/`에 내려받았다. 압축 파일 SHA-256은 `16baaed5bbb82831c91b30b685ef03b76cc13cdf2c7ec7c2687b5b064bd990d3`이다. 이전 기본 온톨로지 매핑의 커밋과 같다. 이번에는 신규 문제에 해당하는 RDF/XML 모듈 9개를 별도로 추출해 정의와 관계의 적용 범위를 확인했다. OWL 추론기와 전체 import 추론은 수행하지 않았다. [커밋 고정 원본](https://github.com/edmcouncil/fibo/tree/33a92cd34285d532c158da97bb42add089f135d3) · [기존 FINTOS 대조](../../ontology/alignment/fibo/FIBO_review.md)

| FIBO에서 확인한 개념 | FINTOS 보강안과 매핑 수준 |
| --- | --- |
| `ContractParty`, `hasContractParty`, `hasExecutionDate`, `hasEffectiveDate`, `Supplier`, `supplies` | 계약 당사자를 역할로 모델링하고 서명일·효력일·인도 시작일·공개일을 분리한다. FIBO `supplies`는 공급 역할에서 공급 대상에 향하는 속성이므로 FINTOS의 `Company → SupplyContract`와는 부분 대응이다. 수주잔고, 제품군별 반복수주, 공시된 해지 사유는 프로젝트의 도메인 개념으로 보존한다. [Contracts.rdf](https://github.com/edmcouncil/fibo/blob/33a92cd34285d532c158da97bb42add089f135d3/FND/Agreements/Contracts.rdf) · [ProductsAndServices.rdf](https://github.com/edmcouncil/fibo/blob/33a92cd34285d532c158da97bb42add089f135d3/FND/ProductsAndServices/ProductsAndServices.rdf) |
| `Guaranty`, `Guarantor`, `isGuaranteedBy`, `hasGuaranteedAmount`, `Debt`, `isOwedBy`, `isOwedTo` | 보증과 기초 채무를 각각 식별하고 보증 제공자와 채권·채무 관계를 분리한다. 보증액은 보증 노드에, 차입 원금은 채무 노드에 둔다. 표준 `isGuaranteedBy`의 대상은 보증인 역할이므로 법인 바로가기 관계와 동치 처리하지 않는다. [Guaranty.rdf](https://github.com/edmcouncil/fibo/blob/33a92cd34285d532c158da97bb42add089f135d3/FBC/DebtAndEquities/Guaranty.rdf) · [Debt.rdf](https://github.com/edmcouncil/fibo/blob/33a92cd34285d532c158da97bb42add089f135d3/FBC/DebtAndEquities/Debt.rdf) |
| `Shareholder`, `VotingShareholder`, `hasSubsidiary`, `isControllingAffiliateOf` | 주주·의결권 보유자·지배자의 의미는 다르다. FIBO `hasSubsidiary`의 범위와 제약을 일괄 적용할 수 없으므로 DART상의 최대주주, 특수관계인 합산, K-IFRS 연결 범위는 각각의 출처와 판정 기준을 보존한다. [CorporateControl.rdf](https://github.com/edmcouncil/fibo/blob/33a92cd34285d532c158da97bb42add089f135d3/BE/OwnershipAndControl/CorporateControl.rdf) · [CorporateOwnership.rdf](https://github.com/edmcouncil/fibo/blob/33a92cd34285d532c158da97bb42add089f135d3/BE/OwnershipAndControl/CorporateOwnership.rdf) |
| `ConvertibleBond`, `hasConvertibleDate`, `PrivateOffering`, `DefaultEvent` | 증권, 모집, 신용 사건을 분리하는 데 활용한다. 내려받은 `ConvertibleBond` 정의에는 주가가 특정 수준을 넘는 조건에 관한 문구가 있으므로 국내 CB 전체에 동치 매핑하지 않는다. 전환가격 조정, 옵션, 납입 변경, 전환 청구는 원문 조건을 담는 별도 관측·이벤트로 둔다. [Bonds.rdf](https://github.com/edmcouncil/fibo/blob/33a92cd34285d532c158da97bb42add089f135d3/SEC/Debt/Bonds.rdf) · [SecuritiesIssuance.rdf](https://github.com/edmcouncil/fibo/blob/33a92cd34285d532c158da97bb42add089f135d3/SEC/Securities/SecuritiesIssuance.rdf) · [CreditEvents.rdf](https://github.com/edmcouncil/fibo/blob/33a92cd34285d532c158da97bb42add089f135d3/FBC/DebtAndEquities/CreditEvents.rdf) |

한국에서 바로 가져다 쓸 수 있는 공개 근거는 OpenDART의 공시 종류와 입력 필드, KRX 양식이다. 회계 계정·단위·기간은 IFRS Accounting Taxonomy와 XBRL을 참조한다. 조사한 범위에서 이들을 모두 포괄하면서 공개 시점별 정정, 기업 역할, 프로젝트 노출까지 정의한 재사용 가능 한국 공시 OWL 표준은 확인하지 못했다. [OpenDART 개발가이드](https://opendart.fss.or.kr/guide/main.do?apiGrpCd=DS005) · [IFRS Accounting Taxonomy](https://www.ifrs.org/issued-standards/ifrs-taxonomy/ifrs-accounting-taxonomy-2025/)

## TRACE 목적에 맞는 구조와 LPG 선택 근거

하나의 공통 식별 체계 위에 **사건**, **노출**, **공개 당시 상태**를 모듈로 둔다. 공통 식별자에는 OpenDART 법인 ID, 별도 증권 ID, 이벤트 ID, 접수번호와 문서 버전이 포함된다.

| 모듈 | 주요 질문 | 표현 |
| --- | --- | --- |
| 사건 | 누가 무엇을 얼마나 결정·체결·정정·해지했나 | 사건 노드, 여러 참여 역할, 대상 계약·증권·제품, 수치 관측 |
| 노출 | 누구의 공시가 어떤 경로로 어느 기업에 중요한가 | 공급망, 고객 매출 의존도, 프로젝트 분류, 보증과 지배 관계. 방향과 규모를 각 관계 유형에 맞춰 사용 |
| 공개 당시 상태 | 진입 시점에 알 수 있던 값과 적용 상태는 무엇인가 | 공개 시점·효력 시점·종료/이행 시점, 정정의 항목 범위, 버전별 근거. 시점별 그래프 및 모델 입력을 이 모듈에서 구성 |

현재 구현은 Neo4j **레이블 속성 그래프(LPG)**이고, CSV가 프로젝트 개념 명세다. LPG는 저장·질의 모델이고 OWL은 개념과 공리를 형식적으로 기술하는 언어다. RDF는 OWL 온톨로지와 사실을 함께 표현할 수 있는 그래프 모델이다. [Neo4j LPG 문서](https://neo4j.com/docs/getting-started/appendix/graphdb-concepts/) · [W3C OWL 2](https://www.w3.org/TR/owl2-overview/) · [W3C RDF](https://www.w3.org/TR/rdf11-concepts/)

| 현재 과제 | LPG를 운영 모델로 쓰는 근거 | RDF·OWL이 추가 가치를 주는 경우 |
| --- | --- | --- |
| 역할과 기간을 가진 계약·보증 | 노드와 방향을 가진 관계로 사건 및 참여 역할을 표현하고, 기간·근거·식별 속성을 붙여 Cypher에서 함께 조회한다. | FIBO와 공통 식별자로 교환하거나 서로 다른 시스템의 역할·유형을 명시적으로 대조한다. |
| 특정 시점의 정정값 복원 | FINTOS는 금호에이치티에서 10/28·10/29 기준 지분율 52.25%·52.39%와 유지된 변경일의 원문 근거를 각각 반환했다. 공개일 필터와 정정 우선순위가 조회에 명시돼 있다. | 같은 사실을 RDF로 내보내고 SPARQL로 조회할 수 있다. OWL의 추론과 별도로 업무 날짜 규칙과 SHACL 검증 범위를 설계한다. |
| 파이프라인과 실험 반복 | 이미 있는 S3·EC2 적재와 Cypher 조회, 특징 생성 코드를 재사용할 수 있다. 공급계약·시설투자·실적 그래프의 재적재 건수와 날짜 조회를 검증했다. | RDF 배포와 기관 간 어휘 연계가 요구되면 매핑된 일부 모듈을 함께 제공할 수 있다. |

근거는 **현재 구현의 적합성과 재사용 가능한 운영 경로**다. 동일 데이터와 동등한 모델에서 Neo4j와 RDF 저장소의 속도·비용을 직접 비교하지 않았다. 표현 구조와 예측 성능의 효과는 별도로 측정한다. [FINTOS 데이터 설명서](../../site/dataset/index.html) · [부분 정정 검증 사례](../../site/journal/2026-11-27-ontology-and-shacl/index.html) · [W3C SHACL](https://www.w3.org/TR/shacl/)

## 여러 온톨로지·그래프를 함께 쓰는 연구

질문을 세 가지로 구분한다. 첫째는 같은 사실을 LPG와 RDF로 각각 표현하는 경우다. 둘째는 원문에 있는 서로 다른 의미를 관계 유형별로 추출해 함께 쓰는 경우다. 셋째는 같은 원문과 사실을 서로 다른 구조로 표현해 어느 구조가 검색·예측에 도움이 되는지 보는 경우다. FINTOS에 가장 직접적인 가설은 둘째와 셋째다.

| 연구 | 실제 비교와 FINTOS에 주는 근거 |
| --- | --- |
| *Multi-GCGRU* | 중국 CSI300/CSI500에서 지분·산업·뉴스 동시 등장 그래프를 함께 쓴 모형이 각 단일 관계 그래프보다 높은 정확도를 보고했다. CSI300에서 결합 57.54%, 가장 높은 단일 관계 56.28%였다. 서로 다른 데이터에서 추출한 관계를 합친 실험이다. [논문 표 II](https://arxiv.org/abs/2005.04955) |
| *MDGNN* | CSI300에서 여러 관계를 모두 쓴 설정의 Prec@30은 52.32%, 주식 간 관계만 쓴 설정은 51.28%였다. 주식 간 관계에 산업 소속만 더한 설정은 51.01%였다. 관계가 추가될 때 이득과 손실 모두 가능하며 각 관계를 별도로 제거해 볼 근거다. [AAAI 논문 표 4](https://arxiv.org/html/2402.06633) |
| *HyperGraphRAG* | 이항 관계 그래프와 다자 관계를 보존한 구조를 문서 질의응답에서 비교했다. 보증인·채무자·채권자·프로젝트처럼 여러 역할을 한 사건에 묶어 보존할 근거로 참고할 수 있다. 질의응답 실험이며 주가 예측 실험과 평가 지표가 다르다. [NeurIPS 논문](https://proceedings.neurips.cc/paper_files/paper/2025/file/df55ee6e59f8ac4a625219e11fe9ddba-Paper-Conference.pdf) |
| *Cohen & Frazzini* | 주요 고객–공급사의 경제적 연관과 자산 간 수익률 전파를 검증했다. 공개된 중요한 거래와 전달 방향을 모델에 넣는 이유가 된다. 미국 시장의 월간 전략과 FINTOS의 다음 거래일 시가→종가 분류는 검증 대상이 다르다. [Journal of Finance](https://doi.org/10.1111/j.1540-6261.2008.01379.x) |

**같은 한국 공시 원문을 복수 온톨로지로 각각 구축하고, 같은 시점·같은 종목·같은 모형에서 결합이 단일 온톨로지보다 낫다는 것을 직접 검증한 연구는 이번 조사에서 확인하지 못했다.** 따라서 한 원문에서 도메인 모듈별 관계를 만들고, 각 모듈을 단독·결합으로 투입하는 실험이 FINTOS의 독립적인 연구 질문이 된다.

같은 원문에서 얻는 정보량과 그래프 표현 효과를 구분하려면 비교군을 추가한다. 가격·업종·직접 공시를 공통 기준선으로 두고, **사건 그래프만**, **기업 노출 그래프만**, **둘을 함께** 투입한다. 같은 사실과 같은 특성 수를 쓰는 평탄화 기준군을 포함해 관계 구조가 실제로 기여했는지 확인한다. 두 그래프의 같은 공시·같은 사건은 공통 ID로 한 번만 센다. RDF와 LPG를 비교한다면 사실 집합과 질의 결과를 동일하게 맞춘 뒤 변환 손실, 모델링 비용, 조회 시간과 메모리를 비교한다.

기존 연구 가운데 한국 주식시장 CIKM 연구는 OpenDART 재무제표와 외부 경쟁사 관계를 이용한 GraphRAG 질의 사례를 제시한다. FinKario는 FIBO를 참조해 금융 사건 유형과 추출 틀을 만드는 접근을 보여준다. Doc2EDAG는 한 사건의 참여자와 조건이 공시 여러 문장에 흩어질 수 있음을 다룬다. 한국 DART 부실위험 연구는 공시 사건의 순서가 재무·가격에 추가 정보를 줄 수 있음을 검증했지만, 결과 변수는 365일·730일 부실 위험이다. [한국 주식시장 지식그래프](https://arxiv.org/html/2601.11528v1) · [FinKario](https://aclanthology.org/2026.acl-long.446/) · [Doc2EDAG](https://aclanthology.org/D19-1032/) · [DART 공시 순서와 부실 위험](https://link.springer.com/article/10.1007/s10690-026-09651-w)

## 다음 검증

1. **수주·고객 의존도와 계약 상태부터 검수한다.** 공급계약·해지·정기보고서의 대표 사례 60건을 추천한다. 원계약에 연결된 해지, 과거 원공시가 없는 해지, 새 계약과 단순 정정, 익명 고객, 명시 프로젝트를 각각 포함한다. 관계별로 고유 원문 수와 식별률, 날짜 확인률, 원문 수준 정밀도·재현율을 기록한다.
2. **같은 증거에서 두 표현을 만든다.** 역할 노드가 있는 사건 그래프와 시점별 기업 간 노출 그래프를 만든다. 후자는 방향, 품목, 갱신 후 값, 매출 대비 중요도, 만료일을 유지하며 원래 사건 ID를 역추적할 수 있어야 한다. 정정 전후를 보존하지 않는 단순 기업 쌍 그래프도 비교 모델로 구성할 수 있다.
3. **같은 표본에서 모델 입력만 바꾼다.** 시장·업종과 주가 기준선, 직접 공시 기준선을 고정한다. 계약 역할과 경제적 규모, 고객·프로젝트 노출, 사건의 버전과 상태를 하나씩 추가한 뒤 결합과 제거 실험을 한다. 같은 업종과 유사한 연결 수를 가진 기업 사이에서 상대 기업을 섞는 대조군으로 실제 연결의 기여를 확인한다. 공시일 이후 관측과 정정은 예측 입력에서 차단한다.
4. **반응 창과 실제 체결 창을 구분한다.** 현재 다음 거래일 시가→종가 목표를 재현하고, 전일 종가→다음 시가 반응은 가격이 개장 전에 움직였는지 확인하는 진단 지표로 둔다. 1·5거래일 수익률도 별도 사전 정의하며 체결 가능한 시점과 비용을 고정한다. 39거래일 기존 테스트는 탐색 기록으로 보존하고, 모델 선택에 사용하지 않은 기간과 더 긴 표본을 확보한 후 성과를 판단한다. 분류 균형 정확도·로그손실, 거래일 군집 신뢰구간, 비용 후 수익률, 정보가 실제로 들어간 표본 수를 함께 보고한다.
