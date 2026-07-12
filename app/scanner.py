import asyncio
import logging
from time import time
from typing import Any
import pandas as pd
from app.ai.deepseek_client import DeepSeekClient
from app.analysis.setup_detector import detect_setup, analyze_timeframe, compute_btc_status, get_current_session
from app.analysis.risk_reward import actual_tp1_risk_reward
from app.config import get_settings
from app.database.repository import get_setting, has_active_signal, save_orderflow_snapshot, save_rejected_setup, save_scan_log, save_signal_log, set_setting, update_signal_status
from app.database.session import SessionLocal
from app.learning.adaptive_scoring import apply_adaptive_scoring
from app.learning.learning_prompt_builder import learning_context
from app.learning.lesson_manager import active_lessons_for_prompt
from app.learning.performance_analyzer import analyze_performance
from app.market_data.base_provider import MarketDataProvider, ProviderError, empty_optional_market_data
from app.market_data import cache as kline_cache
from app.market_data.provider_factory import configured_provider_names, create_provider
from app.orderflow.orderflow_analyzer import enrich_orderflow
from app.orderflow.orderflow_aggregator import orderflow_aggregator
from app.signal.broadcaster import SignalBroadcaster
from app.signal.formatter import admin_signal_message
from app.signal.validator import validate_for_broadcast


logger = logging.getLogger(__name__)


def _to_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _parse_price_range(value: str) -> float:
    if not value:
        return 0.0
    parts = str(value).replace(",", "").split("-")
    numbers = [_to_float(p.strip()) for p in parts if p.strip()]
    return numbers[0] if numbers else 0.0


def _entry_midpoint(entry_raw: str) -> float:
    if not entry_raw:
        return 0.0
    parts = str(entry_raw).replace(",", "").split("-")
    numbers = [_to_float(p.strip()) for p in parts if p.strip()]
    if not numbers:
        return 0.0
    return sum(numbers) / len(numbers)


async def _get_current_price(provider: MarketDataProvider, symbol: str) -> float:
    try:
        tickers = await provider.get_tickers()
        item = next((x for x in tickers if x.get("symbol") == symbol), None)
        if item:
            return float(item.get("last_price") or item.get("bid") or item.get("ask") or 0)
    except Exception:  # noqa: BLE001
        pass
    return 0.0


def _check_signal_freshness(signal: dict, price: float) -> str:
    decision = str(signal.get("decision", "")).upper()
    risk = signal.get("risk", {}) or {}
    sl = _to_float(risk.get("stop_loss") or 0)
    tp1 = _to_float(risk.get("take_profit_1") or 0)
    tp2 = _to_float(risk.get("take_profit_2") or 0)
    entry = _entry_midpoint(risk.get("entry_zone") or "")
    if decision == "BUY":
        if sl and price <= sl:
            return "stale_sl_already_hit"
        if tp2 and price >= tp2:
            return "stale_tp2_already_hit"
        if tp1 and price >= tp1:
            return "stale_tp1_already_hit"
        if entry and price > entry * 1.005:
            return "stale_price_above_entry"
    elif decision == "SELL":
        if sl and price >= sl:
            return "stale_sl_already_hit"
        if tp2 and price <= tp2:
            return "stale_tp2_already_hit"
        if tp1 and price <= tp1:
            return "stale_tp1_already_hit"
        if entry and price < entry * 0.995:
            return "stale_price_below_entry"
    return ""


BATCH_SIZE = 5


def _format_batch_message(batch: list[dict], batch_num: int, total_batches: int) -> str:
    rows = []
    for sig in batch:
        risk = sig.get("risk", {}) or {}
        decision = sig.get("decision", "?")
        emoji = "🟢" if decision == "BUY" else "🔴"
        rows.append(
            f"{emoji} <code>{sig.get('symbol','?')}</code> {decision} | "
            f"conf={sig.get('confidence','?')}% | "
            f"RR=1:{risk.get('risk_reward','?')} | "
            f"Entry: {risk.get('entry_zone','?')} | "
            f"SL: {risk.get('stop_loss','?')} | "
            f"TP: {risk.get('take_profit_1','?')} / {risk.get('take_profit_2','?')}"
        )
    header = f"<b>Signal Batch #{batch_num}/{total_batches}</b>" if total_batches > 1 else "<b>Signals</b>"
    return header + "\n\n" + "\n\n".join(rows)


