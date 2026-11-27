# 최대주주 변경·정정 이력 EC2 데모 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans or superpowers:subagent-driven-development. Track phases with the checkboxes below.

**Goal:** S3의 실제 최대주주 변경 공시 한 사건에서 기준일별 값과 원문 근거를 Neo4j로 조회한다.

**Architecture:** 날짜별 공시 목록을 선택한 뒤 접수번호로 ZIP을 읽는다. 문서별 주장을 보존하고, 근거가 확인된 정정만 필드 단위로 연결한다. 같은 산출물로 Neo4j 적재와 RDF 구조 검증을 수행한다.

**Tech Stack:** Python, CSV, S3, Neo4j Community Compose, SSM, SHACL Core.

**Spec:** `ontology/controller-change-v0.1/README.md` 및 `ontology.csv`.

## 범위와 실패 조건

최대주주 변경과 해당 정정만 첫 데모에 포함한다. 이름만으로 동일 주체를 확정하거나 제목만으로 사건 완료를 추론하지 않는다. 원본과 실제 적재 파일은 제한된 저장소에 둔다. 누락 원문, 모호한 정정 대상, 같은 날 중복, 부분 정정, 재시도 중복을 별도로 검사한다.

- [ ] S3 매니페스트와 일별 JSONL을 확인한다. 샘플의 원본·정정 ZIP을 찾고 SHA-256을 기록한다. 이전 수집본은 접수번호·해시로 대조한다.
- [ ] 정의 CSV·간단 설명서·발표용 PPTX/PDF의 용어와 사례를 대조한다. 공개 문서의 합성 예와 내부 대조에 쓰는 실제 공시를 구분한다.
- [ ] 변환 CLI를 만들고 원본/정정 입력, 소실된 근거, 필드 범위, 재실행에 대한 테스트를 작성한다. 검수되지 않은 정정과 판정 불가 건을 집계한다.
- [ ] 기존 CSV 적재기를 넓혀 검증용 그래프를 만든다. 기준일을 바꾸어 값이 바뀌는지, 수정 범위 밖 값은 유지되는지, 앞선 접수일의 결과에 미래 공시가 섞이지 않는지 검사한다.
- [ ] 코드와 문서만 GitHub에 반영하고 EC2에서 동일 커밋을 실행한다. 디스크와 수집 서비스 상태를 확인한 뒤 Neo4j Community를 기동한다. SSM을 통해 조회하고 같은 쿼리의 결과를 비교한다.
