import requests
import pandas as pd

BASE_URL = "https://api.binance.com"

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