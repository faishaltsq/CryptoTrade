from typing import Any
from app.market_data.base_provider import ProviderError
from app.market_data.provider_factory import configured_provider_names, create_provider


async def run_market_diagnostic() -> list[dict[str, Any]]:
    rows = []
    for name in configured_provider_names():
        provider = create_provider(name)
        result: dict[str, Any] = {"provider": name, "symbols": None, "tickers": None, "status": "unknown", "error": ""}
        try:
            symbols = await provider.get_symbols()
            tickers = await provider.get_tickers()
            result.update({"symbols": len(symbols), "tickers": len(tickers), "status": "ok" if symbols and tickers else "empty"})
        except ProviderError as exc:
            result.update({"status": "failed", "error": exc.message, "detail": exc.detail, "status_code": exc.status_code})
        except Exception as exc:  # noqa: BLE001
            result.update({"status": "failed", "error": str(exc)})
        finally:
            await provider.close()
        rows.append(result)
    return rows


def format_market_diagnostic(rows: list[dict[str, Any]]) -> str:
    lines = ["Market Provider Diagnostic"]
    for row in rows:
        lines.append(
            "\n".join(
                [
                    f"Provider: {row.get('provider')}",
                    f"Status: {row.get('status')}",
                    f"Symbols: {row.get('symbols')}",
                    f"Tickers: {row.get('tickers')}",
                    f"Error: {row.get('error', '')}",
                    f"Detail: {str(row.get('detail', ''))[:300]}",
                ]
            )
        )
    return "\n\n".join(lines)
