# 로컬 실행

Python 3.10 이상 권장. 패키지를 설치하면 `kg`, 설치하지 않아도 프로젝트 루트의 `python3 scripts/kg.py`로 같은 명령을 실행할 수 있다.

```bash
python3 scripts/kg.py --help
python3 scripts/kg.py graph --limit 20
python3 scripts/kg.py report
python3 scripts/kg.py prepare
python3 scripts/kg.py neo4j start
python3 scripts/kg.py neo4j import
python3 scripts/kg.py verify
```

graph/extract는 같은 파일럿 처리의 별칭이다. report는 검증·검토 표를 생성하며 파일럿을 한 번 재실행한다. 실제 데이터가 없는 clone에서는 offline 단위 테스트만 실행 가능하다. 예제 원문은 Git에 포함되지 않는다.

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 scripts/kg.py neo4j status
python3 scripts/kg.py neo4j stop
```

Mac에서 Java/Neo4j가 아직 없으면 `python3 scripts/kg.py install-macos`로 프로젝트 전용 ARM64 패키지를 준비한다. Linux/EC2에는 이 명령 대신 EC2 문서의 Compose를 사용한다. 설치한 바이너리와 PID·로그는 .runtime, DB는 data/neo4j, 암호는 .secrets에 위치한다.

Browser: http://localhost:7474/browser/ . 새 브라우저에서 암호가 필요하면 직접 `python3 scripts/kg.py neo4j credentials`를 실행한다. 출력에는 비밀 값이 있으므로 공유하지 않는다. 로그인 자동 시작 서비스는 등록하지 않는다.

API 키는 OPENDART_API_KEY 환경변수로만 제공한다. .env.local을 쓸 경우 셸에서 set -a / source / set +a로 명시적으로 불러온다. 설정 예제 TOML은 설명용이며 실제 설정은 config.py의 환경변수를 사용한다.

컬렉션 경로를 바꾸려면 KG_DATA_DIR과 KG_COLLECTION_ID를 설정한다. 출력과 런타임은 KG_ARTIFACT_DIR, KG_RUNTIME_DIR, KG_SECRETS_DIR로 분리 가능하다. 단계별 결과는 data/graph 아래에서 관리되며 해당 경로를 공유 저장소로 간주하지 않는다.
