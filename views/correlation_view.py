from __future__ import annotations

import pandas as pd
import streamlit as st
import numpy as np
from plotly.subplots import make_subplots
import plotly.graph_objects as go

from ui.sidebar import Inputs, now_utc
from backtest import data as d
from backtest import correlation as corr

# ── 캐시 설정 ────────────────────────────────────────────────────────────────
CACHE_TTL_PRICE = 600     # 10분
CACHE_TTL_FEAT  = 600     # 10분


def _month_window():
    end = pd.Timestamp(now_utc())
    start = end - pd.DateOffset(months=1)
    return start, end


# ── 로드 (캐시) ──────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=CACHE_TTL_PRICE)
def load_price_1m(symbol: str, interval: str) -> pd.DataFrame:
    start, end = _month_window()
    return d.fetch_futures_klines_range(symbol, interval, start, end)


@st.cache_data(show_spinner=False, ttl=CACHE_TTL_FEAT)
def load_funding(symbol: str) -> pd.DataFrame:
    start, end = _month_window()
    return d.fetch_funding_rate_range(symbol, start, end)


@st.cache_data(show_spinner=False, ttl=CACHE_TTL_FEAT)
def load_oi(symbol: str, interval: str) -> pd.DataFrame:
    start, end = _month_window()
    return d.fetch_open_interest_range(symbol, interval, start, end)


@st.cache_data(show_spinner=False, ttl=CACHE_TTL_FEAT)
def load_top_ls(symbol: str, interval: str, metric: str) -> pd.DataFrame:
    start, end = _month_window()
    return d.fetch_top_traders_long_short_range(symbol, interval, start, end, metric=metric)


@st.cache_data(show_spinner=False, ttl=CACHE_TTL_FEAT)
def load_taker_ratio(symbol: str, interval: str) -> pd.DataFrame:
    start, end = _month_window()
    return d.fetch_taker_buy_sell_range(symbol, interval, start, end)

# ── 라이브(현재값) 전용 로더 — 60초 캐시 ───────────────────────────────────
@st.cache_data(show_spinner=False, ttl=60)
def load_live_funding_pct(symbol: str) -> float | None:
    j = d.fetch_funding_live(symbol)
    return float(j["lastFundingRate"]) * 100.0 if j and j.get("lastFundingRate") else None

@st.cache_data(show_spinner=False, ttl=60)
def load_live_oi(symbol: str) -> float | None:
    return d.fetch_open_interest_snapshot(symbol)

@st.cache_data(show_spinner=False, ttl=60)
def load_latest_top_ls_accounts(symbol: str, period: str = "5m") -> float | None:
    return d.fetch_top_ls_accounts_latest(symbol, period)

@st.cache_data(show_spinner=False, ttl=60)
def load_latest_top_ls_positions(symbol: str, period: str = "5m") -> float | None:
    return d.fetch_top_ls_positions_latest(symbol, period)

@st.cache_data(show_spinner=False, ttl=60)
def load_latest_taker_ratio(symbol: str, period: str = "5m") -> float | None:
    return d.fetch_taker_buy_sell_latest(symbol, period)


# ── 정렬/정규화 유틸 ─────────────────────────────────────────────────────────
# 서로 다른 시계열의 시작/끝이 달라 보이는 문제를 줄이기 위해
# 1) 모든 파생지표를 가격 캔들의 타임스탬프에 맞춰 asof-정렬
# 2) 모든 패널의 x축 범위를 "공통 커버리지 구간"으로 강제


def _align_asof(price_df: pd.DataFrame, fdf: pd.DataFrame, col: str) -> pd.DataFrame:
    """price_df["time"]을 기준으로 fdf[col]을 asof(backward)로 정렬.
    반환: time, value 두 컬럼.
    """
    if fdf is None or fdf.empty:
        return pd.DataFrame(columns=["time", "value"]).astype({"time": "datetime64[ns, UTC]", "value": "float64"})
    idx = price_df[["time"]].sort_values("time")
    f = fdf[["time", col]].dropna().sort_values("time")
    out = pd.merge_asof(idx, f, on="time", direction="backward")
    out.rename(columns={col: "value"}, inplace=True)
    return out


def _forward_return(price_df: pd.DataFrame, k: int) -> pd.DataFrame:
    """k 스텝 미래 로그수익률 r_{t->t+k} = log(P_{t+k}/P_t). 마지막 k개는 NaN."""
    ret = np.log(price_df["close"].shift(-k) / price_df["close"])
    out = price_df[["time"]].copy()
    out["fwd_ret"] = ret
    return out

def _quantile_conditional_return(price_df: pd.DataFrame,
                                 fdf: pd.DataFrame,
                                 feature_col: str,
                                 k: int,
                                 q: int = 5) -> pd.DataFrame | None:
    """특정 피처의 분위(quantile)별로 k-스텝 미래수익률 평균/표본수/SE 계산."""
    if fdf is None or fdf.empty:
        return None
    # 가격 축에 asof 정렬(이미 되어 있으면 그대로 사용 가능)
    feat = _align_asof(price_df, fdf, feature_col)
    if feat.dropna(subset=["value"]).empty:
        return None

    # 미래 수익률
    fr = _forward_return(price_df, k)
    df = price_df[["time"]].merge(feat.rename(columns={"value": "feat"}), on="time", how="left")
    df = df.merge(fr, on="time", how="left").dropna(subset=["feat", "fwd_ret"])

    cats = pd.qcut(df["feat"], q=q, duplicates="drop")  # 라벨 지정 X
    codes = cats.cat.codes  # 0..(k-1), 없는 값은 -1

    # 유효 구간만 사용(= -1 제거)
    mask = codes >= 0
    df = df.loc[mask].copy()
    df["q"] = (codes[mask] + 1).astype(str)  # "1","2",... 형식 라벨

    # 분위가 1개 이하로 떨어지면 분석 불가 -> None 반환
    if df["q"].nunique() < 2:
        return None

    g = df.groupby("q", observed=True)["fwd_ret"]
    out = g.agg(mean="mean", std="std", n="count").reset_index()
    out["se"] = out["std"] / np.sqrt(out["n"]).replace(0, np.nan)
    out["t_stat"] = out["mean"] / out["se"]
    # 퍼센트 표시용 컬럼 (가독성)
    out["mean_pct"] = out["mean"] * 100.0
    return out