async def _send_signal_batches(bot, db, signal_rows: list[tuple], broadcast_enabled: bool) -> int:
    if not signal_rows:
        return 0
    batches = [signal_rows[i:i + BATCH_SIZE] for i in range(0, len(signal_rows), BATCH_SIZE)]
    total = len(batches)
    broadcasted = 0
    for idx, batch in enumerate(batches, 1):
        batch_signals = [s for s, _r, _ok in batch]
        msg = _format_batch_message(batch_signals, idx, total)
        try:
            await bot.send_admin(msg)
            for _, row, _ok in batch:
                update_signal_status(db, row.id, row.status or "pending", "sent_to_admin")
                logger.info("Signal #%d admin sent (batch %d)", row.id, idx)
        except Exception:  # noqa: BLE001
            logger.exception("Batch admin send failed batch=%d/%d", idx, total)
        if broadcast_enabled:
            try:
                ch_msg = _format_channel_batch_message(batch_signals)
                await bot.send_channel(ch_msg)
                for _, row, _ok in batch:
                    update_signal_status(db, row.id, "broadcasted", "broadcasted")
                broadcasted += len(batch)
                logger.info("Batch #%d/%d broadcasted %d signals", idx, total, len(batch))
            except Exception:  # noqa: BLE001
                logger.exception("Batch channel broadcast failed batch=%d/%d", idx, total)
    return broadcasted


async def _prefetch_all(provider: MarketDataProvider, pairs: list[dict]) -> list[tuple[str, dict, dict, int, float]]:
    sem = asyncio.Semaphore(3)

    async def _fetch_one(pair: dict):
        async with sem:
            await asyncio.sleep(0.5)
            symbol = pair["symbol"]
            candles = await _fetch_multi_timeframe(provider, symbol)
            futures = await _fetch_futures(provider, symbol)
            await asyncio.sleep(0.3)
            return (symbol, candles, futures, pair.get("volume_rank", 0), pair.get("spread_pct", 0.0))

    return await asyncio.gather(*[_fetch_one(p) for p in pairs])


async def _fetch_multi_timeframe(provider: MarketDataProvider, symbol: str) -> dict[str, pd.DataFrame]:
    timeframes = {"M15": "15m", "H1": "1h", "H4": "4h", "D1": "1d"}
    result: dict[str, pd.DataFrame] = {}
    for name, interval in timeframes.items():
        cached = kline_cache.get(provider.name, symbol, interval)
        if cached is not None:
            result[name] = klines_to_dataframe(cached)
            continue
        rows = await provider.get_klines(symbol, interval, limit=250)
        kline_cache.set(provider.name, symbol, interval, rows)
        result[name] = klines_to_dataframe(rows)
    return result


async def _fetch_futures(provider: MarketDataProvider, symbol: str) -> dict[str, Any]:
    data = empty_optional_market_data()
    try:
        data.update(await provider.get_funding_rate(symbol))
    except Exception:  # noqa: BLE001
        pass
    try:
        data.update(await provider.get_open_interest(symbol))
    except Exception:  # noqa: BLE001
        pass
    return data


def _format_channel_batch_message(batch: list[dict]) -> str:
    rows = []
    for sig in batch:
        risk = sig.get("risk", {}) or {}
        decision = sig.get("decision", "?")
        emoji = "🟢" if decision == "BUY" else "🔴"
        rows.append(
            f"{emoji} <code>{sig.get('symbol','?')}</code> {decision} | "
            f"Entry: {risk.get('entry_zone','?')} | "
            f"SL: <code>{risk.get('stop_loss','?')}</code> | "
            f"TP: <code>{risk.get('take_profit_1','?')}</code> / <code>{risk.get('take_profit_2','?')}</code>"
        )
    return "<b>New Signals</b>\n\n" + "\n\n".join(rows)


