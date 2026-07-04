def calculate_plan(direction: str, price: float, atr: float, support: float, resistance: float) -> dict:
    if atr <= 0 or price <= 0:
        return {"entry_zone": "", "stop_loss": "", "take_profit_1": "", "take_profit_2": "", "risk_reward": 0}
    buffer = atr * 0.35
    if direction == "BUY":
        entry_low, entry_high = price - atr * 0.25, price + atr * 0.25
        stop = min(support, entry_low - atr) - buffer if support else entry_low - atr * 1.2
        tp1 = price + atr * 1.5
        tp2 = max(resistance, price + atr * 2.5) if resistance else price + atr * 2.5
        risk = max(price - stop, 0.0000001)
        rr = (tp2 - price) / risk
    elif direction == "SELL":
        entry_low, entry_high = price - atr * 0.25, price + atr * 0.25
        stop = max(resistance, entry_high + atr) + buffer if resistance else entry_high + atr * 1.2
        tp1 = price - atr * 1.5
        tp2 = min(support, price - atr * 2.5) if support else price - atr * 2.5
        risk = max(stop - price, 0.0000001)
        rr = (price - tp2) / risk
    else:
        return {"entry_zone": "", "stop_loss": "", "take_profit_1": "", "take_profit_2": "", "risk_reward": 0}
    return {
        "entry_zone": f"{entry_low:.6g}-{entry_high:.6g}",
        "stop_loss": f"{stop:.6g}",
        "take_profit_1": f"{tp1:.6g}",
        "take_profit_2": f"{tp2:.6g}",
        "risk_reward": round(float(rr), 2),
    }


def actual_tp1_risk_reward(decision: str, entry: float, sl: float, tp1: float) -> float:
    if entry <= 0 or sl <= 0 or tp1 <= 0:
        return 0.0
    if decision == "BUY":
        risk = max(entry - sl, 0.00000001)
        reward = max(tp1 - entry, 0)
    elif decision == "SELL":
        risk = max(sl - entry, 0.00000001)
        reward = max(entry - tp1, 0)
    else:
        return 0.0
    if risk == 0:
        return 0.0
    return round(reward / risk, 2)
