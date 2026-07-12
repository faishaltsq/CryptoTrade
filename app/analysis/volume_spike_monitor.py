import asyncio
import logging
from time import time
from typing import Any

from app.config import get_settings
from app.market_data.base_provider import MarketDataProvider, empty_optional_market_data
from app.market_data.provider_factory import create_provider, configured_provider_names

logger = logging.getLogger(__name__)

_SPIKE_COOLDOWN: dict[str, float] = {}
_SPIKE_COOLDOWN_SEC = 600


async def run_volume_spike_monitor(bot) -> None:
    settings = get_settings()
    if not settings.enable_orderflow:
        return
    logger.info("Volume spike monitor started top=%d", settings.max_realtime_pairs)
    while True:
        try:
            provider = await _connect_provider()
            if not provider:
                await asyncio.sleep(30)
                continue
            tickers = await provider.get_tickers()
            top = _top_symbols_by_volume(tickers, settings.max_realtime_pairs)
            for symbol in top:
                try:
                    await _check_symbol(provider, symbol, bot)
                    await asyncio.sleep(0.5)
                except Exception:  # noqa: BLE001
                    pass
            await provider.close()
            from app.watchlist.manager import refresh_all
            await refresh_all(bot)
        except Exception:  # noqa: BLE001
            logger.exception("Volume spike monitor error")
        await asyncio.sleep(30)
    logger.info("Volume spike monitor stopped")


async def _connect_provider() -> MarketDataProvider | None:
    for name in configured_provider_names():
        try:
            return create_provider(name)
        except Exception:  # noqa: BLE001
            pass
    return None


def _top_symbols_by_volume(tickers: list[dict], limit: int) -> list[str]:
    rows = []
    for t in tickers:
        symbol = t.get("symbol", "")
        if not symbol or not symbol.endswith("USDT"):
            continue
        rows.append((symbol, float(t.get("quote_volume") or 0)))
    rows.sort(key=lambda x: x[1], reverse=True)
    return [s for s, _v in rows[:limit]]


