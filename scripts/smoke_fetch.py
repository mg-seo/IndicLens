from backtest.data import fetch_klines

if __name__ == "__main__":
    df = fetch_klines("BTCUSDT", "1h", 50)
    print(df.head())
    print("rows", len(df))