def _recalculate_geometric_rr(ai_response: dict) -> float:
    decision = str(ai_response.get("decision", "")).upper()
    risk_data = ai_response.get("risk") or {}
    entry_raw = risk_data.get("entry_zone") or ai_response.get("entry") or ""
    sl_raw = risk_data.get("stop_loss") or ai_response.get("stop_loss") or ""
    tp2_raw = risk_data.get("take_profit_2") or ai_response.get("take_profit_2") or ""
    entry = _entry_midpoint(entry_raw)
    sl = _to_float(sl_raw)
    tp2 = _to_float(tp2_raw)
    if entry <= 0 or sl <= 0 or tp2 <= 0:
        return float(risk_data.get("risk_reward") or 0)
    calculated = actual_tp1_risk_reward(decision, entry, sl, tp2)
    if calculated <= 0:
        return float(risk_data.get("risk_reward") or 0)
    risk_data["risk_reward"] = calculated
    ai_response["risk"] = risk_data
    return calculated


class MarketScanner:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.ai = DeepSeekClient()
        self.broadcaster = SignalBroadcaster()
        self._pending_batch: list[tuple[dict, Any, bool]] = []

    async def scan(self) -> dict[str, Any]:
        db = SessionLocal()
        rejected_reasons: list[str] = []
        rejected_details: list[dict[str, Any]] = []
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
            signals_sent = 0
            batch_broadcast = auto_broadcast_enabled(db, self.settings.auto_broadcast)
            btc_tf = {}
            try:
                btc_candles = await _fetch_multi_timeframe(provider, "BTCUSDT")
                btc_tf = {name: analyze_timeframe(df) for name, df in btc_candles.items()}
            except Exception:  # noqa: BLE001
                pass
            for pair in pairs:
                symbol = pair["symbol"]
                try:
                    candles = await _fetch_multi_timeframe(provider, symbol)
                    futures_data = await _fetch_futures(provider, symbol)
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
                        if reason == "insufficient_candle_data":
                            rejected_details.append({"symbol": symbol, "reason": reason, "candles": candle_counts(candles)})
                        save_rejected_setup(db, symbol, reason, {**tf_summary, "orderflow": orderflow_summary})
                        continue
                    is_duplicate = has_active_signal(db, symbol)
                    if is_duplicate:
                        rejected_reasons.append("duplicate_active_signal")
                        save_rejected_setup(db, symbol, "duplicate_active_signal", {**tf_summary, "orderflow": orderflow_summary})
                    if btc_tf and symbol.upper() != "BTCUSDT":
                        candidate["btc_context"] = {
                            "btc_d1_trend": btc_tf.get("D1", {}).get("trend", "unclear"),
                            "btc_h4_trend": btc_tf.get("H4", {}).get("trend", "unclear"),
                            "btc_h1_trend": btc_tf.get("H1", {}).get("trend", "unclear"),
                            "btc_status": compute_btc_status(btc_tf),
                            "btc_volume_spike_h1": btc_tf.get("H1", {}).get("volume_spike", False),
                        }
                    session = get_current_session()
                    candidate["session_context"] = session
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
                    zone = candidate.get("zone_analysis", {})
                    demand_dist = zone.get("distance_to_demand_pct", 0)
                    supply_dist = zone.get("distance_to_supply_pct", 0)
                    within_demand = zone.get("price_within_demand", False)
                    within_supply = zone.get("price_within_supply", False)
                    if within_demand:
                        try:
                            await self.broadcaster.bot.send_admin(f"<b>Zone Alert</b>\nSymbol: <b>{symbol}</b>\nPrice INSIDE demand zone {zone.get('demand_zone_low','?')}-{zone.get('demand_zone_high','?')}\nReaction score: {zone.get('demand_reaction_score',0)}/3 (tested {zone.get('demand_test_count',0)}x)")
                        except Exception:  # noqa: BLE001
                            pass
                    elif within_supply:
                        try:
                            await self.broadcaster.bot.send_admin(f"<b>Zone Alert</b>\nSymbol: <b>{symbol}</b>\nPrice INSIDE supply zone {zone.get('supply_zone_low','?')}-{zone.get('supply_zone_high','?')}\nReaction score: {zone.get('supply_reaction_score',0)}/3 (tested {zone.get('supply_test_count',0)}x)")
                        except Exception:  # noqa: BLE001
                            pass
                    elif 0 < demand_dist <= 2:
                        try:
                            await self.broadcaster.bot.send_admin(f"<b>Zone Alert</b>\nSymbol: <b>{symbol}</b>\nApproaching demand zone ({demand_dist}% away)\nZone: {zone.get('demand_zone_low','?')}-{zone.get('demand_zone_high','?')} (tested {zone.get('demand_test_count',0)}x)")
                        except Exception:  # noqa: BLE001
                            pass
                    if 0 < supply_dist <= 2:
                        try:
                            await self.broadcaster.bot.send_admin(f"<b>Zone Alert</b>\nSymbol: <b>{symbol}</b>\nApproaching supply zone ({supply_dist}% away)\nZone: {zone.get('supply_zone_low','?')}-{zone.get('supply_zone_high','?')} (tested {zone.get('supply_test_count',0)}x)")
                        except Exception:  # noqa: BLE001
                            pass
                    tfs = candidate.get("timeframes", {})
                    m15_spike = tfs.get("M15", {}).get("volume_spike")
                    h1_spike = tfs.get("H1", {}).get("volume_spike")
                    had_spike = False
                    spike_emoji = ""
                    spike_dir = ""
                    if m15_spike or h1_spike:
                        had_spike = True
                        spike_dir = candidate.get("candidate_direction", "?").upper()
                        spike_emoji = "🟢" if spike_dir == "BUY" else "🔴"
                        tf_label = "M15" if m15_spike else "H1"
                        ratio_m15 = tfs.get("M15", {}).get("volume_ratio", 0)
                        ratio_h1 = tfs.get("H1", {}).get("volume_ratio", 0)
                        ratio = max(ratio_m15, ratio_h1)
                        try:
                            await self.broadcaster.bot.send_admin(f"{spike_emoji} <b>Volume Spike</b> — {symbol} ({tf_label} {ratio}x avg) | {candidate.get('current_price')}\nAI analyzing...")
                        except Exception:  # noqa: BLE001
                            pass
                    if self.settings.enable_orderflow:
                        orderflow_aggregator.start_depth(provider.name, symbol)
                    ai_response, ai_error = await self.ai.analyze(candidate)
                    ai_response.setdefault("orderflow", {"bias": candidate.get("orderflow", {}).get("orderflow_bias", "insufficient_data"), "confirmation": False, "conflict": candidate.get("orderflow", {}).get("orderflow_conflict", False), "score": candidate.get("orderflow", {}).get("orderflow_score", 0), "absorption_signal": candidate.get("orderflow", {}).get("absorption_signal", "none"), "interpretation": candidate.get("orderflow", {}).get("flow_interpretation", "")})
                    if candidate.get("orderflow", {}).get("orderflow_conflict"):
                        ai_response["orderflow"]["conflict"] = True
                        ai_response["broadcast_allowed"] = False
                    ai_response["scores"] = candidate.get("scores", {})
                    ai_response["provider"] = candidate.get("provider", "") or provider.name
                    ai_response["current_price"] = candidate.get("current_price", 0)
                    adaptive = candidate.get("adaptive_scoring", {}) or {}
                    if adaptive.get("confidence_adjustment"):
                        ai_response["confidence"] = max(0, min(100, int(ai_response.get("confidence") or 0) + int(adaptive["confidence_adjustment"])))
                        ai_response["adaptive_scoring"] = adaptive
                    ai_response["orderflow_summary"] = candidate.get("orderflow", {})
                    if ai_error:
                        logger.warning("AI response issue symbol=%s error=%s", symbol, ai_error)
                    _recalculate_geometric_rr(ai_response)
                    from app.analysis.risk_reward import ensure_tp2_probability
                    ensure_tp2_probability(ai_response, candidate)
                    ok, validation_reason = validate_for_broadcast(ai_response)
                    if is_duplicate:
                        validation_reason = "duplicate_active_signal" if validation_reason == "valid" else f"duplicate_active_signal+{validation_reason}"
                        ok = False
                    ai_response["validation_status"] = "valid" if ok else "warning"
                    ai_response["validation_reason"] = validation_reason
                    broadcast_enabled = auto_broadcast_enabled(db, self.settings.auto_broadcast)
                    should_publish = ai_response.get("decision") in {"BUY", "SELL"}
                    broadcast_status = "pending_admin" if should_publish else "skipped"
                    row = save_signal_log(db, candidate, ai_response, status="pending" if ok else "warning", broadcast_status=broadcast_status)
                    ai_response["signal_id"] = row.id
                    if ok:
                        valid_signals += 1
                    elif not is_duplicate:
                        rejected_reasons.append(validation_reason)
                    if ai_response.get("decision") == "WAIT" and self.settings.enable_zone_monitor:
                        zone = candidate.get("zone_analysis", {})
                        within = zone.get("price_within_demand") or zone.get("price_within_supply")
                        near = 0 < zone.get("distance_to_demand_pct", 999) < self.settings.zone_approaching_pct or 0 < zone.get("distance_to_supply_pct", 999) < self.settings.zone_approaching_pct
                        at_sr = candidate.get("timeframes", {}).get("H1", {}).get("at_support") or candidate.get("timeframes", {}).get("H1", {}).get("at_resistance")
                        from app.watchlist.manager import update_from_scan
                        update_from_scan(symbol, candidate.get("candidate_direction", "?"), ai_response, candidate, ok, is_duplicate, {"within_zone": within, "near_zone": near, "at_sr": at_sr})
                    if had_spike:
                        ai_decision = ai_response.get("decision", "?")
                        ai_conf = ai_response.get("confidence", "?")
                        rr = (ai_response.get("risk") or {}).get("risk_reward", "?")
                        label = "VALID" if ok else validation_reason.replace("_", " ").title()
                        try:
                            await self.broadcaster.bot.send_admin(f"{spike_emoji} <b>AI Result</b> — {symbol}: <b>{ai_decision}</b> (conf={ai_conf}%, RR=1:{rr}) | {label}")
                        except Exception:  # noqa: BLE001
                            pass
                    if ai_response.get("decision") in {"BUY", "SELL"}:
                        from app.watchlist.manager import update_from_scan
                        zone = candidate.get("zone_analysis", {})
                        update_from_scan(symbol, candidate.get("candidate_direction", "?"), ai_response, candidate, ok, is_duplicate, {"within_zone": zone.get("price_within_demand") or zone.get("price_within_supply"), "near_zone": False, "at_sr": candidate.get("timeframes", {}).get("H1", {}).get("at_support") or candidate.get("timeframes", {}).get("H1", {}).get("at_resistance")})
                        signals_sent += 1
                        self._pending_batch.append((ai_response, row, ok))
                        try:
                            msg_ids = await self.broadcaster.bot.send_message(self.settings.telegram_admin_chat_id, admin_signal_message(row.id, ai_response))
                            if msg_ids:
                                set_setting(db, f"admin_msg:{row.id}", str(msg_ids[0]))
                            update_signal_status(db, row.id, row.status or "pending", "sent_to_admin")
                            logger.info("Signal #%d admin sent symbol=%s", row.id, symbol)
                        except Exception:  # noqa: BLE001
                            logger.exception("Admin signal notification failed signal_id=%s symbol=%s", row.id, symbol)
                            update_signal_status(db, row.id, row.status or "pending", "admin_failed")
                        if ok and broadcast_enabled:
                            try:
                                msg_id = await self.broadcaster.broadcast_channel(ai_response)
                                update_signal_status(db, row.id, "broadcasted", "broadcasted")
                                if msg_id:
                                    set_setting(db, f"pin_msg:{row.id}", str(msg_id))
                                    pinned = await self.broadcaster.pin_channel(msg_id)
                                    logger.info("Signal #%d pinned=%s msg_id=%s symbol=%s", row.id, pinned, msg_id, symbol)
                            except Exception as exc:  # noqa: BLE001
                                logger.exception("Channel broadcast failed signal_id=%s symbol=%s", row.id, symbol)
                        if len(self._pending_batch) >= BATCH_SIZE:
                            await _send_signal_batches(self.broadcaster.bot, db, self._pending_batch[:BATCH_SIZE], batch_broadcast)
                            self._pending_batch = self._pending_batch[BATCH_SIZE:]
                    if is_duplicate:
                        try:
                            decision = ai_response.get("decision", "?")
                            conf = ai_response.get("confidence", "?")
                            reason = (ai_response.get("reason") or "-")[:500]
                            orig = _get_active_signal_info(db, symbol)
                            if orig:
                                orig_msg_id = get_setting(db, f"admin_msg:{orig['id']}", "")
                                if orig_msg_id and orig_msg_id.isdigit():
                                    update_text = f"<b>Duplicate Update</b>\nSymbol: <b>{symbol}</b>\nNew AI: <b>{decision}</b> (conf={conf}%)\nOriginal: #{orig['id']} {orig['decision']} (conf={orig['confidence']}%)\n{reason}\n\nSignal ID: <code>{row.id}</code>"
                                    edited = await self.broadcaster.bot.edit_message(self.settings.telegram_admin_chat_id, int(orig_msg_id), update_text)
                                    if not edited:
                                        await self.broadcaster.bot.send_admin(update_text)
                            logger.info("Duplicate update sent symbol=%s decision=%s", symbol, decision)
                        except Exception:  # noqa: BLE001
                            logger.exception("Duplicate update failed symbol=%s", symbol)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Scan failed for symbol=%s", symbol)
                    rejected_reasons.append("scanner error")
                    save_rejected_setup(db, symbol, "scanner error", {"error": str(exc)})
            summary = {
                "pairs": [p["symbol"] for p in pairs],
                "top_volume": [{"symbol": p["symbol"], "quote_volume": p["quote_volume"], "last_price": p.get("last_price", 0), "price_change_pct": p.get("price_change_pct", 0), "rank": p["volume_rank"]} for p in pairs[:20]],
                "rejected_reasons": rejected_reasons,
                "rejected_details": rejected_details[:30],
                "provider": provider.name,
                "kline_cache": kline_cache.snapshot_stats(),
            }
            save_scan_log(db, len(pairs), candidates, valid_signals, len(rejected_reasons), summary)
            cache_s = kline_cache.snapshot_stats()
            logger.info("Scan complete pairs=%d candidates=%d valid=%d cache_hit_rate=%.1f%% hits=%d misses=%d sets=%d entries=%d", len(pairs), candidates, valid_signals, cache_s["hit_rate_pct"], cache_s["hits"], cache_s["misses"], cache_s["sets"], cache_s["total_entries"])
            if signals_sent == 0:
                await self.broadcaster.send_no_valid_setup(len(pairs), rejected_reasons, self.settings.scan_interval_minutes, rejected_details)
            from app.watchlist.manager import refresh_all
            await refresh_all(self.broadcaster.bot)
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
        result: dict[str, pd.DataFrame] = {}
        for name, interval in timeframes.items():
            cached = kline_cache.get(provider.name, symbol, interval)
            if cached is not None:
                result[name] = klines_to_dataframe(cached)
                continue
            rows = await provider.get_klines(symbol, interval, limit=250)
            kline_cache.set(provider.name, symbol, interval, rows)
            result[name] = klines_to_dataframe(rows)
        return result

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
        merged = {**active[symbol], **ticker}
        skip_reason = _pair_quality_filter(symbol, merged)
        if skip_reason:
            logger.debug("Pair filtered symbol=%s reason=%s", symbol, skip_reason)
            continue
        rows.append(merged)
    rows.sort(key=lambda x: float(x.get("quote_volume") or 0), reverse=True)
    for idx, row in enumerate(rows, start=1):
        row["volume_rank"] = idx
    return rows[:max_pairs]