def _quantile_analysis_ui(price_df: pd.DataFrame, feats_raw: dict[str, pd.DataFrame], interval: str):
    st.markdown("### 🎯 조건부 수익률(퀀타일 분석)")
    # 분석 대상 피처 선택
    feat_map = {
        "Funding Rate (%)": ("funding", "fundingRate"),
        "Open Interest": ("oi", "openInterest"),
        "Top L/S (Accounts)": ("top_acc", "longShortRatio"),
        "Top L/S (Positions)": ("top_pos", "longShortRatio"),
        "Taker Buy/Sell Ratio": ("taker_ratio", "buySellRatio"),
    }
    c1, c2, c3 = st.columns(3)
    with c1:
        feat_label = st.selectbox("피처 선택", list(feat_map.keys()))
    with c2:
        # 인터벌에 따라 기본 k 추천값만 다르게(필요시 변경 가능)
        default_k = {"15m": 4, "1h": 4, "4h": 6, "1d": 1}.get(interval, 4)
        k = st.number_input("미래 수익률 스텝 k", min_value=1, max_value=96, value=default_k,
                            help="k 스텝 뒤의 수익률 r(t→t+k). 15m 기준 k=4는 1시간, 1h 기준 k=4는 4시간 등.")
    with c3:
        q = st.selectbox("분위 개수", [5, 10], index=0, help="보통 5분위(퀀타일 5)부터 시작")

    key, col = feat_map[feat_label]
    src = feats_raw.get(key)
    res = _quantile_conditional_return(price_df, src, col, int(k), int(q))

    if res is None or res.empty:
        st.info("분석에 사용할 유효 데이터가 부족합니다.")
        return

    # 표
    st.dataframe(res[["q", "n", "mean_pct", "t_stat"]].rename(columns={
        "q": "quantile", "n": "N", "mean_pct": f"mean r(t→t+{k}) [%]", "t_stat": "t-stat"
    }), use_container_width=True)

    # 바 차트
    fig = go.Figure()
    colors = ["#86efac" if v >= 0 else "#fecaca" for v in res["mean_pct"]]
    fig.add_trace(
        go.Bar(x=res["q"], y=res["mean_pct"], marker_color=colors, name="mean return (%)")
    )
    fig.update_layout(
        title=f"{feat_label} — 분위별 미래수익률 (k={k})",
        xaxis_title="Quantile (낮음 → 높음)",
        yaxis_title="Mean forward return (%)",
        bargap=0.15, height=360, margin=dict(t=40, b=10, l=10, r=10),
    )
    st.plotly_chart(fig, use_container_width=True)

    # 짧은 해석 가이드
    st.caption(
        "상위/하위 분위의 부호/크기를 비교하세요. 상위 분위에서 음수면 mean-reversion 시사, 양수면 추세 연장 가능성."
    )



def _coverage_range(price_df: pd.DataFrame, feats_aligned: dict[str, pd.DataFrame]):
    aligned_list = [v for v in feats_aligned.values() if v is not None]
    aligned_list = [v for v in aligned_list if not v.empty]
    if aligned_list:
        cov_start = max([df.dropna(subset=["value"]) ["time"].min() for df in aligned_list] + [price_df["time"].min()])
        cov_end   = min([df.dropna(subset=["value"]) ["time"].max() for df in aligned_list] + [price_df["time"].max()])
    else:
        cov_start, cov_end = price_df["time"].min(), price_df["time"].max()
    return cov_start, cov_end


def _stacked_chart(price_df: pd.DataFrame, feats_aligned: dict[str, pd.DataFrame]):
    cov_start, cov_end = _coverage_range(price_df, feats_aligned)

    # 시각화
    fig = make_subplots(
        rows=6, cols=1, shared_xaxes=True, vertical_spacing=0.02,
        row_heights=[0.36, 0.16, 0.12, 0.12, 0.12, 0.12],
        subplot_titles=(
            "Price (Futures)", "Funding Rate", "Open Interest",
            "Top Traders Long/Short (Accounts)", "Top Traders Long/Short (Positions)", "Taker Buy/Sell Ratio",
        ),
    )

    # Price (cov window로 자른 뷰)
    p = price_df[(price_df["time"] >= cov_start) & (price_df["time"] <= cov_end)]
    fig.add_trace(
        go.Candlestick(
            x=p["time"], open=p["open"], high=p["high"], low=p["low"], close=p["close"], name="Price"
        ),
        row=1, col=1,
    )

    # Helper to add line
    def _add_line(df: pd.DataFrame, name: str, row: int):
        if df is None or df.empty:
            return
        v = df[(df["time"] >= cov_start) & (df["time"] <= cov_end)]
        if v.dropna(subset=["value"]).empty:
            return
        fig.add_trace(go.Scatter(x=v["time"], y=v["value"], mode="lines", name=name), row=row, col=1)

    _add_line(feats_aligned.get("funding"), "Funding (%)", 2)
    _add_line(feats_aligned.get("oi"), "OpenInterest", 3)
    _add_line(feats_aligned.get("top_acc"), "Top L/S (Accounts)", 4)
    _add_line(feats_aligned.get("top_pos"), "Top L/S (Positions)", 5)
    _add_line(feats_aligned.get("taker_ratio"), "Taker L/S Ratio", 6)

    fig.update_layout(
        hovermode="x unified",
        xaxis_rangeslider_visible=False,
        margin=dict(t=40, b=10, l=10, r=10),
        height=860,
    )
    for i in range(1, 7):
        fig.update_xaxes(showspikes=True, spikemode="across", spikesnap="cursor", row=i, col=1)
        fig.update_xaxes(range=[cov_start, cov_end], row=i, col=1)

    # Funding 패널은 %로 표시
    fig.update_yaxes(ticksuffix="%", row=2, col=1)

    st.plotly_chart(fig, use_container_width=True)



