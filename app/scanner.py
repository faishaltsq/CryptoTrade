import logging
from time import time
from typing import Any
import pandas as pd
from app.ai.deepseek_client import DeepSeekClient
from app.analysis.setup_detector import detect_setup
from app.config import get_settings
from app.database.repository import get_setting, save_orderflow_snapshot, save_rejected_setup, save_scan_log, save_signal_log, update_signal_status
from app.database.session import SessionLocal
from app.learning.adaptive_scoring import apply_adaptive_scoring
from app.learning.learning_prompt_builder import learning_context
from app.learning.lesson_manager import active_lessons_for_prompt
from app.learning.performance_analyzer import analyze_performance
from app.market_data.base_provider import MarketDataProvider, ProviderError, empty_optional_market_data
from app.market_data.provider_factory import configured_provider_names, create_provider
from app.orderflow.orderflow_analyzer import enrich_orderflow
from app.orderflow.orderflow_aggregator import orderflow_aggregator
from app.signal.broadcaster import SignalBroadcaster
from app.signal.validator import validate_for_broadcast


logger = logging.getLogger(__name__)


class MarketScanner:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.ai = DeepSeekClient()
        self.broadcaster = SignalBroadcaster()

    async def scan(self) -> dict[str, Any]:
        db = SessionLocal()
        rejected_reasons: list[str] = []
        candidates = 0
        valid_signals = 0
        pairs: list[dict[str, Any]] = []
        provider: MarketDataProvider | None = None
        provider_errors: list[dict[str, Any]] = []
        try:
            provider, pairs, provider_errors = await self.load_pairs_from_providers()
            if not provider:
                summary = {"status": "skipped", "reason": "market_data_unavailable", "provider_errors": provider_errors}
                save_scan_log(db, 0, 0, 0, 0, summary)
                await self.broadcaster.bot.send_admin("Market data provider tidak bisa diakses. Scan dilewati.\n" + format_provider_errors(provider_errors))
                return {"status": "skipped", "summary": summary}
            if self.settings.enable_orderflow:
                orderflow_aggregator.start(provider.name, [p["symbol"] for p in pairs[: self.settings.max_realtime_pairs]])
            for pair in pairs:
                symbol = pair["symbol"]
                try:
                    candles = await self.get_multi_timeframe(provider, symbol)
                    futures_data = await self.get_futures_data(provider, symbol)
                    orderflow_summaries = orderflow_aggregator.summaries(symbol)
                    if orderflow_summaries["1m"].get("trade_count", 0) == 0:
                        rest_orderflow = await self.get_rest_orderflow(provider, symbol)
                        if rest_orderflow.get("trade_count", 0) > 0:
                            orderflow_summaries = {window: {**rest_orderflow, "window": window} for window in ["10s", "1m", "5m"]}
                    for snapshot in orderflow_summaries.values():
                        snapshot.update({"open_interest": futures_data.get("open_interest", 0), "open_interest_change": futures_data.get("open_interest_change", 0)})
                        enriched = enrich_orderflow(snapshot)
                        if enriched.get("trade_count", 0) > 0:
                            save_orderflow_snapshot(db, enriched)
                    orderflow_summary = orderflow_summaries["1m"]
                    candidate, reason, tf_summary = detect_setup(symbol, candles, futures_data, pair.get("volume_rank", 0), pair.get("spread_pct", 0), orderflow_summary)
                    if not candidate:
                        rejected_reasons.append(reason)
                        save_rejected_setup(db, symbol, reason, {**tf_summary, "orderflow": orderflow_summary})
                        continue
                    candidate["provider"] = provider.name
                    active_lessons = active_lessons_for_prompt(db) if self.settings.enable_signal_learning else []
                    performance = analyze_performance(db, f"{self.settings.performance_lookback_days}d") if self.settings.enable_signal_learning else {}
                    candidate["learning_context"] = learning_context(active_lessons, performance)
                    candidate["active_lessons"] = candidate["learning_context"].get("active_lessons", [])
                    candidate["ai_prompt_version"] = self.settings.learning_prompt_version
                    if self.settings.enable_adaptive_scoring:
                        candidate = apply_adaptive_scoring(candidate, active_lessons, performance)
                        if candidate.get("adaptive_reject_reason"):
                            reason = "adaptive_filter: " + candidate["adaptive_reject_reason"]
                            rejected_reasons.append(reason)
                            save_rejected_setup(db, symbol, reason, {**tf_summary, "orderflow": orderflow_summary, "adaptive_scoring": candidate.get("adaptive_scoring", {})})
                            continue
                    candidates += 1
                    if self.settings.enable_orderflow:
                        orderflow_aggregator.start_depth(provider.name, symbol)
                    ai_response, ai_error = await self.ai.analyze(candidate)
                    ai_response.setdefault("orderflow", {"bias": candidate.get("orderflow", {}).get("orderflow_bias", "insufficient_data"), "confirmation": False, "conflict": candidate.get("orderflow", {}).get("orderflow_conflict", False), "score": candidate.get("orderflow", {}).get("orderflow_score", 0), "absorption_signal": candidate.get("orderflow", {}).get("absorption_signal", "none"), "interpretation": candidate.get("orderflow", {}).get("flow_interpretation", "")})
                    if candidate.get("orderflow", {}).get("orderflow_conflict"):
                        ai_response["orderflow"]["conflict"] = True
                        ai_response["broadcast_allowed"] = False
                    ai_response["scores"] = candidate.get("scores", {})
                    adaptive = candidate.get("adaptive_scoring", {}) or {}
                    if adaptive.get("confidence_adjustment"):
                        ai_response["confidence"] = max(0, min(100, int(ai_response.get("confidence") or 0) + int(adaptive["confidence_adjustment"])))
                        ai_response["adaptive_scoring"] = adaptive
                    ai_response["orderflow_summary"] = candidate.get("orderflow", {})
                    if ai_error:
                        logger.warning("AI response issue symbol=%s error=%s", symbol, ai_error)
                    ok, validation_reason = validate_for_broadcast(ai_response)
                    row = save_signal_log(db, candidate, ai_response, status="pending" if ok else "rejected")
                    if ok:
                        valid_signals += 1
                        await self.broadcaster.send_candidate_to_admin(row.id, ai_response)
                        if auto_broadcast_enabled(db, self.settings.auto_broadcast):
                            await self.broadcaster.broadcast_channel(ai_response)
                            update_signal_status(db, row.id, "broadcasted", "broadcasted")
                    else:
                        rejected_reasons.append(validation_reason)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Scan failed for symbol=%s", symbol)
                    rejected_reasons.append("scanner error")
                    save_rejected_setup(db, symbol, "scanner error", {"error": str(exc)})
            summary = {
                "pairs": [p["symbol"] for p in pairs],
                "top_volume": [{"symbol": p["symbol"], "quote_volume": p["quote_volume"], "last_price": p.get("last_price", 0), "price_change_pct": p.get("price_change_pct", 0), "rank": p["volume_rank"]} for p in pairs[:20]],
                "rejected_reasons": rejected_reasons,
                "provider": provider.name,
            }
            save_scan_log(db, len(pairs), candidates, valid_signals, len(rejected_reasons), summary)
            if valid_signals == 0:
                await self.broadcaster.send_no_valid_setup(len(pairs), rejected_reasons, self.settings.scan_interval_minutes)
            return {"total_pairs": len(pairs), "candidates": candidates, "valid_signals": valid_signals, "rejected": len(rejected_reasons), "summary": summary}
        finally:
            db.close()
            if provider:
                await provider.close()

    async def load_pairs_from_providers(self) -> tuple[MarketDataProvider | None, list[dict[str, Any]], list[dict[str, Any]]]:
        errors = []
        for name in configured_provider_names():
            provider = create_provider(name)
            try:
                symbols = await provider.get_symbols()
                tickers = await provider.get_tickers()
                pairs = merge_top_pairs(symbols, tickers, self.settings.max_pairs)
                if pairs:
                    return provider, pairs, errors
                errors.append({"provider": name, "message": "no_pairs_after_filter"})
                await provider.close()
            except ProviderError as exc:
                errors.append(exc.to_dict())
                await provider.close()
            except Exception as exc:  # noqa: BLE001
                errors.append({"provider": name, "message": str(exc)})
                await provider.close()
        return None, [], errors

    async def get_multi_timeframe(self, provider: MarketDataProvider, symbol: str) -> dict[str, pd.DataFrame]:
        timeframes = {"M15": "15m", "H1": "1h", "H4": "4h", "D1": "1d"}
        return {name: klines_to_dataframe(await provider.get_klines(symbol, interval, limit=250)) for name, interval in timeframes.items()}

    async def get_futures_data(self, provider: MarketDataProvider, symbol: str) -> dict[str, Any]:
        data = empty_optional_market_data()
        try:
            data.update(await provider.get_funding_rate(symbol))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Funding data failed provider=%s symbol=%s error=%s", provider.name, symbol, exc)
        try:
            data.update(await provider.get_open_interest(symbol))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Open interest failed provider=%s symbol=%s error=%s", provider.name, symbol, exc)
        return data

    async def get_rest_orderflow(self, provider: MarketDataProvider, symbol: str) -> dict[str, Any]:
        try:
            trades = await provider.get_recent_trades(symbol, limit=100)
            orderbook = await provider.get_orderbook(symbol, limit=50)
            return build_rest_orderflow_summary(symbol, trades, orderbook)
        except Exception as exc:  # noqa: BLE001
            logger.warning("REST orderflow failed provider=%s symbol=%s error=%s", provider.name, symbol, exc)
            return {}