def _pair_quality_filter(symbol: str, row: dict[str, Any]) -> str:
    """Return a non-empty reason string if the pair should be excluded, else empty string."""
    # Reject symbols with non-ASCII characters (e.g. Chinese characters like '龙虾USDT')
    if not symbol.isascii():
        return "non_ascii_symbol"
    # Reject base tokens that are too short (e.g. 'H', 'B', 'M', 'U' before USDT)
    base = str(row.get("base") or symbol.replace("USDT", "")).upper()
    if len(base) < 2:
        return "base_too_short"
    # Reject extreme 24h movers: likely pump-dump or manipulation (>50% move in either direction)
    try:
        pct = abs(float(row.get("price_change_pct") or 0))
        if pct > 50.0:
            return f"extreme_24h_move_{pct:.0f}pct"
    except (TypeError, ValueError):
        pass
    # Reject pairs with extremely low quote volume (< $50,000 in 24h) — too illiquid
    try:
        qv = float(row.get("quote_volume") or 0)
        if qv < 50_000:
            return "quote_volume_too_low"
    except (TypeError, ValueError):
        pass
    return ""


def is_crypto_perp_symbol(row: dict[str, Any]) -> bool:
    symbol = str(row.get("symbol", "")).upper()
    if not symbol.endswith("USDT"):
        return False
    return True


