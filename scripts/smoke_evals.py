from backtest.data import fetch_klines
from backtest.signals import evaluate_rule
from backtest.engine import backtest_long_only
from backtest.evals import summarize

# 타임프레임별 연율화 상수(대략)
PER_YEAR = {
    "1h": 24 * 365,   # 8760
    "4h": 6 * 365,    # 2190
    "1d": 252,        # 거래일 기준; 크립토는 365 써도 됨
}

if __name__ == "__main__":
    interval = "1h"
    df = fetch_klines("BTCUSDT", interval, 1000)

    entry_rule = {
        "op": "crossover",
        "left":  {"type":"indicator","name":"ema","params":{"span":12},"source":"close"},
        "right": {"type":"indicator","name":"ema","params":{"span":26},"source":"close"}
    }
    exit_rule = {
        "op": "crossunder",
        "left":  {"type":"indicator","name":"ema","params":{"span":12},"source":"close"},
        "right": {"type":"indicator","name":"ema","params":{"span":26},"source":"close"}
    }

    entry_sig = evaluate_rule(entry_rule, df)
    exit_sig  = evaluate_rule(exit_rule, df)

    bt_df, trades = backtest_long_only(df, entry_sig, exit_sig, fee=0.001, slippage=0.001, cooldown=1)

    metrics = summarize(bt_df["equity"], trades, periods_per_year=PER_YEAR[interval])
    print("=== 성과 요약 ===")
    for k, v in metrics.items():
        print(f"{k}: {v:.4f}" if isinstance(v, float) else f"{k}: {v}")
