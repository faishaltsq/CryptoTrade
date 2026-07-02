import asyncio
import logging
from app.config import get_settings
from app.orderflow.orderflow_analyzer import enrich_orderflow
from app.orderflow.bybit_orderflow import BybitOrderflowProvider
from app.orderflow.gate_orderflow import GateOrderflowProvider
from app.orderflow.mexc_orderflow import MEXCOrderflowProvider
from app.orderflow.okx_orderflow import OKXOrderflowProvider


logger = logging.getLogger(__name__)


class OrderflowAggregator:
    def __init__(self) -> None:
        self.provider = None
        self.provider_name = ""
        self.depth_symbols: set[str] = set()
        self._has_active_ws: set[str] = set()

    def create(self, provider_name: str):
        providers = {"bybit": BybitOrderflowProvider, "okx": OKXOrderflowProvider, "gate": GateOrderflowProvider, "mexc": MEXCOrderflowProvider}
        return providers.get(provider_name, BybitOrderflowProvider)()

    def start(self, provider_name: str, symbols: list[str]) -> None:
        settings = get_settings()
        if not settings.enable_orderflow:
            return
        if self.provider and self.provider_name == provider_name and self._has_active_ws:
            return
        ws_priority = _ws_provider_order()
        limited = symbols[: settings.max_realtime_pairs]
        for name in ws_priority:
            try:
                ws_provider = self.create(name)
                logger.info("Orderflow trying provider=%s", name)
                if self.provider:
                    asyncio.create_task(self.provider.stop())
                self.provider = ws_provider
                self.provider_name = name
                self._has_active_ws = set()
                asyncio.create_task(self.provider.subscribe_trades(limited))
                asyncio.create_task(self.provider.subscribe_ticker(limited))
                asyncio.create_task(self.provider.subscribe_kline(limited, "1m"))
                if settings.enable_liquidation_stream:
                    asyncio.create_task(self.provider.subscribe_liquidations(limited))
                logger.info("Orderflow started provider=%s symbols=%s", name, len(limited))
                break
            except Exception as exc:  # noqa: BLE001
                logger.warning("Orderflow provider=%s failed, trying next: %s", name, exc)
                self.provider = None
                self.provider_name = ""
        if not self.provider:
            logger.warning("Orderflow all providers failed to start")

    def start_depth(self, provider_name: str, symbol: str) -> None:
        settings = get_settings()
        if not self.provider or len(self.depth_symbols) >= settings.max_depth_pairs or symbol in self.depth_symbols:
            return
        self.depth_symbols.add(symbol)
        asyncio.create_task(self.provider.subscribe_orderbook([symbol], depth=50))

    def summaries(self, symbol: str) -> dict:
        if self.provider:
            return self.provider.get_summaries(symbol)
        return {window: empty_summary(symbol, window) for window in ["10s", "1m", "5m"]}


def _ws_provider_order() -> list[str]:
    settings = get_settings()
    order = []
    for env_key in ("MARKET_PROVIDER", "FALLBACK_MARKET_PROVIDER", "ALTCOIN_PROVIDER"):
        name = getattr(settings, env_key.lower(), "")
        if name and name not in order:
            order.append(name)
    if "bybit" not in order:
        order.append("bybit")
    if "okx" not in order:
        order.append("okx")
    return order


def empty_summary(symbol: str, window: str) -> dict:
    return enrich_orderflow({"symbol": symbol, "window": window, "buy_volume": 0, "sell_volume": 0, "volume_delta": 0, "delta_ratio": 0, "cumulative_volume_delta": 0, "trade_count": 0, "trade_intensity": "low", "average_trade_size": 0, "large_trade_count": 0, "best_bid": 0, "best_ask": 0, "spread": 0, "bid_depth": 0, "ask_depth": 0, "bid_qty_top_levels": 0, "ask_qty_top_levels": 0, "orderbook_imbalance": 0, "liquidity_wall_side": "none", "liquidity_wall_price": 0, "liquidity_pull_detected": False, "liquidation_buy_notional": 0, "liquidation_sell_notional": 0, "liquidation_spike_detected": False})


orderflow_aggregator = OrderflowAggregator()
