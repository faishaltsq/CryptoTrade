def interpret_orderflow(summary: dict) -> str:
    delta = float(summary.get("volume_delta") or 0)
    imbalance = float(summary.get("orderbook_imbalance") or 0)
    liq_buy = float(summary.get("liquidation_buy_notional") or 0)
    liq_sell = float(summary.get("liquidation_sell_notional") or 0)
    spike = bool(summary.get("liquidation_spike_detected"))
    if delta > 0 and imbalance > 1.15 and spike and liq_sell > liq_buy:
        return "Buyer pressure dominant with sell-side liquidation spike."
    if delta < 0 and 0 < imbalance < 0.85 and spike and liq_buy > liq_sell:
        return "Seller pressure dominant with buy-side liquidation spike."
    if delta > 0 and imbalance > 1:
        return "Buyer pressure supports bid-side liquidity."
    if delta < 0 and 0 < imbalance < 1:
        return "Seller pressure supports ask-side liquidity."
    if float(summary.get("spread") or 0) > 0:
        return "Orderflow mixed; use only as confirmation."
    return "Insufficient realtime orderflow data."


def conflicts_with_direction(direction: str, summary: dict) -> bool:
    delta = float(summary.get("volume_delta") or 0)
    imbalance = float(summary.get("orderbook_imbalance") or 0)
    spread = float(summary.get("spread") or 0)
    avg_trade = float(summary.get("average_trade_size") or 0)
    if avg_trade and spread > avg_trade * 0.5:
        return True
    if direction == "BUY":
        return delta < 0 and 0 < imbalance < 0.75
    if direction == "SELL":
        return delta > 0 and imbalance > 1.35
    return False