def _corr_table(price_df: pd.DataFrame, feats: dict[str, pd.DataFrame], interval: str, symbol: str):
    st.markdown("### 🔗 상관관계 분석 (1개월)")
    lags = list(range(-24, 25))  # ±24 스텝

    def _one(name: str, fdf: pd.DataFrame, col: str):
        if fdf is None or fdf.empty:
            return None
        # 가격 타임스탬프에 asof 정렬한 값으로 상관 계산(시계열 맞춤)
        aligned = _align_asof(price_df, fdf, col)
        if aligned.dropna(subset=["value"]).empty:
            return None
        tmp = pd.DataFrame({"time": aligned["time"], name: aligned["value"]})
        df = corr.feature_return_lag_corr(price_df, tmp, feature_col=name, return_period=1, lags=lags)
        if df.empty:
            return None
        row0 = df[df["lag"] == 0].iloc[0]
        k_max = df.loc[df["pearson"].abs().idxmax()]
        cur_val = float(tmp[name].dropna().iloc[-1])
        # 'current' 칸만 60s 캐시된 라이브 값 우선 사용
        if name == "fundingRate":
            live = load_live_funding_pct(symbol)
            current_out = f"{live:.4f}%" if live is not None else f"{cur_val*100.0:.4f}%"
        elif name == "openInterest":
            live = load_live_oi(symbol)
            current_out = f"{live:,.0f}" if live is not None else f"{cur_val:,.0f}"
        elif name == "topLS_accounts":
            live = load_latest_top_ls_accounts(symbol)
            current_out = f"{live:.2f}" if live is not None else f"{cur_val:.2f}"
        elif name == "topLS_positions":
            live = load_latest_top_ls_positions(symbol)
            current_out = f"{live:.2f}" if live is not None else f"{cur_val:.2f}"
        elif name == "takerBuySellRatio":
            live = load_latest_taker_ratio(symbol)
            current_out = f"{live:.2f}" if live is not None else f"{cur_val:.2f}"
        else:
            current_out = cur_val
        return {
            "feature": name,
            "current": current_out,
            "pearson@0": float(row0["pearson"]) if pd.notna(row0["pearson"]) else None,
            "best_lag": int(k_max["lag"]) if pd.notna(k_max["pearson"]) else None,
            "best_r": float(k_max["pearson"]) if pd.notna(k_max["pearson"]) else None,
        }

    rows = []
    rows.append(_one("fundingRate", feats.get("funding"), "fundingRate"))
    rows.append(_one("openInterest", feats.get("oi"), "openInterest"))
    rows.append(_one("topLS_accounts", feats.get("top_acc"), "longShortRatio"))
    rows.append(_one("topLS_positions", feats.get("top_pos"), "longShortRatio"))
    rows.append(_one("takerBuySellRatio", feats.get("taker_ratio"), "buySellRatio"))
    rows = [r for r in rows if r]

    if not rows:
        st.info("상관분석에 사용할 파생 데이터가 부족합니다.")
        return

    st.dataframe(pd.DataFrame(rows), use_container_width=True)
    st.caption("참고: +lag는 '지표가 가격 수익률을 **선행**'하는 방향(지표(t) ↔ 수익률(t+lag)).")



