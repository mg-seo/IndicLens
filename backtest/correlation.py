from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Iterable


def to_log_returns(close: pd.Series, period: int = 1) -> pd.Series:
    """
    로그 수익률 (기본 1기간)
    r_t = log(close_t / close_{t-period})
    """
    return np.log(close / close.shift(period))


def align_on_time(
    price_df: pd.DataFrame,
    feature_df: pd.DataFrame,
    price_col: str = "close",
    feature_col: str = None,
    how: str = "inner",
) -> pd.DataFrame:
    """
    time 컬럼(KST, tz-aware 가정) 기준으로 두 시계열을 병합.
    - price_df: columns = [time, open, high, low, close, ...]
    - feature_df: columns = [time, <feature_col>]
    """
    if feature_col is None:
        # feature_df의 time 제외 첫 번째 수치 컬럼 자동 탐색
        candidates = [c for c in feature_df.columns if c != "time"]
        if not candidates:
            raise ValueError("feature_df에 time 외 수치 컬럼이 없습니다.")
        feature_col = candidates[0]

    p = price_df[["time", price_col]].copy().rename(columns={price_col: "price"})
    f = feature_df[["time", feature_col]].copy().rename(columns={feature_col: "feature"})

    df = pd.merge(p, f, on="time", how=how).sort_values("time").reset_index(drop=True)
    return df


def lag_corr(
    feature: pd.Series,
    returns: pd.Series,
    lags: Iterable[int] = range(-48, 49),
    method_pearson: str = "pearson",
) -> pd.DataFrame:
    """
    라그 상관.
    규약: lag > 0 이면 feature(t) vs returns(t+lag) → returns.shift(-lag)
          lag < 0 이면 feature(t) vs returns(t-abs(lag)) → returns.shift(+abs(lag))
    """
    idx = feature.index.union(returns.index)
    feat = feature.reindex(idx)
    ret = returns.reindex(idx)

    rows = []
    for L in lags:
        if L > 0:
            r_shift = ret.shift(-L)
        elif L < 0:
            r_shift = ret.shift(abs(L))
        else:
            r_shift = ret

        pair = pd.concat([feat, r_shift], axis=1, keys=["feature", "returns"]).dropna()
        n = len(pair)
        if n >= 3:
            pearson = pair["feature"].corr(pair["returns"], method=method_pearson)
            spearman = pair["feature"].corr(pair["returns"], method="spearman")
        else:
            pearson = np.nan
            spearman = np.nan

        rows.append({"lag": L, "pearson": float(pearson) if pd.notna(pearson) else np.nan,
                     "spearman": float(spearman) if pd.notna(spearman) else np.nan,
                     "n": int(n)})

    out = pd.DataFrame(rows).sort_values("lag").reset_index(drop=True)
    return out


def feature_return_lag_corr(
    price_df: pd.DataFrame,
    feature_df: pd.DataFrame,
    feature_col: str = None,
    interval_per_year: int = None,  # 사용자는 안 넣어도 됨 (이 모듈에서는 미사용)
    return_period: int = 1,
    lags: Iterable[int] = range(-48, 49),
) -> pd.DataFrame:
    """
    편의 함수:
    - time으로 병합 → close로 log returns 계산 → 라그 상관 반환
    """
    df = align_on_time(price_df, feature_df, feature_col=feature_col)
    rets = to_log_returns(df["price"], period=return_period)
    return lag_corr(df["feature"], rets, lags=lags)
