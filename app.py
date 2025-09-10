import streamlit as st
import pandas as pd
import json
from matplotlib import pyplot as plt

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
    st.subheader("🧪 커스텀 룰 → 백테스트")

    # 기본 Entry/Exit 룰 템플릿
    default_entry = {
        "op": "and",
        "args": [
            { "op": "crossover",
              "left":  { "type":"indicator","name":"ema","params":{"span":12},"source":"close" },
              "right": { "type":"indicator","name":"ema","params":{"span":26},"source":"close" }
            },
            { "op": ">",
              "left":  { "type":"indicator","name":"macd","params":{"fast":12,"slow":26,"signal":9}, "field":"hist" },
              "right": { "type":"const","value": 0 }
            }
        ]
    }
    default_exit = {
        "op": "crossunder",
        "left":  {"type":"indicator","name":"ema","params":{"span":12},"source":"close"},
        "right": {"type":"indicator","name":"ema","params":{"span":26},"source":"close"}
    }

    # 룰 JSON 입력 UI
    st.write("**룰 JSON (Entry)**")
    entry_text = st.text_area("Entry JSON", value=json.dumps(default_entry, indent=2), height=220)

    st.write("**룰 JSON (Exit, 선택 입력)**")
    exit_text = st.text_area("Exit JSON (비우면 엔진 기본 로직 사용: entry 재등장 시 청산)", value=json.dumps(default_exit, indent=2), height=180)

    run_bt = st.button("백테스트 실행", type="primary")

    if run_bt:
        try:
            # JSON 파싱
            entry_rule_json = json.loads(entry_text)
            exit_rule_json = json.loads(exit_text) if exit_text.strip() else None

            # 시그널 계산
            entry_sig = evaluate_rule(entry_rule_json, price_df)
            exit_sig  = evaluate_rule(exit_rule_json, price_df) if exit_rule_json else None

            # 백테스트 실행 (룩어헤드 방지: 엔진 내부에서 신호 shift 처리)
            bt_df, trades, trade_log = backtest_long_only(
                price_df,
                entry_sig,
                exit_sig=exit_sig,
                fee=fee,
                slippage=slippage,
                cooldown=int(cooldown),
            )

            # 성과 요약
            PER_YEAR = {"1h": 24 * 365, "4h": 6 * 365, "1d": 365}
            metrics = summarize(bt_df["equity"], trades, periods_per_year=PER_YEAR.get(interval, 365))

            # 벤치마크: Buy & Hold
            bh = price_df[["time", "close"]].copy()
            bh["equity"] = bh["close"] / bh["close"].iloc[0]
            bh_metrics = summarize(bh["equity"], [], periods_per_year=PER_YEAR.get(interval, 365))
            excess = metrics["total_return"] - bh_metrics["total_return"]

            # KPI
            c1, c2, c3, c4, c5, c6 = st.columns(6)
            c1.metric("총수익률", f"{metrics['total_return']*100:,.2f}%")
            c2.metric("CAGR", f"{metrics['cagr']*100:,.2f}%")
            c3.metric("MDD", f"{metrics['mdd']*100:,.2f}%")
            c4.metric("Sharpe", f"{metrics['sharpe']:.2f}")
            c5.metric("거래수", f"{metrics['trades']}")
            c6.metric("승률", f"{metrics['win_rate']*100:,.1f}%")

            st.caption(
                f"📌 벤치마크(B&H) 총수익률: {bh_metrics['total_return']*100:,.2f}% · "
                f"전략 대비 초과수익: {excess*100:,.2f}%"
            )

            # Equity 비교 차트 (한 플롯에 두 곡선)
            fig = plt.figure()
            plt.plot(bt_df["time"], bt_df["equity"], label="Strategy")
            plt.plot(bh["time"], bh["equity"], label="Buy & Hold")
            plt.title("Equity Curve vs Buy & Hold")
            plt.xlabel("time")
            plt.ylabel("equity")
            plt.legend()
            st.pyplot(fig, clear_figure=True)

            # 시그널 시점 미리보기
            st.write("**시그널(최근 10개 True)**")
            sig_times = pd.Series(entry_sig[entry_sig].index).tail(10)
            st.dataframe(pd.DataFrame({"signal_time": sig_times}))

            # 트레이드 로그
            if trade_log:
                st.write("**트레이드 로그 (최근 20건)**")
                log_df = pd.DataFrame(trade_log).sort_values("entry_time").reset_index(drop=True)
                st.dataframe(log_df.tail(20))

                # CSV 다운로드
                csv = log_df.to_csv(index=False).encode("utf-8-sig")
                st.download_button("트레이드 로그 CSV 다운로드", csv, file_name="trades.csv", mime="text/csv")
            else:
                st.info("트레이드가 없습니다.")

            st.caption("※ 룩어헤드 방지: 신호 발생 시 다음 캔들 시가 체결. 수수료·슬리피지 및 쿨다운 반영.")

        except Exception as e:
            st.error(f"룰 해석/백테스트 중 오류: {e}")


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
