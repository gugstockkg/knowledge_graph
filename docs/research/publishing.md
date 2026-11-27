# 연구 기록 발행

`site/`는 GitHub Pages 공개 영역이다. 프로젝트 사이트는 `https://gugstockkg.github.io/knowledge_graph/`에서 열리는 구성을 사용한다. 저장소 관리자가 Settings → Pages → Build and deployment → Source에서 GitHub Actions를 선택하면, `main`의 `site/` 변경을 발행한다. 처음 한 번은 Actions의 `Publish research site`를 수동 실행해도 된다.

## 새 기록의 형식

연구 글은 `site/journal/YYYY-MM-DD-topic/index.html`에 둔다. 기존 글처럼 `../../style.css`를 연결하고, 글의 HTML 머리말에 `fintos:title`(목록 제목), `fintos:summary`(한두 문장의 요약), `fintos:category`(유형), `fintos:published`(시간대가 있는 ISO 8601 발행 일시)를 적는다. 날짜는 폴더 이름의 날짜와 일치해야 한다. 첫 단락에서 질문을 제시하고, 본문에서 선택한 방법·근거·한계를 설명한다. 읽는 사람이 다음 자료를 찾을 수 있도록 관련 글이나 산출물에 연결한다.

- 산출물: 버전, 파일 형식, 자료에서 할 수 있는 일, 공개 파일 링크.
- 설계 기록: 당시 질문, 비교한 대안, 선택 이유, 재검토할 조건.
- 실험: 날짜, 표본 범위, 관찰 결과, 확인하지 못한 범위. 계획·가상 예시·실측 결과는 제목 또는 상태에서 구분한다.

유형은 `backtest`(백테스트), `research`(연구 기록), `validation`(설계와 검증), `evaluation`(실험 설계) 중 하나를 사용한다. GitHub Actions가 발행 일시가 최신인 세 편을 홈에 표시하고, 전체 글은 `journal/` 보관함으로 생성한다. 보관함은 제목·요약 검색, 유형·연도 필터, 페이지 이동을 제공한다. 제목과 요약은 검색 결과에 그대로 표시된다.

로컬에서 확인하려면 새 출력 디렉터리에 정적 사이트를 생성한 뒤 웹 서버를 실행한다.

```bash
python3 scripts/build_research_site.py /tmp/fintos-preview
python3 -m http.server 8000 --directory /tmp/fintos-preview
```

원문 ZIP, 실제 적재 파일, 서비스 주소와 비밀값은 발행 폴더에 넣지 않는다. 공개하기로 확정한 문서만 저장소 링크로 연결한다. GitHub Pages 워크플로는 `site/`에서 만든 정적 사이트만 전송한다.
