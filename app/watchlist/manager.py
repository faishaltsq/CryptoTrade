import hashlib
import logging
from datetime import datetime, timedelta, timezone
from time import time
from typing import Any

from app.config import get_settings
from app.database.session import SessionLocal
from app.database import repository
from app.watchlist.models import SCORE_WEIGHTS, MARKET_STATES, MARKET_STATE_TRANSITIONS

logger = logging.getLogger(__name__)


def calculate_priority(ai_response: dict, candidate: dict) -> int:
    conf = int(ai_response.get("confidence") or 0)
    risk = ai_response.get("risk", {}) or {}
    rr = float(risk.get("risk_reward") or 0)
    of = candidate.get("orderflow", {}) or {}
    orderflow_score = int(of.get("orderflow_score") or 0)
    tfs = candidate.get("timeframes", {})
    m15 = tfs.get("M15", {})
    h1 = tfs.get("H1", {})
    vol_ratio = max(float(m15.get("volume_ratio") or 0), float(h1.get("volume_ratio") or 0))
    vol_ratio = min(vol_ratio, 3.0)
    momentum_score = 100 if (m15.get("volume_spike") and m15.get("cvd_divergence") != "none") else 60 if m15.get("volume_spike") else 30
    htf = tfs.get("H4", {}).get("trend", "")
    htf_score = 100 if htf == candidate.get("candidate_direction", "").lower() else 50 if htf == "ranging" else 20
    quality_mult = 0.8 if conf and rr < 1.5 else 1.0
    score = (
        conf * SCORE_WEIGHTS["confidence"] / 100
        + min(abs(orderflow_score), 20) * SCORE_WEIGHTS["orderflow"] / 20
        + vol_ratio / 3.0 * SCORE_WEIGHTS["volume"]
        + min(rr, 5.0) / 5.0 * SCORE_WEIGHTS["risk_reward"]
        + momentum_score / 100 * SCORE_WEIGHTS["momentum"]
        + htf_score / 100 * SCORE_WEIGHTS["htf_context"]
    )
    return int(max(1, min(99, score * quality_mult)))


def compute_opportunity_score(item) -> int:
    conf = item.confidence or 0
    rr = item.risk_reward or 0
    priority = item.priority_score or 0
    dist = item.trigger_distance_pct or 999
    trigger_score = 15 if dist < 0.5 else 10 if dist < 2.0 else 5 if dist < 5.0 else 0
    return int(
        conf * 0.30
        + priority * 0.35
        + min(rr, 5.0) / 5.0 * 15
        + trigger_score
        + (10 if item.analysis_count > 3 else 0)
    )


def determine_market_state(ai_response: dict, candidate: dict, previous_state: str) -> str:
    decision = ai_response.get("decision", "")
    conf = int(ai_response.get("confidence") or 0)
    tfs = candidate.get("timeframes", {})
    h1 = tfs.get("H1", {})
    m15 = tfs.get("M15", {})
    h4 = tfs.get("H4", {})
    vol_spike = m15.get("volume_spike") or h1.get("volume_spike")
    cvd_div = h1.get("cvd_divergence", "none")
    obv_trend = h1.get("obv_trend", "flat")
    at_support = h1.get("at_support", False)
    at_resistance = h1.get("at_resistance", False)
    h4_trend = h4.get("trend", "")

    if decision in {"BUY", "SELL"} and conf >= 65:
        return "BREAKOUT_READY" if decision == "BUY" else "BREAKDOWN_READY"

    if obv_trend == "rising_divergent" and cvd_div == "bullish":
        return "ACCUMULATING"

    if obv_trend == "falling_divergent" and cvd_div == "bearish" and at_resistance:
        return "ACCUMULATING"

    if h4_trend in ("bullish", "bearish") and vol_spike:
        if at_support or at_resistance:
            return "BREAKOUT_READY" if h4_trend == "bullish" else "BREAKDOWN_READY"
        return "TRENDING"

    if at_support and not at_resistance and (obv_trend == "rising" or cvd_div == "bullish"):
        return "PULLBACK_READY"

    if at_resistance and not at_support:
        return "PULLBACK_READY"

    if m15.get("volume_trend") == "falling" and h1.get("volume_trend") == "falling":
        return "CHOPPY" if conf < 50 else previous_state

    if conf < 40:
        return "WEAK"

    allowed = MARKET_STATE_TRANSITIONS.get(previous_state, set())
    if previous_state in allowed:
        return previous_state
    return "WATCHING"


