import requests
import pandas as pd

BASE_URL = "https://api.binance.com"
FUTURES_BASE = "https://fapi.binance.com"


# Binance klines 한 행은 정확히 12개 요소입니다.
KLINE_COLS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "qav",           # quote asset volume
    "num_trades",
    "taker_base",    # taker buy base asset volume
    "taker_quote",   # taker buy quote asset volume
    "ignore"
]

def fetch_klines(symbol: str = "BTCUSDT", interval: str = "1h", limit: int = 200) -> pd.DataFrame:
    """
    Binance 공개 API에서 OHLCV 캔들 수집.
    반환 컬럼: time(KST), open, high, low, close, volume
    """
    url = f"{BASE_URL}/api/v3/klines"
    params = {"symbol": symbol.upper(), "interval": interval, "limit": int(limit)}
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()

    df = pd.DataFrame(data, columns=KLINE_COLS)

    # 타입 캐스팅
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)

    # 시간 변환 (KST 보기 좋게)
    # open_time(ms) -> tz-aware KST
    df["time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True).dt.tz_convert("Asia/Seoul")

    out = df[["time", "open", "high", "low", "close", "volume"]].copy()
    return out.sort_values("time").reset_index(drop=True)


def _to_kst(ts_ms: int):
    return pd.to_datetime(ts_ms, unit="ms", utc=True).tz_convert("Asia/Seoul")

def _get(url: str, params: dict) -> list:
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    return r.json()

# -------------------------------
# 파생지표 수집 함수들 (MVP)
# -------------------------------

def fetch_funding_rate(symbol: str = "BTCUSDT", limit: int = 200) -> pd.DataFrame:
    """
    /fapi/v1/fundingRate
    반환: time(KST), fundingRate
    """
    url = f"{FUTURES_BASE}/fapi/v1/fundingRate"
    data = _get(url, {"symbol": symbol.upper(), "limit": int(limit)})
    df = pd.DataFrame(data)
    df["time"] = df["fundingTime"].apply(_to_kst)
    df["fundingRate"] = df["fundingRate"].astype(float)
    return df[["time", "fundingRate"]].sort_values("time").reset_index(drop=True)


def fetch_open_interest(symbol: str = "BTCUSDT", interval: str = "1h", limit: int = 200) -> pd.DataFrame:
    """
    /futures/data/openInterestHist
    반환: time(KST), openInterest
    """
    url = f"{FUTURES_BASE}/futures/data/openInterestHist"
    data = _get(url, {"symbol": symbol.upper(), "period": interval, "limit": int(limit)})
    df = pd.DataFrame(data)
    df["time"] = df["timestamp"].apply(_to_kst)
    # sumOpenInterest 또는 openInterest 키가 상황에 따라 존재 → 먼저 있는 걸 사용
    col = "sumOpenInterest" if "sumOpenInterest" in df.columns else "openInterest"
    df["openInterest"] = df[col].astype(float)
    return df[["time", "openInterest"]].sort_values("time").reset_index(drop=True)


def fetch_global_long_short(symbol: str = "BTCUSDT", interval: str = "1h", limit: int = 200) -> pd.DataFrame:
    """
    /futures/data/globalLongShortAccountRatio
    반환: time(KST), longShortRatio
    """
    url = f"{FUTURES_BASE}/futures/data/globalLongShortAccountRatio"
    data = _get(url, {"symbol": symbol.upper(), "period": interval, "limit": int(limit)})
    df = pd.DataFrame(data)
    df["time"] = df["timestamp"].apply(_to_kst)
    df["longShortRatio"] = df["longShortRatio"].astype(float)
    return df[["time", "longShortRatio"]].sort_values("time").reset_index(drop=True)


def fetch_top_traders_long_short(symbol: str = "BTCUSDT", interval: str = "1h", limit: int = 200, metric: str = "accounts") -> pd.DataFrame:
    """
    /futures/data/topLongShortAccountRatio  (metric='accounts')
    /futures/data/topLongShortPositionRatio (metric='positions')
    반환: time(KST), longShortRatio
    """
    if metric not in ("accounts", "positions"):
        raise ValueError("metric must be 'accounts' or 'positions'")
    path = "topLongShortAccountRatio" if metric == "accounts" else "topLongShortPositionRatio"
    url = f"{FUTURES_BASE}/futures/data/{path}"
    data = _get(url, {"symbol": symbol.upper(), "period": interval, "limit": int(limit)})
    df = pd.DataFrame(data)
    df["time"] = df["timestamp"].apply(_to_kst)
    df["longShortRatio"] = df["longShortRatio"].astype(float)
    return df[["time", "longShortRatio"]].sort_values("time").reset_index(drop=True)


def fetch_taker_buy_sell(symbol: str = "BTCUSDT", interval: str = "1h", limit: int = 200) -> pd.DataFrame:
    """
    USDⓈ-M: /futures/data/takerlongshortRatio
    반환: time(KST), buyVol, sellVol, buySellRatio
    """
    url = f"{FUTURES_BASE}/futures/data/takerlongshortRatio"  # <-- 여기!
    data = _get(url, {"symbol": symbol.upper(), "period": interval, "limit": int(limit)})
    df = pd.DataFrame(data)
    df["time"] = df["timestamp"].apply(_to_kst)

    for c in ("buyVol", "sellVol", "buySellRatio"):
        if c in df.columns:
            df[c] = df[c].astype(float)
        else:
            df[c] = pd.NA

    return df[["time", "buyVol", "sellVol", "buySellRatio"]].sort_values("time").reset_index(drop=True)