from __future__ import annotations

import json
from typing import Tuple

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# 사용자 제공 모듈 (IndicLens/backtest/*)
from backtest import data as d
from backtest import signals as sig
from backtest import engine as eng
from backtest import evals as ev

from ui.sidebar import Inputs, now_utc

# ── 캐시 설정 ────────────────────────────────────────────────────────────────
CACHE_TTL_PRICE = 600   # 10분


@st.cache_data(show_spinner=False, ttl=CACHE_TTL_PRICE)
def load_price(symbol: str, interval: str, months: int) -> pd.DataFrame:
    """선물 캔들 페치(기간: months). 캐시됨."""
    end = pd.Timestamp(now_utc())
    start = end - pd.DateOffset(months=int(months))
    df = d.fetch_futures_klines_range(symbol, interval, start, end)
    return df


# ── 룰 빌더 ──────────────────────────────────────────────────────────────────
_SAMPLE_SET = {
    "name": "샘플: RSI 30↗ 매수 / 70↘ 매도",
    "entry": {
        "op": "crossover",
        "left": {"name": "rsi", "params": {"period": 14}},
        "right": {"type": "const", "value": 30},
    },
    "exit": {
        "op": "crossunder",
        "left": {"name": "rsi", "params": {"period": 14}},
        "right": {"type": "const", "value": 70},
    },
}


# 좌/우 스케일 구분: 유효한 비교만 UI에 제공하기 위함
#   - price 계열: close, sma, ema, bbands.*
#   - rsi 계열: rsi
#   - macd 계열: macd.macd / macd.signal / macd.hist

def _scale_of(base: str) -> str:
    if base in ("close", "sma", "ema"):
        return "price"
    if base.startswith("bbands"):
        return "price"
    if base == "rsi":
        return "rsi"
    if base.startswith("macd"):
        return "macd"
    return "unknown"


def _indicator(name: str, span: int | None = None, window: int | None = None, field: str | None = None):
    obj = {"name": name}
    params = {}
    if span is not None:
        params["span"] = int(span)
    if window is not None:
        params["window"] = int(window)
    if params:
        obj["params"] = params
    if field:
        obj["field"] = field
    return obj


def _build_left(base: str, p1: int):
    if base.startswith("macd"):
        # macd 필드는 오른쪽 비교용에서만 사용하므로, 왼쪽에서 macd.필드를 고르면 해당 필드를 명시
        field = base.split(".")[1]
        return _indicator("macd", field=field)
    if base.startswith("bbands"):
        field = base.split(".")[1]
        return _indicator("bbands", window=p1, field=field)
    if base == "sma":
        return _indicator("sma", window=p1)
    if base == "ema":
        return _indicator("ema", span=p1)
    if base == "rsi":
        return {"name": "rsi", "params": {"period": int(p1)}}
    return {"name": base}


def _rule_builder_ui() -> tuple[dict | None, dict | None]:
    st.subheader("🧱 룰 빌더")
    with st.expander("기본 지표로 조건 만들기", expanded=False):
        # 1) 왼쪽(주인공) 선택
        col1, col2 = st.columns(2)
        with col1:
            kind = st.selectbox(
                "조건 유형",
                ["crossover", "crossunder", "compare"],
                help="crossover/crossunder: 왼쪽이 오른쪽을 위/아래로 통과하는 순간. compare: 단순 비교",
            )
            base = st.selectbox(
                "왼쪽(주인공): 지표/소스",
                [
                    "close", "sma", "ema", "rsi",
                    "macd.macd", "macd.signal", "macd.hist",
                    "bbands.bb_upper", "bbands.bb_mid", "bbands.bb_lower",
                ],
                help="왼쪽은 신호의 주인공. 이 값이 기준선(오른쪽)을 넘는지/아닌지 검사합니다.",
            )
            p1 = st.number_input("왼쪽 기간(window/period)", 1, 300, 14,
                                  help="sma/ema/rsi/bbands에 사용. macd/close는 무시")
        left_scale = _scale_of(base if base else "")

        # 2) 오른쪽(기준선) 선택 — 왼쪽의 스케일에 맞춰 옵션 제한
        with col2:
            if left_scale == "rsi":
                right_choice = st.selectbox(
                    "오른쪽(기준선)", ["상수", "rsi"], index=0,
                    help="RSI는 상수(30/70 등) 또는 RSI(기간 다르게)와 비교하는 게 의미 있습니다.",
                )
            elif left_scale == "macd":
                right_choice = st.selectbox(
                    "오른쪽(기준선)", ["상수", "macd.macd", "macd.signal", "macd.hist"], index=1,
                    help="MACD는 신호선과의 교차(macd vs signal) 또는 0선과의 교차(상수 0) 등이 일반적.",
                )
            else:  # price 계열 (close/sma/ema/bbands)
                right_choice = st.selectbox(
                    "오른쪽(기준선)",
                    ["close", "sma", "ema", "bbands.bb_upper", "bbands.bb_mid", "bbands.bb_lower"],
                    index=2,
                    help="가격 스케일끼리 비교. 예) close > ema(20), sma(20) crossover sma(50)",
                )

            # 오른쪽 파라미터 입력(선택에 따라 다름)
            thr = None
            p2 = None
            if right_choice == "상수":
                thr = st.number_input(
                    "오른쪽 상수값",
                    value=0.0,
                    help="RSI 30/70, MACD 0선 등. 가격에는 상수 임계값을 잘 쓰지 않습니다.",
                )
            elif right_choice in ("sma", "ema"):
                p2 = st.number_input("오른쪽 기간(window/span)", 1, 300, 20,
                                      help="sma/ema의 길이")
            elif right_choice.startswith("bbands"):
                p2 = st.number_input("오른쪽 BBANDS 기간(window)", 1, 300, 20,
                                      help="볼린저밴드 중심선 기간")
            elif right_choice == "rsi":
                p2 = st.number_input("오른쪽 RSI 기간(period)", 1, 300, 14,
                                      help="왼쪽 RSI와 다른 기간으로 비교 가능")

        # 3) 좌/우 실제 객체 구성
        left = _build_left(base, p1)
        # 오른쪽 구성
        if right_choice == "상수":
            right = {"type": "const", "value": thr if thr is not None else 0.0}
        elif right_choice == "sma":
            right = _indicator("sma", window=int(p2))
        elif right_choice == "ema":
            right = _indicator("ema", span=int(p2))
        elif right_choice == "rsi":
            right = {"name": "rsi", "params": {"period": int(p2) if p2 else 14}}
        elif right_choice.startswith("bbands"):
            field = right_choice.split(".")[1]
            right = _indicator("bbands", window=int(p2), field=field)
        elif right_choice.startswith("macd"):
            field = right_choice.split(".")[1]
            right = _indicator("macd", field=field)
        else:  # close
            right = {"name": right_choice}

        # 4) 최종 표현식
        if kind in ("crossover", "crossunder"):
            base_expr = {"op": kind, "left": left, "right": right}
        else:
            comp = st.selectbox("비교 연산자", [">", "<", ">=", "<=", "==", "!="], index=1,
                                help="compare 모드에서만 사용")
            base_expr = {"op": comp, "left": left, "right": right}

        st.code(json.dumps(base_expr, ensure_ascii=False, indent=2), language="json")

        use_for = st.radio("이 조건을 어디에 사용할까?", ["매수(Entry)", "매도(Exit)"], horizontal=True)
        entry_expr = base_expr if use_for == "매수(Entry)" else None
        exit_expr = base_expr if use_for == "매도(Exit)" else None

        if st.button("조건 세트에 추가"):
            if "condition_sets" not in st.session_state:
                st.session_state.condition_sets = [_SAMPLE_SET]
            st.session_state.condition_sets.append({
                "name": f"사용자 조건 #{len(st.session_state.condition_sets)}",
                "entry": entry_expr or _SAMPLE_SET["entry"],
                "exit": exit_expr or _SAMPLE_SET["exit"],
            })
            st.success("추가되었습니다. 아래 '조건 리스트'에서 선택해 백테스트!")

    return None, None


