from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import streamlit as st

# ── 옵션 ─────────────────────────────────────────────────────────────────────
_SYMBOLS = ["BTCUSDT", "ETHUSDT"]
_INTERVALS = ["15m", "1h", "4h", "1d"]
_PERIOD_OPTIONS = {"1개월": 1, "3개월": 3, "6개월": 6, "12개월": 12}
# 상관분석 기간(고정) — UI만 셀렉트박스 형태로 노출하되 수정 불가
_CORR_PERIOD_OPTIONS = {"1개월": 1}

# 바이낸스 USDⓂ 선물 기본 수수료(대부분 계정의 디폴트)
#   - 테이커(시장가): 0.04%
#   - 메이커(지정가): 0.02%
_FUTURES_FEE_PRESETS = {
    "테이커(시장가) 0.04%": 0.04,  # percent
    "메이커(지정가) 0.02%": 0.02,  # percent
}
_DEFAULT_FEE_LABEL = "테이커(시장가) 0.04%"


@dataclass
class Inputs:
    symbol: str
    interval: str
    months: int
    fee: float        # 편도 수수료 (비율, 예: 0.0004 == 0.04%)
    slippage: float   # 편도 슬리피지 (비율)
    corr_months: int  # 상관분석 기간(월)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def sidebar_inputs() -> Inputs:
    st.sidebar.header("⚙️ 기본 설정")

    symbol = st.sidebar.selectbox(
        "심볼",
        _SYMBOLS,
        index=0,
        help="테스트할 선물 심볼. 우선 BTC/ETH만 노출.",
    )

    interval = st.sidebar.selectbox(
        "봉 간격",
        _INTERVALS,
        index=1,
        help="캔들 주기 (15m, 1h, 4h, 1d)",
    )

    period_label = st.sidebar.selectbox(
        "백테스트 기간",
        list(_PERIOD_OPTIONS.keys()),
        index=1,
        help="과거 데이터의 길이. 1~12개월 중 선택.",
    )
    months = _PERIOD_OPTIONS[period_label]

    # 상관분석 기간 — 선택 UI는 있지만 disabled (보기 일관성 목적)
    corr_label = st.sidebar.selectbox(
        "상관분석 기간",
        list(_CORR_PERIOD_OPTIONS.keys()),
        index=0,
        disabled=True,
        help="바이낸스 공개 파생지표 API가 보통 최근 30일만 제공하기 때문에 1개월로 고정.",
    )
    corr_months = _CORR_PERIOD_OPTIONS[corr_label]

    st.sidebar.divider()
    st.sidebar.subheader("💸 체결 비용")

    # 수수료는 프리셋(퍼센트)로 선택 → 내부적으로 비율로 변환
    fee_label = st.sidebar.radio(
        "수수료 (편도)",
        list(_FUTURES_FEE_PRESETS.keys()),
        index=list(_FUTURES_FEE_PRESETS.keys()).index(_DEFAULT_FEE_LABEL),
        help="바이낸스 USDⓂ 선물 기본 수수료 기준. VIP/BNB 할인은 '고급 설정'에서 조정 가능.",
        horizontal=False,
    )
    fee_percent = _FUTURES_FEE_PRESETS[fee_label]

    # 슬리피지는 퍼센트 입력 (기본 0.5%) — 0.25% 단위, 소수점 둘째자리 표시
    slippage_percent = st.sidebar.number_input(
        "슬리피지 (%) — 편도",
        min_value=0.0,
        max_value=5.0,
        value=0.5,
        step=0.25,
        format="%0.2f",
        help="시장가 체결 시 평균 미끄러짐 가정치. 0.25% 단위로 설정.",
    )

    return Inputs(
        symbol=symbol,
        interval=interval,
        months=months,
        fee=fee_percent / 100.0,         # percent → ratio
        slippage=slippage_percent / 100.0,
        corr_months=corr_months,
    )
