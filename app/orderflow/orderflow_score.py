from typing import Any


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def calculate_orderflow_score(direction: str, summary: dict[str, Any]) -> int:
    score = 0
    delta = float(summary.get("volume_delta") or 0)
    cvd = float(summary.get("cumulative_volume_delta") or 0)
    imbalance = float(summary.get("orderbook_imbalance") or 0)
    intensity = summary.get("trade_intensity")
    spread = float(summary.get("spread") or 0)
    price = float(summary.get("price") or summary.get("best_ask") or summary.get("best_bid") or 0)
    spread_ok = True if not price or not spread else (spread / price) <= 0.0008
    liq_buy = float(summary.get("liquidation_buy_notional") or 0)
    liq_sell = float(summary.get("liquidation_sell_notional") or 0)
    oi_change = float(summary.get("open_interest_change") or 0)
    absorption = summary.get("absorption_signal", "none")
    pull = bool(summary.get("liquidity_pull_detected"))
    if direction == "BUY":
        score += 5 if delta > 0 else -8 if delta < 0 else 0
        score += 5 if cvd > 0 else -8 if cvd < 0 else 0
        score += 4 if imbalance > 1.10 else -5 if 0 < imbalance < 0.90 else 0
        score += 3 if intensity == "high" and delta > 0 else 0
        score += 3 if summary.get("liquidation_spike_detected") and liq_sell > liq_buy else 0
        score += 3 if oi_change > 0 and delta > 0 else 0
        score += 2 if spread_ok else -5
        score -= 5 if absorption == "possible_bearish_absorption" else 0
        score -= 5 if pull and summary.get("liquidity_wall_side") == "bid" else 0
    elif direction == "SELL":
        score += 5 if delta < 0 else -8 if delta > 0 else 0
        score += 5 if cvd < 0 else -8 if cvd > 0 else 0
        score += 4 if 0 < imbalance < 0.90 else -5 if imbalance > 1.10 else 0
        score += 3 if intensity == "high" and delta < 0 else 0
        score += 3 if summary.get("liquidation_spike_detected") and liq_buy > liq_sell else 0
        score += 3 if oi_change > 0 and delta < 0 else 0
        score += 2 if spread_ok else -5
        score -= 5 if absorption == "possible_bullish_absorption" else 0
        score -= 5 if pull and summary.get("liquidity_wall_side") == "ask" else 0
    return clamp(score, -25, 25)


def calculate_technical_score(tf: dict[str, dict[str, Any]], direction: str) -> int:
    score = 25
    bullish = direction == "BUY"
    htf = [tf["D1"].get("trend"), tf["H4"].get("trend")]
    score += 10 if ((bullish and "bullish" in htf) or (not bullish and "bearish" in htf)) else 0
    score += 8 if tf["H1"].get("bos") or tf["H1"].get("choch") else 0
    score += 7 if tf["M15"].get("bos") or tf["M15"].get("choch") else 0
    score += 5 if tf["H1"].get("liquidity") != "none" or tf["M15"].get("liquidity") != "none" else 0
    score += 5 if tf["H1"].get("order_block") or tf["H1"].get("fvg") != "none" else 0
    return clamp(score, 0, 60)


def calculate_risk_score(risk_reward: float, min_rr: float) -> int:
    if risk_reward < min_rr:
        return 0
    if risk_reward >= 3:
        return 15
    if risk_reward >= 2.5:
        return 12
    return 10
