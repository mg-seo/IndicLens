# 🛠️ 기술 스택 (IndicLens)

## 언어/런타임
- Python 3.13+

## 주요 라이브러리
- **데이터 수집**: `requests`
- **데이터 분석**: `pandas`, `numpy`, `scipy`
- **대시보드/시각화**: `streamlit`, `matplotlib`, `seaborn`

## 개발 도구
- IDE: PyCharm
- 형상 관리: Git + GitHub
- 협업/문서화: Markdown (`docs/`), Google Drive/Docs (보조)

## 운영 환경
- **Streamlit Cloud 배포 (필수)**
  - 실행: `streamlit run app.py`
  - 배포: GitHub 연동 후 Streamlit Cloud 자동 빌드

## 설정/환경 변수 (예시)
```env
TZ=Asia/Seoul
CACHE_DIR=./data
BINANCE_BASE=https://api.binance.com
BINANCE_FUTURES_BASE=https://fapi.binance.com
