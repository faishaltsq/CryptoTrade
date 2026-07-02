from collections import Counter
from typing import Any
import pandas as pd
from app.analysis.indicators import add_indicators, summarize_indicators
from app.analysis.market_structure import analyze_structure
from app.analysis.risk_reward import calculate_plan
from app.analysis.smc import fair_value_gap, liquidity_sweep, order_block
from app.config import get_settings


def analyze_timeframe(df: pd.DataFrame) -> dict[str, Any]:
    enriched = add_indicators(df)
    return {**summarize_indicators(enriched), **analyze_structure(enriched), "liquidity": liquidity_sweep(enriched), "order_block": order_block(enriched), "fvg": fair_value_gap(enriched)}


def detect_setup(symbol: str, candles: dict[str, pd.DataFrame], futures_data: dict[str, Any], volume_rank: int, spread_pct: float, orderflow: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, str, dict[str, Any]]:
    settings = get_settings()
    if any(len(df) < 210 for df in candles.values()):
        return None, "insufficient data", {}
    tf = {name: analyze_timeframe(df) for name, df in candles.items()}
    price = tf["M15"]["price"]
    if spread_pct > 0.08:
        return None, "spread too wide", tf
    if abs(float(futures_data.get("funding_rate") or 0)) > 0.0015:
        return None, "funding too extreme", tf
    higher = [tf["D1"]["trend"], tf["H4"]["trend"]]
    if "ranging" in higher:
        return None, "sideways", tf
    direction = candidate_direction(tf)
    if not direction:
        return None, reject_reason(tf), tf
    htf_conflict = (direction == "BUY" and "bearish" in higher) or (direction == "SELL" and "bullish" in higher)
    if htf_conflict and tf["H4"]["trend"] != direction.lower():
        return None, "conflicting timeframe", tf
    atr = tf["M15"]["atr"]
    plan = calculate_plan(direction, price, atr, tf["H1"].get("support", 0), tf["H1"].get("resistance", 0))
    if plan["risk_reward"] < settings.min_risk_reward:
        return None, "poor risk reward", tf
    if not (tf["M15"]["volume_spike"] or tf["H1"]["volume_spike"]):
        return None, "low volume", tf
    payload = build_ai_payload(symbol, direction, price, tf, futures_data, volume_rank, plan, orderflow or {})
    return payload, "candidate", tf


def candidate_direction(tf: dict[str, dict[str, Any]]) -> str | None:
    bullish_htf = tf["H4"]["trend"] == "bullish" or (tf["D1"]["trend"] == "bullish" and tf["H4"]["trend"] != "bearish")
    bearish_htf = tf["H4"]["trend"] == "bearish" or (tf["D1"]["trend"] == "bearish" and tf["H4"]["trend"] != "bullish")
    buy_trigger = tf["M15"]["choch"] or tf["M15"]["bos"] or tf["H1"]["bos"]
    sell_trigger = buy_trigger
    buy_liq = tf["H1"]["liquidity"] == "sell_side_swept" or tf["M15"]["liquidity"] == "sell_side_swept"
    sell_liq = tf["H1"]["liquidity"] == "buy_side_swept" or tf["M15"]["liquidity"] == "buy_side_swept"
    if bullish_htf and buy_trigger and (buy_liq or "bullish" in tf["H1"]["fvg"] or tf["H1"]["order_block"].get("demand_zone")):
        return "BUY"
    if bearish_htf and sell_trigger and (sell_liq or "bearish" in tf["H1"]["fvg"] or tf["H1"]["order_block"].get("supply_zone")):
        return "SELL"
    return None


