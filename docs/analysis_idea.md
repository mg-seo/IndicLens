# 📑 분석 아이디어 기획서

## 아이디어명  
**IndicLens – 커스텀 백테스트 + 파생지표 상관분석**

## 제안자  
서무경  

---

## 요약
사용자는 SMA, EMA, RSI, MACD, Bollinger Bands 등의 지표를 **GUI 조합 빌더**를 통해 원하는 조건으로 조합하고, 즉시 **백테스트** 성능을 검증할 수 있다.  
또한 바이낸스 선물 지표(펀딩비, 롱/숏 비율, OI, 테이커 매수/매도)와 **가격 수익률 간 시차 상관관계**를 분석하여 전략 인사이트를 제공한다.  
결과는 **Streamlit 대시보드**와 **PPT 보고서**로 제출한다.  

---

## 필요성 및 목적

### 1. 분석 배경
- 개인 투자자들은 지표/파라미터를 직관적으로 선택하는 경우가 많아 근거 기반 선택이 부족함  
- 크립토 특유의 파생 지표(펀딩비, 롱/숏 비율, OI)가 가격에 어떤 영향을 주는지 직관적으로 파악하기 어려움  

### 2. 문제점
- 지표별 효과 검증(백테스트)이 분산되어 있고 재현성이 낮음  
- 파생 지표와 가격의 정량적 관계(상관/시차)가 일관되게 제시되지 않음  

### 3. 추진 목적
- **커스텀 지표 조합 백테스트**로 전략의 효과를 즉시 검증  
- 펀딩비/롱숏/OI/테이커 볼륨과 가격 수익률의 **시차 상관 분석**으로 전략적 힌트 제공  

---

## 분석 목표

### 1. 분석 목표
- SMA/EMA/RSI/MACD/BB 기반 **커스텀 룰 조합 백테스트** 제공  
- **Funding Rate / Global Long-Short / Top Traders Long-Short / OI / Taker Buy-Sell**와  
  **가격 수익률** 간 **상관 및 시차 상관** 계산·시각화  

### 2. 활용 데이터
- Binance Spot/Futures **Klines(OHLCV)**  
- Binance Futures **Funding Rate**, **Open Interest(히스토리)**  
- Binance Futures **Global Long/Short Account Ratio**  
- Binance Futures **Top Traders Long/Short (Accounts/Positions)**  
- Binance Futures **Taker Buy/Sell Volume**  

### 3. 분석 방법
- 수집: REST API(`requests`) + 필요시 binance.vision CSV 병행  
- 전처리: 타임존(KST), 결측/중복 제거, 리샘플·정렬, 캐시(CSV)  
- 지표·시그널: UI 조합 → DSL/JSON 변환 → 백테스트 엔진에 적용  
- 백테스트: 수수료·슬리피지 반영, 전량매수/전량청산(롱 온리)  
- 성과 지표: Total Return, CAGR, MDD, Sharpe, 승률  
- 상관 분석: Pearson/Spearman, **시차(lead/lag) 상관** ±N 구간, 시각화  

### 4. 비고 (예상 문제점 및 고려사항 / 대체 아이디어)
- Binance 파생 **일부 히스토리 API는 최근 30일 제한** → 장기 분석은  
  - (대안) **binance.vision CSV 사용**  

---

## 활용 데이터 상세

| 데이터명 | 보유기관 | 형태 | 양식 | 주기 | 수집방안 | 비고 |
|---|---|---|---|---|---|---|
| Spot/Futures Klines (OHLCV) | Binance | JSON | 시계열(캔들) | 분/시/일 | `/api/v3/klines`, `/fapi/v1/klines` | 백테스트 기본 데이터 |
| Funding Rate History | Binance Futures | JSON | 시계열 | 8h 단위 | `/fapi/v1/fundingRate` | 가격 수익률과 상관 |
| Open Interest History | Binance Futures | JSON/CSV | 시계열 | 5m/15m/1h 등 | `/futures/data/openInterestHist` 또는 binance.vision | 최근 1개월 제한(공용 API) |
| Global Long/Short Account Ratio | Binance Futures | JSON | 시계열 | 5m/15m/1h/4h/1d | `/futures/data/globalLongShortAccountRatio` | 최근 30일 제한 |
| Top Traders Long/Short (Accounts/Positions) | Binance Futures | JSON | 시계열 | 5m/15m/1h/4h/1d | `/futures/data/topLongShortPositionRatio`, `/futures/data/topLongShortAccountRatio` | 현재 롱/숏 우세 현황 |
| Taker Buy/Sell Volume | Binance Futures | JSON | 시계열 | 5m/15m/1h/4h/1d | `/futures/data/takerBuySellVol` | 매수/매도 압력 프록시 |

---

## 기대효과

- **투자자 관점**: 다양한 기술적 지표와 파생 지표를 활용한 전략 효과를 정량적으로 검증해, 개인 투자자들이 **근거 기반 투자 의사결정**을 할 수 있도록 도움을 줄 수 있다.  
- **시장 관점**: 펀딩비·롱/숏 비율·OI·테이커 볼륨 등 파생 지표와 가격의 상관관계를 공개적으로 분석하여, 크립토 시장의 **투명성 제고** 및 **투자 행태 이해**에 기여한다.
