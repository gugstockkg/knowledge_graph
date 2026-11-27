# 연구 기록 발행

`site/`는 GitHub Pages 공개 영역이다. 프로젝트 사이트는 `https://gugstockkg.github.io/knowledge_graph/`에서 열리는 구성을 사용한다. 저장소 관리자가 Settings → Pages → Build and deployment → Source에서 GitHub Actions를 선택하면, `main`의 `site/` 변경을 발행한다. 처음 한 번은 Actions의 `Publish research site`를 수동 실행해도 된다.

## 새 기록의 형식

연구 글은 `site/journal/YYYY-MM-DD-topic/index.html`에 둔다. 기존 글처럼 `../../style.css`를 연결하고, `site/index.html`의 연구 글 목록에 제목·날짜·요약·링크를 추가한다. 첫 단락에서 질문을 제시하고, 본문에서 선택한 방법·근거·한계를 설명한다. 읽는 사람이 다음 자료를 찾을 수 있도록 관련 글이나 산출물에 연결한다.

- 산출물: 버전, 파일 형식, 자료에서 할 수 있는 일, 공개 파일 링크.
- 설계 기록: 당시 질문, 비교한 대안, 선택 이유, 재검토할 조건.
- 실험: 날짜, 표본 범위, 관찰 결과, 확인하지 못한 범위. 계획·가상 예시·실측 결과는 제목 또는 상태에서 구분한다.

원문 ZIP, 실제 적재 파일, 서비스 주소와 비밀값은 발행 폴더에 넣지 않는다. 공개하기로 확정한 문서만 저장소 링크로 연결한다. GitHub Pages 워크플로는 `site/`만 전송한다.