def klines_to_dataframe(rows: list[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    for col in ["open", "high", "low", "close", "volume", "quote_volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = df["open_time"]
    return df


def candle_counts(candles: dict[str, pd.DataFrame]) -> dict[str, int]:
    return {name: len(df) for name, df in candles.items()}


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
        "large_trade_buy_volume": 0,
        "large_trade_sell_volume": 0,
        "large_trade_buy_notional": 0,
        "large_trade_sell_notional": 0,
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




def _get_active_signal_info(db, symbol: str) -> dict | None:
    from app.database.models import SignalLog
    row = db.query(SignalLog).filter(
        SignalLog.symbol == symbol.upper(),
        SignalLog.outcome_status.in_(["pending", "hit_tp1"]),
        SignalLog.decision.in_(["BUY", "SELL"]),
    ).order_by(SignalLog.id.desc()).first()
    if not row:
        return None
    return {"id": row.id, "decision": row.decision, "confidence": row.confidence}


async def _send_watchlist(bot, watchlist: list[dict]) -> None:
    if not watchlist:
        return
    rows = []
    for w in watchlist:
        emoji = "🟢" if w["direction"] == "BUY" else "🔴"
        zone_tag = "IN ZONE" if w.get("within_zone") else "NEAR" if w.get("near_zone") else "S/R"
        rows.append(f"{emoji} <code>{w['symbol']}</code> {w['direction']} [{zone_tag}] conf={w['confidence']}% | Entry: {w['entry']}\n{w['reason'][:120]}")
    msg = "<b>Watchlist — Setup Pantau</b>\n\n" + "\n\n".join(rows) + "\n\n<i>Tunggu konfirmasi: engulfing / orderblock / volume spike / BOS sebelum entry.</i>"
    try:
        await bot.send_channel(msg)
    except Exception:  # noqa: BLE001
        pass
    try:
        await bot.send_admin(msg)
    except Exception:  # noqa: BLE001
        pass


def format_provider_errors(errors: list[dict[str, Any]]) -> str:
    lines = []
    for item in errors[:5]:
        lines.append(f"{item.get('provider')}: {item.get('message')} status={item.get('status_code', '')}")
    return "\n".join(lines) or "No provider error details."


scanner = MarketScanner()
