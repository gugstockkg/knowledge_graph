# 데이터와 버전

| 영역 | 내용 | Git |
|---|---|---|
| ontology/v0.1 | 초기 계층·개념·관계·속성·검증 정의 | 포함 |
| ontology/drafts/v0.2 | FIBO 검토를 반영한 XLSX 초안 | 포함 |
| ontology/alignment/fibo | 1차 대응 검토·공식 소스 버전·해시 | 포함 |
| data/raw/opendart/collections | 날짜 구간별 원문·목록·상태·수집 manifest | 제외 |
| data/raw/opendart/runs | 기존 날짜·회사 단위 수집 실행본 | 제외 |
| data/graph/ownership_pilot_v01/stage2_twenty | 현재 20건 그래프·근거·검토 표·질문 응답 | 제외 |
| data/graph/ownership_pilot_v01/import | Neo4j 형식 CSV와 생성 Cypher | 제외 |
| data/graph/ownership_pilot_v01/baseline_before_migration | 이전 전 그래프 비교 기준 | 제외 |
| artifacts/legacy | 이전 실험 결과와 코드의 보존 사본 | 제외 |
| artifacts/migration | 파일별 복사 해시·의미 비교·DB 절체 기록 | 제외 |

현재 원문 확보 상태와 추출 성공 여부는 다른 개념입니다. 원문이 없으면 관계가 없다는 뜻이 아닙니다. 공시가 여러 XML 파일을 포함할 수 있어 공시 수와 XML 파일 수는 다릅니다.

graph/extract는 지정된 5개 기업에서 두 종류 지분보고를 선택하는 재현 파일럿입니다. 부분적으로 읽은 필드의 위치를 근거로 보존하며 전체 공시를 요약한 결과가 아닙니다. 주식등/주권과 개인/연명 합산을 구분합니다.

소스 스냅샷은 immutable로 보존하고 파생 결과는 재생성합니다. 원본 v0.1과 draft v0.2를 구분하며 OWL/FIBO 완전 호환을 선언하지 않습니다. 경제 값이 같아도 온톨로지·파서·근거 버전이 달라지면 추출 실행 이력을 구분해야 합니다.
