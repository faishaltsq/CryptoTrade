from collections import Counter


def icon(decision: str) -> str:
    return "🟢" if decision == "BUY" else "🔴" if decision == "SELL" else "⚪"


def admin_signal_message(signal_id: int, ai: dict) -> str:
    risk = ai.get("risk", {}) or {}
    entry = ai.get("entry", {}) or {}
    bias = ai.get("bias", {}) or {}
    return f"""{icon(ai.get('decision'))} [{ai.get('symbol')}] - {ai.get('decision')} Candidate

Decision: {ai.get('decision')}
Confidence: {ai.get('confidence')}%
Setup: {ai.get('setup_type')}
RR: 1:{risk.get('risk_reward')}

Bias:
D1: {bias.get('D1')}
H4: {bias.get('H4')}
H1: {bias.get('H1')}
M15: {bias.get('M15')}

Entry:
{entry.get('zone')}

Stop Loss:
{risk.get('stop_loss')}

Take Profit:
TP1: {risk.get('take_profit_1')}
TP2: {risk.get('take_profit_2')}

Reason:
{ai.get('reason')}

Invalid if:
{ai.get('invalid_if')}

Signal ID: {signal_id}"""


def channel_signal_message(ai: dict) -> str:
    risk = ai.get("risk", {}) or {}
    entry = ai.get("entry", {}) or {}
    decision = ai.get("decision")
    order_type = (entry.get("type") or "limit").upper()
    return f"""{icon(decision)} {ai.get('symbol')} - {decision} {order_type}

Entry Zone:
{entry.get('zone')}

Stop Loss:
{risk.get('stop_loss')}

Take Profit:
TP1: {risk.get('take_profit_1')}
TP2: {risk.get('take_profit_2')}

Confidence:
{ai.get('confidence')}%

Setup:
{ai.get('setup_type')}

Invalid if:
{ai.get('invalid_if')}

Risk reminder:
Gunakan risk management masing-masing. Signal ini bukan jaminan profit."""


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
