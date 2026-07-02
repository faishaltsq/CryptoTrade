from typing import Any
import pandas as pd
from app.market_data.binance_client import BinanceClient, fetch_optional, is_binance_error


TIMEFRAMES = {"M15": "15m", "H1": "1h", "H4": "4h", "D1": "1d"}


def klines_to_dataframe(rows: list[list[Any]]) -> pd.DataFrame:
    columns = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore"]
    df = pd.DataFrame(rows, columns=columns)
    for col in ["open", "high", "low", "close", "volume", "quote_volume", "taker_buy_base", "taker_buy_quote"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
    return df


class CandleService:
    def __init__(self, client: BinanceClient) -> None:
        self.client = client

    async def get_multi_timeframe(self, symbol: str) -> dict[str, pd.DataFrame]:
        data = {}
        for name, interval in TIMEFRAMES.items():
            rows = await self.client.klines(symbol, interval, limit=250)
            if is_binance_error(rows):
                raise RuntimeError(rows.get("message", "Binance kline error"))
            data[name] = klines_to_dataframe(rows)
        return data

    async def get_futures_data(self, symbol: str) -> dict[str, Any]:
        premium = await fetch_optional(self.client.premium_index(symbol), {})
        oi = await fetch_optional(self.client.open_interest(symbol), {})
        oi_hist = await fetch_optional(self.client.open_interest_hist(symbol), [])
        ls_ratio = await fetch_optional(self.client.global_long_short_ratio(symbol), [])
        taker_ratio = await fetch_optional(self.client.taker_long_short_ratio(symbol), [])
        premium = {} if is_binance_error(premium) else premium
        oi = {} if is_binance_error(oi) else oi
        oi_hist = [] if is_binance_error(oi_hist) else oi_hist
        ls_ratio = [] if is_binance_error(ls_ratio) else ls_ratio
        taker_ratio = [] if is_binance_error(taker_ratio) else taker_ratio
        oi_change = 0.0
        if len(oi_hist or []) >= 2:
            prev = float(oi_hist[-2].get("sumOpenInterest", 0) or 0)
            cur = float(oi_hist[-1].get("sumOpenInterest", 0) or 0)
            oi_change = ((cur - prev) / prev * 100) if prev else 0.0
        return {
            "mark_price": float((premium or {}).get("markPrice") or 0),
            "funding_rate": float((premium or {}).get("lastFundingRate") or 0),
            "open_interest": float((oi or {}).get("openInterest") or 0),
            "open_interest_change": oi_change,
            "long_short_ratio": float((ls_ratio or [{}])[-1].get("longShortRatio") or 0),
            "taker_buy_sell_ratio": float((taker_ratio or [{}])[-1].get("buySellRatio") or 0),
        }
