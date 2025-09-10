from backtest.data import fetch_klines
import time

if __name__ == "__main__":
    print("첫 호출 (API)")
    df1 = fetch_klines("BTCUSDT", "1h", 50, use_cache=True)
    print(df1.tail(2))

    print("\n두번째 호출 (캐시)")
    df2 = fetch_klines("BTCUSDT", "1h", 50, use_cache=True)
    print(df2.tail(2))

    print("\n캐시 TTL 테스트 (1초 TTL)")
    df3 = fetch_klines("BTCUSDT", "1h", 50, use_cache=True)
    time.sleep(2)
    from backtest.cache import load_cache
    expired = load_cache("klines_BTCUSDT_1h_50", max_age_sec=1)
    print("만료 후 캐시 반환:", expired is not None)
