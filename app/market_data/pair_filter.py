from typing import Any
from app.config import get_settings


def filter_usdt_perpetual_symbols(exchange_info: dict[str, Any]) -> set[str]:
    symbols = set()
    for item in exchange_info.get("symbols", []):
        if item.get("status") == "TRADING" and item.get("quoteAsset") == "USDT" and item.get("contractType") == "PERPETUAL":
            symbols.add(item["symbol"])
    return symbols


def top_volume_pairs(exchange_info: dict[str, Any], tickers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    settings = get_settings()
    allowed = filter_usdt_perpetual_symbols(exchange_info)
    rows = []
    for ticker in tickers:
        symbol = ticker.get("symbol")
        if symbol not in allowed:
            continue
        quote_volume = float(ticker.get("quoteVolume") or 0)
        last_price = float(ticker.get("lastPrice") or 0)
        bid = float(ticker.get("bidPrice") or 0)
        ask = float(ticker.get("askPrice") or 0)
        spread_pct = ((ask - bid) / last_price * 100) if last_price and ask and bid else 0
        rows.append({"symbol": symbol, "quote_volume": quote_volume, "last_price": last_price, "spread_pct": spread_pct, "raw": ticker})
    rows.sort(key=lambda x: x["quote_volume"], reverse=True)
    for idx, row in enumerate(rows, start=1):
        row["volume_rank"] = idx
    return rows[: settings.max_pairs]
