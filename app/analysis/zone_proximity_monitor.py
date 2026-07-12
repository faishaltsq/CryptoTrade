import asyncio
import logging
from time import time
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

_ZONE_COOLDOWN: dict[str, float] = {}


async def run_zone_proximity_monitor(bot) -> None:
    settings = get_settings()
    if not settings.enable_zone_monitor:
        return
    logger.info("Zone proximity monitor started pairs=%d interval=%ds", settings.zone_monitor_pairs, settings.zone_monitor_interval_seconds)
    while True:
        try:
            provider = await _connect_provider()
            if not provider:
                await asyncio.sleep(30)
                continue
            tickers = await provider.get_tickers()
            top = _top_symbols(tickers, settings.zone_monitor_pairs)
            for symbol in top:
                try:
                    await _check_zone_proximity(provider, symbol, bot)
                    await asyncio.sleep(0.3)
                except Exception:  # noqa: BLE001
                    pass
            await provider.close()
            from app.watchlist.manager import refresh_all
            await refresh_all(bot)
        except Exception:  # noqa: BLE001
            logger.exception("Zone monitor error")
        await asyncio.sleep(settings.zone_monitor_interval_seconds)


async def _connect_provider():
    from app.market_data.provider_factory import configured_provider_names, create_provider
    for name in configured_provider_names():
        try:
            return create_provider(name)
        except Exception:  # noqa: BLE001
            pass
    return None


def _top_symbols(tickers: list[dict], limit: int) -> list[str]:
    rows = []
    for t in tickers:
        symbol = t.get("symbol", "")
        if not symbol or not symbol.endswith("USDT"):
            continue
        rows.append((symbol, float(t.get("quote_volume") or 0)))
    rows.sort(key=lambda x: x[1], reverse=True)
    return [s for s, _v in rows[:limit]]


async def _check_zone_proximity(provider, symbol: str, bot) -> None:
    settings = get_settings()
    now = time()
    if now - _ZONE_COOLDOWN.get(symbol, 0) < settings.zone_cooldown_seconds:
        return

    try:
        m15_rows = await provider.get_klines(symbol, "15m", limit=50)
        h1_rows = await provider.get_klines(symbol, "1h", limit=100)
        df_m15 = _to_dataframe(m15_rows)
        df_h1 = _to_dataframe(h1_rows)
        if len(df_m15) < 20 or len(df_h1) < 30:
            return
    except Exception:  # noqa: BLE001
        return

    from app.analysis.market_structure import detect_demand_supply_zones, analyze_structure
    zone_data = detect_demand_supply_zones(df_h1)
    sr_data = analyze_structure(df_m15)
    price = float(df_m15.iloc[-1]["close"])

    proximity = _evaluate_proximity(price, zone_data, sr_data, settings)
    if proximity["status"] == "none":
        return

    if proximity["status"] == "approaching":
        await bot.send_admin(
            f"🔵 <b>Zone Approach</b>\nSymbol: <b>{symbol}</b> nearing {proximity['zone_type']} "
            f"({proximity['distance_pct']:.2f}% away)\nZone: {proximity['zone_low']}-{proximity['zone_high']}"
        )
        return

    _ZONE_COOLDOWN[symbol] = now

    try:
        from app.analysis.setup_detector import detect_setup
        from app.ai.deepseek_client import DeepSeekClient
        from app.signal.validator import validate_for_broadcast
        from app.database.session import SessionLocal
        from app.database.repository import create_signal_log, has_active_signal, update_signal_status

        candles = {}
        for name, interval in {"M15": "15m", "H1": "1h", "H4": "4h", "D1": "1d"}.items():
            raw = await provider.get_klines(symbol, interval, limit=250)
            candles[name] = _to_dataframe(raw)

        candidate, reason, tf_summary = detect_setup(symbol, candles, {"open_interest": 0, "open_interest_change": 0}, 0, 0, _empty_orderflow())
        if not candidate:
            logger.info("Zone monitor rejected symbol=%s reason=%s", symbol, reason)
            return

        candidate["zone_monitor_context"] = {
            "trigger_type": proximity["trigger_type"],
            "zone_type": proximity["zone_type"],
            "zone_high": proximity["zone_high"],
            "zone_low": proximity["zone_low"],
            "zone_test_count": zone_data.get("demand_zone_test_count", 0) or zone_data.get("supply_zone_test_count", 0),
            "price_within_zone": proximity["within_zone"],
            "zone_monitor_triggered": True,
        }

        db = SessionLocal()
        try:
            if has_active_signal(db, symbol):
                return
        finally:
            db.close()

        ai = DeepSeekClient()
        ai_response, _ = await ai.analyze(candidate)
        decision = ai_response.get("decision", "?")
        conf = ai_response.get("confidence", 0)
        risk = ai_response.get("risk", {}) or {}
        rr = risk.get("risk_reward", 0)
        reason_text = (ai_response.get("reason") or "")[:300]

        db = SessionLocal()
        try:
            from app.analysis.risk_reward import ensure_tp2_probability
            ensure_tp2_probability(ai_response, candidate)
            ok, val_reason = validate_for_broadcast(ai_response)
            label = "VALID" if ok else val_reason.replace("_", " ").title()
            emoji = "🟢" if decision == "BUY" else "🔴" if decision == "SELL" else "⏳"
            if decision == "WAIT":
                from app.watchlist.manager import update_from_scan
                update_from_scan(symbol, candidate.get("candidate_direction", "?"), ai_response, candidate, False, False, {"within_zone": True, "near_zone": True, "at_sr": True})
            if decision in {"BUY", "SELL"}:
                from app.watchlist.manager import update_from_scan
                update_from_scan(symbol, candidate.get("candidate_direction", "?"), ai_response, candidate, ok, False, {"within_zone": True, "near_zone": True, "at_sr": True})
                row = create_signal_log(db, candidate, ai_response, status="pending" if ok else "warning", broadcast_status="pending_admin")
                from app.signal.formatter import admin_signal_message
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
        logger.exception("Zone monitor AI analysis failed symbol=%s", symbol)


