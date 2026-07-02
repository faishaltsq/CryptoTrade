import pandas as pd


def detect_liquidity_event(df: pd.DataFrame) -> str:
    recent = df.tail(30)
    prev_low = recent["low"].iloc[:-1].min()
    prev_high = recent["high"].iloc[:-1].max()
    last = recent.iloc[-1]
    if last.low < prev_low and last.close > prev_low:
        return "sell_side_swept"
    if last.high > prev_high and last.close < prev_high:
        return "buy_side_swept"
    return "none"


def detect_supply_demand_zone(df: pd.DataFrame) -> dict:
    recent = df.tail(40).copy()
    atr = float(recent["atr14"].iloc[-1]) if "atr14" in recent else 0
    bullish = recent[(recent["close"] < recent["open"]) & ((recent["high"] - recent["low"]) > atr * 0.5)].tail(1)
    bearish = recent[(recent["close"] > recent["open"]) & ((recent["high"] - recent["low"]) > atr * 0.5)].tail(1)
    return {
        "demand_zone": format_price_zone(bullish) if not bullish.empty else "",
        "supply_zone": format_price_zone(bearish) if not bearish.empty else "",
    }


def detect_price_imbalance(df: pd.DataFrame) -> str:
    data = df.tail(12).reset_index(drop=True)
    last_signal = "none"
    for i in range(2, len(data)):
        if data.loc[i, "low"] > data.loc[i - 2, "high"]:
            last_signal = "bullish_imbalance"
        if data.loc[i, "high"] < data.loc[i - 2, "low"]:
            last_signal = "bearish_imbalance"
    return last_signal


def format_price_zone(row: pd.DataFrame) -> str:
    item = row.iloc[-1]
    return f"{float(item.low):.6g}-{float(item.high):.6g}"
