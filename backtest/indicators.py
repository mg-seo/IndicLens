from __future__ import annotations
import numpy as np
import pandas as pd


def sma(s: pd.Series, window: int) -> pd.Series:
    """
    단순이동평균 (Simple Moving Average)
    NaN 구간을 명확히 하기 위해 min_periods=window 유지
    """
    return s.rolling(window, min_periods=window).mean()


def ema(s: pd.Series, span: int) -> pd.Series:
    """
    지수이동평균 (Exponential Moving Average)
    """
    return s.ewm(span=span, adjust=False).mean()


def rsi(s: pd.Series, period: int = 14) -> pd.Series:
    """
    RSI (Wider 방식)
    0~100 범위, period 구간 전까지는 NaN
    """
    delta = s.diff()

    up = np.where(delta > 0, delta, 0.0)
    down = np.where(delta < 0, -delta, 0.0)

    gain = pd.Series(up, index=s.index)
    loss = pd.Series(down, index=s.index)

    avg_gain = gain.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False, min_periods=period).mean()

    rs = avg_gain / avg_loss
    rsi_val = 100 - (100 / (1 + rs))
    return rsi_val


def macd(s: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """
    MACD 라인, 시그널, 히스토그램 반환
    columns: macd, signal, hist
    """
    ema_fast = ema(s, fast)
    ema_slow = ema(s, slow)
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line

    out = pd.DataFrame({
        'macd': macd_line,
        'signal': signal_line,
        'hist': hist,
    })
    return out


def bbands(s: pd.Series, window: int = 20, k: float = 2.0) -> pd.DataFrame:
    """
    볼린저 밴드
    columns: bb_upper, bb_mid, bb_lower
    """
    mid = sma(s, window)
    std = s.rolling(window=window, min_periods=window).std(ddof=0)
    upper = mid + k * std
    lower = mid - k * std

    out = pd.DataFrame({
        'bb_upper': upper,
        'bb_mid': mid,
        'bb_lower': lower,
    })
    return out