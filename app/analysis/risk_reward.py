def calculate_plan(direction: str, price: float, atr: float, support: float, resistance: float) -> dict:
    if atr <= 0 or price <= 0:
        return {"entry_zone": "", "stop_loss": "", "take_profit_1": "", "take_profit_2": "", "risk_reward": 0}

    buffer = atr * 0.2
    # Maximum risk we're willing to take from price (keeps RR viable)
    max_risk_atr = 2.0

    if direction == "BUY":
        entry_low  = price - atr * 0.25
        entry_high = price + atr * 0.25

        # Use structural support as stop ONLY if it keeps risk within max_risk_atr
        atr_stop = entry_low - atr - buffer       # default: ~1.45x ATR below price
        if support and support < entry_low and (price - support) <= atr * max_risk_atr:
            stop = support - buffer               # tight stop just below structural support
        else:
            stop = atr_stop

        risk = max(price - stop, 0.0000001)

        # TP1: minimum 1.5x risk reward
        tp1 = price + risk * 1.5

        # TP2: use resistance as target if it gives good RR, otherwise extend by ATR
        rr_needed = 2.0   # aim for at least 2:1 on TP2
        tp2_min = price + risk * rr_needed
        if resistance and resistance > price and resistance >= tp2_min:
            tp2 = resistance
        else:
            # Extend TP2 further if needed — allow up to 5x ATR for trending markets
            tp2 = price + max(risk * rr_needed, atr * 3.0)
            tp2 = min(tp2, price + atr * 5.0)

        rr = (tp2 - price) / risk

    elif direction == "SELL":
        entry_low  = price - atr * 0.25
        entry_high = price + atr * 0.25

        # Use structural resistance as stop ONLY if it keeps risk within max_risk_atr
        atr_stop = entry_high + atr + buffer      # default: ~1.45x ATR above price
        if resistance and resistance > entry_high and (resistance - price) <= atr * max_risk_atr:
            stop = resistance + buffer
        else:
            stop = atr_stop

        risk = max(stop - price, 0.0000001)

        tp1 = price - risk * 1.5

        rr_needed = 2.0
        tp2_max = price - risk * rr_needed
        if support and support < price and support <= tp2_max:
            tp2 = support
        else:
            tp2 = price - max(risk * rr_needed, atr * 3.0)
            tp2 = max(tp2, price - atr * 5.0)

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


def estimate_tp2_probability(direction: str, entry: float, tp1: float, tp2: float, sl: float, rsi: float, trend_aligned: bool, at_support: bool, at_resistance: bool) -> int:
    if tp2 <= 0 or tp1 <= 0 or entry <= 0:
        return 0
    if direction == "BUY":
        tp1_dist = (tp1 - entry) / entry * 100
        tp2_dist = (tp2 - entry) / entry * 100
    else:
        tp1_dist = (entry - tp1) / entry * 100
        tp2_dist = (entry - tp2) / entry * 100
    t1_t2_gap = max(tp2_dist - tp1_dist, 0.01)
    prob = 55
    if t1_t2_gap < tp1_dist * 0.3:
        prob -= 12
    elif t1_t2_gap < tp1_dist * 0.6:
        prob -= 5
    elif t1_t2_gap > tp1_dist * 1.5:
        prob += 8
    if trend_aligned:
        prob += 8
    else:
        prob -= 10
    if direction == "BUY" and at_support:
        prob += 5
    elif direction == "SELL" and at_resistance:
        prob += 5
    if rsi > 0:
        if direction == "BUY" and rsi < 30:
            prob += 8
        elif direction == "BUY" and rsi > 65:
            prob -= 5
        elif direction == "SELL" and rsi > 70:
            prob += 8
        elif direction == "SELL" and rsi < 35:
            prob -= 5
    if sl > 0 and entry > 0:
        risk_pct = abs(sl - entry) / entry * 100
        if risk_pct > tp2_dist * 0.8:
            prob -= 8
    return max(10, min(95, prob))


def ensure_tp2_probability(ai_response: dict, candidate: dict) -> None:
    risk = ai_response.get("risk", {}) or {}
    if risk.get("tp2_probability", 0) > 0:
        return
    decision = ai_response.get("decision", "")
    if decision not in {"BUY", "SELL"}:
        return
    tfs = candidate.get("timeframes", {})
    rsi = tfs.get("H1", {}).get("rsi", 50) or tfs.get("M15", {}).get("rsi", 50)
    entry_raw = risk.get("entry_zone", "") or (ai_response.get("entry", {}) or {}).get("zone", "")
    parts = str(entry_raw).replace(",", "-").split("-")
    nums = []
    for p in parts:
        try:
            nums.append(float(p.strip()))
        except (ValueError, TypeError):
            pass
    entry = sum(nums) / len(nums) if nums else 0
    tp1 = float(risk.get("take_profit_1") or 0)
    tp2 = float(risk.get("take_profit_2") or 0)
    sl = float(risk.get("stop_loss") or 0)
    direction = candidate.get("candidate_direction", decision).upper()
    trend_align = (decision == direction)
    h1 = tfs.get("H1", {})
    at_sup = h1.get("at_support", False)
    at_res = h1.get("at_resistance", False)
    risk["tp2_probability"] = estimate_tp2_probability(decision, entry, tp1, tp2, sl, rsi, trend_align, at_sup, at_res)
    risk["tp2_probability_source"] = "computed"
    ai_response["risk"] = risk