def _ensure_state():
    if "condition_sets" not in st.session_state:
        st.session_state.condition_sets = [_SAMPLE_SET]


def _conditions_ui():
    st.subheader("📋 조건 리스트")
    names = [c["name"] for c in st.session_state.condition_sets]
    chosen = st.multiselect("백테스트할 조건 세트 선택 (복수 선택 가능)", names, default=names[:1])
    comb = st.radio("여러 조건을 어떤 방식으로 합칠까?", ["and", "or"], horizontal=True)
    return chosen, comb


def _combine_rules(selected_names: list[str], comb: str) -> tuple[dict, dict]:
    chosen = [c for c in st.session_state.condition_sets if c["name"] in selected_names]
    if not chosen:
        chosen = [st.session_state.condition_sets[0]]
    entry_rules = [c["entry"] for c in chosen]
    exit_rules = [c["exit"] for c in chosen]
    if len(entry_rules) == 1:
        entry = entry_rules[0]
        exit_ = exit_rules[0]
    else:
        entry = {"op": comb, "args": entry_rules}
        exit_ = {"op": comb, "args": exit_rules}
    return entry, exit_


def _plot_equity(price_df: pd.DataFrame, curves: dict[str, pd.Series]):
    fig = go.Figure()
    for name, eq in curves.items():
        fig.add_trace(go.Scatter(x=price_df["time"], y=eq, mode="lines", name=name))
    fig.update_layout(
        title="전략별 에쿼티 곡선 (초기 1.0)",
        hovermode="x unified",
        xaxis=dict(showspikes=True, spikemode="across", spikesnap="cursor"),
        yaxis_title="Equity",
        margin=dict(t=40, b=10, l=10, r=10),
        height=420,
    )
    st.plotly_chart(fig, use_container_width=True)


def view(inputs: Inputs):
    _ensure_state()

    # 1) 데이터 로드 (캐시)
    price_df = load_price(inputs.symbol, inputs.interval, inputs.months)
    if price_df.empty:
        st.error("가격 데이터를 불러오지 못했습니다.")
        return

    # 2) 룰 빌더 UI
    _rule_builder_ui()

    # 3) 조건 리스트 & 조합 방식
    selected, comb = _conditions_ui()
    entry_rule, exit_rule = _combine_rules(selected, comb)

    # 4) 백테스트 실행
    entry_sig = sig.evaluate_rule(entry_rule, price_df)
    exit_sig = sig.evaluate_rule(exit_rule, price_df)

    bt_df, trades, trade_log = eng.backtest_long_only(
        price_df, entry_sig, exit_sig, fee=inputs.fee, slippage=inputs.slippage, cooldown=0
    )

    # Buy&Hold 곡선
    bh = price_df["close"] / price_df["close"].iloc[0]

    # 5) 성과 요약
    periods_per_year = {"15m": 4*24*365, "1h": 24*365, "4h": 6*365, "1d": 365}[inputs.interval]
    summary = ev.summarize(bt_df["equity"], trades, periods_per_year)
    st.markdown("### 📈 성과 요약")
    st.dataframe(pd.DataFrame([summary]), use_container_width=True)

    # 6) 그래프
    _plot_equity(price_df, {"전략": bt_df["equity"], "Buy&Hold": bh})

    with st.expander("🧾 체결 로그"):
        st.dataframe(pd.DataFrame(trade_log))