def _lag_heatmap_ui(price_df: pd.DataFrame, feats_raw: dict[str, pd.DataFrame], interval: str):
    st.markdown("### 🔥 리드/래그 상관 히트맵")

    # 컨트롤
    c1, c2 = st.columns(2)
    with c1:
        k = st.selectbox(
            "미래 수익률 기간 k (return_period)",
            [1, 2, 4, 6, 12, 24],
            index={ "15m":2, "1h":2, "4h":1, "1d":0 }.get(interval, 2),
            help="r(t→t+k). 예: 15m에서 k=4는 1시간 후 수익률"
        )
    with c2:
        L = st.slider(
            "라그/리드 범위 (±L 스텝)",
            min_value=6, max_value=96, value=24, step=2,
            help="x축 = lag. 음수: 피처가 선행, 양수: 피처가 후행"
        )
    lags = list(range(-int(L), int(L)+1))

    # 대상 피처 목록 (raw 기준 이름: (키, 컬럼, 표시명))
    specs = [
        ("funding", "fundingRate", "Funding Rate (%)"),
        ("oi", "openInterest", "Open Interest"),
        ("top_acc", "longShortRatio", "Top L/S (Accounts)"),
        ("top_pos", "longShortRatio", "Top L/S (Positions)"),
        ("taker_ratio", "buySellRatio", "Taker Buy/Sell Ratio"),
    ]

    rows = []
    labels = []
    best_rows = []

    for key, col, label in specs:
        src = feats_raw.get(key)
        if src is None or src.empty:
            continue

        # 가격 축에 asof 정렬
        aligned = _align_asof(price_df, src, col)

        # (상관에 단위는 영향 없지만, 표시 일관을 위해 funding은 %로 변환)
        if key == "funding" and "value" in aligned:
            aligned["value"] = aligned["value"] * 100.0

        if aligned.dropna(subset=["value"]).empty:
            continue

        tmp = pd.DataFrame({"time": aligned["time"], label: aligned["value"]})
        df = corr.feature_return_lag_corr(
            price_df, tmp, feature_col=label, return_period=int(k), lags=lags
        )
        if df is None or df.empty or "pearson" not in df:
            continue

        # 히트맵용 행(피처 1개)
        pearson = df.set_index("lag")["pearson"].reindex(lags).astype(float)
        rows.append(pearson.values.tolist())
        labels.append(label)

        # 베스트 lag/r 기록
        best = df.iloc[df["pearson"].abs().argmax()]
        best_rows.append({
            "feature": label,
            "best_lag": int(best["lag"]),
            "best_r": float(best["pearson"]),
            "r@0": float(df.loc[df["lag"]==0, "pearson"].iloc[0]) if (df["lag"]==0).any() else None,
        })

    if not rows:
        st.info("유효한 피처가 없어 히트맵을 만들 수 없습니다.")
        return

    # 히트맵
    fig = go.Figure(data=go.Heatmap(
        z=rows, x=lags, y=labels,
        colorscale="RdBu", zmid=0, colorbar=dict(title="Pearson r")
    ))
    fig.update_layout(
        title=f"리드/래그 상관 히트맵 (k={k})",
        xaxis_title="lag (음수=피처 선행, 양수=후행)",
        yaxis_title="feature",
        margin=dict(t=50, b=10, l=10, r=10), height=360 + 24*len(labels)
    )
    st.plotly_chart(fig, use_container_width=True)

    # 베스트 라그 표
    if best_rows:
        st.dataframe(
            pd.DataFrame(best_rows).sort_values("feature"),
            use_container_width=True
        )
        st.caption("참고: lag<0이면 피처가 미래 수익률을 선행(예측력 가능성), lag>0이면 후행.")



# ── 이벤트 스터디 ───────────────────────────────────────────────────────────

def _event_indices_from_times(price_df: pd.DataFrame, event_times: pd.Series, L: int) -> list[int]:
    """event_times(UTC)을 가격 그리드 인덱스로 매핑. 좌/우 L 스텝 범위가 넘치는 이벤트는 제외."""
    if event_times is None or len(event_times) == 0:
        return []
    times = price_df["time"].to_numpy()
    idxs: list[int] = []
    for t in pd.to_datetime(event_times).to_numpy():
        i = int(np.searchsorted(times, t, side="left"))
        if i - L < 0 or i + L >= len(times):
            continue
        idxs.append(i)
    return idxs


def _cumret_window(logp: np.ndarray, center: int, L: int) -> np.ndarray | None:
    """중심(center)을 기준으로 [-L, +L] 구간의 누적 로그수익률 벡터(길이 2L+1)."""
    s = center - L
    e = center + L
    if s < 0 or e >= len(logp):
        return None
    seg = logp[s:e+1]
    base = seg[L]
    return seg - base


