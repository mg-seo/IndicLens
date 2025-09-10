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
# -----------------------------
# 룰 빌더 GUI (MVP)
# -----------------------------
st.markdown("### 🧩 룰 빌더 (MVP)")

# 초기 세션 상태
if "rule_rows" not in st.session_state:
    st.session_state.rule_rows = []   # 각 원소는 {"type": "compare"/"cross", ...}
if "rule_logic" not in st.session_state:
    st.session_state.rule_logic = "and"  # and / or

# 공통 셀렉터 유틸
INDICATORS = ["sma", "ema", "rsi", "macd", "bbands"]
SOURCES = ["open", "high", "low", "close"]
OPS = [">", "<", ">=", "<=", "==", "!="]

def build_operand(kind, name, params, field, source, const_value):
    """
    kind: "indicator" | "source" | "const"
    """
    if kind == "const":
        return {"type": "const", "value": const_value}
    if kind == "source":
        # 간단 소스 컬럼 참조 (close 등)
        return {"type": "indicator", "name": name}
    # indicator
    obj = {"type": "indicator", "name": name, "params": params or {}}
    if source:
        obj["source"] = source
    if field:
        obj["field"] = field
    return obj

with st.expander("조건 추가하기", expanded=True):
    cond_type = st.radio("조건 타입", ["비교식", "교차식"], horizontal=True)

    if cond_type == "비교식":
        colA, colB = st.columns(2)
        with colA:
            left_kind = st.selectbox("Left 피연산자", ["indicator", "source"], index=0)
            left_name = st.selectbox("Left 선택", INDICATORS if left_kind=="indicator" else SOURCES)
            left_source = None
            left_params = {}
            left_field = None

            if left_kind == "indicator":
                if left_name in ["sma", "bbands"]:
                    win = st.number_input("window", 5, 200, 20)
                    left_params["window"] = int(win)
                if left_name == "ema":
                    span = st.number_input("span", 2, 200, 12)
                    left_params["span"] = int(span)
                if left_name == "rsi":
                    period = st.number_input("period", 2, 200, 14)
                    left_params["period"] = int(period)
                if left_name == "macd":
                    fast = st.number_input("fast", 2, 200, 12)
                    slow = st.number_input("slow", 2, 200, 26)
                    signal = st.number_input("signal", 2, 200, 9)
                    left_params.update({"fast": int(fast), "slow": int(slow), "signal": int(signal)})
                    left_field = st.selectbox("field", ["macd", "signal", "hist"], index=2)
                if left_name == "bbands":
                    k = st.number_input("k", 0.5, 5.0, 2.0, step=0.1)
                    left_params["k"] = float(k)
                if left_name in ["sma", "ema", "rsi", "bbands", "macd"]:
                    left_source = st.selectbox("source", SOURCES, index=3)

        with colB:
            op = st.selectbox("연산자", OPS, index=1)
            right_kind = st.selectbox("Right 피연산자", ["indicator", "source", "const"], index=2)

            right_name = None; right_params = {}; right_field=None; right_source=None; const_value=None
            if right_kind == "const":
                const_value = st.number_input("상수 값", value=30.0)
            elif right_kind == "source":
                right_name = st.selectbox("Right 선택 (소스)", SOURCES)
            else:
                right_name = st.selectbox("Right 선택 (지표)", INDICATORS, index=0)
                if right_name in ["sma", "bbands"]:
                    win = st.number_input("right.window", 5, 200, 20)
                    right_params["window"] = int(win)
                if right_name == "ema":
                    span = st.number_input("right.span", 2, 200, 26)
                    right_params["span"] = int(span)
                if right_name == "rsi":
                    period = st.number_input("right.period", 2, 200, 14)
                    right_params["period"] = int(period)
                if right_name == "macd":
                    fast = st.number_input("right.fast", 2, 200, 12)
                    slow = st.number_input("right.slow", 2, 200, 26)
                    signal = st.number_input("right.signal", 2, 200, 9)
                    right_params.update({"fast": int(fast), "slow": int(slow), "signal": int(signal)})
                    right_field = st.selectbox("right.field", ["macd", "signal", "hist"], index=2)
                if right_name in ["sma", "ema", "rsi", "bbands", "macd"]:
                    right_source = st.selectbox("right.source", SOURCES, index=3)

        if st.button("조건 추가 (비교식)", use_container_width=True):
            left = build_operand(left_kind, left_name, left_params, left_field, left_source, const_value=None)
            right = build_operand(right_kind, right_name, right_params, right_field, right_source, const_value)
            st.session_state.rule_rows.append({"type": "compare", "op": op, "left": left, "right": right})
            st.success("비교식 조건이 추가되었습니다.")

    else:  # 교차식
        colC, colD = st.columns(2)
        with colC:
            cross_op = st.selectbox("교차 종류", ["crossover", "crossunder"], index=0)
            l_kind = st.selectbox("Left", ["indicator", "source"], index=0, key="cross_l_kind")
            l_name = st.selectbox("Left 선택", INDICATORS if l_kind=="indicator" else SOURCES, key="cross_l_name")
            l_params={}; l_field=None; l_source=None
            if l_kind == "indicator":
                if l_name in ["sma", "bbands"]:
                    win = st.number_input("left.window", 5, 200, 12, key="cross_l_win")
                    l_params["window"] = int(win)
                if l_name == "ema":
                    span = st.number_input("left.span", 2, 200, 12, key="cross_l_span")
                    l_params["span"] = int(span)
                if l_name == "rsi":
                    period = st.number_input("left.period", 2, 200, 14, key="cross_l_period")
                    l_params["period"] = int(period)
                if l_name == "macd":
                    fast = st.number_input("left.fast", 2, 200, 12, key="cross_l_fast")
                    slow = st.number_input("left.slow", 2, 200, 26, key="cross_l_slow")
                    signal = st.number_input("left.signal", 2, 200, 9, key="cross_l_signal")
                    l_params.update({"fast": int(fast), "slow": int(slow), "signal": int(signal)})
                    l_field = st.selectbox("left.field", ["macd", "signal", "hist"], index=2, key="cross_l_field")
                if l_name in ["sma", "ema", "rsi", "bbands", "macd"]:
                    l_source = st.selectbox("left.source", SOURCES, index=3, key="cross_l_source")

        with colD:
            r_kind = st.selectbox("Right", ["indicator", "source"], index=0, key="cross_r_kind")
            r_name = st.selectbox("Right 선택", INDICATORS if r_kind=="indicator" else SOURCES, key="cross_r_name")
            r_params={}; r_field=None; r_source=None
            if r_kind == "indicator":
                if r_name in ["sma", "bbands"]:
                    win = st.number_input("right.window", 5, 200, 26, key="cross_r_win")
                    r_params["window"] = int(win)
                if r_name == "ema":
                    span = st.number_input("right.span", 2, 200, 26, key="cross_r_span")
                    r_params["span"] = int(span)
                if r_name == "rsi":
                    period = st.number_input("right.period", 2, 200, 14, key="cross_r_period")
                    r_params["period"] = int(period)
                if r_name == "macd":
                    fast = st.number_input("right.fast", 2, 200, 12, key="cross_r_fast")
                    slow = st.number_input("right.slow", 2, 200, 26, key="cross_r_slow")
                    signal = st.number_input("right.signal", 2, 200, 9, key="cross_r_signal")
                    r_params.update({"fast": int(fast), "slow": int(slow), "signal": int(signal)})
                    r_field = st.selectbox("right.field", ["macd", "signal", "hist"], index=2, key="cross_r_field")
                if r_name in ["sma", "ema", "rsi", "bbands", "macd"]:
                    r_source = st.selectbox("right.source", SOURCES, index=3, key="cross_r_source")

        if st.button("조건 추가 (교차식)", use_container_width=True):
            left = build_operand(l_kind, l_name, l_params, l_field, l_source, const_value=None)
            right = build_operand(r_kind, r_name, r_params, r_field, r_source, const_value=None)
            st.session_state.rule_rows.append({"type": "cross", "op": cross_op, "left": left, "right": right})
            st.success("교차식 조건이 추가되었습니다.")

