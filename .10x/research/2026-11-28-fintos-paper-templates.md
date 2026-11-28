Status: done
Created: 2026-11-28
Updated: 2026-11-28

# FINTOS 최근 논문 원문 구성 비교

## 조사 범위

FINTOS 읽기 인덱스에서 2025년을 포함해 2026년까지의 62개 항목을 확인했다. 업데이트 대응표와 PDF 경로, 기존 퀀트 인덱스, Stock + KG의 Zotero 키와 제목을 사용해 로컬 PDF 60편을 연결했다. 최근 문헌 갱신 자료 44편, Stock + KG 폴더에서 매칭된 15편, 기존 퀀트 보관함에서 추가로 매칭된 1편이다. 60개 파일의 SHA-256은 서로 달랐다. Q162와 Q165는 대응되는 로컬 PDF를 확인하지 못했다.

판본 연도는 FINTOS 인덱스를 따랐다. 학회 발표 연도, 저자판 작성 연도, 저널 출판 연도가 서로 다를 수 있다. Q194 로컬 PDF에는 도서관 표제와 다른 *Agentic Graph Retrieval-Augmented Generation for Auditable Commercial Registry Analysis*가 표시되어, 로컬 판본의 구성을 기록했다. 페이지는 PDF 파일 첫 장부터 센 위치이며, 주요 항목이 나오는 구간 또는 시작 지점이다. 목차·절 제목·표 캡션 중심의 비교이며, 일부 PDF의 인코딩과 다단 편집 때문에 세부 항목의 유무를 일괄 집계하지 않았다. 표의 유형은 출판처별 공식 분류 대신 논문의 주된 입증 대상에 따라 지정했다.

## 공통 흐름과 증거의 차이

공통 흐름은 연구 질문과 기여 → 데이터 또는 문제 정의 → 방법 → 결과 → 해석과 적용 범위다. 관련 연구는 별도 절, 서론, 실험 뒤에 배치된다. TRACE는 방법 앞에, DeepFund와 BacktestBench는 결과 뒤에 둔다. *Do Individual Investors Ignore Transaction Costs?*는 가설·데이터·주 분석·강건성을 독립 절로 두고, *Optimal Portfolio Choice With Cross-Impact Propagators*는 모형·정리·수치 예시를 먼저 보인 뒤 증명을 전개한다.

| 유형 | 방법에서 명시하는 내용 | 결과에서 입증하는 내용 | 상세 자료 |
|---|---|---|---|
| 가격결정·시장 실증 | 경제 가설, 표본, 변수, 제도, 추정 및 식별 | 계수와 경제적 크기, 포트폴리오 정렬, 기간·시장·자료 판본·정의 변경에 대한 강건성 | 변수 정의, 표본 필터, 추가 회귀 |
| 배분·최적화 | 목적함수, 비중 제약, 신호에서 비중으로의 변환, 거래 마찰과 비교군 | 비용 전후 성과, 회전율, 위험. 알고리즘 논문은 수렴이나 목적함수 값 | 알고리즘, 증명, 제약·비용 민감도 |
| 텍스트·그래프 예측 | 시간 순서, 목표 변수, 관계나 이벤트 표현, 모델, 훈련 설정 | 예측력, 단순 기준 대비 증분, 관계 정보·모듈 제거 효과. 일부는 투자 성과를 별도로 제시 | 프롬프트, 특징, 하이퍼파라미터, 근거 경로 |
| 데이터·벤치마크 | 표본·태스크 구축, 시간 경계, 판정 기준, 평가 지표 | 기준선 순위, 실패 사례, 데이터 오염·판정 안정성·재표집 영향을 검토 | 데이터 스키마, 채점 규칙, 추가 실험 |
| KG·에이전트 시스템 | 스키마, 데이터 출처, 처리 흐름, 도구 또는 역할 | 추출 품질, 질의 결과의 근거, 사람이 검증한 사례, 구성별 차이 | 질의 예시, 역할·호출 설정, 근거 추적 |

## FINTOS 집필 템플릿

