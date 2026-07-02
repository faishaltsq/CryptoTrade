from app.config import get_settings
from app.orderflow.base_orderflow import OrderflowProvider


class MEXCOrderflowProvider(OrderflowProvider):
    name = "mexc"

    def __init__(self) -> None:
        settings = get_settings()
        super().__init__(settings.mexc_spot_ws_url, settings.orderflow_windows.split(","))

    async def send_subscribe(self, ws, args: list[str]) -> None: return None
    async def subscribe_trades(self, symbols: list[str]): return None
    async def subscribe_orderbook(self, symbols: list[str], depth: int = 50): return None
    async def subscribe_ticker(self, symbols: list[str]): return None
    async def subscribe_kline(self, symbols: list[str], interval: str = "1m"): return None
    async def subscribe_liquidations(self, symbols: list[str]): return None