def calculate_probability(ai_response: dict, candidate: dict) -> int:
    conf = int(ai_response.get("confidence") or 0)
    risk = ai_response.get("risk", {}) or {}
    rr = float(risk.get("risk_reward") or 0)
    tfs = candidate.get("timeframes", {})
    h1 = tfs.get("H1", {})
    m15 = tfs.get("M15", {})
    vol_ratio = float(m15.get("volume_ratio") or 1)
    cvd_div = h1.get("cvd_divergence", "none")
    at_sr = h1.get("at_support") or h1.get("at_resistance")
    prob = min(conf + 10, 90) if conf > 0 else 35
    if rr >= 2.0:
        prob += 5
    if vol_ratio >= 1.5:
        prob += 5
    if cvd_div != "none":
        prob += 3
    if at_sr:
        prob += 3
    return max(10, min(95, prob))


def prob_change_reason(prev_prob: int, curr_prob: int, ai_response: dict, candidate: dict) -> str:
    delta = curr_prob - prev_prob
    tfs = candidate.get("timeframes", {})
    m15 = tfs.get("M15", {})
    h1 = tfs.get("H1", {})
    reasons = []
    if delta > 0:
        if m15.get("volume_spike"):
            reasons.append("volume increasing")
        if h1.get("cvd_divergence") != "none":
            reasons.append("orderflow improving")
        if h1.get("at_support") or h1.get("at_resistance"):
            reasons.append("near key level")
    else:
        if m15.get("volume_trend") == "falling":
            reasons.append("volume fading")
        if int(ai_response.get("confidence") or 0) < 40:
            reasons.append("weak confidence")
        if not h1.get("at_support") and not h1.get("at_resistance"):
            reasons.append("mid-zone drift")
    return ", ".join(reasons[:3]) if reasons else "reevaluated"


def compute_trigger_distance(candidate: dict) -> float:
    zone = candidate.get("zone_analysis", {})
    tfs = candidate.get("timeframes", {})
    h1 = tfs.get("H1", {})
    dist = zone.get("distance_to_demand_pct", zone.get("distance_to_supply_pct", 0))
    if dist > 0:
        return round(dist, 2)
    if h1.get("at_support") or h1.get("at_resistance"):
        return 0.0
    return 999.0


def update_from_scan(symbol: str, direction: str, ai_response: dict, candidate: dict, ok: bool, is_duplicate: bool, zone_context: dict) -> None:
    db = SessionLocal()
    try:
        existing = db.query(repository.WatchlistItem).filter(
            repository.WatchlistItem.symbol == symbol.upper(),
            repository.WatchlistItem.direction == direction.upper()
        ).first()

        previous_prob = existing.previous_probability if existing else 0
        previous_state = existing.market_state if existing else "WATCHING"
        prev_count = existing.analysis_count if existing else 0

        priority = calculate_priority(ai_response, candidate)
        market_state = determine_market_state(ai_response, candidate, previous_state)
        current_prob = calculate_probability(ai_response, candidate)
        delta = current_prob - previous_prob if previous_prob > 0 else 0
        prob_reason = prob_change_reason(previous_prob, current_prob, ai_response, candidate) if previous_prob > 0 else "initial"
        trigger_dist = compute_trigger_distance(candidate)
        risk = ai_response.get("risk", {}) or {}

        state = "WATCHING"
        if ai_response.get("decision") in {"BUY", "SELL"} and ok:
            state = "READY"
        elif current_prob < 30:
            state = "WEAK"

        reason = (ai_response.get("reason") or "")[:150]
        expiry = datetime.now(timezone.utc) + timedelta(hours=6)
        entry_zone = risk.get("entry_zone", "")

        row = repository.upsert_watchlist_item(db, symbol, direction,
            market_state=market_state,
            state=state,
            confidence=int(ai_response.get("confidence") or 0),
            priority_score=priority,
            quality_score=max(0, min(100, priority)),
            risk_reward=float(risk.get("risk_reward") or 0),
            current_price=float(candidate.get("current_price") or 0),
            entry_zone=str(entry_zone),
            trigger_distance_pct=trigger_dist,
            previous_probability=current_prob,
            probability_delta=delta,
            prob_change_reason=prob_reason,
            analysis_count=prev_count + 1,
            reason=reason,
            expires_at=expiry,
        )

        opportunity = compute_opportunity_score(row)
        row.opportunity_score = opportunity
        db.commit()

        logger.info("Watchlist updated symbol=%s direction=%s market=%s state=%s prob=%d (Δ%+d) opp=%d",
                     symbol, direction, market_state, state, current_prob, delta, opportunity)
    except Exception:  # noqa: BLE001
        logger.exception("Watchlist update failed symbol=%s", symbol)
    finally:
        db.close()


