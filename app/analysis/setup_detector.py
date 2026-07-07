from collections import Counter
from typing import Any
import pandas as pd
from app.analysis.indicators import add_indicators, summarize_indicators
from app.analysis.market_features import detect_liquidity_event, detect_price_imbalance, detect_supply_demand_zone
from app.analysis.market_structure import analyze_structure
from app.analysis.risk_reward import calculate_plan
from app.config import get_settings
from app.orderflow.orderflow_analyzer import enrich_orderflow
from app.orderflow.orderflow_score import calculate_orderflow_score, calculate_risk_score, calculate_technical_score, clamp


def analyze_timeframe(df: pd.DataFrame) -> dict[str, Any]:
    enriched = add_indicators(df)
    return {
        **summarize_indicators(enriched),
        **analyze_structure(enriched),
        "liquidity": detect_liquidity_event(enriched),
        "price_zone": detect_supply_demand_zone(enriched),
        "imbalance": detect_price_imbalance(enriched),
    }


def market_regime(trend: str, structure: str) -> str:
    if trend in {"bullish", "bearish"} and "higher" in structure or "lower" in structure:
        return "trending"
    if trend == "ranging":
        return "ranging"
    if trend == "unclear":
        return "unclear"
    return "trending"


def volume_status(vol_spike: bool) -> str:
    return "above_average" if vol_spike else "normal"


def detect_setup(symbol: str, candles: dict[str, pd.DataFrame], futures_data: dict[str, Any], volume_rank: int, spread_pct: float, orderflow: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, str, dict[str, Any]]:
    settings = get_settings()
    if any(len(df) < 60 for df in candles.values()):
        return None, "insufficient_candle_data", {}
    tf = {name: analyze_timeframe(df) for name, df in candles.items()}
    price = tf["M15"]["price"]
    if spread_pct > 0.08:
        return None, "spread_too_wide", tf
    if abs(float(futures_data.get("funding_rate") or 0)) > 0.0015:
        return None, "extreme_volatility", tf
    higher = [tf["D1"]["trend"], tf["H4"]["trend"]]
    if Counter(higher).get("ranging", 0) >= 3:
        return None, "low_volatility", tf
    direction = candidate_direction(tf)
    if not direction:
        return None, reject_reason(tf), tf
    htf_conflict = (direction == "BUY" and "bearish" in higher) or (direction == "SELL" and "bullish" in higher)
    if htf_conflict and tf["H4"]["trend"] != direction.lower():
        return None, "unclear_market_context", tf
    atr = tf["M15"]["atr"]
    plan = calculate_plan(direction, price, atr, tf["H1"].get("support", 0), tf["H1"].get("resistance", 0))
    if plan["risk_reward"] < settings.min_risk_reward:
        return None, "poor_risk_reward", tf
    if not (tf["M15"]["volume_spike"] or tf["H1"]["volume_spike"]):
        return None, "low_volume", tf
    enriched_orderflow = enrich_orderflow({**(orderflow or {}), "open_interest": futures_data.get("open_interest", 0), "open_interest_change": futures_data.get("open_interest_change", 0)}, direction)
    enriched_orderflow["orderflow_score"] = calculate_orderflow_score(direction, enriched_orderflow)
    technical_score = calculate_technical_score(tf, direction)
    risk_score = calculate_risk_score(plan["risk_reward"], settings.min_risk_reward)
    final_confidence = clamp(technical_score + enriched_orderflow["orderflow_score"] + risk_score, 0, 100)
    payload = build_ai_payload(symbol, direction, price, tf, futures_data, volume_rank, plan, enriched_orderflow, technical_score, risk_score, final_confidence, settings)
    return payload, "candidate", tf


def candidate_direction(tf: dict[str, dict[str, Any]]) -> str | None:
    bullish_htf = tf["H4"]["trend"] == "bullish" or (tf["D1"]["trend"] == "bullish" and tf["H4"]["trend"] != "bearish")
    bearish_htf = tf["H4"]["trend"] == "bearish" or (tf["D1"]["trend"] == "bearish" and tf["H4"]["trend"] != "bullish")
    if bullish_htf:
        return "BUY"
    if bearish_htf:
        return "SELL"
    return None


def reject_reason(tf: dict[str, dict[str, Any]]) -> str:
    trends = [tf[k]["trend"] for k in ["D1", "H4", "H1", "M15"]]
    if Counter(trends).get("ranging", 0) >= 3:
        return "low_volatility"
    if tf["D1"]["trend"] != "unclear" and tf["H4"]["trend"] != "unclear" and tf["D1"]["trend"] != tf["H4"]["trend"]:
        return "unclear_market_context"
    if not (tf["H1"]["bos"] or tf["H1"]["choch"] or tf["M15"]["bos"] or tf["M15"]["choch"]):
        return "no_actionable_area"
    return "no_actionable_area"