def _event_study_ui(price_df: pd.DataFrame, feats_raw: dict[str, pd.DataFrame], interval: str):
    st.markdown("### 🎯 이벤트 스터디")
    c1, c2, c3 = st.columns(3)
    with c1:
        etype = st.selectbox("이벤트 유형", ["Funding 정산시각", "피처 극단 진입"], index=0)
    with c2:
        default_L = {"15m": 16, "1h": 24, "4h": 12, "1d": 7}.get(interval, 24)
        L = st.slider("윈도우 L(좌/우 스텝)", 4, 96, value=default_L, step=1,
                      help="이벤트를 중심으로 [-L, +L] 누적수익(%) 곡선을 봅니다.")
    with c3:
        agg = st.selectbox("집계", ["mean", "median"], index=0,
                           help="여러 이벤트의 평균 또는 중앙값 곡선")

    event_indices: list[int] = []
    label = ""

    if etype == "Funding 정산시각":
        f = feats_raw.get("funding")
        if f is None or f.empty:
            st.info("펀딩 히스토리가 부족합니다.")
            return
        event_indices = _event_indices_from_times(price_df, f["time"], L)
        label = "Funding Settle"
    else:
        feat_map = {
            "Funding Rate (%)": ("funding", "fundingRate"),
            "Open Interest": ("oi", "openInterest"),
            "Top L/S (Accounts)": ("top_acc", "longShortRatio"),
            "Top L/S (Positions)": ("top_pos", "longShortRatio"),
            "Taker Buy/Sell Ratio": ("taker_ratio", "buySellRatio"),
        }
        c4, c5, c6 = st.columns(3)
        with c4:
            flabel = st.selectbox("피처", list(feat_map.keys()), index=1)
        with c5:
            side = st.selectbox("방향", ["상위 진입", "하위 진입"], index=0,
                                help="상위=상위 분위 경계 돌파, 하위=하위 분위 하향 돌파")
        with c6:
            q = st.selectbox("분위 경계", [0.9, 0.95], index=0,
                              help="예: 0.9=상위 10% 경계")
        key, col = feat_map[flabel]
        src = feats_raw.get(key)
        if src is None or src.empty:
            st.info("피처 데이터가 부족합니다.")
            return
        aligned = _align_asof(price_df, src, col)
        s = aligned["value"].copy()
        # funding은 % 스케일로 임계선 계산
        if key == "funding":
            s = s * 100.0
        thr = s.quantile(q if side == "상위 진입" else (1 - q))
        cond_now = (s >= thr) if side == "상위 진입" else (s <= thr)
        cond_prev = cond_now.shift(1).fillna(False)
        enter = cond_now & (~cond_prev)  # 진입 순간만 이벤트로
        times = aligned.loc[enter, "time"]
        event_indices = _event_indices_from_times(price_df, times, L)
        label = f"{flabel} {'↑' if side=='상위 진입' else '↓'}({int(q*100)}%)"

    if not event_indices:
        st.info("이벤트가 윈도우 내에 충분하지 않습니다.")
        return

    logp = np.log(price_df["close"].to_numpy(dtype=float))
    wins = []
    for i in event_indices:
        w = _cumret_window(logp, i, L)
        if w is not None:
            wins.append(w)
    if not wins:
        st.info("이벤트 윈도우가 없습니다.")
        return

    M = np.vstack(wins)  # (n_events, 2L+1)
    x = np.arange(-L, L+1)

    if agg == "mean":
        y = M.mean(axis=0)
        se = M.std(axis=0, ddof=1) / np.sqrt(M.shape[0])
    else:
        y = np.median(M, axis=0)
        se = None

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=y*100.0, mode="lines", name="cumret(%)"))
    if se is not None:
        upper = (y + 1.96*se) * 100.0
        lower = (y - 1.96*se) * 100.0
        fig.add_trace(go.Scatter(x=x, y=upper, mode="lines", name="+1.96·SE", line=dict(width=0)))
        fig.add_trace(go.Scatter(x=x, y=lower, mode="lines", name="-1.96·SE", fill="tonexty", line=dict(width=0)))
    fig.update_layout(
        title=f"이벤트 스터디 — {label} (N={M.shape[0]})",
        xaxis_title="event lag (스텝)", yaxis_title="누적 수익률(%)",
        hovermode="x unified", height=380, margin=dict(t=50, b=10, l=10, r=10)
    )
    st.plotly_chart(fig, use_container_width=True)



def _rolling_corr_ui(price_df: pd.DataFrame, feats_raw: dict[str, pd.DataFrame], interval: str):
    st.markdown("### 🔄 롤링 상관 (피처 vs 미래수익)")
    # 컨트롤
    feat_map = {
        "Funding Rate (%)": ("funding", "fundingRate", 100.0),  # 표시는 %, 상관엔 스케일 영향 X
        "Open Interest": ("oi", "openInterest", 1.0),
        "Top L/S (Accounts)": ("top_acc", "longShortRatio", 1.0),
        "Top L/S (Positions)": ("top_pos", "longShortRatio", 1.0),
        "Taker Buy/Sell Ratio": ("taker_ratio", "buySellRatio", 1.0),
    }
    c1, c2, c3 = st.columns(3)
    with c1:
        flabel = st.selectbox("피처", list(feat_map.keys()), index=1, key="rc_feat")
    with c2:
        k = st.number_input("미래 수익 k(스텝)", min_value=1, max_value=96,
                            value={"15m":4,"1h":4,"4h":6,"1d":1}.get(interval,4),
                            help="r(t→t+k). 15m에서 4는 1시간 후 수익", key="rc_k")
    with c3:
        win = st.number_input("롤링 윈도 W(스텝)", min_value=10, max_value=500,
                              value={"15m":96,"1h":168,"4h":84,"1d":30}.get(interval,96),
                              help="W 스텝 이동창. 예: 1h에서 168=1주", key="rc_win")

    key, col, fac = feat_map[flabel]
    src = feats_raw.get(key)
    if src is None or src.empty:
        st.info("피처 데이터가 부족합니다.")
        return

    # 1) 피처를 가격축에 asof 정렬
    feat = _align_asof(price_df, src, col)
    if feat.dropna(subset=["value"]).empty:
        st.info("유효 피처 값이 없습니다.")
        return

    # 2) 미래 수익률 r(t→t+k)
    fwd_ret = np.log(price_df["close"].shift(-int(k)) / price_df["close"])
    df = price_df[["time"]].copy()
    df["feat"] = feat["value"].to_numpy()
    df["fwd_ret"] = fwd_ret.to_numpy()
    df = df.dropna()

    if df.empty or len(df) < win:
        st.info("표본이 롤링 윈도보다 적습니다.")
        return

    # 3) 롤링 상관
    rc = df["feat"].rolling(int(win)).corr(df["fwd_ret"])

    # 4) 시각화 — 0 위/아래 색 분리(간단)
    # 4) 시각화 — 0 교차점 보간해서 매끄럽게
    rc_s = rc.reset_index(drop=True)
    base = pd.DataFrame({"time": df["time"].iloc[rc_s.index].values, "r": rc_s.values}).dropna()

    # 0-cross 보간 포인트 삽입
    rows = [base.iloc[0].to_dict()]
    for i in range(1, len(base)):
        r0, r1 = base.iloc[i - 1]["r"], base.iloc[i]["r"]
        t0, t1 = base.iloc[i - 1]["time"], base.iloc[i]["time"]
        if r0 * r1 < 0:  # 부호가 바뀌면 0 교차
            frac = abs(r0) / (abs(r0) + abs(r1))  # 선형비중
            tc = t0 + (t1 - t0) * frac  # 교차 시각
            rows.append({"time": tc, "r": 0.0})
        rows.append(base.iloc[i].to_dict())

    xy = pd.DataFrame(rows).sort_values("time").reset_index(drop=True)
    pos = xy["r"].where(xy["r"] >= 0)
    neg = xy["r"].where(xy["r"] <= 0)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=xy["time"], y=pos, mode="lines", name="r ≥ 0", line=dict(color="#86efac", width=2)))
    fig.add_trace(go.Scatter(x=xy["time"], y=neg, mode="lines", name="r ≤ 0", line=dict(color="#fecaca", width=2)))
    fig.add_hline(y=0, line=dict(width=1, dash="dot", color="rgba(0,0,0,0.45)"))
    fig.update_layout(
        title=f"롤링 상관 — {flabel} vs r(t→t+{int(k)}) [W={int(win)}]",
        xaxis_title="time", yaxis_title="Pearson r",
        hovermode="x unified", height=320, margin=dict(t=50, b=10, l=10, r=10)
    )
    st.plotly_chart(fig, use_container_width=True)

    # 5) 요약(최근값/최대/최소/유효구간 비율)
    tail = rc.dropna()
    if not tail.empty:
        last = float(tail.iloc[-1])
        rmax = float(tail.max()); rmin = float(tail.min())
        strong = float((tail.abs() > 0.2).mean())  # |r|>0.2 비율
        st.caption(f"최근 r={last:+.3f} · 최대 {rmax:+.3f} / 최소 {rmin:+.3f} · |r|>0.2 비율={strong:.0%}")


