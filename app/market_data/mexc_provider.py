from typing import Any
from app.config import get_settings
from app.market_data.base_provider import MarketDataProvider, normalize_interval
from app.market_data.symbol_mapper import internal_to_mexc, mexc_to_internal


class MEXCProvider(MarketDataProvider):
    name = "mexc"

    def __init__(self) -> None:
        settings = get_settings()
        super().__init__(settings.mexc_rest_base_url, settings.request_timeout_seconds)

    async def get_symbols(self) -> list[dict[str, Any]]:
        data = await self._get("/api/v1/contract/detail")
        rows = data.get("data", []) if isinstance(data, dict) else []
        return [{"symbol": mexc_to_internal(x["symbol"]), "provider_symbol": x["symbol"], "base": x.get("baseCoin"), "quote": "USDT", "status": "TRADING"} for x in rows if x.get("quoteCoin") == "USDT" and x.get("state") == 0]

    async def get_tickers(self) -> list[dict[str, Any]]:
        data = await self._get("/api/v1/contract/ticker")
        rows = data.get("data", []) if isinstance(data, dict) else []
        return [{"symbol": mexc_to_internal(x["symbol"]), "provider_symbol": x["symbol"], "last_price": float(x.get("lastPrice") or 0), "quote_volume": float(x.get("amount24") or 0), "bid": float(x.get("bid1") or 0), "ask": float(x.get("ask1") or 0), "spread_pct": 0} for x in rows if x.get("symbol", "").endswith("_USDT")]

    async def get_klines(self, symbol: str, interval: str, limit: int = 200) -> list[dict[str, Any]]:
        data = await self._get(f"/api/v1/contract/kline/{internal_to_mexc(symbol)}", {"interval": normalize_interval(interval, self.name)})
        raw = data.get("data", {}) if isinstance(data, dict) else {}
        times = raw.get("time", [])[-limit:]
        return [{"open_time": int(times[i]) * 1000, "open": raw.get("open", [])[i], "high": raw.get("high", [])[i], "low": raw.get("low", [])[i], "close": raw.get("close", [])[i], "volume": raw.get("vol", [])[i], "quote_volume": raw.get("amount", raw.get("vol", []))[i]} for i in range(len(times))]

    async def get_orderbook(self, symbol: str, limit: int = 50) -> dict[str, Any]:
        data = await self._get(f"/api/v1/contract/depth/{internal_to_mexc(symbol)}", {"limit": limit})
        item = data.get("data", {}) if isinstance(data, dict) else {}
        return {"bids": item.get("bids", []), "asks": item.get("asks", [])}

    async def get_recent_trades(self, symbol: str, limit: int = 100) -> list[dict[str, Any]]:
        data = await self._get(f"/api/v1/contract/deals/{internal_to_mexc(symbol)}", {"limit": limit})
        return data.get("data", []) if isinstance(data, dict) else []

    async def get_funding_rate(self, symbol: str) -> dict[str, Any]:
        return {"funding_rate": 0.0}

    async def get_open_interest(self, symbol: str) -> dict[str, Any]:
        return {"open_interest": 0.0, "open_interest_change": 0.0}
