import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any
import websockets
from app.config import get_settings


logger = logging.getLogger(__name__)
MessageHandler = Callable[[dict[str, Any]], Awaitable[None]]


class BinanceFuturesWebSocketClient:
    def __init__(self, handler: MessageHandler, base_url: str | None = None) -> None:
        self.handler = handler
        ws_url = (base_url or get_settings().binance_futures_ws_url).rstrip("/")
        self.base_url = ws_url.replace("/ws", "/stream?streams=") if ws_url.endswith("/ws") else ws_url
        self.tasks: dict[str, asyncio.Task] = {}
        self.stream_sets: dict[str, set[str]] = {}

    def start(self, name: str, streams: list[str]) -> None:
        normalized = {s.lower() for s in streams}
        if self.stream_sets.get(name) == normalized and name in self.tasks and not self.tasks[name].done():
            return
        self.stop(name)
        self.stream_sets[name] = normalized
        if normalized:
            self.tasks[name] = asyncio.create_task(self._run(name, sorted(normalized)))

    def stop(self, name: str) -> None:
        task = self.tasks.pop(name, None)
        if task and not task.done():
            task.cancel()

    def stop_all(self) -> None:
        for name in list(self.tasks):
            self.stop(name)

    async def _run(self, name: str, streams: list[str]) -> None:
        backoff = 1
        separator = "" if self.base_url.endswith("=") else "/"
        url = self.base_url + separator + "/".join(streams)
        while True:
            try:
                logger.info("Orderflow websocket connecting name=%s streams=%s", name, len(streams))
                async with websockets.connect(url, ping_interval=20, ping_timeout=20, close_timeout=10) as ws:
                    backoff = 1
                    async for message in ws:
                        try:
                            payload = json.loads(message)
                            await self.handler(payload)
                        except Exception:  # noqa: BLE001
                            logger.exception("Orderflow websocket message handling failed name=%s", name)
            except asyncio.CancelledError:
                logger.info("Orderflow websocket stopped name=%s", name)
                raise
            except Exception:  # noqa: BLE001
                logger.exception("Orderflow websocket disconnected name=%s reconnect_in=%s", name, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)
