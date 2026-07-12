from collections import Counter
from typing import Any
import pandas as pd
from app.analysis.indicators import add_indicators, summarize_indicators
from app.analysis.market_features import detect_liquidity_event, detect_price_imbalance, detect_supply_demand_zone
from app.analysis.market_structure import analyze_structure, detect_demand_supply_zones
from app.analysis.risk_reward import calculate_plan
from app.config import get_settings
from app.orderflow.orderflow_analyzer import enrich_orderflow
from app.orderflow.orderflow_score import calculate_orderflow_score, calculate_risk_score, calculate_technical_score, clamp


def analyze_timeframe(df: pd.DataFrame) -> dict[str, Any]:
    enriched = add_indicators(df)
    return {
        **summarize_indicators(enriched),
        **analyze_structure(enriched),
        **detect_demand_supply_zones(enriched),
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


def _volume_gate(tf: dict, volume_rank: int) -> bool:
    """
    Tiered volume filter — returns True if volume activity is sufficient to proceed.

    Tier 1 — Strong spike: M15 or H1 has volume > 1.8x SMA20 (original condition).
              Always passes. Best signal quality.

    Tier 2 — Moderate activity: any of M15/H1/H4 has soft spike (>1.3x SMA20)
              AND at least one timeframe has rising volume trend.
              Passes for all pairs.

    Tier 3 — Top-10 pair exception: for very liquid pairs (rank ≤ 10),
              a soft spike on any timeframe is enough even without rising trend.
              Ensures BTC/ETH/SOL etc. are never blocked by volume filter alone.

    Reject — All timeframes have falling volume AND no soft spike anywhere.
              Dead market, not worth analyzing.
    """
    m15 = tf.get("M15", {})
    h1  = tf.get("H1", {})
    h4  = tf.get("H4", {})

    # Tier 1: strong spike on entry timeframes
    if m15.get("volume_spike") or h1.get("volume_spike"):
        return True

    # Tier 2: moderate spike on any timeframe + at least one rising volume trend
    has_soft_spike = (
        m15.get("volume_spike_soft")
        or h1.get("volume_spike_soft")
        or h4.get("volume_spike_soft")
    )
    has_rising_trend = (
        m15.get("volume_trend") == "rising"
        or h1.get("volume_trend") == "rising"
        or h4.get("volume_trend") == "rising"
    )
    if has_soft_spike and has_rising_trend:
        return True

    # Tier 3: top-10 pair — soft spike anywhere is enough
    if volume_rank <= 10 and has_soft_spike:
        return True

    # Tier 4: not falling volume on any TF — let AI decide
    h4_vol_trend = h4.get("volume_trend", "falling")
    h1_vol_trend = h1.get("volume_trend", "falling")
    m15_vol_trend = m15.get("volume_trend", "falling")
    if h4_vol_trend != "falling" and h1_vol_trend != "falling" and m15_vol_trend != "falling":
        return True

    # Tier 5: anything not totally dead — let AI evaluate
    if h1_vol_trend != "falling" or m15_vol_trend != "falling":
        return True

    # Reject: volume falling across all timeframes
    return False


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
        return None, "no_direction", tf
    atr = tf["M15"]["atr"]
    plan = calculate_plan(direction, price, atr, tf["H1"].get("support", 0), tf["H1"].get("resistance", 0))
    if plan["risk_reward"] < settings.min_risk_reward:
        return None, "poor_risk_reward", tf
    fb_score = false_breakout_score(tf, direction)
    if fb_score >= 7:
        return None, "false_breakout_risk", tf
        return None, "poor_risk_reward", tf
    if not _volume_gate(tf, volume_rank):
        return None, "low_volume", tf

    enriched_orderflow = enrich_orderflow({**(orderflow or {}), "open_interest": futures_data.get("open_interest", 0), "open_interest_change": futures_data.get("open_interest_change", 0)}, direction)
    enriched_orderflow["orderflow_score"] = calculate_orderflow_score(direction, enriched_orderflow)
    technical_score = calculate_technical_score(tf, direction)
    risk_score = calculate_risk_score(plan["risk_reward"], settings.min_risk_reward)
    final_confidence = clamp(technical_score + enriched_orderflow["orderflow_score"] + risk_score - fb_score * 5, 0, 100)
    payload = build_ai_payload(symbol, direction, price, tf, futures_data, volume_rank, plan, enriched_orderflow, technical_score, risk_score, final_confidence, fb_score, settings)
    return payload, "candidate", tf


def candidate_direction(tf: dict[str, dict[str, Any]]) -> str | None:
    bullish_htf = tf["H4"]["trend"] == "bullish" or (tf["D1"]["trend"] == "bullish" and tf["H4"]["trend"] != "bearish")
    bearish_htf = tf["H4"]["trend"] == "bearish" or (tf["D1"]["trend"] == "bearish" and tf["H4"]["trend"] != "bullish")
    at_support = tf["H1"].get("at_support", False)
    at_resistance = tf["H1"].get("at_resistance", False)
    if bullish_htf and at_support:
        return "BUY"
    if bearish_htf and at_resistance:
        return "SELL"
    if bullish_htf and at_resistance:
        return "SELL"
    if bearish_htf and at_support:
        return "BUY"
    if bullish_htf:
        return "BUY"
    if bearish_htf:
        return "SELL"
    return None


def false_breakout_score(tf: dict[str, dict[str, Any]], direction: str) -> int:
    score = 0
    m15 = tf.get("M15", {})
    h1 = tf.get("H1", {})
    h4 = tf.get("H4", {})
    if not m15.get("volume_spike"):
        score += 2
    rsi = m15.get("rsi", 50)
    if (direction == "BUY" and rsi > 75) or (direction == "SELL" and rsi < 25):
        score += 2
    price = m15.get("price", 0)
    if price > 0:
        round_num = round(price, -int(len(str(int(price))) - 1))
        if abs(price - round_num) / price < 0.005:
            score += 1
    if not h1.get("bos") and not h4.get("bos"):
        score += 1
    if direction == "BUY" and m15.get("at_resistance"):
        score += 1
    if direction == "SELL" and m15.get("at_support"):
        score += 1
    if m15.get("volume_trend") == "falling":
        score += 1
    if m15.get("cvd_divergence") == ("bearish" if direction == "BUY" else "bullish"):
        score += 1
    return score


def compute_btc_status(tf: dict[str, dict[str, Any]]) -> str:
    d1 = tf.get("D1", {})
    h4 = tf.get("H4", {})
    h1 = tf.get("H1", {})
    price = h1.get("price", 0)
    ema50_h4 = h4.get("ema50", 0)
    vol_ratio_h1 = h1.get("volume_ratio", 0)
    d1_bull = d1.get("trend") == "bullish"
    h4_bull = h4.get("trend") == "bullish"
    h4_bear = h4.get("trend") == "bearish"
    h1_bull = h1.get("trend") == "bullish"
    h1_bear = h1.get("trend") == "bearish"
    above_ema50 = price > ema50_h4 and ema50_h4 > 0
    if d1_bull and h4_bull and h1_bull and above_ema50:
        return "strongly_bullish"
    if d1_bull and h4_bull:
        return "moderately_bullish"
    if (d1.get("trend") == "bearish" and h4_bear) or h4_bear:
        if h1_bear and not above_ema50:
            if vol_ratio_h1 > 2.0 and h1_bear:
                return "dump_alert"
            return "strongly_bearish"
        return "moderately_bearish"
    return "neutral"


def get_current_session() -> dict:
    from datetime import datetime
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("Asia/Jakarta"))
    hour = now.hour
    if 1 <= hour < 5:
        return {"session": "dead_zone", "quality": "very_low", "confidence_adjustment": -15, "entry_hint": "wait"}
    if 5 <= hour < 7:
        return {"session": "pre_asia", "quality": "low", "confidence_adjustment": -8, "entry_hint": "limit_only"}
    if 7 <= hour < 12:
        return {"session": "asian_peak", "quality": "medium", "confidence_adjustment": -3, "entry_hint": "limit_only"}
    if 12 <= hour < 15:
        return {"session": "asian_late", "quality": "low", "confidence_adjustment": -8, "entry_hint": "wait"}
    if 15 <= hour < 19:
        return {"session": "london", "quality": "high", "confidence_adjustment": 8, "entry_hint": "all_allowed"}
    if 19 <= hour < 21:
        return {"session": "london_ny_overlap", "quality": "highest", "confidence_adjustment": 10, "entry_hint": "all_allowed"}
    if 21 <= hour or hour < 1:
        return {"session": "new_york", "quality": "high", "confidence_adjustment": 8, "entry_hint": "all_allowed"}
    return {"session": "transition", "quality": "low", "confidence_adjustment": -3, "entry_hint": "limit_only"}


