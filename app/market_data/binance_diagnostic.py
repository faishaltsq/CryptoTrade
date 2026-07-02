import asyncio
import json
from typing import Any
import httpx
from app.config import get_settings


ENDPOINTS = [
    ("exchangeInfo", "/fapi/v1/exchangeInfo", None),
    ("ticker_24hr", "/fapi/v1/ticker/24hr", None),
    ("btcusdt_klines", "/fapi/v1/klines", {"symbol": "BTCUSDT", "interval": "1m", "limit": 10}),
]


async def run_binance_diagnostic() -> list[dict[str, Any]]:
    settings = get_settings()
    base_url = settings.binance_futures_base_url.rstrip("/")
    rows = []
    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds, follow_redirects=False) as client:
        for name, path, params in ENDPOINTS:
            endpoint = f"{base_url}{path}"
            try:
                response = await client.get(endpoint, params=params)
                rows.append(
                    {
                        "name": name,
                        "endpoint": endpoint,
                        "status_code": response.status_code,
                        "location": response.headers.get("location", ""),
                        "content_type": response.headers.get("content-type", ""),
                        "body_preview": response.text[:300],
                    }
                )
            except Exception as exc:  # noqa: BLE001
                rows.append({"name": name, "endpoint": endpoint, "error": str(exc)})
    return rows


def format_diagnostic(rows: list[dict[str, Any]]) -> str:
    lines = []
    for row in rows:
        status = row.get("status_code")
        if status == 200:
            verdict = "Binance market endpoint accessible"
        elif status in {301, 302, 303, 307, 308}:
            verdict = f"Redirect detected -> {row.get('location', '')}"
        elif status in {429, 418}:
            verdict = "Rate limit warning"
        else:
            verdict = row.get("error") or f"Unexpected status {status}"
        lines.append(
            "\n".join(
                [
                    f"Endpoint: {row.get('name')}",
                    f"URL: {row.get('endpoint')}",
                    f"Status: {status if status is not None else 'error'}",
                    f"Location: {row.get('location', '')}",
                    f"Content-Type: {row.get('content_type', '')}",
                    f"Result: {verdict}",
                    f"Body: {row.get('body_preview', '')[:300]}",
                ]
            )
        )
    return "\n\n".join(lines)


async def main() -> None:
    rows = await run_binance_diagnostic()
    print(json.dumps(rows, indent=2))
    print("\nSummary:\n" + format_diagnostic(rows))


if __name__ == "__main__":
    asyncio.run(main())
