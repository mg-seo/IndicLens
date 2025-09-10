from backtest.data import fetch_klines, fetch_funding_rate
from backtest.correlation import feature_return_lag_corr

if __name__ == "__main__":
    # 1시간봉 1000개 (약 42일)
    price = fetch_klines("BTCUSDT", "1h", 1000)
    # 펀딩비 최근 200개
    fr = fetch_funding_rate("BTCUSDT", 200)

    res = feature_return_lag_corr(price, fr, feature_col="fundingRate", return_period=1, lags=range(-48, 49))
    print(res.head())
    print(res.tail())
    # 상관 최대/최소 라그 확인
    best_p = res.loc[res["pearson"].abs().idxmax()]
    best_s = res.loc[res["spearman"].abs().idxmax()]
    print("\n[최대 |pearson|] lag={lag}, pearson={pearson:.4f}, n={n}".format(**best_p))
    print("[최대 |spearman|] lag={lag}, spearman={spearman:.4f}, n={n}".format(**best_s))
