import asyncio
import logging
from typing import Any
import httpx
from app.config import get_settings
from app.telegram.message_formatter import split_long_message


logger = logging.getLogger(__name__)
_RETRY_DELAYS = [0.5, 1.0, 2.0, 5.0]
_MESSAGE_COOLDOWN = 0.3


class TelegramBot:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.base_url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}"
        self._last_send_time = 0.0

    def enabled(self) -> bool:
        return bool(self.settings.telegram_bot_token and self.settings.telegram_admin_chat_id)

    async def send_admin(self, text: str, reply_markup: dict[str, Any] | None = None) -> None:
        if not self.enabled():
            raise RuntimeError("Telegram admin not configured: missing TELEGRAM_BOT_TOKEN or TELEGRAM_ADMIN_CHAT_ID")
        await self.send_message(self.settings.telegram_admin_chat_id, text, reply_markup)

    async def send_channel(self, text: str) -> None:
        if not (self.settings.telegram_bot_token and self.settings.telegram_channel_chat_id):
            logger.warning("Telegram channel send skipped: missing token or channel chat id")
            return None
        return await self.send_message(self.settings.telegram_channel_chat_id, text)

    async def pin_chat_message(self, chat_id: str, message_id: int) -> bool:
        try:
            await self._send_with_retry({"chat_id": chat_id, "message_id": message_id}, "pinChatMessage")
            return True
        except Exception:
            logger.warning("Failed to pin message_id=%s in chat_id=%s", message_id, chat_id)
            return False

    async def unpin_chat_message(self, chat_id: str, message_id: int) -> bool:
        try:
            await self._send_with_retry({"chat_id": chat_id, "message_id": message_id}, "unpinChatMessage")
            return True
        except Exception:
            logger.warning("Failed to unpin message_id=%s in chat_id=%s", message_id, chat_id)
            return False

    async def _rate_limit_wait(self) -> None:
        import time
        elapsed = time.monotonic() - self._last_send_time
        if elapsed < _MESSAGE_COOLDOWN:
            await asyncio.sleep(_MESSAGE_COOLDOWN - elapsed)

    async def send_message(self, chat_id: str, text: str, reply_markup: dict[str, Any] | None = None) -> list[int]:
        chunks = split_long_message(text)
        message_ids: list[int] = []
        for idx, chunk in enumerate(chunks):
            payload: dict[str, Any] = {"chat_id": chat_id, "text": chunk, "parse_mode": "HTML", "disable_web_page_preview": True}
            if reply_markup and idx == 0:
                payload["reply_markup"] = reply_markup
            result = await self._send_with_retry(payload)
            if result and isinstance(result, dict):
                mid = result.get("result", {}).get("message_id")
                if isinstance(mid, int):
                    message_ids.append(mid)
        return message_ids

    async def _send_with_retry(self, payload: dict[str, Any], method: str = "sendMessage") -> dict[str, Any]:
        last_error = None
        for attempt, delay in enumerate([0.0] + list(_RETRY_DELAYS)):
            if attempt > 0:
                logger.warning("Telegram send retry attempt=%d delay=%.1fs chat_id=%s", attempt, delay, payload.get("chat_id"))
                await asyncio.sleep(delay)
            try:
                await self._rate_limit_wait()
                async with httpx.AsyncClient(timeout=15) as client:
                    response = await client.post(f"{self.base_url}/{method}", json=payload)
                    import time
                    self._last_send_time = time.monotonic()
                    if response.status_code == 429:
                        retry_after = float(response.headers.get("Retry-After", delay or 5))
                        last_error = f"HTTP 429 rate limited, retry-after={retry_after}s"
                        await asyncio.sleep(retry_after)
                        continue
                    response.raise_for_status()
                    return response.json()
            except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as exc:
                last_error = str(exc)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code >= 500:
                    last_error = f"HTTP {exc.response.status_code}"
                else:
                    raise
        logger.error("Telegram send failed after %d attempts: %s", len(_RETRY_DELAYS) + 1, last_error)
        raise RuntimeError(f"Telegram send exhausted retries: {last_error}")


def approval_keyboard(signal_id: int) -> dict[str, Any]:
    return {"inline_keyboard": [[{"text": "Approve Broadcast", "callback_data": f"signal_approve:{signal_id}"}, {"text": "Reject", "callback_data": f"signal_reject:{signal_id}"}], [{"text": "Details", "callback_data": f"signal_detail:{signal_id}"}, {"text": "Orderflow", "callback_data": f"signal_orderflow:{signal_id}"}]]}
