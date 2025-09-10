from backtest.data import fetch_klines
from backtest import sma, ema, rsi, macd, bbands

if __name__ == '__main__':
    df = fetch_klines("BTCUSDT", "1h", 200)
    close = df["close"]

    df["SMA20"] = sma(close, 20)
    df["EMA20"] = ema(close, 20)
    df["RSI20"] = rsi(close, 14)

    macd_df = macd(close, 12, 26, 9)
    bb_df = bbands(close, 20, 2)

    out = df.join(macd_df).join(bb_df)
    print(out.tail(5))
