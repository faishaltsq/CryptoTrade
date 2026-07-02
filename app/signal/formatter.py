from collections import Counter
from app.telegram.message_formatter import format_signal_broadcast_channel_message, format_signal_candidate_admin_message


def icon(decision: str) -> str:
    return "🟢" if decision == "BUY" else "🔴" if decision == "SELL" else "⚪"


def admin_signal_message(signal_id: int, ai: dict) -> str:
    return format_signal_candidate_admin_message(ai) + f"\n\nSignal ID: <code>{signal_id}</code>"


def channel_signal_message(ai: dict) -> str:
    return format_signal_broadcast_channel_message(ai)


def no_valid_setup_message(total_pairs: int, rejected_reasons: list[str], next_scan_minutes: int) -> str:
    counts = Counter(rejected_reasons)
    rejected = "\n".join(f"- {count} {reason}" for reason, count in counts.most_common()) or "- 0 rejected"
    return f"""No valid setup saat ini.

Scanned:
Top {total_pairs} USDT perpetual pairs

Rejected:
{rejected}

Next scan:
{next_scan_minutes} minutes"""
