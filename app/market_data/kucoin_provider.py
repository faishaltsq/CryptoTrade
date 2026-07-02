from typing import Any
from app.config import get_settings
from app.market_data.base_provider import MarketDataProvider, ProviderError


class KuCoinProvider(MarketDataProvider):
    name = "kucoin"

    def __init__(self) -> None:
        settings = get_settings()
        super().__init__(settings.kucoin_rest_base_url, settings.request_timeout_seconds)

    async def get_symbols(self) -> list[dict[str, Any]]:
        raise ProviderError(self.name, "kucoin_optional_provider_not_enabled")

    async def get_tickers(self) -> list[dict[str, Any]]:
        raise ProviderError(self.name, "kucoin_optional_provider_not_enabled")

    async def get_klines(self, symbol: str, interval: str, limit: int = 200) -> list[dict[str, Any]]:
        raise ProviderError(self.name, "kucoin_optional_provider_not_enabled")

    async def get_orderbook(self, symbol: str, limit: int = 50) -> dict[str, Any]:
        raise ProviderError(self.name, "kucoin_optional_provider_not_enabled")

    async def get_recent_trades(self, symbol: str, limit: int = 100) -> list[dict[str, Any]]:
        raise ProviderError(self.name, "kucoin_optional_provider_not_enabled")

    async def get_funding_rate(self, symbol: str) -> dict[str, Any]:
        return {"funding_rate": 0.0}

    async def get_open_interest(self, symbol: str) -> dict[str, Any]:
        return {"open_interest": 0.0, "open_interest_change": 0.0}