def build_ai_payload(symbol: str, direction: str, price: float, tf: dict[str, dict[str, Any]], futures_data: dict[str, Any], volume_rank: int, plan: dict[str, Any], orderflow: dict[str, Any], technical_score: int, risk_score: int, final_confidence: int, settings) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "market": "USDT_PERPETUAL",
        "provider": settings.market_provider,
        "current_price": price,
        "candidate_direction": direction,
        "scores": {"technical_score": technical_score, "orderflow_score": orderflow.get("orderflow_score", 0), "risk_score": risk_score, "final_confidence": final_confidence},
        "timeframes": {
            "D1": {
                "trend": tf["D1"]["trend"],
                "market_regime": market_regime(tf["D1"]["trend"], tf["D1"]["structure"]),
                "ema_20": round(tf["D1"].get("ema50", 0), 2),
                "ema_50": round(tf["D1"].get("ema50", 0), 2),
                "ema_200": round(tf["D1"].get("ema200", 0), 2),
                "rsi_14": tf["D1"]["rsi"],
                "atr_14": tf["D1"].get("atr", 0),
                "volume_spike": tf["D1"]["volume_spike"],
                "volume_ratio": tf["D1"].get("volume_ratio", 0),
                "volume_trend": tf["D1"].get("volume_trend", "stable"),
                "key_support": tf["D1"]["support"],
                "key_resistance": tf["D1"]["resistance"],
                "recent_structure": tf["D1"]["structure"],
            },
            "H4": {
                "trend": tf["H4"]["trend"],
                "market_regime": market_regime(tf["H4"]["trend"], tf["H4"]["structure"]),
                "rsi_14": tf["H4"]["rsi"],
                "atr_14": tf["H4"].get("atr", 0),
                "nearest_support": extract_support(tf["H4"]),
                "nearest_resistance": extract_resistance(tf["H4"]),
                "momentum": "improving" if tf["H4"]["trend"] == direction.lower() else "declining",
                "volume_spike": tf["H4"]["volume_spike"],
                "volume_ratio": tf["H4"].get("volume_ratio", 0),
                "volume_trend": tf["H4"].get("volume_trend", "stable"),
            },
            "H1": {
                "trend": tf["H1"]["trend"],
                "market_regime": "range_breakout_attempt" if tf["H1"]["bos"] or tf["H1"]["choch"] else "consolidation",
                "recent_breakout": tf["H1"]["bos"],
                "momentum_shift": "bullish" if tf["H1"]["choch"] and direction == "BUY" else "bearish" if tf["H1"]["choch"] else "neutral",
                "volume_spike": tf["H1"]["volume_spike"],
                "volume_ratio": tf["H1"].get("volume_ratio", 0),
                "volume_trend": tf["H1"].get("volume_trend", "stable"),
                "support_zone": tf["H1"]["price_zone"].get("demand_zone", "") if direction == "BUY" else zone(tf["H1"], "resistance"),
                "resistance_zone": tf["H1"]["price_zone"].get("supply_zone", "") if direction == "SELL" else zone(tf["H1"], "support"),
            },
            "M15": {
                "trend": tf["M15"]["trend"],
                "momentum": "bullish" if direction == "BUY" else "bearish",
                "entry_context": "near_support" if direction == "BUY" else "near_resistance",
                "atr_14": tf["M15"].get("atr", 0),
                "volume_spike": tf["M15"]["volume_spike"],
                "volume_ratio": tf["M15"].get("volume_ratio", 0),
                "volume_trend": tf["M15"].get("volume_trend", "stable"),
            },
        },
        "derivatives_data": {
            "funding_rate": f"{float(futures_data.get('funding_rate', 0)) * 100:.4f}%",
            "open_interest": float(futures_data.get("open_interest", 0)),
            "open_interest_change": f"{float(futures_data.get('open_interest_change', 0)):+.2f}%",
            "long_short_ratio": f"{float(futures_data.get('long_short_ratio', 0)):.2f}",
            "taker_buy_sell_ratio": f"{float(futures_data.get('taker_buy_sell_ratio', 0)):.2f}",
            "volume_24h_rank": volume_rank,
        },
        "orderflow": compact_orderflow(orderflow),
        "risk_context": {
            "potential_entry_zone": plan["entry_zone"],
            "nearest_invalid_level": plan["stop_loss"],
            "potential_take_profit_1": plan["take_profit_1"],
            "potential_take_profit_2": plan["take_profit_2"],
            "estimated_risk_reward": plan["risk_reward"],
        },
    }


def compact_orderflow(orderflow: dict[str, Any]) -> dict[str, Any]:
    if not orderflow:
        return {}
    return {
        "window": orderflow.get("window", "1m"),
        "buy_volume": orderflow.get("buy_volume", 0),
        "sell_volume": orderflow.get("sell_volume", 0),
        "volume_delta": orderflow.get("volume_delta", 0),
        "cumulative_volume_delta": orderflow.get("cumulative_volume_delta", 0),
        "delta_ratio": orderflow.get("delta_ratio", 0),
        "trade_intensity": orderflow.get("trade_intensity", "low"),
        "large_trade_count": orderflow.get("large_trade_count", 0),
        "spread": orderflow.get("spread", 0),
        "orderbook_imbalance": orderflow.get("orderbook_imbalance", 0),
        "liquidity_wall_side": orderflow.get("liquidity_wall_side", "none"),
        "liquidation_spike_detected": orderflow.get("liquidation_spike_detected", False),
        "open_interest_change": f"{float(orderflow.get('open_interest_change', 0)):+.2f}%",
        "flow_interpretation": orderflow.get("flow_interpretation", orderflow.get("interpretation", "")),
    }


def extract_support(tf_item: dict[str, Any]) -> float:
    return tf_item.get("price_zone", {}).get("demand_zone", "") or tf_item.get("support", 0)


def extract_resistance(tf_item: dict[str, Any]) -> float:
    return tf_item.get("price_zone", {}).get("supply_zone", "") or tf_item.get("resistance", 0)


def zone(tf_item: dict[str, Any], key: str) -> str:
    return str(tf_item.get(key, ""))
