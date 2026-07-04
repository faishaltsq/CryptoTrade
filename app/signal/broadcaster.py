from app.signal.formatter import admin_signal_message, channel_signal_message, no_valid_setup_message
from app.telegram.admin_bot import TelegramBot


class SignalBroadcaster:
    def __init__(self) -> None:
        self.bot = TelegramBot()

    async def send_candidate_to_admin(self, signal_id: int, ai_response: dict) -> None:
        await self.bot.send_admin(admin_signal_message(signal_id, ai_response))

    async def broadcast_channel(self, ai_response: dict) -> int | None:
        ids = await self.bot.send_channel(channel_signal_message(ai_response))
        return ids[0] if ids else None

    async def send_no_valid_setup(self, total_pairs: int, rejected_reasons: list[str], next_scan_minutes: int, rejected_details: list[dict] | None = None) -> None:
        await self.bot.send_admin(no_valid_setup_message(total_pairs, rejected_reasons, next_scan_minutes, rejected_details))

    async def pin_channel(self, message_id: int) -> bool:
        return await self.bot.pin_chat_message(self.bot.settings.telegram_channel_chat_id, message_id)

    async def unpin_channel(self, message_id: int) -> bool:
        return await self.bot.unpin_chat_message(self.bot.settings.telegram_channel_chat_id, message_id)
