from backtest.data import (
    fetch_funding_rate,
    fetch_open_interest,
    fetch_global_long_short,
    fetch_top_traders_long_short,
    fetch_taker_buy_sell,
)

if __name__ == "__main__":
    print("=== Funding Rate ===")
    fr = fetch_funding_rate("BTCUSDT", 20)
    print(fr.tail(3))

    print("\n=== Open Interest (1h) ===")
    oi = fetch_open_interest("BTCUSDT", "1h", 20)
    print(oi.tail(3))

    print("\n=== Global Long/Short (1h) ===")
    gls = fetch_global_long_short("BTCUSDT", "1h", 20)
    print(gls.tail(3))

    print("\n=== Top Traders (accounts, 1h) ===")
    tt_acc = fetch_top_traders_long_short("BTCUSDT", "1h", 20, metric="accounts")
    print(tt_acc.tail(3))

    print("\n=== Taker Buy/Sell (1h) ===")
    tbs = fetch_taker_buy_sell("BTCUSDT", "1h", 20)
    print(tbs.tail(3))
