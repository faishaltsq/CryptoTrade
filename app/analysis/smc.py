import pandas as pd


def liquidity_sweep(df: pd.DataFrame) -> str:
    recent = df.tail(30)
    prev_low = recent["low"].iloc[:-1].min()
    prev_high = recent["high"].iloc[:-1].max()
    last = recent.iloc[-1]
    if last.low < prev_low and last.close > prev_low:
        return "sell_side_swept"
    if last.high > prev_high and last.close < prev_high:
        return "buy_side_swept"
    return "none"


def order_block(df: pd.DataFrame) -> dict:
    recent = df.tail(40).copy()
    atr = float(recent["atr14"].iloc[-1]) if "atr14" in recent else 0
    bullish = recent[(recent["close"] < recent["open"]) & ((recent["high"] - recent["low"]) > atr * 0.5)].tail(1)
    bearish = recent[(recent["close"] > recent["open"]) & ((recent["high"] - recent["low"]) > atr * 0.5)].tail(1)
    return {
        "demand_zone": zone(bullish) if not bullish.empty else "",
        "supply_zone": zone(bearish) if not bearish.empty else "",
    }


def fair_value_gap(df: pd.DataFrame) -> str:
    data = df.tail(12).reset_index(drop=True)
    last_signal = "none"
    for i in range(2, len(data)):
        if data.loc[i, "low"] > data.loc[i - 2, "high"]:
            last_signal = "bullish_fvg_below_price"
        if data.loc[i, "high"] < data.loc[i - 2, "low"]:
            last_signal = "bearish_fvg_above_price"
    return last_signal


def zone(row: pd.DataFrame) -> str:
    item = row.iloc[-1]
    return f"{float(item.low):.6g}-{float(item.high):.6g}"
