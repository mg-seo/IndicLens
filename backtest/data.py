from __future__ import annotations

import time
from typing import List, Dict

import pandas as pd
import requests

BASE_SPOT = "https://api.binance.com"
BASE_FUT  = "https://fapi.binance.com"
PERIOD_MS = {
    "5m": 5*60_000, "15m": 15*60_000, "30m": 30*60_000,
    "1h": 60*60_000, "2h": 2*60*60_000, "4h": 4*60*60_000,
    "6h": 6*60*60_000, "12h": 12*60*60_000, "1d": 24*60*60_000,
}

# ---- 공통 유틸 --------------------------------------------------------------

def _get(url: str, params: dict) -> list[dict]:
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    # API가 list가 아닌 dict로 줄 수 있는 경우 방어
    if isinstance(data, dict):
        # 히스토리 API는 보통 리스트를 줌. dict가 오면 빈 리스트 취급.
        return data.get("rows", []) if "rows" in data else []
    return data

def _from_ms(ms: int) -> pd.Timestamp:
    # tz-aware UTC
    return pd.to_datetime(int(ms), unit="ms", utc=True)

def _dedup_sort(df: pd.DataFrame) -> pd.DataFrame:
    return df.drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)

def _clamp_30d(start_utc: pd.Timestamp, end_utc: pd.Timestamp) -> pd.Timestamp:
    # 바이낸스 공용 히스토리(derivatives) 30일 제한 감안한 안전 클램프
    end_utc = end_utc.tz_convert("UTC") if end_utc.tzinfo else end_utc.tz_localize("UTC")
    start_utc = start_utc.tz_convert("UTC") if start_utc.tzinfo else start_utc.tz_localize("UTC")
    limit = end_utc - pd.Timedelta(days=29, hours=23)
    return max(start_utc, limit)

def _tz_utc(ts: pd.Timestamp) -> pd.Timestamp:
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


# ---- 현물: KLINES -----------------------------------------------------------

KLINE_COLS = [
    "open_time","open","high","low","close","volume",
    "close_time","qav","num_trades","taker_base","taker_quote","ignore"
]

def fetch_klines_range(
    symbol: str,
    interval: str,
    start_utc: pd.Timestamp,
    end_utc: pd.Timestamp,
    limit_per_req: int = 1000,
    sleep_sec: float = 0.06,
) -> pd.DataFrame:
    """
    /api/v3/klines 페이지네이션 (현물)
    tz-aware UTC time 반환: columns [time, open, high, low, close, volume]
    """
    url = f"{BASE_SPOT}/api/v3/klines"
    start_utc = _tz_utc(start_utc)
    end_utc   = _tz_utc(end_utc)

    rows: List[List] = []
    cur = int(start_utc.timestamp() * 1000)

    while True:
        params = {
            "symbol": symbol.upper(),
            "interval": interval,
            "startTime": cur,
            "endTime": int(end_utc.timestamp() * 1000),
            "limit": min(limit_per_req, 1000),
        }
        data = _get(url, params)
        if not data:
            break
        rows.extend(data)
        last_close = int(data[-1][6])  # close_time
        next_open = last_close + 1
        if next_open <= cur:
            break
        cur = next_open
        if cur > int(end_utc.timestamp() * 1000):
            break
        time.sleep(sleep_sec)

    if not rows:
        return pd.DataFrame(columns=["time","open","high","low","close","volume"])

    df = pd.DataFrame(rows, columns=KLINE_COLS)
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    out = df[["time","open","high","low","close","volume"]]
    return _dedup_sort(out)

def fetch_klines_recent_months(symbol: str, interval: str, months: int = 1) -> pd.DataFrame:
    end = pd.Timestamp.now(tz="UTC")
    start = end - pd.DateOffset(months=int(months))
    return fetch_klines_range(symbol, interval, start, end)


# ---- 선물 파생지표(최근 30일 제한) ----------------------------------------

# period 매핑 (바이낸스 파생 히스토리)
PERIOD_MAP = {
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "2h": "2h",
    "4h": "4h",
    "6h": "6h",
    "12h": "12h",
    "1d": "1d",
}

