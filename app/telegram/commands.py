import json
from sqlalchemy.orm import Session
from app.config import get_settings
from app.database import repository
from app.telegram.message_formatter import (
    format_broadcast_off_message,
    format_broadcast_on_message,
    format_error_message,
    format_help_message,
    format_last_scan_message,
    format_learning_status_message,
    format_lesson_approved_message,
    format_lesson_detail_message,
    format_lesson_disabled_message,
    format_lesson_rejected_message,
    format_lessons_message,
    format_orderflow_summary_message,
    format_orderflow_top_message,
    format_outcomes_message,
    format_pairs_message,
    format_performance_message,
    format_pending_signals_message,
    format_set_confidence_message,
    format_set_rr_message,
    format_signal_detail_message,
    format_signal_review_message,
    format_signal_result_updated_message,
    format_settings_message,
    format_signals_message,
    format_start_message,
    format_status_message,
    format_top_volume_message,
    format_waiting_message,
)
from app.learning.lesson_manager import approve_lesson, disable_lesson, reject_lesson
from app.learning.performance_analyzer import analyze_performance


HELP_TEXT = """Commands:
/start
/status
/scan_now
/pairs
/top_volume
/signals
/signal_detail ID
/signal_result ID RESULT
/pending_signals
/outcomes
/performance
/lessons
/lesson_detail ID
/approve_lesson ID
/reject_lesson ID
/disable_lesson ID
/review_signal ID
/learning_status
/waiting
/settings
/set_confidence <value>
/set_rr <value>
/broadcast_on
/broadcast_off
/last_scan
/diagnose_market
/orderflow SYMBOL
/orderflow_top
/help"""


COMMAND_CALLBACKS = {
    "status": "/status",
    "scan_now": "/scan_now",
    "pairs": "/pairs",
    "top_volume": "/top_volume",
    "signals": "/signals",
    "pending_signals": "/pending_signals",
    "outcomes": "/outcomes",
    "performance": "/performance",
    "lessons": "/lessons",
    "learning_status": "/learning_status",
    "waiting": "/waiting",
    "settings": "/settings",
    "broadcast_on": "/broadcast_on",
    "broadcast_off": "/broadcast_off",
    "last_scan": "/last_scan",
    "diagnose_market": "/diagnose_market",
    "orderflow_top": "/orderflow_top",
    "help": "/help",
}


def command_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "Status", "callback_data": "cmd:status"}, {"text": "Scan Now", "callback_data": "cmd:scan_now"}],
            [{"text": "Pairs", "callback_data": "cmd:pairs"}, {"text": "Top Volume", "callback_data": "cmd:top_volume"}],
            [{"text": "Signals", "callback_data": "cmd:signals"}, {"text": "Waiting", "callback_data": "cmd:waiting"}],
            [{"text": "Pending Signals", "callback_data": "cmd:pending_signals"}, {"text": "Outcomes", "callback_data": "cmd:outcomes"}],
            [{"text": "Performance", "callback_data": "cmd:performance"}, {"text": "Lessons", "callback_data": "cmd:lessons"}],
            [{"text": "Learning Status", "callback_data": "cmd:learning_status"}, {"text": "Orderflow Top", "callback_data": "cmd:orderflow_top"}],
            [{"text": "Settings", "callback_data": "cmd:settings"}, {"text": "Last Scan", "callback_data": "cmd:last_scan"}],
            [{"text": "Broadcast ON", "callback_data": "cmd:broadcast_on"}, {"text": "Broadcast OFF", "callback_data": "cmd:broadcast_off"}],
            [{"text": "Diagnose Market", "callback_data": "cmd:diagnose_market"}, {"text": "Help", "callback_data": "cmd:help"}],
        ]
    }


def pagination_keyboard(kind: str, page: int, total_pages: int) -> dict:
    prev_page = max(1, page - 1)
    next_page = min(total_pages, page + 1)
    return {"inline_keyboard": [[{"text": "Prev", "callback_data": f"{kind}_prev:{prev_page}"}, {"text": "Next", "callback_data": f"{kind}_next:{next_page}"}], [{"text": "Refresh", "callback_data": f"{kind}_refresh:{page}"}, {"text": "Menu", "callback_data": "cmd:help"}]]}


