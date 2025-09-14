import pandas as pd
from backtest import data as d
from ui.sidebar import now_utc

def _info(df, name, time_col="time"):
    if df is None or df.empty:
        print(f"{name:15s} | EMPTY")
        return
    t = df[time_col]
    step = t.diff().dropna()
    med = step.median() if not step.empty else pd.Timedelta(0)
    print(f"{name:15s} | rows={len(df):4d} | start={t.min()} | end={t.max()} | median_step={med}")

def smoke(symbol="BTCUSDT", intervals=("1h","1d")):
    end = pd.Timestamp(now_utc())
    start = end - pd.DateOffset(months=1)
    for iv in intervals:
        print(f"\n=== interval {iv} ===")
        price = d.fetch_futures_klines_range(symbol, iv, start, end)
        _info(price, "price")

        funding = d.fetch_funding_rate_range(symbol, start, end)  # 8h 버킷
        _info(funding, "funding")

        oi = d.fetch_open_interest_range(symbol, iv, start, end)
        _info(oi, "openInterest")

        acc = d.fetch_top_traders_long_short_range(symbol, iv, start, end, metric="accounts")
        _info(acc, "topLS_accounts")

        pos = d.fetch_top_traders_long_short_range(symbol, iv, start, end, metric="positions")
        _info(pos, "topLS_positions")

        taker = d.fetch_taker_buy_sell_range(symbol, iv, start, end)
        _info(taker, "taker_ratio")

if __name__ == "__main__":
    smoke()