# 현재 조건 리스트 표시/관리
st.markdown("#### 현재 조건")
if not st.session_state.rule_rows:
    st.info("추가된 조건이 없습니다.")
else:
    for i, row in enumerate(st.session_state.rule_rows):
        st.write(f"{i+1}) {row}")

    colX, colY, colZ = st.columns([1,1,2])
    with colX:
        if st.button("마지막 조건 삭제"):
            st.session_state.rule_rows.pop()
    with colY:
        if st.button("모두 삭제"):
            st.session_state.rule_rows = []

# 결합 방식 (AND/OR)
st.session_state.rule_logic = st.radio("조건 결합 방식", ["and", "or"], index=0, horizontal=True)

# 룰 JSON 생성 + 미리보기 + entry_sig 개수 표시
if st.button("룰 JSON 생성/적용", type="secondary"):
    if not st.session_state.rule_rows:
        st.warning("조건이 없습니다. 최소 1개 이상 추가하세요.")
    else:
        # 내부 표현을 DSL로 컴파일
        clauses = []
        for r in st.session_state.rule_rows:
            if r["type"] == "compare":
                clauses.append({
                    "op": r["op"],
                    "left": r["left"],
                    "right": r["right"]
                })
            else:  # cross
                clauses.append({
                    "op": r["op"],
                    "left": r["left"],
                    "right": r["right"]
                })
        if len(clauses) == 1:
            compiled = clauses[0]
        else:
            compiled = {"op": st.session_state.rule_logic, "args": clauses}

        # 룰 JSON 텍스트에 주입 (기존 Entry textarea 변수명에 맞게)
        st.session_state["Entry JSON"] = json.dumps(compiled, indent=2)  # 키 이름은 아래 textarea의 label/key에 맞춰주면 자동 반영됨

        # 바로 평가해서 True 개수 피드백
        try:
            entry_sig_preview = evaluate_rule(compiled, price_df)
            st.success(f"룰 적용 완료! True 시그널 개수: {int(entry_sig_preview.sum())}")
        except Exception as e:
            st.error(f"룰 평가 에러: {e}")


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
    entry_text = st.text_area("Entry JSON", key="Entry JSON", value=json.dumps(default_entry, indent=2), height=220)

    st.write("**룰 JSON (Exit, 선택 입력)**")
    exit_text = st.text_area("Exit JSON (비우면 엔진 기본 로직 사용: entry 재등장 시 청산)", key="Exit JSON", value=json.dumps(default_exit, indent=2), height=180)

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
