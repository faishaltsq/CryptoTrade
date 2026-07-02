import json
from sqlalchemy.orm import Session
from app.database import repository
from app.signal.formatter import channel_signal_message
from app.telegram.admin_bot import TelegramBot


async def handle_callback(db: Session, data: str, bot: TelegramBot) -> str:
    action, _, raw_id = data.partition(":")
    if not raw_id.isdigit():
        return "Invalid callback."
    signal_id = int(raw_id)
    row = repository.get_signal(db, signal_id)
    if not row:
        return "Signal not found."
    if action == "approve":
        ai = json.loads(row.ai_response_json)
        await bot.send_channel(channel_signal_message(ai))
        repository.update_signal_status(db, signal_id, "broadcasted", "broadcasted")
        return f"Signal #{signal_id} broadcasted."
    if action == "reject":
        repository.update_signal_status(db, signal_id, "rejected", "rejected")
        return f"Signal #{signal_id} rejected."
    if action == "details":
        return row.ai_response_json
    return "Unknown action."
