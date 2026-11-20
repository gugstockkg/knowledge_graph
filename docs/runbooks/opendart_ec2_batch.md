# OpenDART EC2 일일 수집과 백필

대상: `fintos-dev-cpu`, `i-0e2f7ad78831dad56`, `ap-southeast-2`. Python 3.11 표준 라이브러리와 EC2의 AWS CLI를 사용한다. LLM 호출 없음.

## 배치와 데이터

- 한국 시간 매일 06:30(최대 60초 지연), 전날까지 수집. 최근 3일의 목록을 다시 확인해 늦게 반영된 공시를 보완한다. 마지막 완료 날짜부터 더 오래 누락된 날짜도 따라잡는다.
- 공시 목록은 날짜별 전 페이지, `last_reprt_at=N`. 회사·종목 제한 없이 API가 반환하는 전체 공시와 제공되는 원문을 수집한다. 접수번호 앞 8자리가 아닌 `rcept_dt`로 파티션한다.
- 원본 ZIP은 CRC/XML 존재를 확인하고 보존하며 XML을 별도로 풀지 않는다. JSONL에는 원본 메타데이터, 원본 키, SHA256, 수집 최초 관측시각을 기록한다. 관측시각을 공개시각으로 간주하지 않는다.
- `/var/lib/opendart`: ZIP·일별 목록·SQLite 상태·프로세스 잠금. 키는 `/etc/opendart/api.env`(root:root 0600)에서 systemd가 환경변수로 전달. Git·S3·명령행 인자에 키를 넣지 않는다.
- S3: `s3://fintos-dev-data-gugst5ck/raw/opendart/` 아래 `documents/partition_day=YYYY-MM-DD/<receipt>.zip`, `filings/partition_day=YYYY-MM-DD/filings.jsonl`, `_manifests/partition_day=YYYY-MM-DD/manifest.json`.
- 원문 미제공 013/014와 실패를 구분한다. 미제공은 7일 이후 재확인 가능한 상태로 보관. 완료일도 백필 재방문 시 TTL 만료를 확인한다. ZIP 업로드 실패 시 다음 실행은 로컬 ZIP을 재사용한다.
- 서버 내 요청은 하루(KST) 기본 12,000회, 실행당 1,000회/20분으로 제한. 일일/백필은 같은 잠금·예산을 공유. 020 응답은 다음 KST 날짜 00:05까지 모든 API 호출을 멈춘다. 같은 키를 쓰는 Mac 등 다른 기기의 호출은 서버 계수에 포함되지 않는다.
- 일시 실패·실행 예산 초과는 30분 뒤 재개. 010/011/012/901은 운영자 확인이 필요해 자동 재시작하지 않는다. 실패 구간을 완료 처리하지 않는다.
- EC2가 중지돼 있으면 timer도 실행되지 않는다. Persistent=true는 부팅 후 누락 실행을 보완할 뿐 EC2를 켜지는 않는다. CPU 320시간 예산을 위해 상시 가동을 전제하지 말고 별도 시작/중지 운영을 정해야 한다.

## 설치

```bash
sudo dnf install -y git python3.11
sudo git clone --branch codex/ec2-opendart-batch https://github.com/gugstockkg/knowledge_graph.git /opt/gug-knowledge-graph
sudo useradd --system --home-dir /var/lib/opendart --shell /sbin/nologin opendart
sudo install -d -m 0700 /etc/opendart
sudo install -d -o opendart -g opendart -m 0700 /var/lib/opendart
# 운영자가 안전한 입력 경로로 /etc/opendart/api.env 작성: OPENDART_API_KEY=실제키
# 명령행 인자·히스토리·Git에 키를 넣지 않는다.
sudo chmod 0600 /etc/opendart/api.env
sudo cp /opt/gug-knowledge-graph/infra/systemd/opendart-* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now opendart-daily.timer
sudo systemctl start --no-block opendart-daily.service
```

EC2 인스턴스 역할에 해당 S3 prefix의 PutObject 권한과 SSM 통신 권한이 필요하다. 이 배포는 IAM 역할·보안 그룹을 자동 확대하지 않는다.

## 운영 명령

```bash
sudo systemctl status opendart-daily.service --no-pager
sudo systemctl list-timers opendart-daily.timer --all --no-pager
sudo journalctl -u opendart-daily.service -n 30 --no-pager

# 기간 지정 백필. 기존 완료 데이터와 ZIP은 재사용한다. 일일 구간을 우선 처리한다.
sudo systemctl start --no-block opendart-backfill@2026-01-01_2026-11-18.service
sudo journalctl -u opendart-backfill@2026-01-01_2026-11-18.service -n 30 --no-pager

# 백필 취소: 데이터는 유지, 이 작업의 자동 재시작도 중단
sudo systemctl stop opendart-backfill@2026-01-01_2026-11-18.service

# 상태(키 불필요). 실행 중 잠금이면 잠깐 후 재시도한다.
sudo -u opendart env PYTHONPATH=/opt/gug-knowledge-graph/src /usr/bin/python3.11 -m knowledge_graph.ingestion.batch status
```

범위 CLI는 `python3.11 -m knowledge_graph.ingestion.batch backfill --start YYYY-MM-DD --end YYYY-MM-DD`로도 사용 가능하다. 환경변수/API 키를 지정하지 않은 직접 실행은 수집하지 않는다. 검증용은 별도 `--root`와 `--max-requests`를 사용한다. 오늘·미래 날짜를 완료일로 수집하지 않는다.

## 업데이트·장애 대응

실행 중 서비스를 중단한 후 `/opt/gug-knowledge-graph`에서 검토한 브랜치를 `sudo git pull --ff-only` 한다. systemd 파일이 바뀌면 복사와 daemon-reload 후 timer를 재시작한다. 스케줄과 재시작 상태를 확인한다. API 키는 별도 설정이므로 git pull로 교체되지 않는다.

020은 다른 기기에서도 같은 키를 쓰는지 확인한다. 012는 OpenDART 허용 IP에 EC2 출구 IP가 필요한지 확인한다. S3 오류는 인스턴스 역할·버킷 정책·암호화 키 권한을 점검한다. 디스크 여유 1GiB 미만이면 신규 다운로드를 중단하며 원본을 임의 삭제하지 않는다.
