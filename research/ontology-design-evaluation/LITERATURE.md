# 온톨로지 설계·평가와 LLM 생성 평가 문헌 근거표

확인일: 2026-11-13. 범위: PLAN.md Phase 2의 학술 문헌 15편. 출판사·학회·저자·소속기관 원문을 우선했다. 아래의 **적용**과 **한계 중 프로젝트 관련 해석**은 조사자의 판단이며, 논문이 금융 공시 성능을 입증했다는 뜻이 아니다. 서로 다른 벤치마크의 수치로 모델·방법의 우열을 비교하지 않았다. 유료 원문 구매, 외부 모델/API키 호출, 논문 실험 재실행은 하지 않았다.

## 핵심 구분

| 평가 질문 | 확인 가능한 것 | 별도로 검증할 것 |
|---|---|---|
| TBox에 CQ를 표현할 용어·관계·공리가 있는가? | 스키마 요구 충족, 공리 구조, 계층, CQ별 필요 요소 | 실제 공시의 추출·식별·단위·시간 정확도 |
| ABox에 필요한 사실이 올바르게 적재됐는가? | 원문 대비 사실 정확도·누락, 근거·버전 연결 | 질의 자체의 의미와 시점 조건 |
| 실행한 질의가 정답과 근거를 반환하는가? | 정답·반례·응답 유보·시점 재현 | 전체 도메인 완전성, 운영 규모 성능 |

**CQ를 모델링할 수 있다는 판정은 실제 공시 데이터에서 정답을 반환했다는 판정이 아니다.** 특히 L12·L13의 CQ 모델링 판정은 좋은 모델링 관행과도 분리돼 있고, L14는 인스턴스 질의를 제외한 TBox 벤치마크다. 이 구분은 공시 평가표의 필수 열로 유지한다.

## 서지와 검토 수준

본문 검토는 아래에 명시한 절·예시·한계를 읽었다는 뜻이며, 모든 실험 산출물이나 전체 코드의 재현 검증을 뜻하지 않는다. 초록·서지만 확인한 항목은 그 범위를 넘는 결과를 인용하지 않았다.