def signal_list_keyboard(page: int, total_pages: int, first_signal_id: int | None = None) -> dict:
    rows = [[{"text": "Prev", "callback_data": f"signals_prev:{max(1, page - 1)}"}, {"text": "Next", "callback_data": f"signals_next:{min(total_pages, page + 1)}"}]]
    if first_signal_id:
        rows.append([{"text": "Detail", "callback_data": f"signal_detail:{first_signal_id}"}, {"text": "Menu", "callback_data": "cmd:help"}])
    return {"inline_keyboard": rows}


def command_from_callback(data: str) -> str | None:
    for prefix in ("pairs", "top_volume", "signals", "waiting"):
        if data.startswith(f"{prefix}_"):
            _, _, raw_page = data.partition(":")
            page = raw_page if raw_page.isdigit() else "1"
            return f"/{prefix} {page}"
    if not data.startswith("cmd:"):
        return None
    return COMMAND_CALLBACKS.get(data.split(":", 1)[1])


def is_admin(chat_id: str) -> bool:
    return str(chat_id) == str(get_settings().telegram_admin_chat_id)


def handle_command(db: Session, text: str) -> tuple[str, str | None]:
    settings = get_settings()
    parts = text.strip().split()
    cmd = parts[0] if parts else "/help"
    page = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
    if cmd in {"/start", "/help"}:
        return (format_start_message(settings), None) if cmd == "/start" else (format_help_message(), None)
    if cmd == "/status":
        scan = repository.latest_scan(db)
        auto = repository.get_setting(db, "auto_broadcast", str(settings.auto_broadcast))
        min_conf = repository.get_setting(db, "min_confidence", str(settings.min_confidence))
        min_rr = repository.get_setting(db, "min_risk_reward", str(settings.min_risk_reward))
        summary = json.loads(scan.summary_json) if scan else {}
        return format_status_message({"market_provider": settings.market_provider, "fallback_provider": settings.fallback_market_provider, "enable_orderflow": settings.enable_orderflow, "auto_broadcast": auto, "max_pairs": settings.max_pairs, "max_realtime_pairs": settings.max_realtime_pairs, "max_depth_pairs": settings.max_depth_pairs, "scan_interval_minutes": settings.scan_interval_minutes, "last_scan_time": scan.timestamp if scan else None, "min_confidence": min_conf, "min_risk_reward": min_rr, "total_scanned": getattr(scan, "total_pairs", 0) if scan else 0, "candidate_count": getattr(scan, "candidates_count", 0) if scan else 0, "valid_signal_count": getattr(scan, "valid_signals_count", 0) if scan else 0, "rejected_count": getattr(scan, "rejected_count", 0) if scan else 0, "provider": summary.get("provider")}), None
    if cmd == "/scan_now":
        return "<b>🔎 Manual Scan Started</b>\n\nBot sedang scan market sekarang. Hasil akan dikirim setelah scan selesai.", "scan_now"
    if cmd == "/pairs":
        scan = repository.latest_scan(db)
        summary = json.loads(scan.summary_json) if scan else {}
        provider = summary.get("provider", "-")
        raw_pairs = summary.get("pairs", [])
        top = {x.get("symbol"): x for x in summary.get("top_volume", []) if isinstance(x, dict)}
        pairs = [{"symbol": x, "status": "TRADING", "volume_rank": top.get(x, {}).get("rank", idx + 1), "provider": provider} for idx, x in enumerate(raw_pairs)]
        return format_pairs_message(pairs, page), f"keyboard:pairs:{page}:{max(1, (len(pairs) + 19) // 20)}"
    if cmd == "/top_volume":
        scan = repository.latest_scan(db)
        summary = json.loads(scan.summary_json) if scan else {}
        provider = summary.get("provider", "-")
        pairs = [{**x, "provider": provider} for x in summary.get("top_volume", []) if isinstance(x, dict)]
        return format_top_volume_message(pairs, page), f"keyboard:top_volume:{page}:{max(1, (len(pairs) + 14) // 15)}"
    if cmd == "/signals":
        rows = repository.get_recent_signals(db, 100)
        attach_signal_market_state(db, rows)
        return format_signals_message(rows, page), f"keyboard:signals:{page}:{max(1, (len(rows) + 9) // 10)}:{rows[0].id if rows else ''}"
    if cmd == "/signal_detail":
        if len(parts) < 2 or not parts[1].isdigit():
            return format_error_message("Missing Signal ID", "Gunakan format /signal_detail ID", "Contoh: /signal_detail 123"), None
        row = repository.get_signal_by_id(db, int(parts[1]))
        if not row:
            return format_error_message("Signal Not Found", parts[1]), None
        return format_signal_detail_message(row, repository.get_signal_outcome(db, row.id)), None
    if cmd == "/signal_result":
        allowed = sorted(repository.FINAL_OUTCOMES)
        if len(parts) < 3 or not parts[1].isdigit() or parts[2] not in allowed:
            return format_error_message("Invalid Signal Result", "Gunakan format /signal_result ID RESULT", "Allowed: " + ", ".join(allowed)), None
        row = repository.get_signal_by_id(db, int(parts[1]))
        if not row:
            return format_error_message("Signal Not Found", parts[1]), None
        outcome = repository.update_signal_outcome(db, row.id, parts[2], manual_close_reason(parts[2]))
        return format_signal_result_updated_message(row, outcome), None
    if cmd == "/pending_signals":
        return format_pending_signals_message(repository.get_pending_signals(db)), None
    if cmd == "/outcomes":
        return format_outcomes_message(repository.get_recent_outcomes(db, 50)), None
    if cmd == "/performance":
        period = parts[1] if len(parts) > 1 else "30d"
        if period not in {"7d", "30d", "all"}:
            return format_error_message("Invalid Period", period, "Gunakan /performance 7d, /performance 30d, atau /performance all"), None
        return format_performance_message(analyze_performance(db, period)), None
    if cmd == "/lessons":
        lessons = repository.get_lessons(db, None, 100)
        return format_lessons_message(lessons), None
    if cmd == "/lesson_detail":
        lesson = parse_lesson_arg(db, parts)
        if not lesson:
            return format_error_message("Lesson Not Found", "Gunakan /lesson_detail ID"), None
        return format_lesson_detail_message(lesson, repository.get_signal_review(db, lesson.source_signal_id)), None
    if cmd == "/approve_lesson":
        lesson = parse_lesson_arg(db, parts)
        if not lesson:
            return format_error_message("Lesson Not Found", "Gunakan /approve_lesson ID"), None
        return format_lesson_approved_message(approve_lesson(db, lesson.id)), None
    if cmd == "/reject_lesson":
        lesson = parse_lesson_arg(db, parts)
        if not lesson:
            return format_error_message("Lesson Not Found", "Gunakan /reject_lesson ID"), None
        return format_lesson_rejected_message(reject_lesson(db, lesson.id)), None
    if cmd == "/disable_lesson":
        lesson = parse_lesson_arg(db, parts)
        if not lesson:
            return format_error_message("Lesson Not Found", "Gunakan /disable_lesson ID"), None
        return format_lesson_disabled_message(disable_lesson(db, lesson.id)), None
    if cmd == "/review_signal":
        if len(parts) < 2 or not parts[1].isdigit():
            return format_error_message("Missing Signal ID", "Gunakan /review_signal ID"), None
        row = repository.get_signal_by_id(db, int(parts[1]))
        if not row:
            return format_error_message("Signal Not Found", parts[1]), None
        return "<b>🧠 Signal Review Started</b>\n\nReview sedang diproses.", f"review_signal:{row.id}"
    if cmd == "/learning_status":
        settings = get_settings()
        pending_reviews = len(repository.get_closed_unreviewed_signals(db, 100))
        return format_learning_status_message({"enable_signal_learning": settings.enable_signal_learning, "enable_auto_review": settings.enable_auto_review, "enable_adaptive_scoring": settings.enable_adaptive_scoring, "require_admin_approval_for_lessons": settings.require_admin_approval_for_lessons, "pending_outcomes": len(repository.get_pending_signals(db)), "pending_reviews": pending_reviews, "active_lessons": len(repository.get_lessons(db, "active", 100)), "suggested_lessons": len(repository.get_lessons(db, "suggested", 100)), "lookback_days": settings.performance_lookback_days, "max_lessons": settings.max_active_lessons_in_prompt}), None
    if cmd == "/waiting":
        rows = repository.latest_rejected(db, 200)
        return format_waiting_message(rows, page), f"keyboard:waiting:{page}:{max(1, (len(rows) + 14) // 15)}"
    if cmd == "/settings":
        return format_settings_message(settings.model_dump()), None
    if cmd == "/broadcast_on":
        repository.set_setting(db, "auto_broadcast", "true")
        return format_broadcast_on_message({"min_confidence": settings.min_confidence, "min_risk_reward": settings.min_risk_reward, "channel_enabled": bool(settings.telegram_channel_chat_id)}), None
    if cmd == "/broadcast_off":
        repository.set_setting(db, "auto_broadcast", "false")
        return format_broadcast_off_message({}), None
    if cmd == "/set_confidence" and len(parts) == 2:
        try:
            value = int(parts[1])
            if not 1 <= value <= 100:
                raise ValueError
        except ValueError:
            return format_error_message("Invalid Confidence Value", "Gunakan angka antara 1 sampai 100.", "Contoh: /set_confidence 70"), None
        old = repository.get_setting(db, "min_confidence", str(settings.min_confidence))
        repository.set_setting(db, "min_confidence", parts[1])
        return format_set_confidence_message(old, parts[1]), None
    if cmd == "/set_rr" and len(parts) == 2:
        try:
            value = float(parts[1])
            if value < 1.0:
                raise ValueError
        except ValueError:
            return format_error_message("Invalid RR Value", "Gunakan angka lebih dari atau sama dengan 1.0.", "Contoh: /set_rr 2.0"), None
        old = repository.get_setting(db, "min_risk_reward", str(settings.min_risk_reward))
        repository.set_setting(db, "min_risk_reward", parts[1])
        return format_set_rr_message(old, parts[1]), None
    if cmd == "/last_scan":
        scan = repository.latest_scan(db)
        return format_last_scan_message(scan), None
    if cmd in {"/diagnose_market", "/diagnose_binance"}:
        return "Running market provider diagnostic...", "diagnose_market"
    if cmd == "/orderflow":
        if len(parts) < 2:
            return format_error_message("Missing Symbol", "Gunakan format /orderflow SYMBOL", "Contoh: /orderflow BTCUSDT"), None
        rows = repository.latest_orderflow(db, parts[1], 1)
        if not rows:
            return format_error_message("No Orderflow Data", f"Belum ada data untuk {parts[1].upper()}"), None
        raw = json.loads(rows[0].raw_summary_json or "{}")
        return format_orderflow_summary_message(raw), None
    if cmd == "/orderflow_top":
        return format_orderflow_top_message(repository.latest_orderflow_activity(db, 100)), None
    return format_error_message("Unknown Command", cmd, "Use /help"), None


def attach_signal_market_state(db: Session, rows: list) -> None:
    for row in rows:
        snapshots = repository.latest_orderflow(db, getattr(row, "symbol", ""), 1)
        if not snapshots:
            continue
        snapshot = snapshots[0]
        current_price = float(getattr(snapshot, "price", 0) or getattr(snapshot, "best_ask", 0) or getattr(snapshot, "best_bid", 0) or 0)
        if current_price > 0:
            setattr(row, "current_price", current_price)


def manual_close_reason(result: str) -> str:
    return {
        "hit_tp1": "tp1_hit",
        "hit_tp2": "tp2_hit",
        "hit_sl": "sl_hit",
        "break_even": "be_hit",
        "expired": "expired_by_time",
        "invalidated": "invalidation_rule",
        "manually_closed": "manual_admin_close",
    }.get(result, "manual_admin_close")


def parse_lesson_arg(db: Session, parts: list[str]):
    if len(parts) < 2 or not parts[1].isdigit():
        return None
    return repository.get_lesson(db, int(parts[1]))
