from __future__ import annotations
import numpy as np
import pandas as pd


def total_return(equity: pd.Series) -> float:
    """최종 자산배율 - 1 (예: 0.25 == +25%)"""
    return float(equity.iloc[-1] / equity.iloc[0] - 1.0)


def cagr(equity: pd.Series, periods_per_year: int) -> float:
    """
    CAGR (연복리수익률)
    equity는 동일 간격 시계열(1h, 4h, 1d 등) 기준이어야 함.
    """
    n_periods = len(equity) - 1
    if n_periods <= 0:
        return 0.0
    years = n_periods / periods_per_year
    if years == 0:
        return 0.0
    return float((equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1.0)


def max_drawdown(equity: pd.Series) -> float:
    """MDD (음수 값, 예: -0.35 == -35%)"""
    peak = equity.cummax()
    dd = equity / peak - 1.0
    return float(dd.min())


def sharpe_ratio(returns_per_period: pd.Series, risk_free: float = 0.0, periods_per_year: int = 252) -> float:
    """
    샤프지수 (연율화)
    - returns_per_period: 각 기간 수익률(예: equity.pct_change())
    - risk_free: 기간 수익률 기준의 무위험 수익률(보통 0)
    """
    excess = returns_per_period - risk_free
    mu = excess.mean()
    sigma = excess.std(ddof=1)
    if sigma == 0 or np.isnan(sigma):
        return 0.0
    return float((mu / sigma) * np.sqrt(periods_per_year))


def win_rate(trade_returns: list[float]) -> float:
    """트레이드 승률 (0~1) — trade_returns는 각 거래의 (ret-1) 값"""
    if not trade_returns:
        return 0.0
    wins = sum(1 for r in trade_returns if r > 0)
    return wins / len(trade_returns)


def summarize(equity: pd.Series, trade_returns: list[float], periods_per_year: int) -> dict:
    per_ret = equity.pct_change().dropna()
    return {
        "total_return": total_return(equity),
        "cagr": cagr(equity, periods_per_year),
        "mdd": max_drawdown(equity),
        "sharpe": sharpe_ratio(per_ret, risk_free=0.0, periods_per_year=periods_per_year),
        "trades": len(trade_returns),
        "win_rate": win_rate(trade_returns),
    }
