import asyncio
import json
from typing import Any
from app.config import get_settings
from app.orderflow.base_orderflow import OrderflowProvider


class BybitOrderflowProvider(OrderflowProvider):
    name = "bybit"

    def __init__(self) -> None:
        settings = get_settings()
        super().__init__(settings.bybit_ws_linear_url, settings.orderflow_windows.split(","))

    async def send_subscribe(self, ws, args: list[str]) -> None:
        await ws.send(json.dumps({"op": "subscribe", "args": args}))

    async def subscribe_trades(self, symbols: list[str]):
        args = [f"publicTrade.{s}" for s in symbols]
        self.tasks.append(asyncio.create_task(self._connect(args, self.parse_message)))

    async def subscribe_orderbook(self, symbols: list[str], depth: int = 50):
        args = [f"orderbook.{depth}.{s}" for s in symbols]
        self.tasks.append(asyncio.create_task(self._connect(args, self.parse_message)))

    async def subscribe_ticker(self, symbols: list[str]):
        args = [f"tickers.{s}" for s in symbols]
        self.tasks.append(asyncio.create_task(self._connect(args, self.parse_message)))

    async def subscribe_kline(self, symbols: list[str], interval: str = "1m"):
        bybit_interval = "1" if interval == "1m" else interval.replace("m", "")
        args = [f"kline.{bybit_interval}.{s}" for s in symbols]
        self.tasks.append(asyncio.create_task(self._connect(args, self.parse_message)))

    async def subscribe_liquidations(self, symbols: list[str]):
        args = [f"liquidation.{s}" for s in symbols]
        self.tasks.append(asyncio.create_task(self._connect(args, self.parse_message)))

    async def parse_message(self, message: dict[str, Any]) -> None:
        topic = message.get("topic", "")
        data = message.get("data", [])
        if topic.startswith("publicTrade."):
            symbol = topic.split(".")[-1].upper()
            for item in data if isinstance(data, list) else [data]:
                side = item.get("S")
                self.trades.add_agg_trade(symbol, {"q": item.get("v"), "p": item.get("p"), "T": item.get("T"), "m": side == "Sell"})
        elif topic.startswith("tickers."):
            symbol = topic.split(".")[-1].upper()
            item = data if isinstance(data, dict) else {}
            self.orderbook.add_book_ticker(symbol, {"b": item.get("bid1Price"), "a": item.get("ask1Price"), "B": item.get("bid1Size"), "A": item.get("ask1Size")})
        elif topic.startswith("orderbook."):
            symbol = topic.split(".")[-1].upper()
            item = data if isinstance(data, dict) else {}
            self.orderbook.add_depth(symbol, {"b": item.get("b", []), "a": item.get("a", [])})
        elif topic.startswith("liquidation."):
            symbol = topic.split(".")[-1].upper()
            item = data if isinstance(data, dict) else {}
            self.liquidations.add_force_order(symbol, {"S": item.get("S"), "p": item.get("p"), "q": item.get("v"), "T": item.get("T")})
