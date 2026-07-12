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
    price = float(last.close)
    zone_pct = 0.02
    near_support = support > 0 and abs(price - support) / price < zone_pct
    near_resistance = resistance > 0 and abs(price - resistance) / price < zone_pct
    return {"trend": trend, "structure": structure, "bos": bool(bos_bull or bos_bear), "choch": bool(choch), "support": support, "resistance": resistance, "at_support": near_support, "at_resistance": near_resistance}


def detect_demand_supply_zones(df: pd.DataFrame) -> dict:
    data = swing_points(df, lookback=3).dropna().copy()
    highs = data[data["swing_high"]]
    lows = data[data["swing_low"]]
    demand = _find_demand_zone(data, lows)
    supply = _find_supply_zone(data, highs)
    price = float(data.iloc[-1].close)
    return {
        "demand_zone_low": demand.get("low", 0),
        "demand_zone_high": demand.get("high", 0),
        "demand_zone_test_count": demand.get("test_count", 0),
        "supply_zone_low": supply.get("low", 0),
        "supply_zone_high": supply.get("high", 0),
        "supply_zone_test_count": supply.get("test_count", 0),
        "distance_to_demand_pct": round((price - demand["high"]) / price * 100, 2) if demand.get("high") and price > demand["high"] else round((price - demand["low"]) / price * 100, 2) if demand.get("low") and price >= demand["low"] else 0,
        "distance_to_supply_pct": round((supply["low"] - price) / price * 100, 2) if supply.get("low") and price < supply["low"] else round((supply["high"] - price) / price * 100, 2) if supply.get("high") and price <= supply["high"] else 0,
        "price_within_demand": demand.get("low", 0) > 0 and demand["low"] <= price <= demand["high"],
        "price_within_supply": supply.get("low", 0) > 0 and supply["low"] <= price <= supply["high"],
        "demand_reaction_score": _compute_reaction_score(df, demand, "demand") if demand else 0,
        "supply_reaction_score": _compute_reaction_score(df, supply, "supply") if supply else 0,
    }


def _compute_reaction_score(df: pd.DataFrame, zone: dict, zone_type: str) -> int:
    if not zone:
        return 0
    score = 0
    recent = df.tail(5)
    if len(recent) < 3:
        return 0
    last = recent.iloc[-1]
    prev_vol = recent["volume"].iloc[-3:-1].mean() if len(recent) >= 3 else recent["volume"].iloc[:-1].mean()
    if zone_type == "demand":
        lower_wick = (min(last["close"], last["open"]) - last["low"]) / (last["high"] - last["low"]) if (last["high"] - last["low"]) > 0 else 0
        if lower_wick > 0.5:
            score += 1
        if last["close"] > recent.iloc[-2]["open"] and last["close"] > last["open"]:
            score += 1
        if last["volume"] < prev_vol * 0.8:
            score += 1
    else:
        upper_wick = (last["high"] - max(last["close"], last["open"])) / (last["high"] - last["low"]) if (last["high"] - last["low"]) > 0 else 0
        if upper_wick > 0.5:
            score += 1
        if last["close"] < recent.iloc[-2]["open"] and last["close"] < last["open"]:
            score += 1
        if last["volume"] < prev_vol * 0.8:
            score += 1
    return score


def _find_demand_zone(df: pd.DataFrame, lows: pd.DataFrame) -> dict:
    if len(lows) < 2:
        return {}
    recent_lows = lows.tail(10)
    for idx in reversed(recent_lows.index[:-1]):
        row = df.loc[idx]
        base_candles = df.loc[idx - 5:idx] if idx > 5 else df.loc[:idx]
        impulse = row["close"] > row["open"] and row["volume"] > base_candles["volume"].mean() * 1.2
        if impulse:
            low = float(row["low"])
            high = float(row["close"]) if row["open"] > row["close"] else float(row["open"])
            test_count = _count_zone_tests(df, low, high, "demand")
            if test_count <= 2:
                return {"low": low, "high": high, "test_count": test_count}
    return {}


def _find_supply_zone(df: pd.DataFrame, highs: pd.DataFrame) -> dict:
    if len(highs) < 2:
        return {}
    recent_highs = highs.tail(10)
    for idx in reversed(recent_highs.index[:-1]):
        row = df.loc[idx]
        base_candles = df.loc[idx - 5:idx] if idx > 5 else df.loc[:idx]
        impulse = row["close"] < row["open"] and row["volume"] > base_candles["volume"].mean() * 1.2
        if impulse:
            low = float(row["open"]) if row["close"] > row["open"] else float(row["close"])
            high = float(row["high"])
            test_count = _count_zone_tests(df, low, high, "supply")
            if test_count <= 2:
                return {"low": low, "high": high, "test_count": test_count}
    return {}


def _count_zone_tests(df: pd.DataFrame, zone_low: float, zone_high: float, zone_type: str) -> int:
    tests = 0
    for i in range(max(0, len(df) - 100), len(df)):
        row = df.iloc[i]
        if zone_type == "demand":
            if zone_low <= row["low"] <= zone_high * 1.005:
                tests += 1
        else:
            if zone_low * 0.995 <= row["high"] <= zone_high:
                tests += 1
    return tests
