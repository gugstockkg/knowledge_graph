# 공개 사례와 표현 방식 선택 근거

조사 기준일: **2026-11-13**. 범위: PLAN.md Phase 2–3. 아래는 공개 원문·공식 모델·저장소를 확인한 문헌 조사이며, 해당 기관의 내부 운영 환경이나 성과를 실사한 결과가 아니다. 웹 검색 결과보다 연결된 원문과 원시 모델을 우선했다. 로그인, 전체 데이터 다운로드, DB 구축·변경, 속도 벤치마크는 하지 않았다.

핵심 판단은 **논리 정의, 데이터 교환, 검증, 저장·질의, 추론을 별도 선택하자**는 것이다. RDF·OWL·SHACL은 대체 제품 목록이 아니다. RDF에 RDFS·OWL 의미를 적용하고 SHACL로 입력 조건을 검사할 수 있으며, LPG를 별도 조회 저장소로 둘 수도 있다. 현재 Neo4j Community를 사용하는 사실만으로 온톨로지 정의의 충분성이나 OWL의 필요성이 결정되지 않는다.

## 1. 증거 수준과 사례 요약

다음 구분은 품질 점수가 아니라 무엇이 실제로 확인되는지의 구분이다.

- **모델·표준 공개**: 다운로드 가능한 정의와 코드가 있다. 실제 금융기관 도입 효과를 뜻하지 않는다.
- **운영 서비스 공개**: 데이터 배포·질의 서비스와 사용 설명을 확인했다. 가용성 보장이나 원천 데이터 정확성을 증명하지 않는다.
- **당사자 운영 보고**: 운영자가 설명하거나 벤더가 고객 담당자의 설명을 싣는다. 내부 설계·측정 로그까지 공개한 경우와 구분한다.
- **독립·재현 가능한 효과 측정**: 같은 작업·비교군·환경·지표를 검증할 자료가 있어야 한다. 아래 다섯 사례에서 금융 공시 모델 간 성능 우열을 입증하는 자료는 확보하지 않았다.

| 사례 | 목적·표현 방식 | 이번에 확인한 공개 근거 | 확인 범위와 공백 | 우리에게 유용한 부분 |
|---|---|---|---|---|
| FIBO | 금융 공통 의미 정의, RDF로 교환하는 OWL 온톨로지 | 공식 GitHub, 실제 LegalPersons.rdf, 기여·테스트 지침, 릴리스 노트 | 모델 배포 확인. 특정 은행의 운영 효과·전면 OWL 추론 사용은 미확인 | 기업·법적 주체·계약·증권의 정의·매핑 후보 |
| GLEIF | LEI 식별, 법적 실체·등록·부모관계 구분, RDF/OWL | 공식 L1 문서, GitHub L2.ttl·변환 코드 목록, Golden Copy 안내 | 원천 배포와 RDF 의미 모델 확인. 기존 data.world 공개 RDF 공급은 종료 공지로 접근 불가 | 엔티티 식별과 외부 연결, 관계 기간·상태·미보고 이유 |
| UBS | 데이터 계보·규제 대응, Neo4j LPG + Oracle 동기화 | 고객 담당자 설명을 포함한 Neo4j 사례 | **벤더가 발행한 운영 보고**. 소스·전체 스키마·비교 실험·현재 운영 상태 미공개 | 문서→추출→변환→조회 계보, 기존 시스템과 증분 동기화 |
| Wikidata | 다중 주장·조건·출처를 편집하고 RDF로 제공 | Wikibase RDF 매핑, 실제 Q95 항목, Query Service 매뉴얼 | 공개 모델·데이터·질의 서비스 문서 확인. 공시 수준의 검수·이력 보장은 별개 | Assertion 노드, 시간 qualifier, reference, 미상 표현 |
| UniProt | 과학 지식·주석·근거 통합, RDF/OWL 어휘·SPARQL | 실제 온톨로지 문서, SPARQL 예제, 운영 기관 근거 교육자료 | 모델·서비스 설명 확인. 단일 RDF API 본문은 도구 content-type 제약으로 미독해 | 사실·근거·수동/자동 출처 구분, 통제 어휘 재사용 |

