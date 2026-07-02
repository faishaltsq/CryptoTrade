from typing import Any
from app.orderflow.orderflow_models import OrderflowSummary


def enrich_orderflow(raw: dict[str, Any], direction: str | None = None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    summary = OrderflowSummary(**normalize_raw(raw))
    summary.absorption_signal = detect_absorption(summary, context or {})
    summary.orderflow_bias = detect_bias(summary)
    summary.orderflow_conflict = detect_conflict(summary, direction)
    summary.flow_interpretation = interpret_position_flow(summary)
    return summary.model_dump()


def normalize_raw(raw: dict[str, Any]) -> dict[str, Any]:
    data = dict(raw or {})
    data["price"] = float(data.get("price") or data.get("best_ask") or data.get("best_bid") or 0)
    data["bid_depth"] = float(data.get("bid_depth") or data.get("bid_qty_top_levels") or 0)
    data["ask_depth"] = float(data.get("ask_depth") or data.get("ask_qty_top_levels") or 0)
    data["flow_interpretation"] = data.get("flow_interpretation") or data.get("interpretation") or "Insufficient realtime orderflow data."
    return data


def spread_normal(summary: OrderflowSummary) -> bool:
    if summary.price <= 0 or summary.spread <= 0:
        return True
    return (summary.spread / summary.price) <= 0.0008


def detect_bias(summary: OrderflowSummary) -> str:
    if summary.trade_count < 5 and not summary.best_bid and not summary.best_ask:
        return "insufficient_data"
    if not spread_normal(summary):
        return "conflict"
    bullish = summary.volume_delta > 0 and summary.cumulative_volume_delta > 0 and summary.delta_ratio > 1.15 and summary.orderbook_imbalance > 1.10
    bearish = summary.volume_delta < 0 and summary.cumulative_volume_delta < 0 and 0 < summary.delta_ratio < 0.85 and 0 < summary.orderbook_imbalance < 0.90
    if bullish:
        return "bullish"
    if bearish:
        return "bearish"
    return "neutral"


def detect_conflict(summary: OrderflowSummary, direction: str | None) -> bool:
    if not direction or summary.orderflow_bias == "insufficient_data":
        return False
    if not spread_normal(summary):
        return True
    if direction == "BUY":
        return summary.volume_delta < -abs(summary.buy_volume + summary.sell_volume) * 0.25 or summary.cumulative_volume_delta < 0 or (0 < summary.orderbook_imbalance < 0.90)
    if direction == "SELL":
        return summary.volume_delta > abs(summary.buy_volume + summary.sell_volume) * 0.25 or summary.cumulative_volume_delta > 0 or summary.orderbook_imbalance > 1.10
    return False


def detect_absorption(summary: OrderflowSummary, context: dict[str, Any]) -> str:
    near_resistance = bool(context.get("near_resistance") or context.get("near_supply"))
    near_support = bool(context.get("near_support") or context.get("near_demand"))
    stagnant = abs(summary.volume_delta) > 0 and summary.spread >= 0
    if summary.buy_volume > summary.sell_volume * 1.5 and near_resistance and summary.ask_depth > summary.bid_depth * 1.2 and stagnant:
        return "possible_bearish_absorption"
    if summary.sell_volume > summary.buy_volume * 1.5 and near_support and summary.bid_depth > summary.ask_depth * 1.2 and stagnant:
        return "possible_bullish_absorption"
    return "none"


def interpret_position_flow(summary: OrderflowSummary) -> str:
    buy_pressure = summary.volume_delta > 0
    sell_pressure = summary.volume_delta < 0
    oi_up = summary.open_interest_change > 0
    oi_down = summary.open_interest_change < 0
    parts = []
    if buy_pressure and oi_up:
        parts.append("Buyer taker pressure is dominant. Open interest is rising, suggesting new long risk may be entering.")
    elif buy_pressure and oi_down:
        parts.append("Buyer taker pressure is dominant while open interest is falling, suggesting possible short covering.")
    elif sell_pressure and oi_up:
        parts.append("Seller taker pressure is dominant. Open interest is rising, suggesting new short risk may be entering.")
    elif sell_pressure and oi_down:
        parts.append("Seller taker pressure is dominant while open interest is falling, suggesting possible long closing.")
    else:
        parts.append("Orderflow is mixed or neutral.")
    if summary.liquidation_spike_detected:
        side = "sell-side" if summary.liquidation_sell_notional > summary.liquidation_buy_notional else "buy-side"
        parts.append(f"{side.capitalize()} liquidation spike detected.")
    if summary.absorption_signal != "none":
        parts.append(f"Absorption signal: {summary.absorption_signal}.")
    return " ".join(parts)
