from collections import defaultdict, deque
from time import time
from typing import Any


class TradeFlowStore:
    def __init__(self, max_age_seconds: int = 300) -> None:
        self.max_age_seconds = max_age_seconds
        self.trades: dict[str, deque[dict[str, float]]] = defaultdict(deque)

    def add_agg_trade(self, symbol: str, data: dict[str, Any]) -> None:
        qty = float(data.get("q") or 0)
        price = float(data.get("p") or 0)
        timestamp = float(data.get("T") or int(time() * 1000)) / 1000
        is_buyer_maker = bool(data.get("m"))
        side = "sell" if is_buyer_maker else "buy"
        self.trades[symbol].append({"ts": timestamp, "side": side, "qty": qty, "price": price, "notional": qty * price})
        self._prune(symbol)

    def summary(self, symbol: str, window_seconds: int) -> dict[str, float | int | str]:
        now = time()
        rows = [x for x in self.trades.get(symbol, []) if now - x["ts"] <= window_seconds]
        buy_volume = sum(x["qty"] for x in rows if x["side"] == "buy")
        sell_volume = sum(x["qty"] for x in rows if x["side"] == "sell")
        volume_delta = buy_volume - sell_volume
        total_volume = buy_volume + sell_volume
        avg_trade_size = total_volume / len(rows) if rows else 0.0
        large_threshold = max(avg_trade_size * 3, 0)
        large_trade_count = sum(1 for x in rows if x["qty"] > large_threshold) if rows and large_threshold else 0
        trades_per_second = len(rows) / max(window_seconds, 1)
        return {
            "buy_volume": round(buy_volume, 6),
            "sell_volume": round(sell_volume, 6),
            "volume_delta": round(volume_delta, 6),
            "delta_ratio": round(buy_volume / sell_volume, 4) if sell_volume else round(buy_volume, 4),
            "trade_count": len(rows),
            "trade_intensity": intensity(trades_per_second),
            "average_trade_size": round(avg_trade_size, 6),
            "large_trade_count": large_trade_count,
        }

    def cumulative_volume_delta(self, symbol: str) -> float:
        rows = self.trades.get(symbol, [])
        return round(sum(x["qty"] if x["side"] == "buy" else -x["qty"] for x in rows), 6)

    def _prune(self, symbol: str) -> None:
        cutoff = time() - self.max_age_seconds
        rows = self.trades[symbol]
        while rows and rows[0]["ts"] < cutoff:
            rows.popleft()


def intensity(trades_per_second: float) -> str:
    if trades_per_second >= 8:
        return "high"
    if trades_per_second >= 2:
        return "medium"
    return "low"
