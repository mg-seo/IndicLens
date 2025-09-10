from backtest.data import fetch_klines
from backtest.signals import evaluate_rule
from backtest.engine import backtest_long_only


if __name__ == "__main__":
    df = fetch_klines("BTCUSDT", "1h", 500)

    # 단순 전략: EMA12 ↗ EMA26 진입, EMA12 ↘ EMA26 청산
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

    bt = backtest_long_only(df, entry_sig, exit_sig, fee=0.001, slippage=0.001, cooldown=1)
    print(bt.tail(10))
    print("최종 자산배율:", bt["equity"].iloc[-1])
