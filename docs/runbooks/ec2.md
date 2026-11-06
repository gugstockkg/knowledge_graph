# EC2에서 pull 후 사용

대상은 승인된 CPU용 m6i.xlarge(4 vCPU / 16GiB)이다. 코드만 Git으로 배포하고 원문·파생 데이터·Neo4j DB는 EBS의 별도 경로에 둔다. 이 문서는 배포 준비 절차이며 실제 EC2 기동은 아직 검증하지 않았다.

## 최초 준비

Python 3.10 이상과 Docker Compose 플러그인을 준비하고 저장소를 clone한다. Mac의 .runtime 또는 실행 중 DB 디렉터리를 서버에 복사하지 않는다. 설치할 때 공식 배포처를 사용한다.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
cp .env.example .env.local
chmod 600 .env.local
```

.env.local을 로컬 편집하여 OPENDART_API_KEY, NEO4J_PASSWORD를 넣는다. KG_DATA_DIR은 EBS 영속 경로(예: /srv/knowledge_graph/data), KG_RUNTIME_DIR은 서버의 쓰기 가능한 별도 경로로 지정한다. 현재 사용자와 컨테이너가 해당 경로에 쓸 수 있도록 권한을 설정한다. 예제 파일에 실제 키를 입력하지 않는다.

```bash
set -a
. ./.env.local
set +a
mkdir -p "$KG_DATA_DIR/neo4j" "$KG_DATA_DIR/graph/ownership_pilot_v01/import"
```

기존 데이터가 필요하면 Git이 아닌 별도 전송/S3로 data/raw/opendart를 EBS로 옮기고 체크섬을 검증한다. 인증정보와 과거 로그를 데이터 전송에 섞지 않는다. 초기 파일럿 입력에는 20261001_20261105 컬렉션이 필요하다.

## 실행

```bash
kg collect --start 2026-10-01 --end 2026-11-05
kg graph --limit 20
kg prepare
docker compose --env-file .env.local -f infra/compose.yaml up -d
kg neo4j wait
kg neo4j import
kg verify
```

이미 수집된 원문이 있다면 collect는 생략한다. collect는 캐시를 재사용하므로 한 시간 단위 최신화 서비스로 간주하면 안 된다. 현재 extract/graph는 고정된 5개 기업·최대 20건 파일럿이며 전체 공시 추출 명령이 아니다.

compose 이미지는 Community 2026.10.1로 고정된다. 컨테이너는 내부에서 수신하되 호스트에는 localhost 7474/7687만 바인딩된다. DB가 존재하면 NEO4J_AUTH 값만 바꿔도 기존 DB 암호가 바뀌지 않는다. 기존 인증정보와 일치시켜야 한다.

## Mac에서 접속

SSH를 사용하는 경우 로컬 7474/7687이 이미 사용 중이면 먼저 로컬 서버를 종료하거나 다른 로컬 포트로 터널을 구성한다.

```bash
ssh -L 7474:127.0.0.1:7474 -L 7687:127.0.0.1:7687 EC2_USER@EC2_HOST
```

브라우저에서 http://localhost:7474/browser/ 로 접속한다. EC2 보안그룹에 DB 포트를 인터넷 공개할 필요는 없다. SSM 사용 시에도 두 포트를 로컬로 전달하는 구성을 사용한다.

## 갱신·종료

```bash
git pull --ff-only
python -m pip install -e .
python -m unittest discover -s tests -v
docker compose --env-file .env.local -f infra/compose.yaml stop
```

코드 pull은 DB나 원문을 초기화하지 않는다. 이미지 버전 변경 시에는 백업·복구 테스트 후 명시적으로 docker compose pull/up을 수행한다. `down -v`나 data 디렉터리 삭제를 일반 갱신 절차에 넣지 않는다. EC2 사용시간 320시간과 스토리지 예산은 별도 관리한다.
