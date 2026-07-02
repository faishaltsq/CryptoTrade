from typing import Any
from app.config import get_settings
from app.market_data.base_provider import MarketDataProvider, ProviderError, normalize_interval


class BybitProvider(MarketDataProvider):
    name = "bybit"

    def __init__(self) -> None:
        settings = get_settings()
        super().__init__(settings.bybit_rest_base_url, settings.request_timeout_seconds)

    async def _public_get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        data = await self._get(path, params)
        if str(data.get("retCode")) != "0":
            raise ProviderError(self.name, data.get("retMsg", "bybit_error"), None, data)
        return data.get("result", {})

    async def get_symbols(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        cursor = ""
        while True:
            params = {"category": "linear", "limit": 1000}
            if cursor:
                params["cursor"] = cursor
            result = await self._public_get("/v5/market/instruments-info", params)
            for item in result.get("list", []):
                if item.get("status") == "Trading" and item.get("quoteCoin") == "USDT" and item.get("contractType") == "LinearPerpetual":
                    rows.append({"symbol": item["symbol"], "provider_symbol": item["symbol"], "base": item.get("baseCoin"), "quote": "USDT", "status": "TRADING"})
            cursor = result.get("nextPageCursor") or ""
            if not cursor:
                break
        return rows

    async def get_tickers(self) -> list[dict[str, Any]]:
        result = await self._public_get("/v5/market/tickers", {"category": "linear"})
        rows = []
        for item in result.get("list", []):
            if item.get("symbol", "").endswith("USDT"):
                last = float(item.get("lastPrice") or 0)
                bid = float(item.get("bid1Price") or 0)
                ask = float(item.get("ask1Price") or 0)
                rows.append({"symbol": item["symbol"], "provider_symbol": item["symbol"], "last_price": last, "price_change_pct": float(item.get("price24hPcnt") or 0) * 100, "quote_volume": float(item.get("turnover24h") or 0), "bid": bid, "ask": ask, "spread_pct": ((ask - bid) / last * 100) if last and bid and ask else 0})
        return rows

    async def get_klines(self, symbol: str, interval: str, limit: int = 200) -> list[dict[str, Any]]:
        result = await self._public_get("/v5/market/kline", {"category": "linear", "symbol": symbol, "interval": normalize_interval(interval, self.name), "limit": limit})
        rows = []
        for item in reversed(result.get("list", [])):
            rows.append({"open_time": int(item[0]), "open": item[1], "high": item[2], "low": item[3], "close": item[4], "volume": item[5], "quote_volume": item[6]})
        return rows

    async def get_orderbook(self, symbol: str, limit: int = 50) -> dict[str, Any]:
        result = await self._public_get("/v5/market/orderbook", {"category": "linear", "symbol": symbol, "limit": limit})
        return {"bids": result.get("b", []), "asks": result.get("a", [])}

    async def get_recent_trades(self, symbol: str, limit: int = 100) -> list[dict[str, Any]]:
        result = await self._public_get("/v5/market/recent-trade", {"category": "linear", "symbol": symbol, "limit": limit})
        return result.get("list", [])

    async def get_funding_rate(self, symbol: str) -> dict[str, Any]:
        result = await self._public_get("/v5/market/funding/history", {"category": "linear", "symbol": symbol, "limit": 1})
        item = (result.get("list") or [{}])[0]
        return {"funding_rate": float(item.get("fundingRate") or 0)}

    async def get_open_interest(self, symbol: str) -> dict[str, Any]:
        result = await self._public_get("/v5/market/open-interest", {"category": "linear", "symbol": symbol, "intervalTime": "5min", "limit": 2})
        rows = result.get("list") or []
        current = float(rows[0].get("openInterest") or 0) if rows else 0.0
        previous = float(rows[1].get("openInterest") or 0) if len(rows) > 1 else 0.0
        change = ((current - previous) / previous * 100) if previous else 0.0
        return {"open_interest": current, "open_interest_change": change}