async def _check_symbol(provider: MarketDataProvider, symbol: str, bot) -> None:
    now = time()
    last_alert = _SPIKE_COOLDOWN.get(symbol, 0)
    if now - last_alert < _SPIKE_COOLDOWN_SEC:
        return
    try:
        rows = await provider.get_klines(symbol, "15m", limit=21)
        if len(rows) < 20:
            return
        volumes = [_float_kline_vol(r) for r in rows[-21:]]
        current_vol = volumes[-1] if volumes[-1] > 0 else 0
        avg_vol = sum(volumes[:-1]) / max(len(volumes) - 1, 1)
        if avg_vol <= 0 or current_vol <= 0:
            return
        ratio = current_vol / avg_vol
        if ratio < 2.0:
            return
        _SPIKE_COOLDOWN[symbol] = now
        if _has_pending_duplicate(symbol):
            return
        price = _float_kline_close(rows[-1])
        direction = "BUY" if _float_kline_close(rows[-1]) > _float_kline_open(rows[-1]) else "SELL"
        emoji = "🟢" if direction == "BUY" else "🔴"
        _SPIKE_COOLDOWN[symbol] = now
        try:
            await bot.send_admin(f"{emoji} <b>Vol Spike</b> — {symbol} ({ratio:.1f}x) | {price}\nAI analyzing...")
        except Exception:  # noqa: BLE001
            pass
    except Exception:  # noqa: BLE001
        logger.exception("Spike check failed symbol=%s", symbol)
        return

    try:
        from app.ai.deepseek_client import DeepSeekClient
        from app.analysis.setup_detector import detect_setup
        from app.analysis.risk_reward import calculate_plan
        from app.database.session import SessionLocal
        from app.database.repository import create_signal_log
        from app.signal.validator import validate_for_broadcast

        ai = DeepSeekClient()
        client = provider
        candles = {}
        for name, interval in {"M15": "15m", "H1": "1h", "H4": "4h", "D1": "1d"}.items():
            raw = await client.get_klines(symbol, interval, limit=250)
            import pandas as pd
            df = pd.DataFrame(raw)
            for col in ["open", "high", "low", "close", "volume", "quote_volume"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            if "open_time" in df.columns:
                df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
            candles[name] = df

        candidate, reason, tf_summary = detect_setup(symbol, candles, {"open_interest": 0, "open_interest_change": 0}, 0, 0, {"symbol": symbol, "window": "1m", "buy_volume": 0, "sell_volume": 0, "volume_delta": 0, "delta_ratio": 0, "cumulative_volume_delta": 0, "trade_count": 0, "trade_intensity": "low", "average_trade_size": 0, "large_trade_count": 0, "large_trade_buy_volume": 0, "large_trade_sell_volume": 0, "large_trade_buy_notional": 0, "large_trade_sell_notional": 0, "best_bid": 0, "best_ask": 0, "spread": 0, "bid_depth": 0, "ask_depth": 0, "orderbook_imbalance": 0, "liquidity_wall_side": "none", "liquidity_wall_price": 0, "liquidation_buy_notional": 0, "liquidation_sell_notional": 0, "liquidation_spike_detected": False, "orderflow_bias": "insufficient_data", "flow_interpretation": "No realtime orderflow data."})
        if not candidate:
            logger.info("Volume spike rejected symbol=%s reason=%s", symbol, reason)
            return

        ai_response, ai_error = await ai.analyze(candidate)
        decision = ai_response.get("decision", "?")
        conf = ai_response.get("confidence", 0)
        risk_data = ai_response.get("risk", {}) or {}
        rr = risk_data.get("risk_reward", 0)
        reason_text = (ai_response.get("reason") or "")[:300]

        db = SessionLocal()
        try:
            from app.analysis.risk_reward import ensure_tp2_probability
            ensure_tp2_probability(ai_response, candidate)
            ok, val_reason = validate_for_broadcast(ai_response)
            if ok and int(ai_response.get("confidence") or 0) < 65:
                ok = False
                val_reason = "spike_confidence_below_65"
            label = "VALID" if ok else val_reason.replace("_", " ").title()
            try:
                await bot.send_admin(f"{emoji} <b>AI Result</b> — {symbol}: <b>{decision}</b> (conf={conf}%, RR=1:{rr}) | {label}")
            except Exception:  # noqa: BLE001
                pass
            if decision in {"BUY", "SELL", "WAIT"}:
                from app.watchlist.manager import update_from_scan
                zone = candidate.get("zone_analysis", {})
                update_from_scan(symbol, candidate.get("candidate_direction", "?"), ai_response, candidate, ok, False, {"within_zone": zone.get("price_within_demand", False) or zone.get("price_within_supply", False), "near_zone": False, "at_sr": False})
            if decision in {"BUY", "SELL"}:
                row = create_signal_log(db, candidate, ai_response, status="pending" if ok else "warning", broadcast_status="pending_admin")
                from app.signal.formatter import admin_signal_message
                from app.database.repository import update_signal_status
                try:
                    await bot.send_admin(admin_signal_message(row.id, ai_response))
                    update_signal_status(db, row.id, row.status or "pending", "sent_to_admin")
                except Exception:  # noqa: BLE001
                    update_signal_status(db, row.id, row.status or "pending", "admin_failed")
                if ok:
                    from app.signal.broadcaster import SignalBroadcaster
                    bc = SignalBroadcaster()
                    msg_id = await bc.broadcast_channel(ai_response)
                    if msg_id:
                        from app.database.repository import set_setting
                        set_setting(db, f"pin_msg:{row.id}", str(msg_id))
                        await bc.pin_channel(msg_id)
                    update_signal_status(db, row.id, "broadcasted", "broadcasted")
        finally:
            db.close()
    except Exception:  # noqa: BLE001
        logger.exception("Volume spike AI analysis failed symbol=%s", symbol)


def _float_kline_vol(row: dict) -> float:
    for key in ("volume", "v", "vol"):
        try:
            return float(row.get(key, 0) or 0)
        except (ValueError, TypeError):
            pass
    return 0.0


def _float_kline_close(row: dict) -> float:
    for key in ("close", "c"):
        try:
            return float(row.get(key, 0) or 0)
        except (ValueError, TypeError):
            pass
    return 0.0


def _float_kline_open(row: dict) -> float:
    for key in ("open", "o"):
        try:
            return float(row.get(key, 0) or 0)
        except (ValueError, TypeError):
            pass
    return 0.0


def _has_pending_duplicate(symbol: str) -> bool:
    try:
        from app.database.session import SessionLocal
        from app.database.repository import has_active_signal
        db = SessionLocal()
        try:
            return has_active_signal(db, symbol)
        finally:
            db.close()
    except Exception:  # noqa: BLE001
        return False