_LAST_REFRESH = 0.0
_REFRESH_DEBOUNCE = 30
_CACHED_MSG_ID: int | None = None
_CACHED_CHAT_ID: str = ""
_PREV_HASH: str = ""
_EDIT_COOLDOWN = 60
_LAST_EDIT = 0.0


async def refresh_all(bot) -> None:
    global _LAST_REFRESH, _CACHED_MSG_ID, _CACHED_CHAT_ID, _PREV_HASH, _LAST_EDIT
    now = time()
    if now - _LAST_REFRESH < _REFRESH_DEBOUNCE:
        return
    _LAST_REFRESH = now
    if not _CACHED_MSG_ID:
        _load_cached_msg_id()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stored_date = _get_stored_date()
    if stored_date and stored_date != today:
        _CACHED_MSG_ID = None
        _PREV_HASH = ""
    db = SessionLocal()
    try:
        repository.remove_expired_watchlist(db)

        items = repository.get_active_watchlist(db)
        for item in items:
            item.opportunity_score = compute_opportunity_score(item)
        db.commit()

        ready = [i for i in items if i.state == "READY"]
        watching = [i for i in items if i.state == "WATCHING"]
        weak = [i for i in items if i.state == "WEAK"]

        for lst in (ready, watching, weak):
            lst.sort(key=lambda x: x.opportunity_score, reverse=True)

        msg = _render_message(ready, watching, weak)
        msg_hash = hashlib.sha256(msg.encode()).hexdigest()
        if msg_hash == _PREV_HASH:
            return
        _PREV_HASH = msg_hash

        if now - _LAST_EDIT < _EDIT_COOLDOWN:
            return
        _LAST_EDIT = now

        settings = get_settings()
        if not _CACHED_CHAT_ID:
            _CACHED_CHAT_ID = settings.telegram_admin_chat_id

        if _CACHED_MSG_ID and _CACHED_CHAT_ID:
            edited = await _edit_msg(bot, _CACHED_CHAT_ID, _CACHED_MSG_ID, msg)
            if not edited:
                _CACHED_MSG_ID = None
        if not _CACHED_MSG_ID and _CACHED_CHAT_ID:
            mid = await _send_msg(bot, _CACHED_CHAT_ID, msg)
            if mid:
                _CACHED_MSG_ID = mid
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                repository.set_setting(db, "watchlist_message_id", str(mid))
                repository.set_setting(db, "watchlist_chat_id", _CACHED_CHAT_ID)
                repository.set_setting(db, "watchlist_date", today)
        logger.info("Watchlist refreshed: READY=%d WATCHING=%d WEAK=%d", len(ready), len(watching), len(weak))
    except Exception:  # noqa: BLE001
        logger.exception("Watchlist refresh failed")
    finally:
        db.close()


async def force_refresh(bot) -> None:
    global _CACHED_MSG_ID
    _CACHED_MSG_ID = None
    db = SessionLocal()
    try:
        repository.clear_all_watchlist(db)
    finally:
        db.close()
    await refresh_all(bot)


