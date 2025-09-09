# 📅 프로젝트 진행 일정 (IndicLens)

## Day 1. 주제 기획
- 분석 주제 확정 (IndicLens)
- Binance API 데이터 소스 조사
- 분석 구성 설계 (대시보드 탭, 지표, 성과 지표)
- 분석 아이디어 기획서 작성
- **산출물**: 분석 아이디어 기획서 (docs/analysis_idea.md)

---

## Day 2. 데이터 수집 & 초기 탐색
- Binance API 호출 함수 구현 (Klines, Funding, OI, 롱숏, 테이커)
- CSV 저장 및 캐싱 구조(data 폴더) 설정
- 초기 탐색 및 시각화
- **산출물**: `backtest/data.py`, `scripts/smoke_fetch.py`

---

## Day 3. 데이터 분석
- 지표 함수 구현 (SMA, EMA, RSI, MACD, Bollinger Bands)
- 사용자 조합 기반 시그널 생성 및 백테스트 엔진 개발
- 성과 지표 계산 (Total Return, CAGR, MDD, Sharpe, 승률)
- 파생 지표와 가격 수익률 상관 및 시차 상관 분석
- Streamlit 대시보드 **초안** 구현
- **산출물**: `backtest/indicators.py`, `backtest/signals.py`, `backtest/engine.py`, `backtest/evals.py`, `backtest/correlation.py`, `app.py` (초안)

---

## Day 4. 대시보드 완성 & 발표 준비
- 대시보드 UI 개선 및 완성
- 사용자 관점 흐름 정리 (커스텀 지표 → 백테스트 → 상관분석)
- 발표자료(PPT) 작성
- **산출물**: 완성된 Streamlit 앱, PPT 초안

---

## Day 5. 최종 발표
- 대시보드 시연 및 발표
- 팀원/강사 피드백 반영
- 프로젝트 회고 작성
- **산출물**: 최종 발표자료(PPT/PDF), GitHub 정리 (README, 실행 가이드)

---

## 📦 최종 산출물
- 분석 보고서 (PPT/PDF)
- 데이터 수집 및 분석 코드 (GitHub)
- Streamlit 대시보드

---

## 📈 프로젝트 수행 후 역량
- 분석 주제를 기획하고 결과를 시각적으로 전달하는 능력
- 파이썬을 활용한 데이터 수집·전처리·시각화 능력
- OpenAPI 활용 경험
- 개인 프로젝트 완수 경험 및 협업 역량 강화