def _oi_quadrant_scatter_ui(price_df: pd.DataFrame, feats_raw: dict[str, pd.DataFrame], interval: str):
    st.markdown("### ⭕ ΔOI vs 미래수익 (사분면)")
    if feats_raw.get("oi") is None or feats_raw["oi"].empty:
        st.info("OI 데이터가 부족합니다.")
        return

    c1, c2 = st.columns(2)
    with c1:
        k = st.number_input("미래 수익 k(스텝)", min_value=1, max_value=96,
                            value={"15m":4,"1h":4,"4h":6,"1d":1}.get(interval,4), key="oi_k")
    with c2:
        mode = st.selectbox("ΔOI 정의", ["diff", "pct_change"], index=1,
                            help="diff=절대 변화량, pct_change=증가율", key="oi_mode")

    # 1) OI를 가격축에 asof 정렬
    aligned = _align_asof(price_df, feats_raw["oi"], "openInterest")
    s = aligned["value"].astype(float)

    # 2) ΔOI
    d_oi = s.pct_change() if mode == "pct_change" else s.diff()

    # 3) 미래 수익 r(t→t+k)
    fwd_ret = np.log(price_df["close"].shift(-int(k)) / price_df["close"])

    df = price_df[["time"]].copy()
    df["d_oi"] = d_oi.to_numpy()
    df["fwd"] = fwd_ret.to_numpy()
    df = df.dropna()
    if df.empty:
        st.info("유효 표본이 없습니다.")
        return

    # 4) 산점도 〈사분면 파스텔 색 + 추세선〉
    fig = go.Figure()

    # 사분면별 그룹
    groups = {
        "+ΔOI & +ret": df[(df["d_oi"] > 0) & (df["fwd"] > 0)],
        "-ΔOI & +ret": df[(df["d_oi"] < 0) & (df["fwd"] > 0)],
        "-ΔOI & -ret": df[(df["d_oi"] < 0) & (df["fwd"] < 0)],
        "+ΔOI & -ret": df[(df["d_oi"] > 0) & (df["fwd"] < 0)],
    }
    # 파스텔 팔레트
    palette = {
        "+ΔOI & +ret": "#9AD1B9",  # pastel green
        "-ΔOI & +ret": "#A8C5F0",  # pastel blue
        "-ΔOI & -ret": "#F5A6A6",  # pastel red
        "+ΔOI & -ret": "#F7CBA7",  # pastel orange
    }

    # 사분면별 산점도
    for name, g in groups.items():
        if g.empty:
            continue
        fig.add_trace(go.Scatter(
            x=g["d_oi"], y=g["fwd"] * 100.0,
            mode="markers",
            name=f"{name} (N={len(g)})",
            marker=dict(size=6, opacity=0.75, color=palette[name]),
            text=g["time"].dt.strftime("%Y-%m-%d %H:%M"),
            hovertemplate="ΔOI=%{x:.4f}<br>ret=%{y:.3f}%<br>%{text}<extra></extra>"
        ))

    # 0 축
    fig.add_vline(x=0, line=dict(width=1, dash="dot"))
    fig.add_hline(y=0, line=dict(width=1, dash="dot"))

    # 전체 추세선 (최소 2개 표본일 때)
    if len(df) >= 2:
        xv = df["d_oi"].to_numpy()
        yv = (df["fwd"] * 100.0).to_numpy()
        m, b = np.polyfit(xv, yv, 1)
        xline = np.linspace(df["d_oi"].min(), df["d_oi"].max(), 60)
        yline = m * xline + b
        fig.add_trace(go.Scatter(
            x=xline, y=yline, mode="lines",
            name=f"trend (slope={m:.3g})",
            line=dict(width=2, dash="dash", color="#7E8BA3")
        ))

    fig.update_layout(
        title=f"ΔOI vs r(t→t+{int(k)})",
        xaxis_title=("ΔOI (pct_change)" if mode == "pct_change" else "ΔOI (diff)"),
        yaxis_title="forward return (%)",
        height=360, margin=dict(t=50, b=10, l=10, r=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1.0),
        template="plotly_white"
    )
    st.plotly_chart(fig, use_container_width=True)

    # 5) 사분면 통계
    q1 = (df["d_oi"]>0) & (df["fwd"]>0)
    q2 = (df["d_oi"]<0) & (df["fwd"]>0)
    q3 = (df["d_oi"]<0) & (df["fwd"]<0)
    q4 = (df["d_oi"]>0) & (df["fwd"]<0)
    stats = pd.DataFrame({
        "quadrant": ["+ΔOI & +ret", "-ΔOI & +ret", "-ΔOI & -ret", "+ΔOI & -ret"],
        "N": [q1.sum(), q2.sum(), q3.sum(), q4.sum()],
        "mean_ret_%": [df.loc[q1,"fwd"].mean()*100.0,
                       df.loc[q2,"fwd"].mean()*100.0,
                       df.loc[q3,"fwd"].mean()*100.0,
                       df.loc[q4,"fwd"].mean()*100.0],
    })
    st.dataframe(stats, use_container_width=True)
    st.caption("우상(+/+)·우하(+/-) 비중과 평균수익을 비교해 추세/되돌림 성향을 점검합니다.")