def _load_cached_msg_id() -> None:
    global _CACHED_MSG_ID, _CACHED_CHAT_ID
    db = SessionLocal()
    try:
        wl_id = repository.get_setting(db, "watchlist_message_id", "")
        wl_chat = repository.get_setting(db, "watchlist_chat_id", "")
        if wl_id and wl_id.isdigit():
            _CACHED_MSG_ID = int(wl_id)
        if wl_chat:
            _CACHED_CHAT_ID = wl_chat
    except Exception:  # noqa: BLE001
        pass
    finally:
        db.close()


def _get_stored_date() -> str:
    db = SessionLocal()
    try:
        return repository.get_setting(db, "watchlist_date", "")
    finally:
        db.close()


def _render_message(ready: list, watching: list, weak: list) -> str:
    now_wib = _now_wib()
    lines = [f"<b>📊 LIVE WATCHLIST</b> • {now_wib}", ""]

    groups = [
        ("🟩 BREAKOUT READY", ready),
        ("🟨 ACCUMULATING", [i for i in watching if i.market_state == "ACCUMULATING"]),
        ("⬜ CHOPPY", [i for i in watching if i.market_state in ("CHOPPY", "TRENDING", "PULLBACK_READY", "WATCHING")]),
        ("🟥 WEAK", weak),
    ]

    for label, items in groups:
        if not items:
            continue
        show = items[:8]
        lines.append(f"<b>{label}</b> ({len(items)})")
        lines.append("━" * 20)
        for i in show:
            rendered = _render_entry(i)
            lines.append(rendered)
        if len(items) > 8:
            lines.append(f"<i>  ...and {len(items) - 8} more pairs → /watchlist_full</i>")
        lines.append("")

    ready_n = len(ready)
    acc_n = len([i for i in watching if i.market_state == "ACCUMULATING"])
    chp_n = len([i for i in watching if i.market_state in ("CHOPPY", "TRENDING", "PULLBACK_READY", "WATCHING")])
    w_n = len(weak)

    lines.append("━" * 20)
    lines.append(f"<b>📈 Summary:</b> {ready_n} Ready | {acc_n} Acc | {chp_n} Chp | {w_n} Weak")
    lines.append(f"<b>📋 Total:</b> {ready_n + acc_n + chp_n + w_n} pairs tracked")
    lines.append("<i>/watchlist_full</i> for all pairs")
    lines.append("")
    lines.append("<i>ℹ️ Conf=Confidence Δ=Change Opp=Opportunity RR=Risk:Reward</i>")
    return "\n".join(lines)


def _render_entry(i) -> str:
    emoji = "🟢" if i.direction == "BUY" else "🔴"
    conf = i.confidence or 0
    opp = i.opportunity_score or 0
    rr = i.risk_reward or 0
    dist = i.trigger_distance_pct or 0
    ms = i.market_state or "WATCHING"
    delta = i.probability_delta or 0
    delta_str = f"Δ{'+' if delta > 0 else ''}{delta}" if delta else ""
    conf_part = f"Conf {conf}%" + (f" ({delta_str})" if delta_str else "")
    rr_part = f"RR {rr:.1f}" if rr and rr > 0 else "RR —"
    if conf >= 40:
        trigger_txt = "NOW" if dist <= 0 else f"{dist:.2f}%" if dist < 999 else "--"
    else:
        trigger_txt = "--"
    tags = _dedup_tags(_tag_from_reason(i.reason), i.direction)
    lines = [f"{emoji} <b>{i.symbol}</b> <i>[{_status_label(ms)}]</i>"]
    lines.append(f"   {conf_part} • Opp {opp} • {rr_part}")
    lines.append(f"   Trigger: {trigger_txt}")
    if tags:
        lines.append(f"   {' • '.join(tags)}")
    return "\n".join(lines)


def _status_label(ms: str) -> str:
    m = {"BREAKOUT_READY": "BRK READY", "BREAKDOWN_READY": "BRK READY", "ACCUMULATING": "ACCUMULATING",
         "TRENDING": "TRENDING", "PULLBACK_READY": "PULLBACK", "CHOPPY": "CHOPPY",
         "WEAK": "WEAK", "WATCHING": "WATCHING", "INVALID": "INVALID"}
    return m.get(ms, ms)


