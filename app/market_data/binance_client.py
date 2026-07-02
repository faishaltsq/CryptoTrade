import asyncio
import logging
from typing import Any
import httpx
from app.config import get_settings


logger = logging.getLogger(__name__)
REDIRECT_CODES = {301, 302, 303, 307, 308}


def binance_error(kind: str, message: str, **extra) -> dict[str, Any]:
    return {"_binance_error": True, "kind": kind, "message": message, **extra}


def is_binance_error(value: Any) -> bool:
    return isinstance(value, dict) and bool(value.get("_binance_error"))


class BinanceClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.base_urls = [self.settings.binance_futures_base_url.rstrip("/")]
        self.base_urls.extend(url.strip().rstrip("/") for url in self.settings.binance_futures_fallback_urls.split(",") if url.strip())
        self.base_urls = list(dict.fromkeys(self.base_urls))
        self.client = httpx.AsyncClient(timeout=self.settings.request_timeout_seconds, follow_redirects=False)

    async def close(self) -> None:
        await self.client.aclose()

    async def _get(self, path: str, params: dict[str, Any] | None = None, retries: int = 2) -> Any:
        last_error: dict[str, Any] | None = None
        for attempt in range(retries + 1):
            for base_url in self.base_urls:
                try:
                    await asyncio.sleep(self.settings.request_delay_seconds)
                    response = await self.client.get(f"{base_url}{path}", params=params)
                    if response.status_code in REDIRECT_CODES:
                        location = response.headers.get("location", "")
                        logger.warning("Binance redirect detected status=%s location=%s base_url=%s path=%s", response.status_code, location, base_url, path)
                        last_error = binance_error("redirect", "Redirect detected from Binance market endpoint", status_code=response.status_code, location=location, endpoint=f"{base_url}{path}")
                        continue
                    if response.status_code == 429:
                        retry_after = response.headers.get("retry-after")
                        logger.warning("Binance rate limit status=429 retry_after=%s path=%s", retry_after, path)
                        last_error = binance_error("rate_limit", "Binance rate limit 429", status_code=429, retry_after=retry_after, endpoint=f"{base_url}{path}")
                        await asyncio.sleep(float(retry_after or 1))
                        continue
                    if response.status_code == 418:
                        logger.error("Binance temporary ban/rate-limit status=418 path=%s", path)
                        return binance_error("temporary_ban", "Binance returned 418 temporary ban/rate-limit", status_code=418, endpoint=f"{base_url}{path}")
                    if response.status_code >= 400:
                        preview = response.text[:300]
                        logger.warning("Binance HTTP error status=%s path=%s body=%s", response.status_code, path, preview)
                        last_error = binance_error("http_error", "Binance HTTP error", status_code=response.status_code, body_preview=preview, endpoint=f"{base_url}{path}")
                        continue
                    try:
                        return response.json()
                    except ValueError:
                        preview = response.text[:300]
                        logger.warning("Binance non-JSON response path=%s content_type=%s body=%s", path, response.headers.get("content-type", ""), preview)
                        return binance_error("non_json", "Binance response is not valid JSON", status_code=response.status_code, content_type=response.headers.get("content-type", ""), body_preview=preview, endpoint=f"{base_url}{path}")
                except (httpx.HTTPError, ValueError) as exc:
                    last_error = binance_error("request_error", str(exc), endpoint=f"{base_url}{path}")
                    logger.warning("Binance request failed base_url=%s path=%s attempt=%s error=%s", base_url, path, attempt + 1, exc)
            wait = 0.5 * (attempt + 1)
            await asyncio.sleep(wait)
        return last_error or binance_error("unknown", f"Binance request failed after retries: {path}")

    async def get_exchange_info(self) -> dict[str, Any]:
        return await self._get("/fapi/v1/exchangeInfo")

    async def get_24h_tickers(self) -> list[dict[str, Any]] | dict[str, Any]:
        return await self._get("/fapi/v1/ticker/24hr")

    async def get_klines(self, symbol: str, interval: str, limit: int = 200) -> list[list[Any]] | dict[str, Any]:
        return await self._get("/fapi/v1/klines", {"symbol": symbol, "interval": interval, "limit": limit})

    async def get_depth(self, symbol: str, limit: int = 100) -> dict[str, Any]:
        return await self._get("/fapi/v1/depth", {"symbol": symbol, "limit": limit})

    async def get_premium_index(self, symbol: str | None = None) -> dict[str, Any] | list[dict[str, Any]]:
        params = {"symbol": symbol} if symbol else None
        return await self._get("/fapi/v1/premiumIndex", params)

    async def get_funding_rate(self, symbol: str, limit: int = 100) -> list[dict[str, Any]] | dict[str, Any]:
        return await self._get("/fapi/v1/fundingRate", {"symbol": symbol, "limit": limit})

    async def get_open_interest(self, symbol: str) -> dict[str, Any]:
        return await self._get("/fapi/v1/openInterest", {"symbol": symbol})

    async def get_open_interest_hist(self, symbol: str, period: str = "5m", limit: int = 30) -> list[dict[str, Any]] | dict[str, Any]:
        return await self._get("/futures/data/openInterestHist", {"symbol": symbol, "period": period, "limit": limit})

    async def get_global_long_short_ratio(self, symbol: str, period: str = "5m", limit: int = 30) -> list[dict[str, Any]] | dict[str, Any]:
        return await self._get("/futures/data/globalLongShortAccountRatio", {"symbol": symbol, "period": period, "limit": limit})

    async def get_taker_long_short_ratio(self, symbol: str, period: str = "5m", limit: int = 30) -> list[dict[str, Any]] | dict[str, Any]:
        return await self._get("/futures/data/takerlongshortRatio", {"symbol": symbol, "period": period, "limit": limit})

    async def exchange_info(self) -> dict[str, Any]:
        return await self.get_exchange_info()

    async def ticker_24hr(self) -> list[dict[str, Any]] | dict[str, Any]:
        return await self.get_24h_tickers()

    async def klines(self, symbol: str, interval: str, limit: int = 250) -> list[list[Any]] | dict[str, Any]:
        return await self.get_klines(symbol, interval, limit)

    async def premium_index(self, symbol: str) -> dict[str, Any]:
        return await self.get_premium_index(symbol)

    async def open_interest(self, symbol: str) -> dict[str, Any]:
        return await self.get_open_interest(symbol)

    async def open_interest_hist(self, symbol: str, period: str = "15m", limit: int = 2) -> list[dict[str, Any]] | dict[str, Any]:
        return await self.get_open_interest_hist(symbol, period, limit)

    async def global_long_short_ratio(self, symbol: str, period: str = "15m", limit: int = 1) -> list[dict[str, Any]] | dict[str, Any]:
        return await self.get_global_long_short_ratio(symbol, period, limit)

    async def taker_long_short_ratio(self, symbol: str, period: str = "15m", limit: int = 1) -> list[dict[str, Any]] | dict[str, Any]:
        return await self.get_taker_long_short_ratio(symbol, period, limit)


async def fetch_optional(coro, default=None):
    try:
        return await coro
    except Exception as exc:  # noqa: BLE001
        logger.warning("Optional Binance data failed: %s", exc)
        return default
