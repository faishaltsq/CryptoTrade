from app.signal.formatter import admin_signal_message, channel_signal_message, no_valid_setup_message
from app.telegram.admin_bot import TelegramBot, approval_keyboard


class SignalBroadcaster:
    def __init__(self) -> None:
        self.bot = TelegramBot()

    async def send_candidate_to_admin(self, signal_id: int, ai_response: dict) -> None:
        await self.bot.send_admin(admin_signal_message(signal_id, ai_response), approval_keyboard(signal_id))

    async def broadcast_channel(self, ai_response: dict) -> None:
        await self.bot.send_channel(channel_signal_message(ai_response))

    async def send_no_valid_setup(self, total_pairs: int, rejected_reasons: list[str], next_scan_minutes: int, rejected_details: list[dict] | None = None) -> None:
        await self.bot.send_admin(no_valid_setup_message(total_pairs, rejected_reasons, next_scan_minutes, rejected_details))