1. **초록과 서론**에 한 가지 핵심 비교, 기준선, 주 지표의 차이와 불확실성, 적용 범위를 명시한다. 관련 연구는 선행 설계·재현한 부분·FINTOS에서 새로 묻는 질문을 연결한다.
2. **데이터**에는 시장·종목군·제외 규칙·표본 기간·관측 단위·공시 및 관계 공개 시점·라벨 시점을 표로 둔다. 예측과 운용의 경우 의사결정·주문·체결 시점을 함께 제시한다.
3. **방법**에는 기준선과 추가 정보의 정확한 차이, 시간순 학습·검증·평가, 동일 비교 조건, 지표 산식을 적는다. 운용 연구는 비중·현금·거래비용·회전율 규칙을, KG 연구는 관계 유형·방향·유효기간과 근거 추적을 추가한다.
4. **결과**의 첫 표에는 같은 표본의 기준선, 비교군, 차이와 불확실성, 표본 수를 넣는다. 이어서 연구 유형에 맞춰 관계 제거, 비용·체결 민감도, 기간별 성과 또는 근거 검증 결과를 제시한다.
5. **논의와 재현 부록**에 실패 조건, 자료와 모델의 적용 범위, 실행 설정, 원문·코드·결과표 위치를 남긴다. 공시 그래프 예측의 정확도, 실제 전략의 비용 차감 성과, KG 추출의 품질은 각각 해당 결과표에서 해석한다.

## 논문별 원문 구조

### 배분·최적화

