from typing import Any
from app.config import get_settings
from app.market_data.base_provider import MarketDataProvider, ProviderError, normalize_interval
from app.market_data.symbol_mapper import internal_to_okx, okx_to_internal


class OKXProvider(MarketDataProvider):
    name = "okx"

    def __init__(self) -> None:
        settings = get_settings()
        super().__init__(settings.okx_rest_base_url, settings.request_timeout_seconds)

    async def _public_get(self, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        data = await self._get(path, params)
        if str(data.get("code")) != "0":
            raise ProviderError(self.name, data.get("msg", "okx_error"), None, data)
        return data.get("data", [])

    async def get_symbols(self) -> list[dict[str, Any]]:
        data = await self._public_get("/api/v5/public/instruments", {"instType": "SWAP"})
        rows = []
        for item in data:
            if item.get("state") == "live" and item.get("settleCcy") == "USDT" and item.get("ctType") == "linear":
                rows.append({"symbol": okx_to_internal(item["instId"]), "provider_symbol": item["instId"], "base": item.get("ctValCcy"), "quote": "USDT", "status": "TRADING"})
        return rows

    async def get_tickers(self) -> list[dict[str, Any]]:
        data = await self._public_get("/api/v5/market/tickers", {"instType": "SWAP"})
        rows = []
        for item in data:
            if item.get("instId", "").endswith("-USDT-SWAP"):
                last = float(item.get("last") or 0)
                bid = float(item.get("bidPx") or 0)
                ask = float(item.get("askPx") or 0)
                open_24h = float(item.get("open24h") or 0)
                rows.append({"symbol": okx_to_internal(item["instId"]), "provider_symbol": item["instId"], "last_price": last, "price_change_pct": ((last - open_24h) / open_24h * 100) if last and open_24h else 0, "quote_volume": float(item.get("volCcy24h") or 0), "bid": bid, "ask": ask, "spread_pct": ((ask - bid) / last * 100) if last and bid and ask else 0})
        return rows

    async def get_klines(self, symbol: str, interval: str, limit: int = 200) -> list[dict[str, Any]]:
        inst_id = internal_to_okx(symbol) if not symbol.endswith("-SWAP") else symbol
        data = await self._public_get("/api/v5/market/candles", {"instId": inst_id, "bar": normalize_interval(interval, self.name), "limit": limit})
        rows = []
        for item in reversed(data):
            rows.append({"open_time": int(item[0]), "open": item[1], "high": item[2], "low": item[3], "close": item[4], "volume": item[5], "quote_volume": item[7] if len(item) > 7 else item[5]})
        return rows

    async def get_orderbook(self, symbol: str, limit: int = 50) -> dict[str, Any]:
        inst_id = internal_to_okx(symbol) if not symbol.endswith("-SWAP") else symbol
        data = await self._public_get("/api/v5/market/books", {"instId": inst_id, "sz": limit})
        item = data[0] if data else {}
        return {"bids": item.get("bids", []), "asks": item.get("asks", [])}

    async def get_recent_trades(self, symbol: str, limit: int = 100) -> list[dict[str, Any]]:
        inst_id = internal_to_okx(symbol) if not symbol.endswith("-SWAP") else symbol
        return await self._public_get("/api/v5/market/trades", {"instId": inst_id, "limit": limit})

    async def get_funding_rate(self, symbol: str) -> dict[str, Any]:
        inst_id = internal_to_okx(symbol) if not symbol.endswith("-SWAP") else symbol
        data = await self._public_get("/api/v5/public/funding-rate", {"instId": inst_id})
        item = data[0] if data else {}
        return {"funding_rate": float(item.get("fundingRate") or 0)}

    async def get_open_interest(self, symbol: str) -> dict[str, Any]:
        inst_id = internal_to_okx(symbol) if not symbol.endswith("-SWAP") else symbol
        data = await self._public_get("/api/v5/public/open-interest", {"instType": "SWAP", "instId": inst_id})
        item = data[0] if data else {}
        return {"open_interest": float(item.get("oiCcy") or item.get("oi") or 0), "open_interest_change": 0.0}