def _quick_signal_tester_ui(price_df: pd.DataFrame, feats_raw: dict[str, pd.DataFrame], interval: str):
    st.markdown("### ⚡ 퀵 시그널 테스트 (조건 → k-스텝 기대수익)")

    feat_map = {
        "Funding Rate (%)": ("funding", "fundingRate", 100.0),  # 임계 계산은 % 스케일
        "Open Interest": ("oi", "openInterest", 1.0),
        "Top L/S (Accounts)": ("top_acc", "longShortRatio", 1.0),
        "Top L/S (Positions)": ("top_pos", "longShortRatio", 1.0),
        "Taker Buy/Sell Ratio": ("taker_ratio", "buySellRatio", 1.0),
    }
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        flabel = st.selectbox("피처", list(feat_map.keys()), index=1, key="qs_feat")
    with c2:
        mode = st.selectbox("임계 방식", ["분위(quantile)", "z-score"], index=0, key="qs_mode",
                            help="분위는 상/하위 비율로, z-score는 표준화 기준으로 임계 설정")
    with c3:
        side = st.selectbox("방향", ["상위가 조건", "하위가 조건"], index=0, key="qs_side")
    with c4:
        k = st.number_input("미래 수익 k(스텝)", min_value=1, max_value=96,
                            value={"15m":4,"1h":4,"4h":6,"1d":1}.get(interval,4), key="qs_k")

    # 임계 파라미터
    c5, c6 = st.columns(2)
    thr_q = 0.8
    thr_z = 1.0
    with c5:
        if mode == "분위(quantile)":
            thr_q = st.slider("분위 임계 (상위 x / 하위 1-x)", 0.50, 0.99, 0.80, 0.01, key="qs_thr_q")
    with c6:
        if mode == "z-score":
            thr_z = st.slider("z-score 임계 |z| ≥", 0.0, 3.0, 1.0, 0.1, key="qs_thr_z")

    key, col, fac = feat_map[flabel]
    src = feats_raw.get(key)
    if src is None or src.empty:
        st.info("피처 데이터가 부족합니다.")
        return

    # 1) 피처를 가격 축에 asof 정렬
    feat = _align_asof(price_df, src, col)
    if feat.dropna(subset=["value"]).empty:
        st.info("유효 피처 값이 없습니다.")
        return

    s = feat["value"].astype(float)
    if key == "funding":
        s = s * fac  # % 스케일

    # 2) 조건 마스크
    if mode == "분위(quantile)":
        thr = s.quantile(thr_q if side == "상위가 조건" else (1 - thr_q))
        cond = (s >= thr) if side == "상위가 조건" else (s <= thr)
    else:
        z = (s - s.mean()) / s.std(ddof=1)
        cond = (z >= thr_z) if side == "상위가 조건" else (z <= -thr_z)

    # “진입 순간만” 보고 싶으면 아래 주석 해제
    cond = cond & (~cond.shift(1).fillna(False))

    # 3) k-스텝 미래수익
    fr = np.log(price_df["close"].shift(-int(k)) / price_df["close"])
    df = price_df[["time"]].copy()
    df["cond"] = cond.to_numpy()
    df["fwd"] = fr.to_numpy()
    df = df.dropna()

    if df["cond"].sum() == 0:
        st.info("조건을 만족하는 표본이 없습니다. 임계를 낮춰 보세요.")
        return

    sub = df.loc[df["cond"]]
    N = int(sub.shape[0])
    mean = float(sub["fwd"].mean())
    std = float(sub["fwd"].std(ddof=1))
    se = std / np.sqrt(N) if N > 0 else np.nan
    tstat = mean / se if se and se > 0 else np.nan
    hit = float((sub["fwd"] > 0).mean())

    # 표
    st.dataframe(pd.DataFrame([{
        "samples": N,
        "hit(>0)": f"{hit:.1%}",
        f"mean r(t→t+{int(k)}) [%]": mean * 100.0,
        "t-stat": tstat,
        "uncond mean [%]": float(df["fwd"].mean()) * 100.0
    }]), use_container_width=True)

    # 막대 비교
    fig = go.Figure()
    fig.add_trace(go.Bar(name="조건 충족 평균", x=["conditional"], y=[mean*100.0]))
    fig.add_trace(go.Bar(name="무조건 평균", x=["unconditional"], y=[float(df['fwd'].mean())*100.0]))
    fig.update_layout(barmode="group", title=f"{flabel} — 조건부 vs 무조건 평균 (k={int(k)})",
                      yaxis_title="forward return (%)", height=320, margin=dict(t=50,b=10,l=10,r=10))
    st.plotly_chart(fig, use_container_width=True)

    # (옵션) 단순 에쿼티: 조건 충족 시점의 수익만 누적
    eq = (df["fwd"] * df["cond"].astype(float)).fillna(0.0).cumsum() * 100.0

    # ▶ 고정(확대/이동 불가) 라인 차트로 교체
    fig_eq = go.Figure()
    fig_eq.add_trace(go.Scatter(
        x=df.loc[eq.index, "time"],
        y=eq.values,
        mode="lines",
        name="cumulative PnL (%)"
    ))
    # 축 줌/팬 완전 고정
    fig_eq.update_xaxes(fixedrange=True)
    fig_eq.update_yaxes(fixedrange=True)

    fig_eq.update_layout(
        title="Cumulative PnL (%)",
        xaxis_title="time",
        yaxis_title="%",
        height=300,
        margin=dict(t=40, b=10, l=10, r=10)
    )

    # 인터랙션 끄는 설정: 모드바/스크롤줌/더블클릭 리셋 비활성화
    st.plotly_chart(
        fig_eq,
        use_container_width=True,
        config={
            "displayModeBar": False,
            "scrollZoom": False,
            "doubleClick": False
        }
    )