def _hist_window_paged(
    url: str,
    symbol: str,
    period: str,
    start_utc: pd.Timestamp,
    end_utc: pd.Timestamp,
    per_req_limit: int = 500,
    safety_sleep: float = 0.05,
) -> list[dict]:
    """히스토리 API(30일 제한) 안전 수집: 기간창 분할 + limit=500 고정."""
    start_utc = _tz_utc(start_utc)
    end_utc   = _tz_utc(end_utc)
    start_ms  = int(start_utc.timestamp() * 1000)
    end_ms    = int(end_utc.timestamp() * 1000)

    step = PERIOD_MS[period] * per_req_limit  # 500캔들씩 창 자르기
    rows: list[dict] = []
    cur = start_ms

    while cur <= end_ms:
        wnd_end = min(cur + step - 1, end_ms)
        params = {
            "symbol": symbol.upper(),
            "period": period,
            "startTime": cur,
            "endTime": wnd_end,
            "limit": per_req_limit,
        }
        try:
            r = requests.get(url, params=params, timeout=20)
            if r.status_code == 429:
                time.sleep(0.2)
                r = requests.get(url, params=params, timeout=20)
            r.raise_for_status()
            data = r.json()
            if data:
                rows.extend(data)
        finally:
            # 다음 창으로 이동
            cur = wnd_end + 1
            if safety_sleep:
                time.sleep(safety_sleep)
    return rows


def fetch_open_interest_range(symbol: str, interval: str, start_utc: pd.Timestamp, end_utc: pd.Timestamp) -> pd.DataFrame:
    url = f"{BASE_FUT}/futures/data/openInterestHist"
    period = PERIOD_MAP.get(interval)
    if not period:
        raise ValueError(f"Unsupported interval for OI: {interval}")
    start_eff = _clamp_30d(start_utc, end_utc)

    rows = _hist_window_paged(url, symbol, period, start_eff, end_utc, per_req_limit=500)
    if not rows:
        return pd.DataFrame(columns=["time","openInterest"])

    df = pd.DataFrame(rows)
    df["time"] = df["timestamp"].apply(lambda x: _from_ms(int(x)))
    col = "sumOpenInterest" if "sumOpenInterest" in df.columns else "openInterest"
    df["openInterest"] = pd.to_numeric(df[col], errors="coerce")
    return _dedup_sort(df[["time","openInterest"]])

def fetch_top_traders_long_short_range(symbol: str, interval: str, start_utc: pd.Timestamp, end_utc: pd.Timestamp, metric: str="accounts") -> pd.DataFrame:
    if metric not in ("accounts","positions"):
        raise ValueError("metric must be 'accounts' or 'positions'")
    path = "topLongShortAccountRatio" if metric=="accounts" else "topLongShortPositionRatio"
    url = f"{BASE_FUT}/futures/data/{path}"
    period = PERIOD_MAP.get(interval)
    if not period:
        raise ValueError(f"Unsupported interval: {interval}")
    start_eff = _clamp_30d(start_utc, end_utc)

    rows = _hist_window_paged(url, symbol, period, start_eff, end_utc, per_req_limit=500)
    if not rows:
        return pd.DataFrame(columns=["time","longShortRatio"])

    df = pd.DataFrame(rows)
    df["time"] = df["timestamp"].apply(lambda x: _from_ms(int(x)))
    df["longShortRatio"] = pd.to_numeric(df["longShortRatio"], errors="coerce")
    return _dedup_sort(df[["time","longShortRatio"]])

def fetch_taker_buy_sell_range(symbol: str, interval: str, start_utc: pd.Timestamp, end_utc: pd.Timestamp) -> pd.DataFrame:
    url = f"{BASE_FUT}/futures/data/takerlongshortRatio"
    period = PERIOD_MAP.get(interval)
    if not period:
        raise ValueError(f"Unsupported interval: {interval}")
    start_eff = _clamp_30d(start_utc, end_utc)

    rows = _hist_window_paged(url, symbol, period, start_eff, end_utc, per_req_limit=500)
    if not rows:
        return pd.DataFrame(columns=["time","buyVol","sellVol","buySellRatio"])

    df = pd.DataFrame(rows)
    df["time"] = df["timestamp"].apply(lambda x: _from_ms(int(x)))
    for c in ("buyVol","sellVol","buySellRatio"):
        df[c] = pd.to_numeric(df.get(c, pd.NA), errors="coerce")
    return _dedup_sort(df[["time","buyVol","sellVol","buySellRatio"]])