def reject_reason(tf: dict[str, dict[str, Any]]) -> str:
    trends = [tf[k]["trend"] for k in ["D1", "H4", "H1", "M15"]]
    if Counter(trends).get("ranging", 0) >= 3:
        return "low_volatility"
    if not (tf["H1"]["bos"] or tf["H1"]["choch"] or tf["M15"]["bos"] or tf["M15"]["choch"]):
        return "no_actionable_area"
    return "no_actionable_area"


def build_ai_payload(symbol: str, direction: str, price: float, tf: dict[str, dict[str, Any]], futures_data: dict[str, Any], volume_rank: int, plan: dict[str, Any], orderflow: dict[str, Any], technical_score: int, risk_score: int, final_confidence: int, fb_score: int, settings) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "market": "USDT_PERPETUAL",
        "provider": settings.market_provider,
        "current_price": price,
        "candidate_direction": direction,
        "scores": {"technical_score": technical_score, "orderflow_score": orderflow.get("orderflow_score", 0), "risk_score": risk_score, "final_confidence": final_confidence, "false_breakout_score": fb_score},
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
                "obv_trend": tf["D1"].get("obv_trend", "flat"),
                "cvd_divergence": tf["D1"].get("cvd_divergence", "none"),
                "key_support": tf["D1"]["support"],
                "key_resistance": tf["D1"]["resistance"],
                "at_support": tf["D1"].get("at_support", False),
                "at_resistance": tf["D1"].get("at_resistance", False),
                "recent_structure": tf["D1"]["structure"],
            },
            "H4": {
                "trend": tf["H4"]["trend"],
                "market_regime": market_regime(tf["H4"]["trend"], tf["H4"]["structure"]),
                "rsi_14": tf["H4"]["rsi"],
                "atr_14": tf["H4"].get("atr", 0),
                "nearest_support": extract_support(tf["H4"]),
                "nearest_resistance": extract_resistance(tf["H4"]),
                "at_support": tf["H4"].get("at_support", False),
                "at_resistance": tf["H4"].get("at_resistance", False),
                "momentum": "improving" if tf["H4"]["trend"] == direction.lower() else "declining",
                "volume_spike": tf["H4"]["volume_spike"],
                "volume_ratio": tf["H4"].get("volume_ratio", 0),
                "volume_trend": tf["H4"].get("volume_trend", "stable"),
                "obv_trend": tf["H4"].get("obv_trend", "flat"),
                "cvd_divergence": tf["H4"].get("cvd_divergence", "none"),
            },
            "H1": {
                "trend": tf["H1"]["trend"],
                "market_regime": "range_breakout_attempt" if tf["H1"]["bos"] or tf["H1"]["choch"] else "consolidation",
                "recent_breakout": tf["H1"]["bos"],
                "momentum_shift": "bullish" if tf["H1"]["choch"] and direction == "BUY" else "bearish" if tf["H1"]["choch"] else "neutral",
                "volume_spike": tf["H1"]["volume_spike"],
                "volume_ratio": tf["H1"].get("volume_ratio", 0),
                "volume_trend": tf["H1"].get("volume_trend", "stable"),
                "obv_trend": tf["H1"].get("obv_trend", "flat"),
                "cvd_divergence": tf["H1"].get("cvd_divergence", "none"),
                "support_zone": tf["H1"]["price_zone"].get("demand_zone", "") if direction == "BUY" else zone(tf["H1"], "resistance"),
                "resistance_zone": tf["H1"]["price_zone"].get("supply_zone", "") if direction == "SELL" else zone(tf["H1"], "support"),
                "at_support": tf["H1"].get("at_support", False),
                "at_resistance": tf["H1"].get("at_resistance", False),
            },
            "M15": {
                "trend": tf["M15"]["trend"],
                "momentum": "bullish" if direction == "BUY" else "bearish",
                "entry_context": "near_support" if direction == "BUY" else "near_resistance",
                "atr_14": tf["M15"].get("atr", 0),
                "at_support": tf["M15"].get("at_support", False),
                "at_resistance": tf["M15"].get("at_resistance", False),
                "volume_spike": tf["M15"]["volume_spike"],
                "volume_ratio": tf["M15"].get("volume_ratio", 0),
                "volume_trend": tf["M15"].get("volume_trend", "stable"),
            },
        },
        "zone_analysis": {
            "demand_zone_low": tf["H1"].get("demand_zone_low", 0),
            "demand_zone_high": tf["H1"].get("demand_zone_high", 0),
            "demand_test_count": tf["H1"].get("demand_zone_test_count", 0),
            "price_within_demand": tf["H1"].get("price_within_demand", False),
            "demand_reaction_score": tf["H1"].get("demand_reaction_score", 0),
            "supply_zone_low": tf["H1"].get("supply_zone_low", 0),
            "supply_zone_high": tf["H1"].get("supply_zone_high", 0),
            "supply_test_count": tf["H1"].get("supply_zone_test_count", 0),
            "price_within_supply": tf["H1"].get("price_within_supply", False),
            "supply_reaction_score": tf["H1"].get("supply_reaction_score", 0),
            "distance_to_demand_pct": tf["H1"].get("distance_to_demand_pct", 0),
            "distance_to_supply_pct": tf["H1"].get("distance_to_supply_pct", 0),
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
    bid_depth = float(orderflow.get("bid_depth") or 0)
    ask_depth = float(orderflow.get("ask_depth") or 0)
    depth_ratio = round(bid_depth / ask_depth, 3) if ask_depth > 0 else bid_depth
    depth_signal = "buy_pressure" if depth_ratio > 1.5 else "sell_pressure" if depth_ratio < 0.67 else "balanced"
    wall_side = orderflow.get("liquidity_wall_side", "none")
    wall_direction = "buy_support" if wall_side == "bid" else "sell_resistance" if wall_side == "ask" else "none"
    return {
        "window": orderflow.get("window", "1m"),
        "buy_volume": orderflow.get("buy_volume", 0),
        "sell_volume": orderflow.get("sell_volume", 0),
        "volume_delta": orderflow.get("volume_delta", 0),
        "cumulative_volume_delta": orderflow.get("cumulative_volume_delta", 0),
        "delta_ratio": orderflow.get("delta_ratio", 0),
        "trade_intensity": orderflow.get("trade_intensity", "low"),
        "large_trade_count": orderflow.get("large_trade_count", 0),
        "large_trade_buy_notional": orderflow.get("large_trade_buy_notional", 0),
        "large_trade_sell_notional": orderflow.get("large_trade_sell_notional", 0),
        "large_trade_buy_volume": orderflow.get("large_trade_buy_volume", 0),
        "large_trade_sell_volume": orderflow.get("large_trade_sell_volume", 0),
        "spread": orderflow.get("spread", 0),
        "bid_depth": round(bid_depth, 2),
        "ask_depth": round(ask_depth, 2),
        "depth_ratio": depth_ratio,
        "depth_signal": depth_signal,
        "best_bid": orderflow.get("best_bid", 0),
        "best_ask": orderflow.get("best_ask", 0),
        "orderbook_imbalance": orderflow.get("orderbook_imbalance", 0),
        "liquidity_wall_side": wall_side,
        "liquidity_wall_price": orderflow.get("liquidity_wall_price", 0),
        "wall_direction": wall_direction,
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