def _evaluate_proximity(price: float, zone_data: dict, sr_data: dict, settings) -> dict:
    if zone_data.get("price_within_demand"):
        return {"status": "entering", "trigger_type": "price_within_demand", "zone_type": "demand",
                "within_zone": True, "zone_high": zone_data["demand_zone_high"],
                "zone_low": zone_data["demand_zone_low"], "distance_pct": 0.0}
    if zone_data.get("price_within_supply"):
        return {"status": "entering", "trigger_type": "price_within_supply", "zone_type": "supply",
                "within_zone": True, "zone_high": zone_data["supply_zone_high"],
                "zone_low": zone_data["supply_zone_low"], "distance_pct": 0.0}
    if sr_data.get("at_support"):
        sup = sr_data.get("support", 0)
        return {"status": "entering", "trigger_type": "near_support", "zone_type": "support",
                "within_zone": True, "zone_high": sup, "zone_low": sup, "distance_pct": 0.0}
    if sr_data.get("at_resistance"):
        res = sr_data.get("resistance", 0)
        return {"status": "entering", "trigger_type": "near_resistance", "zone_type": "resistance",
                "within_zone": True, "zone_high": res, "zone_low": res, "distance_pct": 0.0}
    dist_demand = zone_data.get("distance_to_demand_pct", 999)
    dist_supply = zone_data.get("distance_to_supply_pct", 999)
    pct = settings.zone_approaching_pct
    if 0 < dist_demand <= pct:
        return {"status": "approaching", "zone_type": "demand", "distance_pct": dist_demand,
                "zone_high": zone_data["demand_zone_high"], "zone_low": zone_data["demand_zone_low"]}
    if 0 < dist_supply <= pct:
        return {"status": "approaching", "zone_type": "supply", "distance_pct": dist_supply,
                "zone_high": zone_data["supply_zone_high"], "zone_low": zone_data["supply_zone_low"]}
    return {"status": "none"}


def _to_dataframe(rows: list[dict]) -> "pd.DataFrame":
    import pandas as pd
    df = pd.DataFrame(rows)
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _empty_orderflow() -> dict:
    return {"symbol": "", "window": "1m", "buy_volume": 0, "sell_volume": 0, "volume_delta": 0, "delta_ratio": 0,
            "cumulative_volume_delta": 0, "trade_count": 0, "trade_intensity": "low", "average_trade_size": 0,
            "large_trade_count": 0, "large_trade_buy_volume": 0, "large_trade_sell_volume": 0,
            "large_trade_buy_notional": 0, "large_trade_sell_notional": 0, "best_bid": 0, "best_ask": 0,
            "spread": 0, "bid_depth": 0, "ask_depth": 0, "orderbook_imbalance": 0,
            "liquidity_wall_side": "none", "liquidity_wall_price": 0, "liquidation_buy_notional": 0,
            "liquidation_sell_notional": 0, "liquidation_spike_detected": False,
            "orderflow_bias": "insufficient_data", "flow_interpretation": ""}