## 2. 사례별 확인 내용

### 2.1 FIBO: 공통 금융 의미의 재사용 후보

**목적·표현.** EDM Council과 OMG가 금융 용어의 공통 의미를 관리한다. 공식 저장소는 OWL 기반 모델과 변경·기여 절차를 공개한다. 이것은 자체 금융 데이터베이스를 완성해 주는 서비스가 아니라 의미를 재사용·매핑할 수 있는 자산이다. [공식 저장소](https://github.com/edmcouncil/fibo), [ONTOLOGY_GUIDE](https://github.com/edmcouncil/fibo/blob/master/ONTOLOGY_GUIDE.md)

**실제 모델 확인.** `BE/LegalEntities/LegalPersons.rdf` 원문에서 `owl:Ontology`, `owl:imports`, `owl:versionIRI`, 클래스·제약과 변경 주석을 확인했다. `LegalPerson`에 자연인도 포함될 수 있다는 법적 의미를 한국 공시의 ‘법인’과 이름만으로 동일시하면 안 된다. Commons 등 외부 import가 있으므로 한 파일만 복사하는 방식도 의미 보존을 보장하지 않는다. [LegalPersons.rdf 원문](https://raw.githubusercontent.com/edmcouncil/fibo/master/BE/LegalEntities/LegalPersons.rdf)

**운영·성과 공백.** 저장소의 production/release는 해당 프로젝트의 배포 성숙도다. 모든 금융기관의 운영 도입이나 우리 데이터에 대한 충분성을 뜻하지 않는다. 기여 지침은 production과 development의 검사 강도가 다름을 명시한다. 릴리스 노트는 예제 individual을 별도 모듈로 옮겨 실제 최신 참조 데이터와 구분한 변경도 기록한다. 이 사례에서 우리에게 필요한 것은 ‘금융 표준을 썼다’는 명칭이 아니라 정의·출처·버전·import·매핑 변경을 관리하는 방법이다. [기여·검사 지침](https://github.com/edmcouncil/fibo/blob/master/CONTRIBUTING.md), [공식 릴리스](https://github.com/edmcouncil/fibo/releases)

**우리 적용 판단.** Company·Organization·Security·Contract 등 가까운 후보를 먼저 읽고, 정확한 동치·상위개념·부분 대응을 구분한다. 한국 법제·공시에서의 의미 차이를 검토하기 전 `owl:equivalentClass`나 `owl:sameAs`를 붙이지 않는다. 필요한 작은 모듈과 정의를 버전 고정해 검증하며 FIBO 전체 import를 기본값으로 삼지 않는다.

### 2.2 GLEIF: 식별자와 관계 자체의 상태·기간

**목적·표현.** GLEIF 공식 문서는 Golden Copy를 RDF로 변환하고 L1·L2·법적 형태·등록기관·예외 어휘로 설명하는 구조를 소개한다. LEI 코드, 그 코드가 식별하는 실체, 등록부 항목을 구별할 수 있다. [공식 RDF 소개](https://www.gleif.org/en/lei-data/semantic-representation-of-the-lei/lei-model-in-rdf-resource-description-framework), [L1 모델 문서](https://www.gleif.org/ontology/pylodev2/GLEIF_L1.html)

**실제 모델·코드 확인.** 공개 `GLEIF-IT/lei-rdf`의 `ontology/`에는 Base·L1·L2·ReportingException 어휘가, `code/`에는 L1·L2 XML 변환 XSL과 실행 스크립트가 있다. L2.ttl 본문은 부모·자녀·관계 기간·관계 상태를 관계 리소스에 연결한다. 회계 연결의 direct/ultimate parent를 일반적인 지분 보유·지배·계약 상대방 관계로 읽으면 안 된다. [저장소](https://github.com/GLEIF-IT/lei-rdf), [변환 코드 목록](https://github.com/GLEIF-IT/lei-rdf/tree/master/code), [L2.ttl 원문](https://raw.githubusercontent.com/GLEIF-IT/lei-rdf/master/ontology/L2.ttl)

**배포 경로의 중요한 공백.** GLEIF 소개는 data.world RDF의 주간 갱신을 설명하지만, 해당 [공식 연결 대상](https://data.world/gleif/lei-data)을 직접 열면 [서비스 종료 공지](https://data.world/community/goodbye/)로 이동한다. data.world는 Open Data Community가 **2026-07-13 종료됐고 데이터셋 다운로드가 불가능하다**고 밝힌다. FIBO의 2026-08-07 회의록도 RDF 다운로드 장애와 복구 논의를 기록한다. 따라서 소개 페이지의 주간 갱신 문구를 현재 작동하는 RDF 공급의 증거로 쓸 수 없다. Golden Copy 원천 배포와 공개 온톨로지·변환 코드의 존재는 별도로 확인된다. [회의록](https://dil-edmcouncil.atlassian.net/wiki/spaces/SEC/pages/1105264654/2026-08-07%2BMeeting%2Bnotes), [원천 Golden Copy 안내](https://www.gleif.org/en/lei-data/gleif-golden-copy/download-the-golden-copy)

**우리 적용 판단.** LEI는 외부 식별 연결의 강한 후보지만 국내 공시 기업·개인 전체에 존재한다고 가정하지 않는다. 로컬 ID와 외부 ID 및 매칭 근거·일자를 보존한다. 부모관계 부재를 ‘부모가 없다’로 바꾸지 않고 미보고·예외·미확인과 구별한다. 최신 RDF 공급 정상화 여부와 원천 CDF 버전 호환성은 도입 전에 다시 확인한다. L1 문서의 ‘RDF(turtle)’ 링크는 이번 접근에서 404였고, 대신 GitHub의 실제 모델 원문을 확인했다.

### 2.3 UBS: 금융기관 LPG 운영의 문서화된 보고

**목적·표현.** Neo4j가 발행한 UBS 사례는 데이터 계보·거버넌스에서 Oracle 기반 시스템과 Neo4j를 연결한 구성을 설명한다. 초기 적재 뒤 Oracle 테이블의 트랜잭션을 읽어 증분 동기화하고, Cypher로 계보를 조회해 GraphJSON·D3 시각화 및 Excel 내보내기에 이용한다고 한다. 제품은 **Neo4j Enterprise**로 명시된다. [UBS 사례 원문](https://neo4j.com/customer-stories/ubs/)

**확인 수준.** 담당자의 실명 설명과 구체적 데이터 흐름이 있어 일반적인 ‘그래프가 금융에 좋다’는 주장보다 확인 가능한 내용이 많다. 다만 발행자는 공급 업체이며, 전체 모델·Cypher 코드·원시 운영 로그·동일 조건 비교군·현재 운영 상태는 확보하지 못했다. 보고된 편의성은 당사자 경험이고, LPG가 RDF나 RDB보다 보편적으로 빠르다는 증거가 아니다. 규제 준수 인증을 별도로 확인한 것도 아니다.

**우리 적용 판단.** Assertion→EvidenceSpan→DocumentVersion→ExtractionRun의 계보 경로, 실패·재처리·증분 갱신 관리를 참고할 수 있다. Enterprise 기능과 예산을 Community 환경에 그대로 전제하지 않는다. 이 사례는 공시 의미 모델이나 OWL 추론 효과를 검증한 사례가 아니다.

### 2.4 Wikidata: 주장과 출처를 별도 노드로 다루기

**목적·표현.** Wikibase의 전체 RDF 문장 표현은 statement node를 두고 본래 값·qualifier·rank·reference를 연결한다. `p:`→statement, `ps:`→값, `pq:`→조건, `prov:wasDerivedFrom`→reference라는 역할이 다르다. 간단한 `wdt:` truthy 경로는 qualifier를 생략하므로 시간·범위가 필요한 질의의 충분한 대안이 아니다. rank는 normal/preferred/deprecated 구분이며 확률적 신뢰도나 공시의 법적 효력 상태를 뜻하지 않는다. [공식 RDF 매핑](https://www.mediawiki.org/wiki/Wikibase/Indexing/RDF_Dump_Format)

**실제 데이터 확인.** Google Q95의 공식 항목에서 이름 값에 시작·종료 시점과 reference·retrieved가 붙는 구성을 확인했다. 다른 일부 문장은 reference가 없었다. 따라서 출처를 저장할 수 있다는 모델 능력과 각 문장에 실제로 출처가 있다는 데이터 품질은 다르다. 단일 항목의 Turtle export는 도구 접근 제한으로 본문을 읽지 못했고, 항목 화면과 공식 매핑 문서를 대조했다. [실제 항목 Q95](https://www.wikidata.org/wiki/Q95), [Query Service 운영 매뉴얼](https://www.mediawiki.org/wiki/Wikidata_Query_Service/User_Manual)

**우리 적용 판단.** 동일 회사의 동일 속성에 시간·출처가 다른 주장을 공존시키는 설계를 참고한다. 하지만 qualifier의 valid time, reference의 retrieved time, 시스템이 주장을 처음 저장한 transaction time은 서로 다르다. Wikidata식 qualifier와 rank만 복제해 ‘정정 전 당시 알려진 값’이 자동 재현된다고 주장할 수 없다. DocumentVersion과 공개 시점·효력 기간·시스템 기록 기간을 별도로 보존하고, 특정 문서 표·문단의 EvidenceSpan도 유지해야 한다.

### 2.5 UniProt: 도메인은 달라도 근거 관리 패턴은 재사용 가능

**목적·표현.** UniProt RDF 온톨로지는 Protein·Annotation·Citation·Attribution 등과 `attribution`·`evidence` 관계를 공개한다. 운영 SPARQL 페이지는 실제 어휘와 named graph를 사용하는 예제를 제공하고, taxonomy subclass가 materialize돼 있다는 구현 조건까지 설명한다. 표준을 채택해도 서비스별 데이터 준비 방식이 질의 결과·작성법에 영향을 준다는 사례다. [실제 온톨로지 문서](https://purl.uniprot.org/html/index-en.html), [공식 SPARQL 서비스와 예제](https://sparql.uniprot.org/)

**근거·확인 공백.** EMBL-EBI 교육자료는 ECO로 정보의 기원을 나타내고 수동·자동 assertion을 구분한다고 설명한다. SIB의 RDF 교육 예제는 statement reification과 Attribution·source·evidence 연결을 제시한다. 단백질 단일 레코드 RDF API는 응답 형식 제한으로 본문을 파싱하지 못했다. 공개 서비스 문서·온톨로지·교육 예제를 확인했으며, 금융 CQ의 정확도 개선을 실증한 자료로 취급하지 않는다. [운영 기관 근거 설명](https://www.ebi.ac.uk/training/online/courses/uniprot-exploring-protein-sequence-and-functional-info/where-does-the-data-come-from/data-evidence/), [SIB RDF 근거 질의 예제](https://sib-swiss.github.io/sparql-training/UniProt/10_evidence_citation.html)

**우리 적용 판단.** ‘원문 진술’, ‘자동 추출’, ‘검수 완료’, ‘추론 결과’의 기원을 통제 어휘로 구분하고, 추출 자신감과 근거 종류를 별도 속성으로 둔다. RDF/OWL 문서가 공개돼 있다는 사실만으로 서비스가 모든 OWL 공리를 런타임에 추론한다고 가정하지 않는다.

## 3. 표준 상태: 확정 권고안과 진행 중 초안을 구분

2026-11-13 이전 버전을 기준으로 공식 W3C의 상태 표시를 확인했다. 최신 URL은 바뀔 수 있으므로 재현 실험에는 버전 URL을 함께 남긴다.

| 계층 | 안정된 기준 | 기준일에 확인한 새 버전 | 실험에 대한 의미 |
|---|---|---|---|
| RDF 데이터 모델 | [RDF 1.1 Concepts, 2014-02-25 Recommendation](https://www.w3.org/TR/2014/REC-rdf11-concepts-20140225/) | [RDF 1.2 Concepts, 2026-11-12 Candidate Recommendation Draft](https://www.w3.org/TR/2026/CRD-rdf12-concepts-20261112/) | RDF 1.2를 이미 확정 Recommendation이라고 쓰지 않는다. Triple term 등 새 기능은 구현 호환성을 별도 확인 |
| RDFS | [RDF Schema 1.1 Recommendation](https://www.w3.org/TR/rdf-schema/) | [RDF 1.2 Schema, 2026-11-12 Working Draft](https://www.w3.org/TR/2026/WD-rdf12-schema-20261112/) | 기본 상속·domain/range 의미와 초안 기능을 구분 |
| OWL | [OWL 2, 2012-12-11 Second Edition Recommendation](https://www.w3.org/TR/owl2-overview/) | 이 조사에서 그 이후의 대체 Recommendation을 확인하지 못함 | 사용한 문법·의미 체계·프로파일·추론기를 명시 |
| SHACL | [SHACL, 2017-07-20 Recommendation](https://www.w3.org/TR/2017/REC-shacl-20170720/) | [SHACL 1.2 Core, 2026-11-10 Working Draft](https://www.w3.org/TR/2026/WD-shacl12-core-20261110/) | 1.2 초안을 2017 Core/SPARQL 지원과 혼동하지 않음 |

**후속 소규모 PoC 기준은 RDF 1.1 + OWL 2 + SHACL 2017로 잡는 것이 안전하다.** 이는 새 표준을 부정하는 판단이 아니라 현재 확보한 구현과 검증 결과를 재현하기 위한 버전 고정이다. LPG의 Cypher·저장·제약 의미는 Neo4j의 제품 버전과 문서로 고정한다. RDF 1.2의 annotation 구문 유무가 우리 프로젝트의 근거 노드 필요성을 없애지는 않는다.

## 4. 서로 다른 계층의 의미

| 선택 항목 | 주로 제공하는 것 | 스스로 제공하지 않는 것 |
|---|---|---|
| RDF | IRI·blank node·literal과 triple, dataset을 통한 교환 가능한 그래프 모델 | 금융 용어 정의, 필수 필드 검사, 특정 DB의 속도·운영 기능 |
| RDFS | 클래스·속성 계층, domain/range 등의 기본 의미와 entailment | 필수값·최대 개수 검사, 모든 OWL 표현력 |
| OWL 2 | 명시한 공리의 논리적 귀결, 클래스 정의·일관성·동일성 등에 대한 형식 의미 | 원문 참 여부, 입력 필수 필드 검증, 임의의 업무 계산·시점 필터 |
| SHACL | 지정 data graph·target에 대한 shape 조건과 validation report | 원문 사실성, 모든 OWL 귀결, 모든 시점·범위의 완전성 |
| Neo4j LPG/Cypher | label·typed relationship·property 저장, 패턴·경로 질의, 지원되는 DB 제약 | label·edge 이름에서 자동으로 따라오는 OWL 의미·완전한 추론 |

RDFS의 domain/range는 타입을 **추론**하는 의미다. 예를 들어 Person 전용이라고 생각한 속성을 Company에 써도 단순히 입력을 거부하는 SQL형 제약이 되지 않는다. 별도 shape나 적재 규칙으로 금지 조건을 써야 한다. `Company rdfs:subClassOf Organization`과 `x rdf:type Company`에서 Organization을 얻는 데는 **RDFS면 충분**하다. 이 예만으로 OWL 도입의 필수성을 주장하지 않는다. [RDFS 공식 의미 설명](https://www.w3.org/TR/rdf-schema/)

### OWL의 공개 세계·동일성·카디널리티

OWL은 데이터에 없는 사실을 곧 거짓으로 취급하지 않는다. 어떤 회사의 부모가 기록되지 않았다고 ‘부모 없음’이 추론되지 않는다. 서로 다른 이름·IRI라고 언제나 서로 다른 개체라는 가정도 하지 않는다. `sameAs`는 단순 유사도 링크가 아니라 동일 개체라는 강한 주장이다. 최대 1 부모라는 공리 아래 두 부모 IRI가 있다고 해서 항상 입력 오류가 나지는 않는다. 조건에 따라 둘이 같은 개체라는 귀결이 가능하고, 명시적 서로 다름·상충 공리까지 있으면 비일관성이 될 수 있다. 최소 1이라는 공리는 실제 그래프에 이름 있는 값 하나가 반드시 입력됐는지 검사하는 장치가 아니다. 반면 SHACL `minCount`·`maxCount`는 검증 대상 그래프의 값 노드를 세므로 목적이 다르다. [OWL 2 Primer의 데이터베이스·공개 세계·동일성 설명](https://www.w3.org/TR/owl2-primer/)

### SHACL을 실행할 때 고정할 조건

검증의 data graph, shapes graph, targets, entailment·전처리 여부를 함께 기록한다. `sh:closed`는 지정 shape에 대한 허용 속성 조건이고 전체 시스템이 완전한 지식을 가진다는 선언이 아니다. OWL/RDFS closure를 먼저 만들면 검증 대상 타입·속성·개수가 달라질 수 있다. 따라서 원본 graph 검증과 closure graph 검증을 구분하고 결과 변화의 이유를 설명한다. SHACL 검증 실패는 입력 조건 불충족이며 항상 OWL 논리 모순인 것은 아니다. 검사 통과 역시 원문과의 일치나 근거의 신뢰성을 증명하지 않는다. Core로 표현하기 어려운 교차 노드·기간 비교는 SHACL-SPARQL 또는 별도 업무 검사로 명시한다. [SHACL 2017 Recommendation](https://www.w3.org/TR/2017/REC-shacl-20170720/)

### LPG에도 질의 의미는 있으나 OWL 추론은 자동 부여되지 않음

Neo4j의 label, 관계 타입, 값과 Cypher에는 제품이 정한 실행 의미가 있다. ‘LPG는 의미가 없다’는 설명은 부정확하다. 다만 `Company`·`Organization` label과 `SUBCLASS_OF` 관계를 저장하기만 해서는 OWL/RDFS 상속·동일성·모순 탐지가 자동 실행되지 않는다. 적재 시 label 전파, Cypher 경로 질의, 별도 추론·규칙 계층 중 무엇을 구현했는지 밝혀야 한다. neosemantics는 계층 기반 조회 등 추가 기능을 문서화하지만 이를 완전한 OWL 2 DL 추론기로 간주하지 않는다. [Neo4j property graph 모델](https://neo4j.com/docs/getting-started/appendix/graphdb-concepts/), [n10s 추론 절차의 실제 범위](https://neo4j.com/labs/neosemantics/5.14/inference/)

관계 속성은 짧은 이항 관계의 기간·역할을 붙이기에 편리하다. 다중 참여자 이벤트, 관계 자체에 연결되는 여러 근거·추출 실행·정정 주장이 있으면 LPG에서도 Event·Participation·Assertion 노드가 유용하다. RDF에서도 같은 노드 패턴을 사용할 수 있다. 형식을 바꾸면 업무상의 n-ary 관계가 저절로 사라지는 것은 아니다.

## 5. OWL은 필요한 표현력부터 프로파일을 고른다

공식 프로파일은 표현 위치와 허용 공리까지 제한하므로 키워드 하나가 지원된다는 이유만으로 전체 모델이 해당 프로파일이라고 부르지 않는다. [OWL 2 Profiles Recommendation](https://www.w3.org/TR/owl2-profiles/)

| 후보 | 적용을 고려할 요구 | 이번 프로젝트의 확인 조건 |
|---|---|---|
| RDFS만 사용 | 클래스·속성 상속, domain/range 타입 귀결 | 상속 외 추론 CQ가 없다면 먼저 이 범위로 충분한지 검사 |
| OWL 2 EL | 큰 클래스 계층과 existential·교집합 중심 분류 | 허용되지 않는 합집합·전면 부정·카디널리티 등을 요구하는지 검사 |
| OWL 2 QL | 관계형 데이터를 그대로 두고 질의를 재작성하는 접근 | SQL/가상화 필요성부터 확인. property chain·카디널리티·같음 공리 등을 전제하면 범위 벗어날 수 있음 |
| OWL 2 RL | 규칙 기반으로 계산 가능한 제한된 귀결 | Python PoC의 OWL-RL closure 후보. 사용 공리·추론기 범위와 전체 import closure의 프로파일 적합성을 별도로 검사 |
| OWL 2 DL | 제한 프로파일로 표현하지 못하는 실제 요구 공리 | 필요한 공리·일관성 검사와 추론기 지원·운영 비용을 확인한 뒤 확대 |

OWL 파일을 읽거나 triple을 저장하는 라이브러리와, 해당 프로파일의 귀결을 계산하는 추론기는 역할이 다르다. OWL-RL 결과로 모든 OWL 2 DL 공리의 완전한 정합성 검사가 끝났다고 말하지 않는다. 이 표는 일반적인 성능 순위가 아니라 적용 가능한 표현 범위다.

**같은 답, 다른 계산 계약의 예.** `holding_of_security`의 주어를 HoldingAssertion, 목적어를 Security로 정하고 `issued_by`가 Security→Company라면 두 관계의 property chain으로 HoldingAssertion→Company의 파생 관계를 정의할 수 있다. 같은 회사 목록은 Cypher의 두 단계 경로와 SPARQL property path로도 얻는다. OWL 방식은 정의된 공리를 여러 질의에서 재사용하고 귀결을 계산하는 선택이고, 경로 질의는 그 질의가 지정한 경로로 답을 계산하는 선택이다. 결과가 같다는 이유만으로 추론기의 필요성이나 불필요성이 결정되지는 않는다. 파생 관계를 ‘회사 지분을 현재 보유한다’로 명명하기 전 보유 주체·증권 종류·기간·정정 상태까지 맞는지 확인해야 한다. 날짜 교집합·공개 시점 필터는 해당 단순 chain이 자동 처리하지 않는다.

## 6. Neo4j Community의 기능을 전제로 검증을 설계

확인한 공식 current 문서에서 CE는 단일 인스턴스, ACID·Cypher·API를 제공한다. 클러스터·온라인 백업 등 EE 기능을 CE 운영 가정으로 가져오지 않는다. **로컬에 실제 설치된 버전과 에디션은 이 조사에서 검사하지 않았으므로 아래는 문서상 구분이며 설치 검증 결과가 아니다.** [에디션 공식 설명](https://neo4j.com/docs/operations-manual/current/introduction/)

제약 문서는 속성 uniqueness와 달리 **property existence, property type, node/relationship key** 제약을 Enterprise 기능으로 표시한다. uniqueness는 없는 값을 필수로 만들지 않는다. 따라서 ‘ID가 유일해야 한다’와 ‘모든 노드에 ID가 있어야 한다’를 분리해야 한다. 특정 관계의 최대 개수·허용 endpoint label·기간 순서·EvidenceSpan 필수 연결 등 업무 규칙이 전체적으로 자동 보장된다고 가정하지 않는다. CE에서는 Python 입력 검증과 Cypher 위반 탐지, 쓰기 경로 관리 등을 조합하고, 조회형 사후 검사가 원자적 DB 제약과 같은 동시성 보장을 주지 않는 점도 구분한다. [제약 생성 공식 문서](https://neo4j.com/docs/cypher-manual/current/schema/constraints/create-constraints/)

후속 실험에는 Neo4j DB 버전·Cypher 버전·에디션·활성 플러그인과 실제 실행 가능 제약을 기록한다. n10s/APOC/추론기/SHACL 검증기는 각각 별도 구성 요소로 취급한다. 금융기관의 Enterprise 운영 사례가 CE의 기능 보장 근거는 아니다.

## 7. 후보 선택의 필수 조건과 전환 조건

| 후보 | 적합할 수 있는 조건 | 추가로 감당할 비용·실패 조건 |
|---|---|---|
| LPG + 명시적 정의 + Python/Cypher 검증 | 기존 Neo4j·Python 역량을 활용하고 핵심 CQ를 명시적 경로로 충족 | 외부 IRI 매핑·형식 의미·검증 규칙을 별도로 유지. CE의 제한으로 입력 품질이 빠질 수 있음 |
| RDF/RDFS + SHACL + SPARQL | 외부 URI·표준 연결·교환과 실행 가능한 그래프 검증이 핵심 | 질의·shape·도구 학습과 기존 파이프라인 전환. RDFS 이상 공리를 필요로 하면 별도 결정 |
| RDF + 목적에 맞는 OWL + SHACL | 명시적으로 요구한 귀결·분류·일관성 CQ가 실제 이득을 보임 | 프로파일·추론기·검증 순서·갱신·파생값 취소 관리. OWL을 필수 필드 검사로 오용하면 실패 |
| RDF/OWL 의미 원본 + LPG 조회 투영 | 대외 의미 교환과 LPG 응용의 필요를 둘 다 실증 | 두 모델 버전·ID·자료형·다중값·근거·정정·삭제 동기화. 왕복 변환 손실 검사 없이 단순 import를 의미 보존으로 간주하면 실패 |

**필수 통과 조건**은 표현 방식과 무관하게 핵심 CQ의 정답·응답 유보, 증권/회사 구별, 공개·효력·기록 시점, 정정 이력, 근거 경로와 오류 표본 검출이다. **선호 조건**은 팀 학습 비용, 표준 재사용 편의, 질의 유지 비용, 도구·라이선스·갱신 운영 부담이다. 근거 없는 총점이나 서로 다른 데이터의 벤치마크로 대안을 줄 세우지 않는다.

후속 PoC는 동일한 작은 정답 그래프에서 LPG 참조 구현·Cypher 예제, RDFLib/SPARQL·pySHACL, RDFS/OWL-RL closure를 분리해 비교한다. 기존 Neo4j DB 변경 없이 시작할 수 있다. 상속·경로 조회·검증만으로 요구가 충족되면 OWL을 필수로 삼지 않고, 여러 질의에 걸친 의미 공리 재사용과 정합성 검사의 이득이 확인되면 해당 프로파일을 검토한다. 혼합형은 양쪽의 필요가 따로 확인됐을 때만 고려한다.

## 8. 아직 확인하지 못한 것

1. FIBO 특정 릴리스 전체 import closure의 프로파일 적합성·우리 CQ 충족률, 금융기관별 실제 운영·정량 효과.
2. GLEIF의 대체 공개 RDF 배포 경로와 복구 여부, 현재 CDF→RDF 변환 재현성, 국내 공시 기업의 LEI 커버리지.
3. UBS 내부 스키마·소스·운영 로그와 현재 운영 지속 여부. 해당 사례의 개선 경험을 우리 비용·속도로 환산할 근거.
4. Wikidata와 UniProt 서비스의 정량 가용성·정확도·공시 적용 성과. 실제 다운로드 전체를 검수하거나 추론기 구현을 검사하지 않았다.
5. 로컬 Neo4j의 실제 버전·에디션·제약 지원. 공식 current 문서는 변하므로 배포할 버전의 문서와 실행 결과를 고정해야 한다.
6. 작은 PoC 결과를 대규모 금융 운영의 성능·총비용으로 일반화할 근거. 이 문서는 속도 우열을 판단하지 않는다.
