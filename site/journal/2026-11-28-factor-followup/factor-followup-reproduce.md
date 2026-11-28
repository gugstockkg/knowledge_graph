# 한·미 팩터 후속 검증 재현

결과 계산은 EC2에서 실행하였다. 아래 명령은 런타임에 보관한 원본을 참조하며 거래 주문을 발행하지 않는다. Python 3.11 환경에서 실행한다. 전략별 결과는 달마다 새로 진입한 12·24개월 계좌를 재생한 값이다.

## 한국

[KR 시세와 원공시 수집](reproduction.zip)에 수집 버전과 입력 범위를 기록했다. 한국 실험은 가격수익률과 가정한 폐지 정산의 효과를 평가한다. 거래가 멈춘 포지션은 만기까지 남을 수 있으므로 만기 수익률은 순자산 평가 기준이다.

```bash
python3 scripts/kr_factor_extension.py   --input /var/lib/fintos-portfolio/kr-research-data/factor-closing-volume/panel/kr_market_monthly.csv   --out /var/lib/fintos-portfolio/kr-research-data/factor-closing-volume/results
```

`kr_factor_coverage.csv`는 월별 후보와 폐지 플래그, `kr_factor_cohorts.csv`는 12·24개월 각 계좌의 수익률, 낙폭, 폐지 이벤트, 관측 누락 평가 및 만기 미청산 잔고를 담는다.

## 미국

[SEC 원공시 수집](reproduction.zip)과 [과거 SPY 보유 공시 및 시세 수집](https://github.com/gugstockkg/knowledge_graph/tree/main/research/portfolio-exit)을 참조한다. 당시 SPY 보유 스냅샷의 종목을 현재 SEC 티커 지도에 일대일로 연결하고, 배당·분할 조정 월별 시세가 평가와 준비 기간 내내 있는 종목을 남긴다. 가치 점수는 해당 재무연도의 접수번호별 발행주식 수를 주식분할과 맞춰 계산한 시가총액을 사용한다. 원래 보유 스냅샷에 있더라도 종목코드 변경, 복수 주식 종류 또는 말소로 가격·식별자를 연결할 수 없는 종목은 제외될 수 있다. 결과는 달러 기준이다.

```bash
study=/var/lib/fintos-portfolio/2026-11-28
python3 scripts/us_factor_extension.py \
  --archive "$study/full-constituents" --sec "$study/us-pit" \
  --splits-cache "$study/us-factor-extension/splits" \
  --out "$study/us-factor-extension/replay"
```

[미국의 표본·주문 원장 필드와 검증 기록](reproduction.zip)

## 공개 포트폴리오

```bash
python3 scripts/french_factor_reference.py --out /var/lib/fintos-portfolio/2026-11-28/factors-pit/us-reference
python3 scripts/french_window_audit.py \
  --raw /var/lib/fintos-portfolio/2026-11-28/factors-pit/us-reference/raw \
  --out results/french_window_audit.csv
python3 scripts/run_public_factor_followup.py --out results/public-followup
python3 scripts/run_aqr_followup.py --out results/aqr-followup
```

원본 제공처가 이전 관측치를 갱신할 수 있다. 집계를 정확히 다시 계산할 때는 `results/`의 매니페스트에 있는 SHA-256과 내려받은 파일을 비교한다. [문헌별 실험과 건너뛴 사유](literature-followup.csv)