def fetch_funding_rate_range(symbol: str,
                             start_utc: pd.Timestamp,
                             end_utc: pd.Timestamp) -> pd.DataFrame:
    """
    /futures/data/fundingRate  (8h 단위, 페이징 필요)
    """
    url = f"{BASE_FUT}/fapi/v1/fundingRate"
    s = _tz_utc(start_utc)
    e = _tz_utc(end_utc)
    rows: list[dict] = []

    while s < e:
        params = {
            "symbol": symbol.upper(),
            "startTime": int(s.timestamp() * 1000),
            "endTime": int(e.timestamp() * 1000),
            "limit": 1000,
        }
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
        if not data:
            break

        rows.extend(data)

        # 다음 루프 시작: 마지막 fundingTime + 1ms
        last = int(data[-1]["fundingTime"])
        s = pd.Timestamp(last, unit="ms", tz="UTC") + pd.Timedelta(milliseconds=1)

        # 마지막 페이지일 경우 종료
        if len(data) < params["limit"]:
            break

        time.sleep(0.05)  # 안전슬립

    if not rows:
        return pd.DataFrame(columns=["time", "fundingRate"])

    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["fundingTime"], unit="ms", utc=True)
    df["fundingRate"] = pd.to_numeric(df["fundingRate"], errors="coerce")
    return _dedup_sort(df[["time", "fundingRate"]])

def fetch_futures_klines_range(symbol: str, interval: str, start_utc: pd.Timestamp, end_utc: pd.Timestamp) -> pd.DataFrame:
    """
    Binance USDⓂ 선물 캔들(/fapi/v1/klines) 범위 수집.
    spot용 fetch_klines_range와 동일한 페이징 방식(마지막 closeTime+1ms)으로 수집.
    반환: time, open, high, low, close, volume
    """
    import requests
    symbol = symbol.upper()
    url = "https://fapi.binance.com/fapi/v1/klines"
    rows = []
    s = start_utc
    while s < end_utc:
        params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": int(s.timestamp() * 1000),
            "endTime": int(end_utc.timestamp() * 1000),
            "limit": 1000,
        }
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
        if not data:
            break
        rows.extend(data)
        # 다음 루프 시작: 마지막 캔들의 closeTime + 1ms
        last_close_ms = int(data[-1][6])  # closeTime
        s = pd.Timestamp(last_close_ms, unit="ms", tz="UTC") + pd.Timedelta(milliseconds=1)
        if len(data) < params["limit"]:
            break

    if not rows:
        return pd.DataFrame(columns=["time","open","high","low","close","volume"])

    df = pd.DataFrame(
        rows,
        columns=[
            "openTime","open","high","low","close","volume",
            "closeTime","quoteAssetVolume","numberOfTrades",
            "takerBuyBase","takerBuyQuote","ignore",
        ],
    )
    df["time"] = pd.to_datetime(df["openTime"], unit="ms", utc=True)
    for col in ["open","high","low","close","volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)
    return df[["time","open","high","low","close","volume"]]

# === 현재가 표시 ===
def fetch_funding_live(symbol: str) -> dict:
    """Premium Index의 최근 펀딩률 (실시간/예상치). raw json 반환."""
    url = f"{BASE_FUT}/fapi/v1/premiumIndex"
    r = requests.get(url, params={"symbol": symbol.upper()}, timeout=10)
    r.raise_for_status()
    return r.json()  # {"lastFundingRate": "0.00010000", "nextFundingTime": ...}

def fetch_open_interest_snapshot(symbol: str) -> float:
    """현재 OI 스냅샷. 숫자(float)만 반환."""
    url = f"{BASE_FUT}/fapi/v1/openInterest"
    r = requests.get(url, params={"symbol": symbol.upper()}, timeout=10)
    r.raise_for_status()
    j = r.json()
    return float(j["openInterest"])

def fetch_latest_bucket(endpoint: str, symbol: str, period: str = "5m") -> dict | None:
    """
    endpoint: "topLongShortAccountRatio" | "topLongShortPositionRatio" | "takerlongshortRatio"
    period:   "5m", "15m", "1h", ...
    """
    url = f"{BASE_FUT}/futures/data/{endpoint}"
    r = requests.get(url, params={"symbol": symbol.upper(), "period": period, "limit": 1}, timeout=10)
    r.raise_for_status()
    arr = r.json()
    return arr[-1] if arr else None

def fetch_top_ls_accounts_latest(symbol: str, period: str = "5m") -> float | None:
    j = fetch_latest_bucket("topLongShortAccountRatio", symbol, period)
    return float(j["longShortRatio"]) if j else None

def fetch_top_ls_positions_latest(symbol: str, period: str = "5m") -> float | None:
    j = fetch_latest_bucket("topLongShortPositionRatio", symbol, period)
    return float(j["longShortRatio"]) if j else None

def fetch_taker_buy_sell_latest(symbol: str, period: str = "5m") -> float | None:
    j = fetch_latest_bucket("takerlongshortRatio", symbol, period)
    return float(j["buySellRatio"]) if j else None
