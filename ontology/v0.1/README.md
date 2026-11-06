# GUG 기업 관계·이벤트 온톨로지 정의서 v0.1

작성일: 2026-11-06. 팀 검토용 제안 초안이며 합의 완료된 스키마가 아닙니다.

## 파일 구성
- 01_ontology_overview.csv: 요청하신 9개 계층에 시장 관측·추론 확장 계층을 추가한 요약.
- 02_concept_definitions.csv: 개념 정의와 식별 기준.
- 03_relationship_definitions.csv: 방향이 있는 관계, 출발·도착 개념, 제약.
- 04_property_dictionary.csv: 시간·상태·금액·추출 관련 속성. 세미콜론으로 묶은 속성은 같은 처리 규약을 설명하며 실제 구현 시 개별 필드로 분리합니다.
- 05_validation_rules.csv: 표본 검수와 구현 시 적용할 규칙.

## 팀 검토 방법
각 CSV를 Google Sheets의 별도 시트로 가져오고 담당자와 팀 검토 의견을 입력합니다. 검토상태는 초안 / 검토중 / 합의 / 보류로 관리하는 것을 제안합니다. 변경 시 영문 ID 유지 여부와 데이터 마이그레이션 영향을 함께 검토하세요. 자동 동기화나 공유 업로드는 설정하지 않았습니다.

P0: 식별·근거·시간·지분·경영진의 초기 기반. P1: 계약·기업행위·재무·업종. P2: 사업·제품·시장 관측·추론 확장. 우선순위는 제안이며 이번에 모든 계층을 구현한다는 뜻은 아닙니다.

## 모델 사용 원칙
이 문서는 Neo4j 등으로 옮기기 전의 논리 정의입니다. 세미콜론으로 나열한 출발/도착 개념은 허용 유형의 합집합이며 한 노드에 모든 라벨을 붙이라는 뜻이 아닙니다. Company는 Organization의 하위 유형입니다. 다른 상속 관계와 URI 네임스페이스는 후속 결정 대상입니다.

원문에서 추출한 도메인 관계는 Assertion으로 주체·predicate·객체(또는 literal_value)를 기록하고 EvidenceSpan과 ExtractionRun을 연결합니다. 객체형 관계는 HAS_SUBJECT/HAS_OBJECT, 속성값 주장은 HAS_SUBJECT와 literal_value를 사용합니다. predicate는 관계 ID 또는 속성 ID를 참조합니다. HAS_SUBJECT/HAS_OBJECT 등의 관리용 연결 자체를 다시 Assertion으로 감싸는 무한 재귀 구조는 만들지 않습니다. 검증된 도메인 엣지를 직접 생성하는 경우 해당 assertion_id를 유지합니다.

HAS_SUBJECT/HAS_OBJECT의 허용 유형 '개념 ID 전체'는 02 파일에 정의한 개념을 뜻합니다. 관계 이름은 구현 전 제안 명칭입니다. 구체적인 다중성, 전체 이벤트별 역할 목록, 속성의 수치 정밀도, 열거형 확장 절차는 다음 버전에서 확정합니다.

공개시점, 효력기간, 시스템 기록기간을 구분합니다. 현황의 기준일을 관계 시작일로 바꾸지 않습니다. 정정 또는 철회는 과거 이력을 지우지 않고 후속 버전과 연결합니다. validated는 근거와 추출 결과의 일치를 검증한 상태이며 공시 내용 자체의 진실이나 미래 사건의 실현을 보증하지 않습니다.

## 현재 근거와 한계
로컬 수집 자료: data/raw/opendart/collections/20261001_20261105. 16,295건 공시 목록, 원문 확보 14,035건, 미확보 2,260건. 표본 60건에서 XML/HTML 혼재, 정정 전후 내용, 미래 분할 일정, 이사 선임 안건 등의 문제를 확인했습니다. 전체 원문 의미 분석이나 모든 후보 필드의 추출 가능성 검증은 아직 수행하지 않았습니다. CSV의 제약과 예시는 설계 제안이며 실제 추출 결과 데이터가 아닙니다.

## 다음 합의 항목
1. P0에서 답할 질문 10~15개와 대상 기업 100개 선정 기준.
2. 지분의 보유/소유 및 특별관계자 합산 범위.
3. 인물 식별·임시 엔티티 병합 절차.
4. 정정 공시와 이전 공시를 연결하는 증거 기준.
5. 시간 단위 갱신의 운영 시간대와 320시간 CPU 예산 정합성.
6. 표본 정답과 별도 검증 문서를 통해 관계별 정확도·토큰 예산 결정.

## 설계 참고 자료
- OpenDART 공시검색: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019001
- OpenDART 사업보고서 주요정보: https://opendart.fss.or.kr/guide/main.do?apiGrpCd=DS002
- KRX API 서비스 목록: https://openapi.krx.co.kr/contents/OPP/INFO/service/OPPINFO004.cmd
- FIBO: https://spec.edmcouncil.org/fibo/index.html
- W3C PROV-O: https://www.w3.org/TR/prov-o/
- TRACE: https://arxiv.org/abs/2603.12500
이 자료들은 설계 참고이며 각 개념이 해당 표준과 완전히 호환된다는 뜻은 아닙니다.

## 파일 형식
CSV는 UTF-8 BOM, 쉼표 구분, CRLF 줄바꿈입니다. CSV에는 시트·색상·필터 UI가 저장되지 않습니다. 식별자 열은 가져올 때 텍스트로 지정하세요. 이 문서에는 실제 기업 식별번호나 개인 원문 데이터를 넣지 않았습니다.