def merge_top_pairs(symbols: list[dict[str, Any]], tickers: list[dict[str, Any]], max_pairs: int) -> list[dict[str, Any]]:
    active = {x["symbol"]: x for x in symbols if x.get("status") == "TRADING" and x.get("quote") == "USDT" and is_crypto_perp_symbol(x)}
    rows = []
    for ticker in tickers:
        symbol = ticker.get("symbol")
        if symbol not in active:
            continue
        rows.append({**active[symbol], **ticker})
    rows.sort(key=lambda x: float(x.get("quote_volume") or 0), reverse=True)
    for idx, row in enumerate(rows, start=1):
        row["volume_rank"] = idx
    return rows[:max_pairs]


def is_crypto_perp_symbol(row: dict[str, Any]) -> bool:
    base = str(row.get("base") or row.get("symbol", "").replace("USDT", "")).upper()
    denylist = {"XAU", "XAG", "SOXL", "SNDK", "SKHYNIX", "MU", "NVDA", "AAPL", "TSLA", "META", "GOOGL", "AMZN", "MSFT", "MSTR", "COIN"}
    return base not in denylist


def klines_to_dataframe(rows: list[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    for col in ["open", "high", "low", "close", "volume", "quote_volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = df["open_time"]
    return df


def build_rest_orderflow_summary(symbol: str, trades: list[dict[str, Any]], orderbook: dict[str, Any]) -> dict[str, Any]:
    cutoff_ms = int((time() - 60) * 1000)
    buy_volume = 0.0
    sell_volume = 0.0
    total_qty = 0.0
    trade_count = 0
    for trade in trades:
        ts = trade_timestamp_ms(trade)
        if ts and ts < cutoff_ms:
            continue
        qty = trade_qty(trade)
        if qty <= 0:
            continue
        side = trade_side(trade)
        if side == "sell":
            sell_volume += qty
        else:
            buy_volume += qty
        total_qty += qty
        trade_count += 1
    bids = parse_levels(orderbook.get("bids", []))
    asks = parse_levels(orderbook.get("asks", []))
    bid_depth = sum(q for _, q in bids[:10])
    ask_depth = sum(q for _, q in asks[:10])
    best_bid = bids[0][0] if bids else 0.0
    best_ask = asks[0][0] if asks else 0.0
    wall_side, wall_price = liquidity_wall(bids[:10], asks[:10])
    volume_delta = buy_volume - sell_volume
    return enrich_orderflow({
        "symbol": symbol.upper(),
        "window": "1m",
        "price": best_ask or best_bid,
        "buy_volume": round(buy_volume, 6),
        "sell_volume": round(sell_volume, 6),
        "volume_delta": round(volume_delta, 6),
        "cumulative_volume_delta": round(volume_delta, 6),
        "delta_ratio": round(buy_volume / sell_volume, 4) if sell_volume else round(buy_volume, 4),
        "trade_count": trade_count,
        "trade_intensity": "medium" if trade_count >= 60 else "low",
        "average_trade_size": round(total_qty / trade_count, 6) if trade_count else 0,
        "large_trade_count": 0,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread": round(best_ask - best_bid, 8) if best_bid and best_ask else 0,
        "bid_depth": round(bid_depth, 6),
        "ask_depth": round(ask_depth, 6),
        "bid_qty_top_levels": round(bid_depth, 6),
        "ask_qty_top_levels": round(ask_depth, 6),
        "orderbook_imbalance": round(bid_depth / ask_depth, 4) if ask_depth else round(bid_depth, 4),
        "liquidity_wall_side": wall_side,
        "liquidity_wall_price": wall_price,
        "liquidity_pull_detected": False,
        "liquidation_buy_notional": 0,
        "liquidation_sell_notional": 0,
        "liquidation_spike_detected": False,
    })


def trade_timestamp_ms(trade: dict[str, Any]) -> int:
    value = trade.get("T") or trade.get("time") or trade.get("ts") or trade.get("create_time_ms") or trade.get("create_time") or 0
    try:
        ts = float(value)
    except (TypeError, ValueError):
        return 0
    return int(ts * 1000) if ts < 10_000_000_000 else int(ts)


def trade_qty(trade: dict[str, Any]) -> float:
    for key in ("q", "qty", "size", "sz", "vol", "v", "amount"):
        try:
            value = float(trade.get(key) or 0)
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            return value
    return 0.0


def trade_side(trade: dict[str, Any]) -> str:
    side = str(trade.get("side") or trade.get("S") or "").lower()
    if side in {"sell", "s", "ask"}:
        return "sell"
    if side in {"buy", "b", "bid"}:
        return "buy"
    if "m" in trade:
        return "sell" if bool(trade.get("m")) else "buy"
    side_code = str(trade.get("type") or trade.get("trade_type") or "").lower()
    if side_code in {"2", "sell"}:
        return "sell"
    return "buy"


def parse_levels(levels: list[Any]) -> list[tuple[float, float]]:
    parsed = []
    for level in levels:
        if isinstance(level, dict):
            price = level.get("p") or level.get("price") or level.get("px")
            qty = level.get("s") or level.get("size") or level.get("qty") or level.get("sz")
        else:
            price = level[0] if len(level) > 0 else 0
            qty = level[1] if len(level) > 1 else 0
        try:
            parsed.append((float(price or 0), float(qty or 0)))
        except (TypeError, ValueError):
            continue
    return parsed


def liquidity_wall(bids: list[tuple[float, float]], asks: list[tuple[float, float]]) -> tuple[str, float]:
    levels = [("bid", p, q) for p, q in bids] + [("ask", p, q) for p, q in asks]
    if not levels:
        return "none", 0.0
    side, price, _ = max(levels, key=lambda x: x[2])
    return side, float(price)


def auto_broadcast_enabled(db, default: bool) -> bool:
    value = get_setting(db, "auto_broadcast", str(default))
    return str(value).lower() in {"1", "true", "yes", "on"}


def format_provider_errors(errors: list[dict[str, Any]]) -> str:
    lines = []
    for item in errors[:5]:
        lines.append(f"{item.get('provider')}: {item.get('message')} status={item.get('status_code', '')}")
    return "\n".join(lines) or "No provider error details."


scanner = MarketScanner()
