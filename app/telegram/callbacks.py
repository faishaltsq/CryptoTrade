import json
from sqlalchemy.orm import Session
from app.database import repository
from app.telegram.message_formatter import format_error_message, format_orderflow_summary_message, format_signal_broadcast_channel_message, format_signal_candidate_admin_message
from app.telegram.admin_bot import TelegramBot


async def handle_callback(db: Session, data: str, bot: TelegramBot) -> str:
    action, _, raw_id = data.partition(":")
    if not raw_id.isdigit():
        return format_error_message("Invalid Callback", data)
    signal_id = int(raw_id)
    row = repository.get_signal(db, signal_id)
    if not row:
        return format_error_message("Signal Not Found", signal_id)
    if action in {"approve", "signal_approve"}:
        ai = json.loads(row.ai_response_json)
        await bot.send_channel(format_signal_broadcast_channel_message(ai))
        repository.update_signal_status(db, signal_id, "broadcasted", "broadcasted")
        return f"<b>✅ Signal Broadcasted</b>\n\nSignal <code>#{signal_id}</code> berhasil dikirim ke channel."
    if action in {"reject", "signal_reject"}:
        repository.update_signal_status(db, signal_id, "rejected", "rejected")
        return f"<b>🟡 Signal Rejected</b>\n\nSignal <code>#{signal_id}</code> ditolak."
    if action in {"details", "signal_detail"}:
        return format_signal_candidate_admin_message(json.loads(row.ai_response_json))
    if action == "signal_orderflow":
        return format_orderflow_summary_message(json.loads(row.orderflow_summary_json or "{}"))
    return format_error_message("Unknown Action", action)
