import pandas as pd


def backtest_long_only(price_df: pd.DataFrame,
                       entry_sig: pd.Series,
                       exit_sig: pd.Series | None = None,
                       fee: float = 0.001,
                       slippage: float = 0.001,
                       cooldown: int = 0) -> pd.DataFrame:
    """
    단순 롱 온리 백테스트 엔진 (MVP)
    - entry_sig: 진입 조건 (True 시 다음 캔들 시가 매수)
    - exit_sig: 청산 조건 (없으면 반대 시그널 없고 hold)
    - fee/slippage: 거래 비용 (비율)
    - cooldown: 청산 후 n 캔들 동안 재진입 금지
    """
    df = price_df.copy().reset_index(drop=True)
    df = df[["time", "open", "high", "low", "close"]].copy()

    # 룩어헤드 방지 → 다음 캔들 체결
    entry_sig = entry_sig.shift(1).fillna(False)
    exit_sig = exit_sig.shift(1).fillna(False) if exit_sig is not None else pd.Series(False, index=df.index)

    pos = 0
    entry_price = 0.0
    cool = 0
    trades = []
    equity = 1.0
    curve = []

    for i, row in df.iterrows():
        price = row["open"]

        # 쿨다운 관리
        if cool > 0:
            cool -= 1

        # 포지션 없는 상태
        if pos == 0:
            if entry_sig.iloc[i] and cool == 0:
                pos = 1
                entry_price = price * (1 + fee + slippage)
        else:
            # 청산 조건: exit_sig가 있으면 그때 청산, 아니면 entry_sig 반대
            if exit_sig.iloc[i] or entry_sig.iloc[i]:
                ret = (price * (1 - fee - slippage)) / entry_price
                equity *= ret
                trades.append(ret - 1.0)
                pos = 0
                entry_price = 0.0
                cool = cooldown

        curve.append(equity)

    df["equity"] = curve
    return df, trades