def _dedup_tags(tags: list[str], direction: str) -> list[str]:
    conflicting = [("Bullish HTF", "Bearish HTF"), ("Near Supp", "Near Res"), ("Overbought", "Oversold")]
    result = list(tags)
    for a, b in conflicting:
        if a in result and b in result:
            if direction == "BUY":
                result.remove(b)
            elif direction == "SELL":
                result.remove(a)
            else:
                result[:] = [t for t in result if t not in (a, b)]
    seen = set()
    unique = [t for t in result if not (t in seen or seen.add(t))]
    return unique[:3]


def _now_wib() -> str:
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%H:%M WIB")


async def render_full_watchlist() -> str:
    db = SessionLocal()
    try:
        repository.remove_expired_watchlist(db)
        items = repository.get_active_watchlist(db)
        for item in items:
            item.opportunity_score = compute_opportunity_score(item)
        db.commit()

        ready = [i for i in items if i.state == "READY"]
        watching = [i for i in items if i.state == "WATCHING"]
        weak = [i for i in items if i.state == "WEAK"]
        for lst in (ready, watching, weak):
            lst.sort(key=lambda x: x.opportunity_score, reverse=True)

        now_wib = _now_wib()
        lines = [f"<b>📊 FULL WATCHLIST</b> • {now_wib}", ""]
        groups = [
            ("🟩 BREAKOUT READY", ready, None),
            ("🟨 ACCUMULATING", [i for i in watching if i.market_state == "ACCUMULATING"], None),
            ("⬜ CHOPPY", [i for i in watching if i.market_state in ("CHOPPY", "TRENDING", "PULLBACK_READY", "WATCHING")], None),
            ("🟥 WEAK", weak, None),
        ]
        for label, items, _ in groups:
            if not items:
                continue
            lines.append(f"<b>{label}</b> ({len(items)})")
            lines.append("━" * 20)
            for i in items:
                lines.append(_render_entry(i))
            lines.append("")
        lines.append(f"<b>Total:</b> {len(items)} pairs")
        return "\n".join(lines)
    finally:
        db.close()


def _tag_from_reason(reason: str) -> list[str]:
    if not reason:
        return ["Monitoring"]
    r = reason.lower()
    tags = []
    checks = [
        ("Bullish HTF", ["bullish", "higher high", "d1 bullish", "h4 bullish"]),
        ("Bearish HTF", ["bearish", "lower low", "d1 bearish", "h4 bearish"]),
        ("Vol Rising", ["volume spike", "volume rising", "volume increasing"]),
        ("Vol Fading", ["volume fading", "volume falling", "volume declining", "low volume"]),
        ("Near Supp", ["at_support", "near support", "support holding"]),
        ("Near Res", ["at_resistance", "near resistance", "resistance holding"]),
        ("Overbought", ["overbought", "rsi overbought"]),
        ("Oversold", ["oversold", "rsi oversold"]),
        ("Trend Strong", ["strong trend", "trend intact"]),
        ("Trend Weak", ["momentum declining", "momentum weakening"]),
        ("Ranging", ["ranging", "consolidation", "choppy", "range bound"]),
        ("Brkout Soon", ["breakout forming", "breakout attempt", "breakout ready"]),
        ("Accumulating", ["accumulation", "obv rising", "cvd bullish"]),
        ("Fake Breakout", ["false breakout", "fakeout", "bull trap", "bear trap"]),
        ("Good RR", ["favorable rr", "risk-reward favorable"]),
        ("Need Confirm", ["waiting confirmation", "need confirmation", "wait for reaction"]),
    ]
    for tag, keywords in checks:
        if any(k in r for k in keywords):
            tags.append(tag)
    return tags[:2] or ["Monitoring"]


async def _edit_msg(bot, chat_id: str, msg_id: int, text: str) -> bool:
    try:
        await bot._send_with_retry({"chat_id": chat_id, "message_id": msg_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}, "editMessageText")
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("Watchlist edit failed msg_id=%d: %s", msg_id, e)
        return False


async def _send_msg(bot, chat_id: str, text: str) -> int | None:
    try:
        ids = await bot.send_message(chat_id, text)
        return ids[0] if ids else None
    except Exception as e:  # noqa: BLE001
        logger.warning("Watchlist send failed: %s", e)
        return None
