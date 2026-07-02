from app.config import get_settings
from app.market_data.base_provider import MarketDataProvider
from app.market_data.bybit_provider import BybitProvider
from app.market_data.gate_provider import GateProvider
from app.market_data.kucoin_provider import KuCoinProvider
from app.market_data.mexc_provider import MEXCProvider
from app.market_data.okx_provider import OKXProvider


PROVIDERS = {
    "bybit": BybitProvider,
    "okx": OKXProvider,
    "gate": GateProvider,
    "mexc": MEXCProvider,
    "kucoin": KuCoinProvider,
}


def create_provider(name: str) -> MarketDataProvider:
    key = name.lower().strip()
    if key not in PROVIDERS:
        raise ValueError(f"Unknown market provider: {name}")
    return PROVIDERS[key]()


def configured_provider_names() -> list[str]:
    settings = get_settings()
    names = [settings.market_provider, settings.fallback_market_provider, settings.altcoin_provider]
    seen = []
    for name in names:
        key = name.lower().strip()
        if key and key not in seen:
            seen.append(key)
    return seen
