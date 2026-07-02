import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import Any
import websockets
from app.orderflow.liquidation_flow import LiquidationFlowStore
from app.orderflow.orderbook_flow import OrderBookFlowStore
from app.orderflow.trade_flow import TradeFlowStore
from app.orderflow.volume_delta import interpret_orderflow


logger = logging.getLogger(__name__)
WINDOW_SECONDS = {"10s": 10, "1m": 60, "5m": 300}


class OrderflowProvider(ABC):
    name: str

    def __init__(self, ws_url: str, windows: list[str] | None = None) -> None:
        self.ws_url = ws_url
        self.windows = windows or ["10s", "1m", "5m"]
        self.trades = TradeFlowStore()
        self.orderbook = OrderBookFlowStore()
        self.liquidations = LiquidationFlowStore()
        self.tasks: list[asyncio.Task] = []

    async def stop(self) -> None:
        for task in self.tasks:
            if not task.done():
                task.cancel()
        self.tasks = []

    async def _connect(self, args: list[str], parser) -> None:
        backoff = 1
        while True:
            try:
                async with websockets.connect(self.ws_url, ping_interval=20, ping_timeout=20) as ws:
                    await self.send_subscribe(ws, args)
                    backoff = 1
                    async for message in ws:
                        try:
                            await parser(json.loads(message))
                        except Exception:  # noqa: BLE001
                            logger.exception("%s orderflow parse failed", self.name)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("%s orderflow websocket failed reconnect_in=%s", self.name, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

    @abstractmethod
    async def send_subscribe(self, ws, args: list[str]) -> None: ...

    @abstractmethod
    async def subscribe_trades(self, symbols: list[str]): ...

    @abstractmethod
    async def subscribe_orderbook(self, symbols: list[str], depth: int = 50): ...

    @abstractmethod
    async def subscribe_ticker(self, symbols: list[str]): ...

    @abstractmethod
    async def subscribe_kline(self, symbols: list[str], interval: str = "1m"): ...

    @abstractmethod
    async def subscribe_liquidations(self, symbols: list[str]): ...

    def get_summary(self, symbol: str, window: str = "1m") -> dict[str, Any]:
        seconds = WINDOW_SECONDS.get(window, 60)
        symbol = symbol.upper()
        summary = {
            "symbol": symbol,
            "window": window,
            **self.trades.summary(symbol, seconds),
            "cumulative_volume_delta": self.trades.cumulative_volume_delta(symbol),
            **self.orderbook.summary(symbol),
            "liquidity_pull_detected": self.orderbook.liquidity_pull_detected(symbol),
            **self.liquidations.summary(symbol, seconds),
        }
        summary["bid_depth"] = summary.get("bid_qty_top_levels", 0)
        summary["ask_depth"] = summary.get("ask_qty_top_levels", 0)
        summary["interpretation"] = interpret_orderflow(summary)
        return summary

    def get_summaries(self, symbol: str) -> dict[str, dict[str, Any]]:
        return {window: self.get_summary(symbol, window) for window in self.windows}
