import logging
from time import time
from typing import Any


logger = logging.getLogger(__name__)

TTL_SECONDS: dict[str, int] = {
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}

_store: dict[tuple[str, str, str], tuple[float, list[dict[str, Any]]]] = {}
_hits: int = 0
_misses: int = 0
_sets: int = 0


def _key(provider: str, symbol: str, interval: str) -> tuple[str, str, str]:
    return (provider.lower(), symbol.upper(), interval)


def get(provider: str, symbol: str, interval: str, min_candles: int = 50) -> list[dict[str, Any]] | None:
    global _hits, _misses
    entry = _store.get(_key(provider, symbol, interval))
    if entry is None:
        _misses += 1
        return None
    timestamp, rows = entry
    if time() - timestamp > TTL_SECONDS.get(interval, 900):
        del _store[_key(provider, symbol, interval)]
        _misses += 1
        return None
    if len(rows) < min_candles:
        _misses += 1
        return None
    _hits += 1
    return rows


def set(provider: str, symbol: str, interval: str, rows: list[dict[str, Any]], min_candles: int = 50) -> None:
    global _sets
    if len(rows) >= min_candles:
        _store[_key(provider, symbol, interval)] = (time(), rows)
        _sets += 1


def clear() -> None:
    global _hits, _misses, _sets
    _store.clear()
    _hits = 0
    _misses = 0
    _sets = 0


def stats() -> dict[str, Any]:
    total = len(_store)
    by_interval: dict[str, int] = {}
    for (_provider, _symbol, interval), (_ts, rows) in _store.items():
        by_interval[interval] = by_interval.get(interval, 0) + 1
    hit_rate = round(_hits / (_hits + _misses) * 100, 1) if (_hits + _misses) else 0
    return {
        "total_entries": total,
        "by_interval": by_interval,
        "hits": _hits,
        "misses": _misses,
        "sets": _sets,
        "hit_rate_pct": hit_rate,
    }


def snapshot_stats() -> dict[str, Any]:
    return stats()
