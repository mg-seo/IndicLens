from __future__ import annotations
import operator
import pandas as pd
import numpy as np

from .indicators import sma, ema, rsi, macd, bbands


# ---------- 유틸: 시리즈/스칼라 normalize ----------
def _to_series(obj, df: pd.DataFrame) -> pd.Series:
    """
    피연산자 JSON을 판다스 Series로 변환.
    - const -> Series(상수)
    - indicator -> 해당 지표 계산(필요 시 field 선택)
    - name: "close" | "open" 등 OHLCV 컬럼 바로 참조도 허용(MVP)
    """
    t = obj.get("type")

    # 상수
    if t == "const":
        val = obj["value"]
        return pd.Series(val, index=df.index, dtype="float64")

    # 지표/소스
    if t == "indicator" or "name" in obj:
        name = obj["name"]

        # 단순 소스 컬럼 참조
        if name in df.columns:
            return df[name].astype(float)

        params = obj.get("params", {})
        field = obj.get("field", None)
        source_col = obj.get("source", "close")

        src = df[source_col].astype(float)

        if name == "sma":
            return sma(src, params.get("window", 20))
        if name == "ema":
            return ema(src, params.get("span", 20))
        if name == "rsi":
            return rsi(src, params.get("period", 14))
        if name == "macd":
            m = macd(src, params.get("fast", 12), params.get("slow", 26), params.get("signal", 9))
            if field is None:
                raise ValueError("macd 지표는 field('macd'|'signal'|'hist')가 필요합니다.")
            return m[field]
        if name == "bbands":
            b = bbands(src, params.get("window", 20), params.get("k", 2.0))
            if field is None:
                raise ValueError("bbands 지표는 field('bb_upper'|'bb_mid'|'bb_lower')가 필요합니다.")
            return b[field]

        raise ValueError(f"지원하지 않는 indicator/source name: {name}")

    raise ValueError(f"알 수 없는 operand 유형: {obj}")


# ---------- 교차 연산 ----------
def _crossover(a: pd.Series, b: pd.Series) -> pd.Series:
    prev = (a.shift(1) <= b.shift(1))
    now = (a > b)
    return (prev & now).fillna(False)

def _crossunder(a: pd.Series, b: pd.Series) -> pd.Series:
    prev = (a.shift(1) >= b.shift(1))
    now = (a < b)
    return (prev & now).fillna(False)


# ---------- 비교/논리 파서 ----------
_ops_compare = {
    ">": operator.gt,
    "<": operator.lt,
    ">=": operator.ge,
    "<=": operator.le,
    "==": operator.eq,
    "!=": operator.ne,
}

def _eval_expr(expr: dict, df: pd.DataFrame) -> pd.Series:
    # 논리 단항
    if expr.get("op") == "not":
        arg = _eval_expr(expr["arg"], df)
        return (~arg).fillna(False)

    # 논리 다항
    if expr.get("op") == "and":
        args = expr["args"]
        res = pd.Series(True, index=df.index)
        for e in args:
            res = res & _eval_expr(e, df)
        return res.fillna(False)

    if expr.get("op") == "or":
        args = expr["args"]
        res = pd.Series(False, index=df.index)
        for e in args:
            res = res | _eval_expr(e, df)
        return res.fillna(False)

    # 교차
    if expr.get("op") == "crossover":
        left = _to_series(expr["left"], df)
        right = _to_series(expr["right"], df)
        return _crossover(left, right)

    if expr.get("op") == "crossunder":
        left = _to_series(expr["left"], df)
        right = _to_series(expr["right"], df)
        return _crossunder(left, right)

    # 비교
    if expr.get("op") in _ops_compare:
        left = _to_series(expr["left"], df)
        right = _to_series(expr["right"], df)
        return _ops_compare[expr["op"]](left, right).fillna(False)

    # 리프(= 단일 피연산자만 들어온 경우)도 허용: True/False Series로 변환 시도
    if "type" in expr or "name" in expr:
        s = _to_series(expr, df)
        # 0/NaN -> False, 그 외 True 로 캐스팅
        return s.fillna(0).astype(bool)

    raise ValueError(f"지원하지 않는 expr: {expr}")


def evaluate_rule(rule_json: dict, ohlcv: pd.DataFrame) -> pd.Series:
    """
    JSON DSL → Boolean Series (시그널) 변환
    ※ 룩어헤드 방지는 '백테스트 체결'에서 처리(예: signal.shift(1))
    """
    # ohlcv: columns = time, open, high, low, close, volume
    df = ohlcv.set_index("time")
    return _eval_expr(rule_json, df).astype(bool)