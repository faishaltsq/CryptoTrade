import pandas as pd


def swing_points(df: pd.DataFrame, lookback: int = 3) -> pd.DataFrame:
    out = df.copy()
    out["swing_high"] = out["high"] == out["high"].rolling(lookback * 2 + 1, center=True).max()
    out["swing_low"] = out["low"] == out["low"].rolling(lookback * 2 + 1, center=True).min()
    return out


def analyze_structure(df: pd.DataFrame) -> dict:
    data = swing_points(df).dropna().copy()
    highs = data[data["swing_high"]].tail(3)
    lows = data[data["swing_low"]].tail(3)
    last = data.iloc[-1]
    if len(highs) < 2 or len(lows) < 2:
        return {"trend": "unclear", "structure": "unclear", "bos": False, "choch": False, "support": 0, "resistance": 0}
    higher_highs = highs["high"].iloc[-1] > highs["high"].iloc[-2]
    higher_lows = lows["low"].iloc[-1] > lows["low"].iloc[-2]
    lower_highs = highs["high"].iloc[-1] < highs["high"].iloc[-2]
    lower_lows = lows["low"].iloc[-1] < lows["low"].iloc[-2]
    resistance = float(highs["high"].iloc[-1])
    support = float(lows["low"].iloc[-1])
    if higher_highs and higher_lows:
        trend, structure = "bullish", "higher_high_higher_low"
    elif lower_highs and lower_lows:
        trend, structure = "bearish", "lower_high_lower_low"
    elif abs(resistance - support) / max(float(last.close), 1) < 0.035:
        trend, structure = "ranging", "range"
    else:
        trend, structure = "unclear", "mixed"
    bos_bull = last.close > resistance
    bos_bear = last.close < support
    choch = (trend == "bearish" and bos_bull) or (trend == "bullish" and bos_bear)
    return {"trend": trend, "structure": structure, "bos": bool(bos_bull or bos_bear), "choch": bool(choch), "support": support, "resistance": resistance}
