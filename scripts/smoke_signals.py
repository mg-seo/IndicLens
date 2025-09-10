import json
from backtest.data import fetch_klines
from backtest.signals import evaluate_rule

if __name__ == "__main__":
    df = fetch_klines("BTCUSDT", "1h", 1000)

    rule = {
        "op": "crossover",
        "left": {"type": "indicator", "name": "close"},
        "right": {"type": "indicator", "name": "bbands", "params": {"window": 20, "k": 2}, "field": "bb_lower"}
    }

    sig = evaluate_rule(rule, df)
    print(sig.tail(20))
    print("True(시그널) 개수:", int(sig.sum()))