| ID·원문 | 연도 | 원문에 들어가는 내용과 배치 | PDF 쪽 |
|---|---:|---|---|
| [Q088 Machine Learning and the Implementable Efficient Frontier](https://research-api.cbs.dk/ws/portalfiles/portal/81132615/theis_ingerslev_jensen_et_al_machine_learning_and_the_implementable_efficient_frontier_publishersversion.pdf) | 2026 | 거래 마찰을 포함한 효율적 투자선 정의 → 해법 → 표준 비교군 → 데이터와 실증 성과 | 10–31 |
| [Q196 Optimal Factor Timing in a High-Dimensional Setting](https://bpb-us-w2.wpmucdn.com/voices.uchicago.edu/dist/f/575/files/2025/01/FactorDynamics_revision.pdf) | 2025 | 팩터·예측변수 목록 → 표본 밖 포트폴리오 수익률 → 회전율과 비용 차감 | 14–26 |
| [Q202 Universal Portfolio Shrinkage](https://www.nber.org/system/files/working_papers/w32004/w32004.pdf) | 2026 | 이차 모멘트 축소 → UPSA 구성 → 실증 → 경제적 설명과 시뮬레이션 | 9–39 |
| [Q210 Machine Learning Meets Markowitz](https://www.nber.org/system/files/working_papers/w34861/w34861.pdf) | 2026 | 기존 포트폴리오 이론과 ML의 접점 → 방법 → 실증 응용 | 8–48 |
| [Q219 STABLE: Shift-Tolerant Allocation via Black-Litterman Using Conditional Diffusion Estimates](https://proceedings.iclr.cc/paper_files/paper/2026/file/4d4dbc5c955c5d273eed12d565335068-Paper-Conference.pdf) | 2026 | 확산 기반 추정과 Black–Litterman 배분 → 시장별 성과 → 모듈 제거 | 3–24 |
| [Q223 Learning to Manage Investment Portfolios beyond Simple Utility Functions](https://arxiv.org/pdf/2510.26165) | 2025 | 운용 의사결정 학습 → 무거래·무작위·팩터 기준선 → 실험 비교 | 2–6 |
| [Q226 Decision-focused Sparse Tangent Portfolio Optimization](https://raw.githubusercontent.com/mlresearch/v306/main/assets/jeon26a/jeon26a.pdf) | 2026 | 희소 접점 포트폴리오 문제 → 의사결정 중심 학습 → 기존 예측·최적화법 비교 | 3–7 |
| [Q227 A Linearly Convergent Proximal Subgradient Algorithm for Sparse Portfolio Optimization with Transaction Cost](https://raw.githubusercontent.com/mlresearch/v306/main/assets/yao26s/yao26s.pdf) | 2026 | 거래비용이 있는 희소 최적화 문제 → 알고리즘과 수렴 근거 → 수치 실험 | 3–8 |
| [Q228 Online Portfolio Selection with ML Predictions](https://proceedings.neurips.cc/paper_files/paper/2025/file/76981cb7a06b5ad53639f5bbe9924388-Paper-Conference.pdf) | 2025 | 예측 없는 기준과 예측 순위 입력 → 최악·최선 성능 보장 → 실증 | 4–10 |
| [Q235 Optimal Portfolio Choice With Cross‐Impact Propagators](https://arxiv.org/pdf/2403.10273v2) | 2026 | 교차 가격충격 모형과 해 → 수치 예시 → 확률적 적분방정식과 증명 | 4–34 |
| [Q236 Randomized signature methods in optimal portfolio selection](https://arxiv.org/pdf/2312.16448v1) | 2025 | 시그니처 기반 최적화 → 거래비용 → 벤치마크와 데이터 → 결과 | 5–27 |

### 텍스트·그래프 예측

| ID·원문 | 연도 | 원문에 들어가는 내용과 배치 | PDF 쪽 |
|---|---:|---|---|
| [Q094 Can ChatGPT forecast stock price movements? Return predictability and large language models](https://arxiv.org/pdf/2304.07619) | 2026 | 제도와 정보처리 가설 → 표본과 프롬프트 → 모델별 비교 → 가격 반응 속도 | 8–35 |
| [Q168 TRACE: Temporal Rule-Anchored Chain-of-Evidence on Knowledge Graphs for Interpretable Stock Movement Prediction](https://arxiv.org/pdf/2603.12500) | 2026 | 시간 규칙과 근거 경로 → 평가 표본 → 방향 예측 비교 → 구성요소 제거 | 2–9 |
| [Q170 Temporal Relational Reasoning of Large Language Models for Detecting Stock Portfolio Crashes](https://arxiv.org/pdf/2410.17266) | 2025 | 시간 관계 추론 문제 → 포트폴리오 급락 실험 → 결과 → 후속 과제 | 3–8 |
| [Q171 StockMem: An Event-Reflection Memory Framework for Stock Forecasting](https://arxiv.org/pdf/2512.02720) | 2025 | 이벤트와 반성 메모리 설계 → 예측 실험 → 결론 | 4–8 |
| [Q178 LLM-Enhanced Dynamic Financial Knowledge Graphs for Cross-Entity Signal Propagation and alpha discovery](https://arxiv.org/pdf/2607.10932) | 2026 | 전파 메커니즘 → 계량 가설 → 시뮬레이션 → Russell 1000 적용 설계와 보정 평가 → 한계 | 7–29 |
| [Q184 FinRipple: Aligning Large Language Models with Financial Market for Event Ripple Effect Awareness](https://arxiv.org/pdf/2505.23826) | 2025 | 이벤트의 파급 영향 모델 → 예측 평가와 장중 포트폴리오 규칙 → 한계 | 3–9 |
| [Q190 FactorGCL: A Hypergraph-Based Factor Model with Temporal Residual Contrastive Learning for Stock Returns Prediction](https://ojs.aaai.org/index.php/AAAI/article/view/31993) | 2025 | 하이퍼그래프 팩터 모형 → 예측 비교 → 제거 실험 → 투자 시뮬레이션 | 6–7 |
| [Q193 Beyond sentiment: knowledge graph-driven financial market forecasting with large language models-extracted enterprise relations and adaptive residual networks](https://doi.org/10.1007/s41060-026-01064-2) | 2026 | 기업 관계 추출 프롬프트와 잔차망 → 종목 선택과 하이퍼파라미터 → 예측 결과표 | 5–15 |
| [Q204 A Financial Brain Scan of the LLM](https://arxiv.org/pdf/2508.21285v4) | 2026 | LLM 진단 방법 → 거시 경제적 성향 측정 → 시뮬레이션과 조정 실험 | 8–31 |
| [Q220 Learning Universal Multi-level Market Irrationality Factors to Improve Stock Return Forecasting](https://arxiv.org/pdf/2502.04737) | 2025 | 개별·시장 수준 비합리성 팩터 → 예측 모형·훈련 → 실험 → 관련 연구 | 2–9 |
| [Q221 Regime-Aware Interpretable Ranking for Sector Rotation](https://arxiv.org/pdf/2610.26456) | 2026 | 국면 인지 섹터 순위 방법 → 실험 설정 → 결과 | 3–8 |
| [Q230 Attention-based Graph Neural Networks in Firm CDS Prediction](https://www.belindachenchen.com/uploads/GNN/Attention_based_Graph_Neural_Networks_in_Firm_CDS_Prediction.pdf) | 2025 | 기업 CDS 예측 개념 → 그래프 모델과 방법 → 실증 결과 | 6–30 |
| [Q237 Deep limit order book forecasting: a microstructural guide](https://discovery.ucl.ac.uk/id/eprint/10218102/1/Deep%20limit%20order%20book%20forecasting%20a%20microstructural%20guide.pdf) | 2025 | 호가장 데이터 → 방법과 미시구조 가정 → 예측 결과 → 향후 과제 | 5–22 |

### 데이터·벤치마크

| ID·원문 | 연도 | 원문에 들어가는 내용과 배치 | PDF 쪽 |
|---|---:|---|---|
| [Q175 Predictive AI with External Knowledge Infusion: Datasets and Benchmarks for Stock Markets](https://arxiv.org/pdf/2504.20058) | 2026 | 시간 KG 구축 → 학습 기준선 → 실험 설정 → 제거 실험과 반사실 설명 | 3–9 |
| [Q186 FinReflectKG -- HalluBench: GraphRAG Hallucination Benchmark for Financial Question Answering Systems](https://arxiv.org/pdf/2603.20252) | 2026 | 환각 검출기와 삼중항 입력 → 검증된 문답 표본 → 분류 성능과 KG 품질 민감도 | 4–10 |
| [Q187 FinReflectKG -- EvalBench: Benchmarking Financial KG with Multi-Dimensional Evaluation](https://arxiv.org/pdf/2510.05710) | 2026 | 다차원 평가 방법 → 평가자 비교와 안정성 → 결과 | 4–6 |
| [Q205 AI-Powered (Finance) Scholarship](https://www.nber.org/system/files/working_papers/w33363/w33363.pdf) | 2025 | 연구 아이디어 생성·평가 절차 → 결과 → 연구 생산 과정에 대한 논의 | 8–19 |
| [Q207 DatedGPT: Preventing Lookahead Bias in Large Language Models with Time-Aware Pretraining](https://arxiv.org/pdf/2603.11838) | 2026 | 시점별 학습 데이터 구축 → 시간 인지 사전학습 → 평가 결과 | 2–4 |
| [Q213 Persistent Anomalies and Nonstandard Sharpe Ratios](https://www.paris-december.eu/sites/default/files/papers/2025/coqueret-perignon-oct-2025.pdf) | 2026 | 복수 연구 설계 → 상관된 결과의 문제 → 경로별 재표집 → 이상현상 대규모 평가 | 5–24 |
| [Q216 The Memorization Problem: Can We Trust LLMs’ Economic Forecasts?](https://arxiv.org/pdf/2504.14765) | 2026 | 암기 문제의 정식화 → 식별·평가 방법 → 데이터 → 결과 | 9–58 |
| [Q218 Time Travel is Cheating: Going Live with DeepFund for Real-Time Fund Investment Benchmarking](https://proceedings.neurips.cc/paper_files/paper/2025/file/f37b0e09b90e9a6833aacf5768362b54-Paper-Datasets_and_Benchmarks_Track.pdf) | 2025 | 라이브 투자 환경 → LLM·시점 설정표 → 실시간 성과표 → 한계와 체크리스트 | 2–17 |
| [Q222 FinDER: Financial Dataset for Question Answering and Evaluating Retrieval-Augmented Generation](https://arxiv.org/pdf/2504.15800v3) | 2025 | 금융 QA 데이터 구축 → 검색·답변 평가 설정 → 비교 결과 | 3–10 |
| [Q224 When Agents Trade: Live Multi-Market Trading Arena for LLM Agents](https://arxiv.org/pdf/2510.11695v2) | 2026 | 실시간 다중시장 투자 환경 → 실험 설정 → 성과 → 규칙과 채점 | 3–10 |
| [Q225 BacktestBench: Benchmarking Large Language Models for Automated Quantitative Strategy Backtesting](https://arxiv.org/pdf/2605.17937) | 2026 | 과제 구성 → AutoBacktest → 실험과 제거 비교 → DB 스키마와 프롬프트 부록 | 2–24 |
| [Q231 High-Throughput Asset Pricing](https://arxiv.org/pdf/2311.10685) | 2025 | 대량 탐색 설계 → 데이터 마이닝 성과 → 경험적 베이즈 → 거짓발견 통제 비교 | 5–17 |
| [Q233 The Uncertainty of Machine Learning Predictions in Asset Pricing](https://arxiv.org/pdf/2503.00549) | 2025 | ML 예측 신뢰구간 추정 → 응용 → 실증 검증 | 6–40 |

### KG·에이전트 시스템

| ID·원문 | 연도 | 원문에 들어가는 내용과 배치 | PDF 쪽 |
|---|---:|---|---|
| [Q180 Knowledge Graph Construction for Stock Markets with LLM-Based Explainable Reasoning](https://arxiv.org/pdf/2601.11528) | 2025 | 시장 KG 구축과 질의 방식 → 기업 사례 및 설명 | 2–5 |
| [Q183 FundaPod: A Multi-Persona Agent Pod Platform with Knowledge Graph Memory for AI-Assisted Fundamental Investment Research](https://arxiv.org/pdf/2605.27864) | 2026 | 리서치 설계 원칙 → 에이전트 구조와 메모리 → 연구 참여 사례 → 한계 논의 | 6–18 |
| [Q185 FinReflectKG: Agentic Construction and Evaluation of Financial Knowledge Graphs](https://dl.acm.org/doi/10.1145/3768292.3770363) | 2025 | 금융 KG 스키마 → 구성 파이프라인 → 평가 → 논의 | 2–7 |
| [Q188 FinKario: Event-Enhanced Automated Construction of Financial Knowledge Graph](https://arxiv.org/pdf/2508.00961) | 2025 | 사건 강화 KG 구축 → 추출·구축 실험 → 결론 | 3–9 |
| [Q194 Agentic GraphRAG: Navigating Unstructured Financial Data with Collaborative AI](https://arxiv.org/pdf/2605.18770) | 2026 | 상업등기 데이터 → 질의 시스템과 호출 구성 → 추출 수동 검증 → 질문군별 구조 비교 | 6–25 |
| [Q229 Trade in Minutes! Rationality-Driven Agentic System for Quantitative Financial Trading](https://proceedings.iclr.cc/paper_files/paper/2026/file/2db9fbe4f34340cb928c653a6333084b-Paper-Conference.pdf) | 2026 | 정책·최적화·배포 단계와 주문 규칙 → 실험 → 관련 연구와 결론 | 2–10 |

### 가격결정·시장 실증

| ID·원문 | 연도 | 원문에 들어가는 내용과 배치 | PDF 쪽 |
|---|---:|---|---|
| [Q197 Short versus long-run demand elasticities in asset pricing](https://www.hbs.edu/ris/Publication%20Files/26-070_4d9218f6-e1d0-439b-a233-d91503eba0f6.pdf) | 2026 | 동태 수요탄력성 이론 → 변수 구축 → 축약형 증거 → 구조 추정 → 반전 지표와 응용 | 9–27 |
| [Q198 Do Individual Investors Ignore Transaction Costs?](https://www.cambridge.org/core/services/aop-cambridge-core/content/view/CD89C67B3D931D0BE4123C3BFFE6803B/S0022109025101695a.pdf/do-individual-investors-ignore-transaction-costs.pdf) | 2025 | 가설 → 거래 자료 → 비용과 보유 기간 → 강건성 | 5–29 |
| [Q199 Rewriting CRSP’s History: Impact of Altered Monthly Returns on Asset Pricing](https://jfqa.org/wp-content/uploads/2026/02/26501_Rewriting_CRSP_History.pdf) | 2026 | CRSP 판본 변경 → 월수익률 차이 → 프리미엄 차이 → 해석 | 10–37 |
| [Q200 Trended Momentum](https://www.cambridge.org/core/services/aop-cambridge-core/content/view/406C5E422D79B42AE16618F062A21A4B/S0022109026103275a.pdf/trended-momentum.pdf) | 2026 | 추세 명료도 개념과 산식 → 모멘텀 포트폴리오 결과 | 5–8 |
| [Q201 Alpha Go Everywhere: Machine Learning and International Stock Returns](https://cityuhkfintech.com/wp-content/uploads/2022/04/submission_94.pdf) | 2025 | 학습 모형 소개 → 추정 방법 → 미국 종목 예측 → 국제시장 검증 | 8–37 |
| [Q203 A Bound on Price Impact and Disagreement](https://memento.epfl.ch/public/upload/files/vanderBeckpaper.pdf) | 2026 | 가격충격 이론 → 데이터와 관측 사실 → 상한 추정 → 이벤트 밖 적용 | 7–35 |
| [Q206 Causal Inference for Asset Pricing](https://www.paulhuebner.com/_files/ugd/3d316e_ae78d3a55704491ba906c427e6d0e6c2.pdf) | 2025 | 가격결정의 인과 문제 → 자산 수요 모형과 추정 → 가격충격과 회사채 응용 | 7–45 |
| [Q208 Equity Valuation Without DCF](https://iksa.or.kr/file/download/11833) | 2025 | 할인 알파 기반 가치평가 → 데이터와 변수 → 종목 펀더멘털 가치 추정 | 7–20 |
| [Q209 Haven’t We Seen This Before? Return Predictions from 200 Years of News](https://fraconference.com/wp-content/uploads/ninja-forms/2/chen_2025-07-03_qd32l.pdf) | 2025 | 역사 뉴스의 측정 → 주식시장 예측 → 위험과 거시 예측 | 8–32 |
| [Q211 Mimicking Finance](https://chelseayao.com/static/file/Cohen_Lu_Nguyen_WP25_Mimicking%20Finance.pdf) | 2026 | 이론 → 펀드·종목 데이터와 ML → 정밀도의 동학 → 펀드 수익 예측 | 7–35 |
| [Q212 News Consumption in the Wild](https://leeds-faculty.colorado.edu/garcia/News_Consumption_in_the_Wild_20260201.pdf) | 2026 | 뉴스 소비 자료 → 행태의 실증 패턴 → 결론 | 7–24 |
| [Q214 Stocks for the Long Run or Liquidity? Tax Data Evidence and Portfolio Choice Implications](https://patrick-adams.com/files/papers/PatrickAdams_JMP_Latest.pdf) | 2026 | 가계 대차대조표 → 행정 세금 자료 → 저축 행태 분석과 배분 함의 | 10–22 |
| [Q215 The Hidden Cost of Stock Market Concentration: When Funds Hit Regulatory Limits](https://www.sikorskaya.net/files/Pastor_Sikorskaya_Wang_2025.pdf) | 2026 | 규제 배경 → 규제 구속 여부 → 펀드 대응 → 성과와 수익 예측 → 능동·수동 구분 | 8–39 |
| [Q217 The Unintended Consequences of Rebalancing](https://www.nber.org/system/files/working_papers/w33554/revisions/w33554.rev0.pdf) | 2025 | 리밸런싱 압력 측정 → 신호 검증 → 선행 매매 시뮬레이션과 해석 | 7–39 |
| [Q232 Machine Forecast Disagreement](https://www.nber.org/system/files/working_papers/w31583/w31583.pdf) | 2025 | 모형 간 예측 불일치 정의 → 데이터·변수 → 실증과 강건성 → 예측력의 원천 | 8–38 |
| [Q234 The Many Facets of Stock Momentum: Distinguishing Factor and Stock Components](https://www.quoniam.com/wp-content/uploads/2025/10/The-Many-Facets-of-Stock-Momentum.pdf) | 2025 | 종목·팩터 모멘텀 분해 → 팩터 적재·스패닝 → 강건성 및 시변 노출 | 8–22 |
| [Q238 Noisy factors? The retroactive impact of methodological changes on the Fama–French factors](https://fnce.wharton.upenn.edu/wp-content/uploads/2021/10/AdrianaRobertsonNoisyFactors.pdf) | 2026 | 팩터 개정 전후 자료 → 주식·펀드 결과 변화 → 개정 품질과 권고 | 8–29 |
