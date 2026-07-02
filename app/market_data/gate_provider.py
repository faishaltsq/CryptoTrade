from typing import Any
from app.config import get_settings
from app.market_data.base_provider import MarketDataProvider, normalize_interval
from app.market_data.symbol_mapper import gate_to_internal, internal_to_gate


class GateProvider(MarketDataProvider):
    name = "gate"

    def __init__(self) -> None:
        settings = get_settings()
        super().__init__(settings.gate_rest_base_url, settings.request_timeout_seconds)

    async def get_symbols(self) -> list[dict[str, Any]]:
        data = await self._get("/futures/usdt/contracts")
        return [{"symbol": gate_to_internal(x["name"]), "provider_symbol": x["name"], "base": x.get("underlying"), "quote": "USDT", "status": "TRADING"} for x in data if not x.get("in_delisting") and x.get("name", "").endswith("_USDT")]

    async def get_tickers(self) -> list[dict[str, Any]]:
        data = await self._get("/futures/usdt/tickers")
        rows = []
        for x in data:
            contract = x.get("contract", "")
            if contract.endswith("_USDT"):
                last = float(x.get("last") or 0)
                rows.append({"symbol": gate_to_internal(contract), "provider_symbol": contract, "last_price": last, "quote_volume": float(x.get("volume_24h_quote") or 0), "bid": 0, "ask": 0, "spread_pct": 0})
        return rows

    async def get_klines(self, symbol: str, interval: str, limit: int = 200) -> list[dict[str, Any]]:
        data = await self._get("/futures/usdt/candlesticks", {"contract": internal_to_gate(symbol), "interval": normalize_interval(interval, self.name), "limit": limit})
        return [{"open_time": int(float(x.get("t", 0)) * 1000), "open": x.get("o"), "high": x.get("h"), "low": x.get("l"), "close": x.get("c"), "volume": x.get("v"), "quote_volume": x.get("sum", x.get("v"))} for x in data]

    async def get_orderbook(self, symbol: str, limit: int = 50) -> dict[str, Any]:
        data = await self._get("/futures/usdt/order_book", {"contract": internal_to_gate(symbol), "limit": limit})
        return {"bids": [[x.get("p"), x.get("s")] for x in data.get("bids", [])], "asks": [[x.get("p"), x.get("s")] for x in data.get("asks", [])]}

    async def get_recent_trades(self, symbol: str, limit: int = 100) -> list[dict[str, Any]]:
        return await self._get("/futures/usdt/trades", {"contract": internal_to_gate(symbol), "limit": limit})

    async def get_funding_rate(self, symbol: str) -> dict[str, Any]:
        data = await self.get_tickers()
        item = next((x for x in data if x["symbol"] == symbol), {})
        return {"funding_rate": float(item.get("funding_rate") or 0)}

    async def get_open_interest(self, symbol: str) -> dict[str, Any]:
        return {"open_interest": 0.0, "open_interest_change": 0.0}
