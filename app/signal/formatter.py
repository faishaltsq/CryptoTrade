from collections import Counter
from app.telegram.message_formatter import format_signal_candidate_admin_message


def icon(decision: str) -> str:
    return "🟢" if decision == "BUY" else "🔴" if decision == "SELL" else "⚪"


def admin_signal_message(signal_id: int, ai: dict) -> str:
    return format_signal_candidate_admin_message(ai) + signal_footer(ai, signal_id)


def channel_signal_message(ai: dict) -> str:
    return format_signal_candidate_admin_message(ai) + signal_footer(ai, ai.get("signal_id"))


def signal_footer(ai: dict, signal_id: int | None = None) -> str:
    validation = ai.get("validation_status", "")
    reason = ai.get("validation_reason", "")
    suffix = f"\n\nSignal ID: <code>{signal_id}</code>" if signal_id else ""
    if validation:
        suffix += f"\nValidation: <b>{validation}</b>"
    if reason and reason != "valid":
        suffix += f"\nValidation Reason: <code>{reason}</code>"
    return suffix


def no_valid_setup_message(total_pairs: int, rejected_reasons: list[str], next_scan_minutes: int, rejected_details: list[dict] | None = None) -> str:
    counts = Counter(rejected_reasons)
    rejected = "\n".join(f"- {count} {reason}" for reason, count in counts.most_common()) or "- 0 rejected"
    candle_rows = []
    for item in rejected_details or []:
        if item.get("reason") != "insufficient_candle_data":
            continue
        counts_by_tf = item.get("candles", {}) or {}
        candle_rows.append(f"- {item.get('symbol')}: M15={counts_by_tf.get('M15', 0)}, H1={counts_by_tf.get('H1', 0)}, H4={counts_by_tf.get('H4', 0)}, D1={counts_by_tf.get('D1', 0)}")
        if len(candle_rows) >= 8:
            break
    candle_section = "\n\nInsufficient candle examples:\n" + "\n".join(candle_rows) if candle_rows else ""
    return f"""No valid setup saat ini.

Scanned:
Top {total_pairs} USDT perpetual pairs

Rejected:
{rejected}
{candle_section}

Next scan:
{next_scan_minutes} minutes"""
