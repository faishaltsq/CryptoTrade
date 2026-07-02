from collections import defaultdict, deque
from time import time
from typing import Any


class LiquidationFlowStore:
    def __init__(self, max_age_seconds: int = 300) -> None:
        self.events: dict[str, deque[dict[str, float | str]]] = defaultdict(deque)
        self.max_age_seconds = max_age_seconds

    def add_force_order(self, symbol: str, data: dict[str, Any]) -> None:
        order = data.get("o", data)
        side = str(order.get("S", ""))
        price = float(order.get("p") or order.get("ap") or 0)
        qty = float(order.get("q") or 0)
        ts = float(order.get("T") or int(time() * 1000)) / 1000
        liquidation_side = "sell" if side == "SELL" else "buy" if side == "BUY" else "unknown"
        self.events[symbol].append({"ts": ts, "side": liquidation_side, "notional": price * qty})
        self._prune(symbol)

    def summary(self, symbol: str, window_seconds: int) -> dict[str, float | bool]:
        now = time()
        rows = [x for x in self.events.get(symbol, []) if now - float(x["ts"]) <= window_seconds]
        buy_notional = sum(float(x["notional"]) for x in rows if x["side"] == "buy")
        sell_notional = sum(float(x["notional"]) for x in rows if x["side"] == "sell")
        largest = max([float(x["notional"]) for x in rows], default=0.0)
        avg = (buy_notional + sell_notional) / len(rows) if rows else 0.0
        return {
            "liquidation_buy_notional": round(buy_notional, 2),
            "liquidation_sell_notional": round(sell_notional, 2),
            "liquidation_spike_detected": bool(largest > max(avg * 3, 50000)),
        }

    def _prune(self, symbol: str) -> None:
        cutoff = time() - self.max_age_seconds
        rows = self.events[symbol]
        while rows and float(rows[0]["ts"]) < cutoff:
            rows.popleft()
