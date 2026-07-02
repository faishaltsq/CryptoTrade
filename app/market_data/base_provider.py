import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any
import httpx


logger = logging.getLogger(__name__)


class ProviderError(RuntimeError):
    def __init__(self, provider: str, message: str, status_code: int | None = None, detail: Any = None) -> None:
        super().__init__(message)
        self.provider = provider
        self.message = message
        self.status_code = status_code
        self.detail = detail

    def to_dict(self) -> dict[str, Any]:
        return {"provider": self.provider, "message": self.message, "status_code": self.status_code, "detail": self.detail}


class MarketDataProvider(ABC):
    name: str

    def __init__(self, base_url: str, timeout: float = 15.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=timeout, follow_redirects=False)

    async def close(self) -> None:
        await self.client.aclose()

    async def _get(self, path: str, params: dict[str, Any] | None = None, retries: int = 2) -> Any:
        last_error: ProviderError | None = None
        for attempt in range(retries + 1):
            try:
                response = await self.client.get(f"{self.base_url}{path}", params=params)
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location", "")
                    logger.warning("%s redirect status=%s location=%s path=%s", self.name, response.status_code, location, path)
                    raise ProviderError(self.name, "redirect_detected", response.status_code, {"location": location, "path": path})
                if response.status_code == 429:
                    retry_after = float(response.headers.get("retry-after") or attempt + 1)
                    logger.warning("%s rate limited path=%s retry_after=%s", self.name, path, retry_after)
                    await asyncio.sleep(retry_after)
                    continue
                if response.status_code == 418:
                    raise ProviderError(self.name, "temporary_ban_or_rate_limit", 418, {"path": path})
                if response.status_code >= 400:
                    raise ProviderError(self.name, "http_error", response.status_code, response.text[:300])
                try:
                    return response.json()
                except ValueError as exc:
                    raise ProviderError(self.name, "non_json_response", response.status_code, response.text[:300]) from exc
            except ProviderError as exc:
                last_error = exc
                if exc.status_code in {301, 302, 303, 307, 308, 418}:
                    break
            except httpx.HTTPError as exc:
                last_error = ProviderError(self.name, str(exc), None, {"path": path})
                logger.warning("%s request failed path=%s attempt=%s error=%s", self.name, path, attempt + 1, exc)
            await asyncio.sleep(0.5 * (attempt + 1))
        raise last_error or ProviderError(self.name, "request_failed", None, {"path": path})

    @abstractmethod
    async def get_symbols(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def get_tickers(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def get_klines(self, symbol: str, interval: str, limit: int = 200) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def get_orderbook(self, symbol: str, limit: int = 50) -> dict[str, Any]: ...

    @abstractmethod
    async def get_recent_trades(self, symbol: str, limit: int = 100) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def get_funding_rate(self, symbol: str) -> dict[str, Any]: ...

    @abstractmethod
    async def get_open_interest(self, symbol: str) -> dict[str, Any]: ...


def normalize_interval(interval: str, provider: str) -> str:
    maps = {
        "bybit": {"15m": "15", "1h": "60", "4h": "240", "1d": "D"},
        "okx": {"15m": "15m", "1h": "1H", "4h": "4H", "1d": "1D"},
        "gate": {"15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"},
        "mexc": {"15m": "Min15", "1h": "Min60", "4h": "Hour4", "1d": "Day1"},
    }
    return maps.get(provider, {}).get(interval, interval)


def empty_optional_market_data() -> dict[str, Any]:
    return {"funding_rate": 0.0, "open_interest": 0.0, "open_interest_change": 0.0, "long_short_ratio": 0.0, "taker_buy_sell_ratio": 0.0}
