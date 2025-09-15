# views/data_preview.py (새 파일 추천)
import io, pandas as pd, streamlit as st
from ui.sidebar import now_utc
from backtest import data as d

def _month():
    end = pd.Timestamp(now_utc()); start = end - pd.DateOffset(months=1)
    return start, end

def _preview_block(title, df, percent_cols=()):
    st.subheader(title)
    if df is None or df.empty:
        st.info("데이터 없음"); return
    # 보기 좋게 포맷
    styler = df.head(20).style.format({c:"{:.4f}" for c in df.columns if c not in percent_cols})
    st.dataframe(df.head(20), use_container_width=True)  # 가볍게는 이걸로
    # CSV 다운로드
    st.download_button("CSV 다운로드", df.to_csv(index=False).encode("utf-8"),
                       file_name=f"{title.replace(' ','_')}.csv", mime="text/csv")

def _excel_safe_df(df: pd.DataFrame) -> pd.DataFrame:
    """Excel에 쓰기 전에 tz-aware datetime -> tz-naive(UTC)로 변환."""
    out = df.copy()
    # tz 붙은 datetime 컬럼만 찾아서 변환
    for c in out.select_dtypes(include=["datetimetz"]).columns:
        # UTC 기준 값 유지한 채로 tz 정보만 제거
        out[c] = out[c].dt.tz_convert("UTC").dt.tz_localize(None)
        # (선택) 컬럼명에 표기 추가
        out.rename(columns={c: f"{c} (UTC)"}, inplace=True)
    return out


def view(symbol: str, interval: str):
    start, end = _month()
    price   = d.fetch_futures_klines_range(symbol, interval, start, end)
    funding = d.fetch_funding_rate_range(symbol, start, end)
    oi      = d.fetch_open_interest_range(symbol, interval, start, end)
    top_acc = d.fetch_top_traders_long_short_range(symbol, interval, start, end, metric="accounts")
    top_pos = d.fetch_top_traders_long_short_range(symbol, interval, start, end, metric="positions")
    taker   = d.fetch_taker_buy_sell_range(symbol, interval, start, end)

    tabs = st.tabs(["Price(선물Klines)", "Funding", "Open Interest",
                    "Top L/S (Accounts)", "Top L/S (Positions)", "Taker Buy/Sell Ratio"])

    with tabs[0]: _preview_block("Price Futures Klines", price)
    with tabs[1]:
        if funding is not None and not funding.empty:
            funding = funding.assign(fundingPct=funding["fundingRate"]*100)
        _preview_block("Funding Rate", funding, percent_cols=("fundingPct",))
    with tabs[2]: _preview_block("Open Interest", oi)
    with tabs[3]: _preview_block("Top L/S (Accounts)", top_acc)
    with tabs[4]: _preview_block("Top L/S (Positions)", top_pos)
    with tabs[5]: _preview_block("Taker Buy/Sell Ratio", taker)

    # 통합 XLSX 내보내기(시트별)
    if st.button("📘 전체 XLSX 내보내기"):
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="xlsxwriter") as xw:
            for name,df in {
                "price":price, "funding":funding, "open_interest":oi,
                "top_ls_accounts":top_acc, "top_ls_positions":top_pos, "taker_ratio":taker
            }.items():
                if df is not None and not df.empty:
                    df_xlsx = _excel_safe_df(df)
                    df_xlsx.to_excel(xw, index=False, sheet_name=name[:31])
        st.download_button("다운로드: crypto_samples.xlsx", buf.getvalue(),
                           file_name="crypto_samples.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
