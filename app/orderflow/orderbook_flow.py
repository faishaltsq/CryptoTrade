from collections import defaultdict, deque
from time import time
from typing import Any


class OrderBookFlowStore:
    def __init__(self, max_age_seconds: int = 300) -> None:
        self.book_ticker: dict[str, dict[str, float]] = {}
        self.depth_snapshots: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
        self.max_age_seconds = max_age_seconds

    def add_book_ticker(self, symbol: str, data: dict[str, Any]) -> None:
        bid = float(data.get("b") or 0)
        ask = float(data.get("a") or 0)
        bid_qty = float(data.get("B") or 0)
        ask_qty = float(data.get("A") or 0)
        self.book_ticker[symbol] = {"bid": bid, "ask": ask, "bid_qty": bid_qty, "ask_qty": ask_qty, "ts": time()}

    def add_depth(self, symbol: str, data: dict[str, Any]) -> None:
        bids = [(float(p), float(q)) for p, q in data.get("b", [])[:10]]
        asks = [(float(p), float(q)) for p, q in data.get("a", [])[:10]]
        self.depth_snapshots[symbol].append({"ts": time(), "bids": bids, "asks": asks})
        self._prune(symbol)

    def summary(self, symbol: str) -> dict[str, float | str]:
        ticker = self.book_ticker.get(symbol, {})
        latest_depth = self.depth_snapshots.get(symbol, deque())[-1] if self.depth_snapshots.get(symbol) else {}
        bids = latest_depth.get("bids", [])
        asks = latest_depth.get("asks", [])
        bid_qty = sum(q for _, q in bids) or float(ticker.get("bid_qty") or 0)
        ask_qty = sum(q for _, q in asks) or float(ticker.get("ask_qty") or 0)
        bid = float(ticker.get("bid") or (bids[0][0] if bids else 0))
        ask = float(ticker.get("ask") or (asks[0][0] if asks else 0))
        wall_side, wall_price = liquidity_wall(bids, asks)
        return {
            "best_bid": bid,
            "best_ask": ask,
            "bid_qty_top_levels": round(bid_qty, 6),
            "ask_qty_top_levels": round(ask_qty, 6),
            "orderbook_imbalance": round(bid_qty / ask_qty, 4) if ask_qty else round(bid_qty, 4),
            "spread": round(ask - bid, 8) if ask and bid else 0.0,
            "liquidity_wall_side": wall_side,
            "liquidity_wall_price": wall_price,
        }

    def liquidity_pull_detected(self, symbol: str) -> bool:
        rows = self.depth_snapshots.get(symbol, deque())
        if len(rows) < 2:
            return False
        prev, cur = rows[-2], rows[-1]
        prev_qty = sum(q for _, q in prev["bids"] + prev["asks"])
        cur_qty = sum(q for _, q in cur["bids"] + cur["asks"])
        return bool(prev_qty and cur_qty < prev_qty * 0.65)

    def _prune(self, symbol: str) -> None:
        cutoff = time() - self.max_age_seconds
        rows = self.depth_snapshots[symbol]
        while rows and rows[0]["ts"] < cutoff:
            rows.popleft()


def liquidity_wall(bids: list[tuple[float, float]], asks: list[tuple[float, float]]) -> tuple[str, float]:
    levels = [("bid", p, q) for p, q in bids] + [("ask", p, q) for p, q in asks]
    if not levels:
        return "none", 0.0
    side, price, _ = max(levels, key=lambda x: x[2])
    return side, float(price)
