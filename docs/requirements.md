# 📑 요구사항 명세서 (IndicLens)

## 1. 기능 요구사항 (FR)

| ID | 설명 | 우선순위 | 비고 |
|----|------|---------|------|
| FR-1 | 사용자 입력(심볼, 기간, 지표 파라미터)에 따른 백테스트 | High | SMA, EMA, RSI, MACD, BB |
| FR-2 | 성과 지표 계산 (총수익률, CAGR, MDD, Sharpe, 승률) | High | 대시보드 KPI 카드 |
| FR-3 | 파생지표(Funding/OI/롱숏/테이커)와 가격 수익률 상관분석 | High | Pearson, Spearman |
| FR-4 | 상관분석 시 시차(±N 구간) 지원 | Medium | 기본 ±12시간 |
| FR-5 | Top Traders 롱/숏 우세 현황 표시 | Medium | 계기판/스파크라인 |

---

## 2. 비기능 요구사항 (NFR)

| ID | 설명 | 우선순위 | 비고 |
|----|------|---------|------|
| NFR-1 | 대시보드 초기 로딩 3초 이내 (캐시 기준) | High | |
| NFR-2 | 실행/배포 재현성 보장 (`requirements.txt`, README) | High | |
| NFR-3 | 클라우드 배포 (Streamlit Cloud) | High | |

---

## 3. 데이터 요구사항

| 데이터명 | 보유기관 | 형태 | 양식 | 주기 | 수집방안 | 비고 |
|----------|----------|------|------|------|----------|------|
| Spot/Futures Klines (OHLCV) | Binance | JSON | 시계열(캔들) | 분/시/일 | `/api/v3/klines`, `/fapi/v1/klines` | 백테스트 기본 데이터 |
| Funding Rate History | Binance Futures | JSON | 시계열 | 8h 단위 | `/fapi/v1/fundingRate` | 가격 수익률과 상관 |
| Open Interest History | Binance Futures | JSON/CSV | 시계열 | 5m/15m/1h 등 | `/futures/data/openInterestHist` 또는 binance.vision | 최근 1개월 제한(공용 API) |
| Global Long/Short Account Ratio | Binance Futures | JSON | 시계열 | 5m/15m/1h/4h/1d | `/futures/data/globalLongShortAccountRatio` | 최근 30일 제한 |
| Top Traders Long/Short (Accounts/Positions) | Binance Futures | JSON | 시계열 | 5m/15m/1h/4h/1d | `/futures/data/topLongShortPositionRatio`, `/futures/data/topLongShortAccountRatio` | 현재 롱/숏 우세 현황 |
| Taker Buy/Sell Volume | Binance Futures | JSON | 시계열 | 5m/15m/1h/4h/1d | `/futures/data/takerBuySellVol` | 매수/매도 압력 프록시 |

---

## 4. 제약 및 고려사항
- Binance 파생 일부 히스토리 API는 **최근 30일 제한**  
- 장기 분석 필요 시 **binance.vision CSV 사용**