def reject_reason(tf: dict[str, dict[str, Any]]) -> str:
    trends = [tf[k]["trend"] for k in ["D1", "H4", "H1", "M15"]]
    if Counter(trends).get("ranging", 0) >= 2:
        return "sideways"
    if tf["D1"]["trend"] != "unclear" and tf["H4"]["trend"] != "unclear" and tf["D1"]["trend"] != tf["H4"]["trend"]:
        return "conflicting timeframe"
    if not (tf["H1"]["bos"] or tf["H1"]["choch"] or tf["M15"]["bos"] or tf["M15"]["choch"]):
        return "weak structure"
    return "no clear entry"


def build_ai_payload(symbol: str, direction: str, price: float, tf: dict[str, dict[str, Any]], futures_data: dict[str, Any], volume_rank: int, plan: dict[str, Any], orderflow: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "market": "USDT_PERPETUAL",
        "price": price,
        "candidate_direction": direction,
        "timeframes": {
            "D1": {"trend": tf["D1"]["trend"], "structure": tf["D1"]["structure"], "rsi": tf["D1"]["rsi"], "ema_bias": tf["D1"]["ema_bias"], "key_support": tf["D1"]["support"], "key_resistance": tf["D1"]["resistance"]},
            "H4": {"trend": tf["H4"]["trend"], "structure": tf["H4"]["structure"], "poi": poi(tf["H4"], direction), "liquidity": tf["H4"]["liquidity"], "nearest_demand": tf["H4"]["order_block"].get("demand_zone", ""), "nearest_supply": tf["H4"]["order_block"].get("supply_zone", "")},
            "H1": {"trend": tf["H1"]["trend"], "bos": tf["H1"]["bos"], "choch": tf["H1"]["choch"], "fvg": tf["H1"]["fvg"], "order_block": "valid_demand" if direction == "BUY" else "valid_supply"},
            "M15": {"trigger": trigger(tf["M15"], direction), "entry_zone": plan["entry_zone"], "atr": tf["M15"]["atr"]},
        },
        "futures_data": {
            "funding_rate": f"{float(futures_data.get('funding_rate', 0)) * 100:.4f}%",
            "open_interest_change": f"{float(futures_data.get('open_interest_change', 0)):+.2f}%",
            "long_short_ratio": f"{float(futures_data.get('long_short_ratio', 0)):.2f}",
            "taker_buy_sell_ratio": f"{float(futures_data.get('taker_buy_sell_ratio', 0)):.2f}",
            "volume_24h_rank": volume_rank,
        },
        "orderflow": compact_orderflow(orderflow),
        "risk_plan": plan,
    }


def compact_orderflow(orderflow: dict[str, Any]) -> dict[str, Any]:
    if not orderflow:
        return {}
    return {
        "window": orderflow.get("window", "1m"),
        "buy_volume": orderflow.get("buy_volume", 0),
        "sell_volume": orderflow.get("sell_volume", 0),
        "volume_delta": orderflow.get("volume_delta", 0),
        "delta_ratio": orderflow.get("delta_ratio", 0),
        "cumulative_volume_delta": orderflow.get("cumulative_volume_delta", 0),
        "trade_intensity": orderflow.get("trade_intensity", "low"),
        "orderbook_imbalance": orderflow.get("orderbook_imbalance", 0),
        "spread": orderflow.get("spread", 0),
        "liquidity_wall_side": orderflow.get("liquidity_wall_side", "none"),
        "liquidation_spike_detected": orderflow.get("liquidation_spike_detected", False),
        "interpretation": orderflow.get("interpretation", ""),
    }


def poi(tf_item: dict[str, Any], direction: str) -> str:
    if direction == "BUY" and tf_item["order_block"].get("demand_zone"):
        return "demand_zone"
    if direction == "SELL" and tf_item["order_block"].get("supply_zone"):
        return "supply_zone"
    return tf_item.get("fvg", "none")


def trigger(tf_item: dict[str, Any], direction: str) -> str:
    side = "bullish" if direction == "BUY" else "bearish"
    if tf_item["choch"]:
        return f"choch_{side}"
    if tf_item["bos"]:
        return f"bos_{side}"
    return "wait_confirmation"