def view(inputs: Inputs):
    st.subheader("📊 가격 & 파생지표 스택 차트 (1개월)")
    price_df = load_price_1m(inputs.symbol, inputs.interval)

    # 원본 로드
    feats_raw = {
        "funding": load_funding(inputs.symbol),
        "oi": load_oi(inputs.symbol, inputs.interval),
        "top_acc": load_top_ls(inputs.symbol, inputs.interval, metric="accounts"),
        "top_pos": load_top_ls(inputs.symbol, inputs.interval, metric="positions"),
        "taker_ratio": load_taker_ratio(inputs.symbol, inputs.interval),
    }

    if price_df.empty:
        st.error("가격 데이터가 없습니다.")
        return

    # 가격 타임스탬프에 asof로 정렬한 버전(시각화/상관 모두 동일 축 사용)
    feats_aligned = {
        "funding": _align_asof(price_df, feats_raw.get("funding"), "fundingRate"),
        "oi": _align_asof(price_df, feats_raw.get("oi"), "openInterest"),
        "top_acc": _align_asof(price_df, feats_raw.get("top_acc"), "longShortRatio"),
        "top_pos": _align_asof(price_df, feats_raw.get("top_pos"), "longShortRatio"),
        "taker_ratio": _align_asof(price_df, feats_raw.get("taker_ratio"), "buySellRatio"),
    }

    # Funding은 시각화용으로 % 단위로 변환 (거래소 표기와 일치)
    if feats_aligned["funding"] is not None and not feats_aligned["funding"].empty:
        feats_aligned["funding"]["value"] = feats_aligned["funding"]["value"] * 100

    # 지표 설명 도움말
    with st.expander("ℹ️ 지표 설명"):
        st.markdown(
            """
            - **Funding Rate (%)**: 8시간마다 교환되는 자금조달비. **양수**면 롱→숏 지급, **음수**면 숏→롱 지급. 표기는 **거래소와 동일한 % 단위**(소수점 4자리).
            - **Open Interest (OI)**: 미결제약정 규모. 포지션이 **쌓이면↑**, 청산·포기되면 **줄어듭니다**. (원시 단위는 거래소 API 기준)
            - **Top Traders Long/Short — Accounts/Positions**: 상위 트레이더의 **롱:숏 비율**. **1 초과**면 롱 측이 우세.
            - **Taker Buy/Sell Ratio**: 시장가(공격적) 매수/매도 체결량 비율. **1 초과**면 매수 우위.
            """
        )


    cov_start, cov_end = _coverage_range(price_df, feats_aligned)
    st.caption(f"표시 구간: {cov_start} → {cov_end} (모든 파생/가격의 교집합 구간)")

    # Optional 디버그 표
    if st.checkbox("디버그: 각 시리즈 커버리지/결측 보기", value=False):
        rows = []
        def _row(name: str, df: pd.DataFrame):
            if df is None or df.empty:
                rows.append({"series": name, "rows": 0, "start": None, "end": None, "non_null": 0, "nulls": 0})
                return
            valid = df.dropna(subset=["value"]) if "value" in df.columns else df.dropna()
            rows.append({
                "series": name,
                "rows": len(df),
                "start": valid["time"].min() if not valid.empty else None,
                "end": valid["time"].max() if not valid.empty else None,
                "non_null": int(valid.shape[0]) if not valid.empty else 0,
                "nulls": int(df.shape[0] - (valid.shape[0] if not valid.empty else 0)),
            })
        _row("price(time only)", price_df[["time"]].assign(value=1.0))
        for k,v in feats_aligned.items():
            _row(k, v)
        st.dataframe(pd.DataFrame(rows), use_container_width=True)

    _stacked_chart(price_df, feats_aligned)
    # 상관은 원본을 align해서 계산
    _corr_table(price_df, feats_raw, inputs.interval, inputs.symbol)

    _quantile_analysis_ui(price_df, feats_raw, inputs.interval)

    _lag_heatmap_ui(price_df, feats_raw, inputs.interval)

    _event_study_ui(price_df, feats_raw, inputs.interval)

    _rolling_corr_ui(price_df, feats_raw, inputs.interval)

    _oi_quadrant_scatter_ui(price_df, feats_raw, inputs.interval)

    _quick_signal_tester_ui(price_df, feats_raw, inputs.interval)
