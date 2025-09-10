import streamlit as st
import pandas as pd

from backtest.data import (
    fetch_klines,
    fetch_funding_rate,
)
from backtest.signals import evaluate_rule
from backtest.engine import backtest_long_only
from backtest.evals import summarize
from backtest.correlation import feature_return_lag_corr

# ---- 페이지 설정
st.set_page_config(page_title="IndicLens", layout="wide")

st.title("📊 IndicLens")
st.caption("커스텀 백테스트 · 파생지표 상관분석 대시보드 (MVP)")

# ---- 사이드바 입력
with st.sidebar:
    st.header("⚙️ 설정")
    symbol = st.text_input("심볼", value="BTCUSDT").upper()
    interval = st.selectbox("인터벌", ["1h", "4h", "1d"], index=0)
    limit = st.slider("캔들 개수", min_value=200, max_value=1000, value=600, step=50)

    st.divider()
    st.subheader("거래 비용 / 정책")
    fee = st.number_input("수수료(%)", value=0.1, step=0.01) / 100.0
    slippage = st.number_input("슬리피지(%)", value=0.1, step=0.01) / 100.0
    cooldown = st.number_input("쿨다운(캔들)", value=1, step=1, min_value=0)

    st.divider()
    st.subheader("상관 분석")
    lag_window = st.slider("라그 범위 (±)", min_value=12, max_value=96, value=48, step=12)
    return_period = st.selectbox("수익률 기간", [1, 2, 4, 6, 12], index=0)

# ---- 데이터 로드
price_df = fetch_klines(symbol, interval, limit, use_cache=True)

# ---- 탭
tab_bt, tab_corr = st.tabs(["🧪 백테스트", "🔗 상관분석"])

# ======================
# 🧪 백테스트 탭
# ======================
with tab_bt:
    st.subheader("전략: EMA12 ↗ EMA26 진입, EMA12 ↘ EMA26 청산")

    entry_rule = {
        "op": "crossover",
        "left":  {"type":"indicator","name":"ema","params":{"span":12},"source":"close"},
        "right": {"type":"indicator","name":"ema","params":{"span":26},"source":"close"}
    }
    exit_rule = {
        "op": "crossunder",
        "left":  {"type":"indicator","name":"ema","params":{"span":12},"source":"close"},
        "right": {"type":"indicator","name":"ema","params":{"span":26},"source":"close"}
    }

    entry_sig = evaluate_rule(entry_rule, price_df)
    exit_sig  = evaluate_rule(exit_rule, price_df)

    bt_df, trades = backtest_long_only(
        price_df,
        entry_sig,
        exit_sig,
        fee=fee,
        slippage=slippage,
        cooldown=int(cooldown),
    )

    # 타임프레임별 연율화 상수
    PER_YEAR = {"1h": 24 * 365, "4h": 6 * 365, "1d": 365}
    metrics = summarize(bt_df["equity"], trades, periods_per_year=PER_YEAR[interval])

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("총수익률", f"{metrics['total_return']*100:,.2f}%")
    c2.metric("CAGR", f"{metrics['cagr']*100:,.2f}%")
    c3.metric("MDD", f"{metrics['mdd']*100:,.2f}%")
    c4.metric("Sharpe", f"{metrics['sharpe']:.2f}")
    c5.metric("거래수", f"{metrics['trades']}")
    c6.metric("승률", f"{metrics['win_rate']*100:,.1f}%")

    st.line_chart(
        bt_df.set_index("time")[["close", "equity"]],
        height=320
    )

    st.caption("※ 룩어헤드 방지: 신호 발생 시 다음 캔들 시가 체결. 수수료·슬리피지 및 쿨다운 반영.")

# ======================
# 🔗 상관분석 탭
# ======================
with tab_corr:
    st.subheader("Funding Rate ↔ 가격 로그수익률 라그 상관")

    fr = fetch_funding_rate(symbol, limit=200)
    corr_df = feature_return_lag_corr(
        price_df, fr, feature_col="fundingRate",
        return_period=int(return_period),
        lags=range(-int(lag_window), int(lag_window) + 1)
    )

    st.dataframe(corr_df, height=320)
    st.line_chart(
        corr_df.set_index("lag")[["pearson", "spearman"]],
        height=280
    )

    with st.expander("라그 해석 도움말", expanded=False):
        st.markdown(
            "- **양수 lag**: 지표가 미래 수익률을 선행(lead) → 예) lag=6이면 feature(t) vs returns(t+6)\n"
            "- **음수 lag**: 지표가 과거 수익률을 추종(lag) → returns(t-abs(lag))\n"
            "- 결측/샘플수 적은 구간은 자동 제외(n 열 참고)"
        )
