import logging
from typing import Any
import httpx
from app.config import get_settings
from app.telegram.message_formatter import split_long_message


logger = logging.getLogger(__name__)


class TelegramBot:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.base_url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}"

    def enabled(self) -> bool:
        return bool(self.settings.telegram_bot_token and self.settings.telegram_admin_chat_id)

    async def send_admin(self, text: str, reply_markup: dict[str, Any] | None = None) -> None:
        if not self.enabled():
            logger.warning("Telegram admin send skipped: missing token or admin chat id")
            return
        await self.send_message(self.settings.telegram_admin_chat_id, text, reply_markup)

    async def send_channel(self, text: str) -> None:
        if not (self.settings.telegram_bot_token and self.settings.telegram_channel_chat_id):
            logger.warning("Telegram channel send skipped: missing token or channel chat id")
            return
        await self.send_message(self.settings.telegram_channel_chat_id, text)

    async def send_message(self, chat_id: str, text: str, reply_markup: dict[str, Any] | None = None) -> None:
        async with httpx.AsyncClient(timeout=15) as client:
            chunks = split_long_message(text)
            for idx, chunk in enumerate(chunks):
                payload: dict[str, Any] = {"chat_id": chat_id, "text": chunk, "parse_mode": "HTML", "disable_web_page_preview": True}
                if reply_markup and idx == 0:
                    payload["reply_markup"] = reply_markup
                response = await client.post(f"{self.base_url}/sendMessage", json=payload)
                response.raise_for_status()


def approval_keyboard(signal_id: int) -> dict[str, Any]:
    return {"inline_keyboard": [[{"text": "Approve Broadcast", "callback_data": f"signal_approve:{signal_id}"}, {"text": "Reject", "callback_data": f"signal_reject:{signal_id}"}], [{"text": "Details", "callback_data": f"signal_detail:{signal_id}"}, {"text": "Orderflow", "callback_data": f"signal_orderflow:{signal_id}"}]]}
