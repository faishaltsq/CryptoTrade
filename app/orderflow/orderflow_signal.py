import logging
from typing import Any
from app.orderflow.liquidation_flow import LiquidationFlowStore
from app.orderflow.orderbook_flow import OrderBookFlowStore
from app.orderflow.trade_flow import TradeFlowStore
from app.orderflow.volume_delta import conflicts_with_direction, interpret_orderflow
from app.orderflow.websocket_client import BinanceFuturesWebSocketClient


logger = logging.getLogger(__name__)
WINDOWS = {"10s": 10, "1m": 60, "5m": 300}


class OrderflowSignalService:
    def __init__(self) -> None:
        self.trades = TradeFlowStore()
        self.orderbook = OrderBookFlowStore()
        self.liquidations = LiquidationFlowStore()
        self.ws = BinanceFuturesWebSocketClient(self.handle_message)
        self.monitored_symbols: set[str] = set()
        self.candidate_symbols: set[str] = set()

    def start_monitored_streams(self, symbols: list[str]) -> None:
        self.monitored_symbols = {s.upper() for s in symbols}
        streams = []
        for symbol in self.monitored_symbols:
            lower = symbol.lower()
            streams.extend([f"{lower}@aggTrade", f"{lower}@bookTicker", f"{lower}@kline_1m", f"{lower}@markPrice@1s"])
        self.ws.start("monitored", streams)

    def start_candidate_stream(self, symbol: str) -> None:
        self.candidate_symbols.add(symbol.upper())
        streams = []
        for item in self.candidate_symbols:
            lower = item.lower()
            streams.extend([f"{lower}@depth@500ms", f"{lower}@forceOrder"])
        self.ws.start("candidates", streams)

    def stop(self) -> None:
        self.ws.stop_all()

    async def handle_message(self, payload: dict[str, Any]) -> None:
        stream = payload.get("stream", "")
        data = payload.get("data", {})
        symbol = (data.get("s") or stream.split("@")[0]).upper()
        if not symbol:
            return
        event_type = data.get("e", "")
        if event_type == "aggTrade":
            self.trades.add_agg_trade(symbol, data)
        elif event_type == "bookTicker" or "bookTicker" in stream:
            self.orderbook.add_book_ticker(symbol, data)
        elif event_type == "depthUpdate":
            self.orderbook.add_depth(symbol, data)
        elif event_type == "forceOrder":
            self.liquidations.add_force_order(symbol, data)
        elif event_type in {"kline", "markPriceUpdate"}:
            return
        else:
            logger.debug("Unhandled orderflow event stream=%s event=%s", stream, event_type)

    def summary(self, symbol: str, window: str = "1m") -> dict[str, Any]:
        seconds = WINDOWS.get(window, 60)
        symbol = symbol.upper()
        trade = self.trades.summary(symbol, seconds)
        book = self.orderbook.summary(symbol)
        liq = self.liquidations.summary(symbol, seconds)
        summary = {
            "symbol": symbol,
            "window": window,
            **trade,
            "cumulative_volume_delta": self.trades.cumulative_volume_delta(symbol),
            **book,
            "liquidity_pull_detected": self.orderbook.liquidity_pull_detected(symbol),
            **liq,
        }
        summary["interpretation"] = interpret_orderflow(summary)
        return summary

    def summaries(self, symbol: str) -> dict[str, dict[str, Any]]:
        return {window: self.summary(symbol, window) for window in WINDOWS}

    def confirmation_conflicts(self, direction: str, symbol: str, window: str = "1m") -> bool:
        return conflicts_with_direction(direction, self.summary(symbol, window))


orderflow_service = OrderflowSignalService()
