from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import repository
from app.market_data.provider_factory import configured_provider_names, create_provider


FINAL_CLOSE_REASONS = {
    "hit_tp1": "tp1_hit",
    "hit_tp2": "tp2_hit",
    "hit_sl": "sl_hit",
    "break_even": "be_hit",
    "expired": "expired_by_time",
    "invalidated": "invalidation_rule",
    "manually_closed": "manual_admin_close",
}


async def track_pending_outcomes(db: Session) -> dict[str, Any]:
    settings = get_settings()
    if not settings.enable_outcome_tracking:
        return {"status": "disabled", "checked": 0, "updated": 0}
    checked = 0
    updated = 0
    for signal in repository.get_pending_signals(db):
        checked += 1
        price = await current_price(signal.symbol)
        outcome = repository.get_signal_outcome(db, signal.id) or repository.create_signal_outcome(db, signal.id, {})
        if not outcome:
            continue
        if price > 0:
            update_excursions(db, signal, outcome, price)
            result = detect_result(signal.decision, price, outcome.stop_loss, outcome.take_profit_1, outcome.take_profit_2)
            if not result:
                result = await detect_result_from_candles(signal, outcome)
            if result:
                apply_outcome(db, signal.id, result, price)
                updated += 1
                continue
            if market_window_expired(signal, price):
                candle_result = await detect_result_from_candles(signal, outcome)
                if candle_result:
                    apply_outcome(db, signal.id, candle_result, price)
                else:
                    apply_outcome(db, signal.id, "expired", price)
                updated += 1
                continue
        if expired(signal):
            candle_result = await detect_result_from_candles(signal, outcome)
            if candle_result:
                apply_outcome(db, signal.id, candle_result, price)
            else:
                apply_outcome(db, signal.id, "expired", price)
            updated += 1
    return {"status": "completed", "checked": checked, "updated": updated}


async def current_price(symbol: str) -> float:
    for name in configured_provider_names():
        provider = create_provider(name)
        try:
            tickers = await provider.get_tickers()
            item = next((x for x in tickers if x.get("symbol") == symbol), None)
            if item:
                return float(item.get("last_price") or item.get("ask") or item.get("bid") or 0)
        except Exception:  # noqa: BLE001
            pass
        finally:
            await provider.close()
    return 0.0


async def _fetch_recent_klines(symbol: str, since: datetime) -> list[dict[str, Any]]:
    for name in configured_provider_names():
        provider = create_provider(name)
        try:
            raw = await provider.get_klines(symbol, "15m", limit=50)
            klines = []
            for row in raw:
                ts = _kline_timestamp(row)
                if ts and ts >= since:
                    klines.append(row)
            return klines
        except Exception:  # noqa: BLE001
            pass
        finally:
            await provider.close()
    return []


