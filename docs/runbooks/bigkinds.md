# 빅카인즈 로컬 자동 수집

정치·경제·국제와 각 하위분류를 OR 조건으로 조회한다. 수집 프로그램은 Playwright로 공식 검색 화면과 엑셀 내보내기를 조작하며 LLM을 호출하지 않는다. 월별 조회에서 출발해 결과가 2만 건을 넘으면 날짜 구간을 나눈다. 하루가 2만 건을 넘거나 다운로드가 지연되면 분류별로도 나눈다.

## 설치와 실행

Python 3.10 이상과 Google Chrome이 필요하다. 저장소 루트에서 실행한다.

```bash
python3 -m venv .venv-news
.venv-news/bin/python -m pip install -e '.[news]'
.venv-news/bin/python scripts/kg.py news --start 2026-01-01 --end 2026-11-10
```

프로그램이 연 전용 Chrome 창에서 직접 로그인한다. 기존 개인 Chrome 프로필을 읽지 않고 `.runtime/bigkinds/profile/`에 수집 전용 로그인 세션을 유지한다. 로그인 세션이 만료되면 `waiting_for_login` 상태로 전환하고 사용자 로그인을 기다린다. 로그인 후 수집을 자동 재개한다. CAPTCHA나 사이트의 추가 확인 절차가 나오면 사용자가 직접 처리한다.

## 저장과 재개

- `artifacts/ingestion/bigkinds_status.json`에 실행 상태, PID, 현재 날짜 구간과 누적 고유 기사 수를 기록한다.
- `data/news/bigkinds/<시작일>_<종료일>_politics_economy_international/raw/`에 원본 엑셀을 저장한다.
- 같은 폴더의 `news.sqlite3`에 기사 메타데이터와 검증된 날짜·분류 체크포인트를 저장한다. 기사 식별자로 중복을 제거한다.
- 엑셀의 실제 행 수, 날짜 범위, 분류를 모두 확인한 뒤 기사와 체크포인트를 하나의 DB 트랜잭션으로 기록한다. 정규화 데이터에는 본문을 포함하지 않는다.
- 기존 경제 뉴스 파일은 체크섬과 내용을 검증해 재사용한다. 경제 수집 완료를 정치·국제의 완료로 처리하지 않는다.
- 전체 완료 시 `articles.jsonl`을 내보낸다. 수집 중 메타데이터는 SQLite에 축적한다.

같은 기간으로 다시 실행하면 검증한 구간을 건너뛴다. 동시에 두 수집기를 실행하면 파일 잠금이 중복 실행을 막는다. 로그와 실제 데이터, 브라우저 프로필은 Git 제외 경로에 둔다.

마지막 완료 거래일과 관계없이 뉴스 수집 종료일은 달력 날짜로 지정한다. 진행 중인 날짜까지 수집하면 이후 같은 날에 추가된 기사는 별도 증분 수집 범위로 관리해야 한다.

공식 Playwright 다운로드 이벤트를 받은 후 파일을 영구 경로로 저장한다. [Playwright 다운로드 문서](https://playwright.dev/python/docs/downloads)