| ID | 연도·저자·정확한 제목 | 출처·게재 상태 | 이번 검토 범위 |
|---|---|---|---|
| L01 | 1995, Thomas R. Gruber. *Toward Principles for the Design of Ontologies Used for Knowledge Sharing* | IJHCS 43, 907–928. [저자 PDF](https://tomgruber.org/writing/onto-design.pdf), [DOI](https://doi.org/10.1006/ijhc.1995.1081). PDF는 1993-08-23 개정 원고 표기 | 본문 §3 설계 기준·예시. 출판연도와 원고 개정연도 구별 |
| L02 | 1995, Michael Grüninger, Mark S. Fox. *Methodology for the Design and Evaluation of Ontologies* | IJCAI-95 Workshop on Basic Ontological Issues in Knowledge Sharing. [연구실 공식 방법 소개](https://eil.mie.utoronto.ca/theory/enterprise-modelling/entmethod/), [원문 PDF](https://www.eil.utoronto.ca/enterprise-modelling/papers/gruninger-ijcai95.pdf) | 공식 방법 소개·서지 확인. 원문 PDF는 열리지만 텍스트 추출 불가; 본문 정독으로 계산하지 않음 |
| L03 | 2002, Nicola Guarino, Christopher Welty. *Evaluating Ontological Decisions with OntoClean* | Communications of the ACM 45(2), 61–65. [소속기관 원문](https://www.loa.istc.cnr.it/old/Papers/CACM2002.pdf) | 본문 rigidity, identity/unity, subsumption 오용 예시 |
| L04 | 2007, Samir Tartir, I. Budak Arpinar. *Ontology Evaluation and Ranking using OntoQA* | IEEE ICSC 2007. [저자 원문](https://budakarpinar.github.io/papers/OntoQA-ICSC-2007.pdf) | 본문 구조·지표 정의·사용자 선호에 따른 순위. 2005 선행 OntoQA와 2007 논문을 혼동하지 않음 |
| L05 | 2011, Astrid Duque-Ramos, Jesualdo Tomás Fernández-Breis, Robert Stevens, Nathalie Aussenac-Gilles. *OQuaRE: A SQuaRE-based Approach for Evaluating the Quality of Ontologies* | Journal of Research and Practice in Information Technology 43(2), 159–176. [Manchester 공식 서지·초록](https://research.manchester.ac.uk/en/publications/oquare-a-square-based-approach-for-evaluating-the-quality-of-onto/), [저자 교정본](https://www.cs.man.ac.uk/~stevensr/papers/OQuareProof.pdf) | 공식 초록·서지와 검색 노출 원고 첫 부분. 교정본 본문 요청은 timeout; 세부 척도·실험 수치 미인용 |
| L06 | 2014, María Poveda-Villalón, Asunción Gómez-Pérez, Mari Carmen Suárez-Figueroa. *OOPS! (OntOlogy Pitfall Scanner!): An On-line Tool for Ontology Evaluation* | IJSWIS 10(2), 7–34. [DOI](https://doi.org/10.4018/ijswis.2014040102), [공식 카탈로그·인용 서지](https://oops.linkeddata.es/catalogue.jsp) | 2014 본문은 미검토. 공식 pitfall 카탈로그 본문과 2012 선행 논문 [*Did you validate your ontology? OOPS!*](https://2012.eswc-conferences.org/sites/default/files/eswc2012_submission_322.pdf) 본문을 보조 근거로 사용 |
| L07 | 2001, Natalya F. Noy, Deborah L. McGuinness. *Ontology Development 101: A Guide to Creating Your First Ontology* | Stanford KSL-01-05 기술보고서; 저널 실험 논문 아님. [저자기관 본문](https://protege.stanford.edu/publications/ontology_development/ontology101-noy-mcguinness.html), [공식 안내](https://protegewiki.stanford.edu/wiki/Ontology101) | 범위 설정·반복 개발·클래스와 명칭 구분·계층 오류 본문 |
| L08 | 1997, Mariano Fernández-López, Asunción Gómez-Pérez, Natalia Juristo. *METHONTOLOGY: From Ontological Art Towards Ontological Engineering* | AAAI Spring Symposium, SS-97-06, 33–40. [학회 원문](https://cdn.aaai.org/Symposia/Spring/1997/SS-97-06/SS97-06-005.pdf) | 본문 개발 과정·목적/범위·중간 표현·통합 문서 |
| L09 | 2009, Valentina Presutti, Enrico Daga, Aldo Gangemi, Eva Blomqvist. *eXtreme Design with Content Ontology Design Patterns* | WOP 2009, CEUR-WS 516, 83–97. [학회 원문](https://ceur-ws.org/Vol-516/pap21.pdf) | 본문 local/generic use case, CQ와 패턴 선택, 반복·협업 개발 |
| L10 | 2024 행사 / 2025 proceedings, Youssra Rebboud, Pasquale Lisena, Lionel Tailhardat, Raphaël Troncy. *Benchmarking LLM-based Ontology Conceptualization: A Proposal* | ISWC 2024 특별 세션, CEUR-WS 3953. [학회 원문](https://ceur-ws.org/Vol-3953/365.pdf), [저자기관 서지](https://www.eurecom.fr/en/publication/7944) | 본문 제안 작업·평가 방법 표·미래 계획. PDF copyright는 2025, 행사일은 2024-11-13 |
| L11 | 2024, Achim Reiz, Kurt Sandkuhl. *NEOntometrics – A Public Endpoint for Calculating Ontology Metrics* | Transactions on Graph Data and Knowledge 2(2), Article 2; 2024-12-18 출판. [출판사 본문](https://drops.dagstuhl.de/storage/08tgdk/tgdk-vol002/tgdk-vol002-issue002/html/TGDK.2.2.2/TGDK.2.2.2.html), [DOI](https://doi.org/10.4230/TGDK.2.2.2) | 본문 도구 목적·지표 구성·§5 평가 전략. 금융 의미 평가 결과로 취급하지 않음 |
| L12 | 2025, Anna Sofia Lippolis, Mohammad Javad Saeedizade, Robin Keskisärkkä, Sara Zuppiroli, Miguel Ceriani, Aldo Gangemi, Eva Blomqvist, Andrea Giovanni Nuzzolese. *Ontology Generation using Large Language Models* | **arXiv 프리프린트 2503.05388v1**, 2025-03-07. [서지](https://arxiv.org/abs/2503.05388), [본문](https://arxiv.org/html/2503.05388v1) | 본문 §3–6 정의·데이터·평가·결과, 논의·한계. 확인한 arXiv 기록에 학회/저널 게재 정보 없음 |
| L13 | 2025, Anna Sofia Lippolis, Mohammad Javad Saeedizade, Robin Keskisärkkä, Aldo Gangemi, Eva Blomqvist, Andrea Giovanni Nuzzolese. *Assessing the Capability of Large Language Models for Domain-Specific Ontology Generation* | ESWC 2025 ELMKE 워크숍, CEUR-WS 3977. [공식 목차](https://ceur-ws.org/Vol-3977/), [arXiv v1 서지](https://arxiv.org/abs/2504.17402), [본문](https://arxiv.org/html/2504.17402v1) | 본문 정의·수동 판정·결과·§8 한계. Domain-OntoGen은 저장소명이며 논문 제목 아님 |
| L14 | 2026, Jiayi Li, Ziyuan Wang, Daniel Garijo, María Poveda-Villalón. *CQ4OE: A benchmark for assessing LLM-assisted ontology generation from competency questions* | **arXiv 프리프린트 2609.26029v1**, 2026-09-22. [서지](https://arxiv.org/abs/2609.26029), [본문](https://arxiv.org/html/2609.26029v1) | 본문 §3 주석·gold 구축, §4 지표, §5–6 결과·한계. 확인한 기록에 정식 게재 정보 없음 |
| L15 | 2026, Jiayi Li, Daniel Garijo, María Poveda-Villalón. *Large Language Models for Ontology Engineering: A Systematic Literature Review* | Semantic Web: Interoperability, Usability, Applicability; 2026-07-13 온라인 출판. [출판사 본문·DOI 10.1177/22104968261465514](https://journals.sagepub.com/doi/10.1177/22104968261465514) | 본문 §3 선정 방법·§4.3 평가 방법·재현성 논의. 2026 논문이지만 검색 기간은 2018–2025년 5월 |

## 자료별 평가 방법·한계·공시 적용

### L01 — 설계 원리

- **대상·방법·결론:** 지식 공유를 위한 설계물의 명확성, 정합성, 확장 가능성, 최소 인코딩 편향, 최소 존재론적 개입을 제시한다. 논리 공리뿐 아니라 자연어 정의·예시와 추론의 일치도 정합성에 포함한다. 정량 벤치마크가 아니다.
- **한계:** 다섯 기준은 범용 합격 점수나 공시 평가 가중치가 아니다. 목적에 따른 설계 판단이 필요하다.
- **적용:** `Assertion`과 원문 사실, 회사와 제출인, 결정과 완료의 정의를 예시·반례와 연결한다. Neo4j에 편리하다는 이유만으로 개념 의미를 정하지 않는다.

### L02 — CQ 기반 범위와 요구사항

- **대상·방법·결론:** 연구실 공식 설명은 동기 시나리오 → 비형식 CQ → 1차논리 용어 → 형식 CQ → 의미·제약 순서를 제시한다. CQ는 온톨로지 범위를 정의하는 근거다.
- **한계:** 이번에는 공식 요약 수준이다. 이 방법의 원문 실험이나 특정 CQ 통과율을 확인했다고 주장하지 않는다.
- **적용:** “정정 이전에 알려진 계약금액”을 질문 문장만 적지 말고 입력 시점·필요 개념·기대 답·근거로 풀어 쓴다.

### L03 — 역할·동일성과 계층 의미

- **대상·방법·결론:** rigidity, identity, unity 등의 메타속성으로 subsumption 선택을 점검한다. 본문은 anti-rigid 역할이 rigid 유형을 포괄하는 계층의 문제를 예시로 설명한다. 논리적 의미에 기반한 개념 검토이며 정확도 벤치마크가 아니다.
- **한계:** 메타속성 부여에는 전문가 판단이 필요하고, 잘못된 원문 추출이나 시간 값은 자동으로 해결되지 않는다.
- **적용:** 사람·조직의 정체성과 임원·제출인·계약 상대방이라는 역할을 구분한다. 역할의 기간·행위 문맥은 별도로 표현한다. 모든 역할 클래스가 금지된다고 해석하지 않는다.

### L04 — 구조·적재 지표와 목적별 순위

- **대상·방법·결론:** schema와 populated knowledge base를 나눠 관계·속성·상속의 풍부함, 클래스 사용 등 지표를 계산하고 키워드 관련성과 사용자 선호로 순위를 조정한다. 논문 스스로 도메인에 따라 선호하는 구조가 달라짐을 설명한다.
- **한계:** 깊이·관계 수·인스턴스 수가 크다는 사실만으로 의미가 정확하거나 공시 질의를 잘 푼다는 결론은 나오지 않는다. 2005 선행 논문의 독립 원문은 이번에 검토하지 않았다.
- **적용:** v0.1과 개정안의 구조·실제 사용 여부를 진단하되, 쓰이지 않는 클래스와 아직 표본에 없는 클래스를 구별한다. 목적 불명의 종합 순위는 만들지 않는다.

### L05 — 품질 모델과 측정의 분리

- **대상·방법·결론:** 공식 초록은 SQuaRE에 기반한 품질 특성·하위 특성·자동 측정 지표를 구성하고, 하위 값들을 결합해 특성을 평가하며 두 응용 도메인에 적용했다고 설명한다.
- **한계:** 이번에 본문을 확보하지 못해 정규화 구간·가중치·세부 도메인 결과는 검증하지 않았다. 공시의 합격 기준으로 그 수치를 가져올 근거가 없다.
- **적용:** 먼저 “기능 적합성·유지보수성 등 무엇을 평가하는가”를 정의하고 측정 지표를 붙이는 구성만 참고한다. 보편 점수표로 채택하지 않는다.

### L06 — 자동 pitfall 검사의 범위

- **대상·방법·결론:** 공식 카탈로그는 다의적 요소, 이름 규약 혼용, 누락된 주석 등 모델링 문제 후보를 critical/important/minor로 분류한다. 2012 본문은 온톨로지 개발 도구와 독립적인 자동 진단 도구를 설명한다.
- **한계:** 2014 논문의 만족도·사용 통계·도구 비교 실험은 본문 미검토이므로 재인용하지 않는다. 카탈로그 경고가 특정 공시 모델에서 실제 오류인지 별도 판단해야 한다. 통과가 요구사항 충족을 보장하지 않는다.
- **적용:** OWL 산출물이 있을 때 반복 진단 보조로 사용한다. LPG에 이름만 대응시켜 동일 검사를 수행했다고 쓰지 않는다. V01–V18의 업무 제약·시점 누출 검사는 별도로 구현한다.

### L07 — 반복 가능한 정의서 작성

- **대상·방법·결론:** 와인 예제로 목적·범위, 재사용, 용어, 클래스 계층, 속성·제약, 인스턴스의 반복 개발을 설명한다. 개념과 이름, 동의어와 별개 클래스를 구별하고 응용·전문가 논의로 수정한다.
- **한계:** 실무 입문 기술보고서이며 현대 LLM 생성의 효과나 OWL/Neo4j 성능 비교 근거가 아니다.
- **적용:** 클래스·관계마다 정의·동의어·예시·반례·속성·유지 책임을 적는다. 보통주와 우선주의 차이가 이름만의 차이인지 실제 질의에 필요한 구별인지 확인한다.

### L08 — 개발 산출물과 검증 과정

- **대상·방법·결론:** 화학 온톨로지 구축 경험을 바탕으로 진화하는 프로토타입과 명세·개념화·통합·구현·평가·문서화 과정을 제시한다. 용어집·속성 표·규칙 표·재사용 정의의 통합 문서 등 중간 표현을 강조한다.
- **한계:** 과정의 체계성이 결과 온톨로지의 정답률을 자동 보장하지 않는다. 공시·LLM 도메인 실험은 아니다.
- **적용:** 현재 CSV 정의서의 자연어 검증 규칙, 실행 코드, 테스트 결과를 서로 연결한다. 외부 표준에서 가져온 용어의 원래 의미와 로컬 변경도 기록한다.

### L09 — CQ 단위 모듈과 패턴 재사용

- **대상·방법·결론:** local use case와 generic use case를 CQ 등 호환되는 형식으로 표현하고, 맞는 content pattern을 선택·재사용하는 협업·증분 방법을 제시한다. 시간에 따른 역할과 n-ary 관계도 패턴이 해결하는 문제의 예다.
- **한계:** 패턴이 존재한다고 현재 공시 요구에 맞거나 운영 효율이 입증되는 것은 아니다. 모듈 통합 후 충돌·중복 점검이 필요하다.
- **적용:** 계약 참여자·역할·기간, 정정 버전·주장·근거를 작은 CQ 묶음으로 설계한 뒤 통합한다. 패턴명보다 실제 보존해야 하는 의미로 선택한다.

### L10 — 평가 작업을 섞지 않기

- **대상·방법·결론:** 온톨로지 개념화, CQ 생성, 문서화, CQ 질의 생성, KG 언어화에 각각 다른 평가를 붙이는 **벤치마크 제안**이다. 개념화에는 정확성·완전성·간결성 및 논리 일관성, 질의에는 구조 비교 등을 제안한다.
- **한계:** 완성된 대규모 비교 실험의 우승 결과가 아니다. 본문도 적응성·명확성·계산 효율을 다루지 않는다고 명시한다. 질의 구조 유사성만으로 실행 결과 동등성이 보장되지 않는다.
- **적용:** 생성 정의서, 생성 질의, 생성 설명문을 별개 평가한다. 공시는 질의 구조뿐 아니라 고정 데이터에 대한 정답·시간 조건·근거를 검사한다.

### L11 — 지표 계산의 재현성

- **대상·방법·결론:** 공개 지표 계산 서비스와 오픈소스 구현, 지표 선택 안내, Git 기반 변화 분석을 제공한다. 본문은 도구 목적에 따른 평가 전략과 구현·성능 평가를 구분한다. 공개 코드·평가 자료가 연결돼 있다.
- **한계:** 지표를 계산할 수 있다는 증거와 그 지표가 공시 의미 품질을 예측한다는 증거는 다르다. 이번에 서비스에 로컬 자료를 업로드하거나 실행하지 않았다.
- **적용:** 구조 지표를 도입하면 정의·분모·라이브러리 버전·imports 포함 여부를 고정한다. 값 변화의 의미를 CQ 변경과 함께 해석한다.

### L12 — Ontogenia와 다차원 평가

- **대상·방법·결론:** 10개 온톨로지, 100개 CQ, 29개 user story를 바탕으로 최소 모듈과 Memoryless CQbyCQ·Ontogenia를 평가한다. CQ에 필요한 요소가 있으면 모델링 가능으로 보되 좋은 모델링인지는 별개다. 불필요한 요소와 전문가 검토를 더한다. 요구 충족 개선과 함께 잉여 요소·오류·품질 변동을 보고한다.
- **한계:** 특정 모듈·요구에 대한 결과이며, novice 학생 비교를 숙련 전문가 대체나 금융 일반화로 확대할 수 없다. 불필요함은 주어진 CQ 집합에 상대적이다. 저장소 연결은 확인했지만 코드 재현은 하지 않았다.
- **적용:** CQ별 필수 개념·관계·공리를 연결하고 잉여·누락·의미 오류를 따로 센다. 미래 확장용 요소는 근거가 있는 범위 확장으로 표시한다. 실제 공시 정답 평가를 추가한다.

### L13 — 도메인 일반화 주장의 조건

- **대상·방법·결론:** 6개 도메인·95개 curated CQ와 user story로 o1-preview·DeepSeek의 생성을 비교한다. 두 ontology engineer가 modelled/not modelled/minor issue로 수동 판정한다. 해당 기준에서 도메인별 성능이 대체로 일관됐다고 보고한다.
- **한계:** 한 평가 기준·두 reasoning 모델·정해진 표본에 한정된다. 논문은 학습 데이터 누출 가능성과 모델 범위를 명시한다. 평가의 modelled는 SPARQL 질의를 쓸 수 있는 요소가 있다는 뜻으로 모델링 품질과 분리된다.
- **적용:** 공시의 일반화는 유형·정정·비공개·기간·단위 사례를 직접 시험해야 한다. minor issue 허용 결과와 무수정 통과 결과를 합치지 않고, 사람이 보정한 부분도 남긴다.

### L14 — CQ와 gold 공리의 추적성

- **대상·방법·결론:** 6개 온톨로지에서 CQ2Term 99개 CQ, CQ2Onto 118개 CQ를 구성한다. 용어·속성 특성·domain/range·TBox 공리·계층 closure의 P/R/F1와 CQ별 부분/완전 coverage를 나눠 평가한다. 용어 복원이 구조·공리 생성보다 쉽다는 결과다. CQ→필수 요소·공리 provenance와 정렬 흔적을 공개한다.
- **한계:** 인스턴스 질의·외부 지식 요구 CQ는 제외한다. 용어 정렬 오류가 후속 점수로 전파되고 threshold와 유사어 판정에 의존한다. closure 복구도 원자적 계층 관계로 분해 가능한 공리에 제한된다. 공개 자료의 학습 오염 가능성이 있다. 프리프린트다.
- **적용:** 공시 CQ→개념/관계/제약 연결표와 평가 흔적을 채택한다. 동등한 대안 설계는 사람이 검토한다. TBox coverage를 실제 ABox 정답률로 이름 바꾸지 않는다. 복잡한 시간·근거 의미는 실행 테스트로 보완한다.

### L15 — 최근 문헌 전체의 증거 수준

- **대상·방법·결론:** 36편을 49개 task-level study로 분해한다. 명시적 평가 프로토콜이 있는 39개 study의 정량·정성·혼합 평가를 분석하고, 작업·데이터·지표·실험 흐름의 이질성과 프로토콜/코드 공개 부족을 지적한다.
- **한계:** 검색은 2025년 5월까지의 영어·동료심사 자료 중심이므로 2026 최신 실험 전체를 포괄하지 않는다. 논문 수와 study 수는 다른 분모다. 검토 논문들의 정확도를 같은 작업처럼 합칠 수 없다.
- **적용:** 생성의 입력·출력·사람 역할·정답 출처·모델/프롬프트/비용·반복 횟수·코드 공개 여부를 기록한다. 생성 모델의 자기평가만으로 합격시키지 않는다.

## 공시 프로젝트에 도입할 평가 구성 — 조사자 종합

1. **사람이 확정한 요구와 gold:** CQ·정답·허용 대안·반례·응답 유보 기준을 공시 원문과 연결한다. AI가 만든 CQ와 AI가 만든 gold만으로 닫힌 평가를 만들지 않는다.
2. **TBox 평가:** CQ별 필수 구별·관계·시간·근거 표현 여부를 확인한다. OWL 후보라면 일관성·불만족 클래스와 공리/계층 검사를 추가한다. LPG 후보에는 실제 구현 가능한 스키마·Cypher 검사를 명시한다.
3. **ABox 평가:** 같은 표본에서 관계·수치·단위·분모·기간·식별·공개 시점·정정 버전·EvidenceSpan을 원문과 대조한다. 누락과 잘못 추가한 사실을 각각 센다.
4. **실행 평가:** 고정 입력·기대 결과로 핵심 CQ를 실행한다. 빈 결과만 내는 모델, 제약이 없어 오류가 없는 모델이 통과하지 못하도록 양성·음성·미상 사례를 함께 둔다.
5. **자동 검사와 인간 판단 분리:** parser/reasoner/제약/질의 실행은 기계 검사의 범위, 역할·동일성·정답·유사어 동등성·대안 설계의 적절성은 검수 범위로 남긴다. 자동 정렬과 LLM judge의 판정도 검토 가능한 보조 증거다.
6. **결과 보고:** 필수 실패 조건을 먼저 제시하고 coverage·정확도·중복·수정량·시간·비용을 별개 표시한다. 도메인/모델/생성 변동과 미검수 부분을 숨기는 단일 종합 점수는 만들지 않는다.

## 검증 및 남은 공백

- 원문/공식 페이지에서 제목·저자·연도와 최근 4편의 버전·게재 상태를 확인했다. 원문·공식 페이지를 직접 열어 확인했으며 DOI는 출처 식별 링크로 함께 제공했다. DOI/arXiv 식별자를 새로운 논문으로 중복 계산하지 않았다.
- 본문 근거를 확인한 자료는 L01, L03, L04, L07–L15다. L06은 **2014 논문 본문 대신 공식 카탈로그·2012 선행 원문**을 읽었다. L02는 공식 연구실 요약, L05는 공식 초록·서지 수준이다.
- OQuaRE 세부 척도, L02 원문의 상세 증명·사례, 2014 OOPS!의 실험은 추가 원문 확인이 필요하다. 이 문서는 이들 미확인 수치를 사용하지 않는다.
- 저자 공개 저장소는 재현 자료의 존재와 링크 확인 수준이다. gold의 독립 검수, 라이선스 전체, 데이터 누출, 모델 출력·비용·통계 재계산을 이번에 완료한 것은 아니다.
- 이 문헌군만으로 한국 금융 공시의 정정·철회·비공개·시점 재현 능력, RDF/OWL/LPG 운영 성능, 주가 예측 효과를 결론 낼 수 없다. 공시 표본 실험과 실제 배포 사례는 다른 산출물에서 평가한다.

권장 읽기 순서: L01 → L02·L03 → L04·L05·L06 → L12·L13 → L14 → L15. 개발 절차와 문서 양식은 L07–L09, 평가 작업 설계와 지표 구현은 L10–L11을 참조한다.