def _kline_timestamp(row: dict[str, Any]) -> datetime | None:
    ts_ms = row.get("open_time") or row.get("t") or row.get("ts") or 0
    try:
        ts_s = float(ts_ms)
        if ts_s > 10_000_000_000:
            ts_s /= 1000
        return datetime.fromtimestamp(ts_s, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


async def detect_result_from_candles(signal: Any, outcome: Any) -> str | None:
    if not signal.timestamp:
        return None
    ts = signal.timestamp
    if not ts.tzinfo:
        ts = ts.replace(tzinfo=timezone.utc)
    klines = await _fetch_recent_klines(signal.symbol, ts)
    if not klines:
        return None
    decision = str(signal.decision or "").upper()
    sl = float(outcome.stop_loss or 0)
    tp1 = float(outcome.take_profit_1 or 0)
    tp2 = float(outcome.take_profit_2 or 0)
    if decision == "BUY":
        for row in klines:
            high = _parse_ohlc(row, "high")
            low = _parse_ohlc(row, "low")
            if sl and low <= sl:
                return "hit_sl"
            if tp2 and high >= tp2:
                return "hit_tp2"
            if tp1 and high >= tp1:
                return "hit_tp1"
    elif decision == "SELL":
        for row in klines:
            high = _parse_ohlc(row, "high")
            low = _parse_ohlc(row, "low")
            if sl and high >= sl:
                return "hit_sl"
            if tp2 and low <= tp2:
                return "hit_tp2"
            if tp1 and low <= tp1:
                return "hit_tp1"
    return None


def _parse_ohlc(row: dict[str, Any], field: str) -> float:
    for key in (field, field[0], field.upper(), field.capitalize()):
        val = row.get(key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                pass
    return 0.0


def detect_result(decision: str, price: float, stop_loss: float, tp1: float, tp2: float) -> str | None:
    decision = decision.upper()
    if decision == "BUY":
        if stop_loss and price <= stop_loss:
            return "hit_sl"
        if tp2 and price >= tp2:
            return "hit_tp2"
        if tp1 and price >= tp1:
            return "hit_tp1"
    if decision == "SELL":
        if stop_loss and price >= stop_loss:
            return "hit_sl"
        if tp2 and price <= tp2:
            return "hit_tp2"
        if tp1 and price <= tp1:
            return "hit_tp1"
    return None


def update_excursions(db: Session, signal: Any, outcome: Any, price: float) -> None:
    entry = float(outcome.entry_price or 0)
    if entry <= 0:
        return
    if signal.decision == "BUY":
        favorable = max(0.0, price - entry)
        adverse = max(0.0, entry - price)
    else:
        favorable = max(0.0, entry - price)
        adverse = max(0.0, price - entry)
    outcome.max_favorable_excursion = max(float(outcome.max_favorable_excursion or 0), favorable)
    outcome.max_adverse_excursion = max(float(outcome.max_adverse_excursion or 0), adverse)
    outcome.duration_minutes = duration_minutes(signal.timestamp)
    db.add(outcome)
    db.commit()


def apply_outcome(db: Session, signal_id: int, result: str, close_price: float = 0.0) -> None:
    outcome = repository.update_signal_outcome(db, signal_id, result, FINAL_CLOSE_REASONS.get(result), close_price or None)
    if not outcome:
        return
    now = datetime.now(timezone.utc)
    if result == "hit_tp1":
        outcome.first_tp_hit_at = now
    elif result == "hit_tp2":
        outcome.second_tp_hit_at = now
    elif result == "hit_sl":
        outcome.stop_loss_hit_at = now
    elif result == "expired":
        outcome.expired_at = now
    db.add(outcome)
    db.commit()


def market_window_expired(signal: Any, price: float) -> bool:
    settings = get_settings()
    timestamp = signal.timestamp
    if not timestamp or price <= 0:
        return False
    if not timestamp.tzinfo:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    window_end = timestamp + timedelta(minutes=settings.signal_market_valid_minutes)
    if datetime.now(timezone.utc) < window_end:
        return False
    entry_zone = str(getattr(signal, "entry_zone", "") or "")
    parts = [p.strip() for p in entry_zone.replace(",", "-").split("-") if p.strip()]
    if len(parts) < 2:
        return True
    low = float(parts[0]) if parts[0].replace(".", "").replace("-", "").isdigit() else 0
    high = float(parts[-1]) if parts[-1].replace(".", "").replace("-", "").isdigit() else 0
    if low <= 0 or high <= 0:
        return True
    return price < low or price > high


def expired(signal: Any) -> bool:
    timestamp = signal.timestamp
    if not timestamp:
        return False
    if not timestamp.tzinfo:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) >= timestamp + timedelta(hours=expiry_hours(signal))


def expiry_hours(signal: Any) -> int:
    settings = get_settings()
    label = str(getattr(signal, "setup_type", "") or "").lower()
    if "scalp" in label or "m15" in label:
        return settings.signal_expiry_m15_hours
    if "swing" in label or "h4" in label:
        return settings.signal_expiry_h4_hours
    return settings.signal_expiry_h1_hours


def duration_minutes(started_at: datetime | None) -> int:
    if not started_at:
        return 0
    if not started_at.tzinfo:
        started_at = started_at.replace(tzinfo=timezone.utc)
    return max(0, int((datetime.now(timezone.utc) - started_at).total_seconds() // 60))
