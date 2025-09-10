from __future__ import annotations
import os
import time
import pandas as pd
from pathlib import Path

CACHE_DIR = Path("data/cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_path(name: str) -> Path:
    return CACHE_DIR / f"{name}.csv"


def save_cache(df: pd.DataFrame, name: str):
    """DataFrame을 CSV로 저장"""
    path = _cache_path(name)
    df.to_csv(path, index=False)


def load_cache(name: str, max_age_sec: int | None = None) -> pd.DataFrame | None:
    """
    캐시 로드 (없거나 TTL 초과 시 None 반환)
    - name: 캐시 파일 이름
    - max_age_sec: 초 단위 TTL (None이면 무제한)
    """
    path = _cache_path(name)
    if not path.exists():
        return None

    if max_age_sec is not None:
        mtime = path.stat().st_mtime
        age = time.time() - mtime
        if age > max_age_sec:
            return None

    return pd.read_csv(path, parse_dates=["time"])
