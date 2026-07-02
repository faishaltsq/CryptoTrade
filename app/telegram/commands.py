from sqlalchemy.orm import Session
from app.config import get_settings
from app.database import repository


HELP_TEXT = """Commands:
/start
/status
/scan_now
/pairs
/top_volume
/signals
/waiting
/settings
/set_confidence <value>
/set_rr <value>
/broadcast_on
/broadcast_off
/last_scan
/diagnose_market
/help"""


COMMAND_CALLBACKS = {
    "status": "/status",
    "scan_now": "/scan_now",
    "pairs": "/pairs",
    "top_volume": "/top_volume",
    "signals": "/signals",
    "waiting": "/waiting",
    "settings": "/settings",
    "broadcast_on": "/broadcast_on",
    "broadcast_off": "/broadcast_off",
    "last_scan": "/last_scan",
    "diagnose_market": "/diagnose_market",
    "help": "/help",
}


def command_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "Status", "callback_data": "cmd:status"}, {"text": "Scan Now", "callback_data": "cmd:scan_now"}],
            [{"text": "Pairs", "callback_data": "cmd:pairs"}, {"text": "Top Volume", "callback_data": "cmd:top_volume"}],
            [{"text": "Signals", "callback_data": "cmd:signals"}, {"text": "Waiting", "callback_data": "cmd:waiting"}],
            [{"text": "Settings", "callback_data": "cmd:settings"}, {"text": "Last Scan", "callback_data": "cmd:last_scan"}],
            [{"text": "Broadcast ON", "callback_data": "cmd:broadcast_on"}, {"text": "Broadcast OFF", "callback_data": "cmd:broadcast_off"}],
            [{"text": "Diagnose Market", "callback_data": "cmd:diagnose_market"}, {"text": "Help", "callback_data": "cmd:help"}],
        ]
    }


def command_from_callback(data: str) -> str | None:
    if not data.startswith("cmd:"):
        return None
    return COMMAND_CALLBACKS.get(data.split(":", 1)[1])


def is_admin(chat_id: str) -> bool:
    return str(chat_id) == str(get_settings().telegram_admin_chat_id)


def handle_command(db: Session, text: str) -> tuple[str, str | None]:
    settings = get_settings()
    parts = text.strip().split()
    cmd = parts[0] if parts else "/help"
    if cmd in {"/start", "/help"}:
        return HELP_TEXT, None
    if cmd == "/status":
        scan = repository.latest_scan(db)
        auto = repository.get_setting(db, "auto_broadcast", str(settings.auto_broadcast))
        min_conf = repository.get_setting(db, "min_confidence", str(settings.min_confidence))
        min_rr = repository.get_setting(db, "min_risk_reward", str(settings.min_risk_reward))
        return f"Bot active\nPairs: {settings.max_pairs}\nAuto broadcast: {auto}\nMin confidence: {min_conf}\nMin RR: {min_rr}\nLast scan: {scan.timestamp if scan else 'never'}", None
    if cmd == "/scan_now":
        return "Manual scan queued.", "scan_now"
    if cmd in {"/pairs", "/top_volume"}:
        scan = repository.latest_scan(db)
        return scan.summary_json if scan else "No scan yet.", None
    if cmd == "/signals":
        rows = repository.latest_signals(db)
        return "\n".join(f"#{r.id} {r.symbol} {r.decision} {r.confidence}% RR {r.risk_reward}" for r in rows) or "No signals.", None
    if cmd == "/waiting":
        rows = repository.waiting_signals(db)
        return "\n".join(f"#{r.id} {r.symbol} WAIT {r.reason[:80]}" for r in rows) or "No waiting setups.", None
    if cmd == "/settings":
        return f"MIN_CONFIDENCE={repository.get_setting(db, 'min_confidence', str(settings.min_confidence))}\nMIN_RISK_REWARD={repository.get_setting(db, 'min_risk_reward', str(settings.min_risk_reward))}\nAUTO_BROADCAST={repository.get_setting(db, 'auto_broadcast', str(settings.auto_broadcast))}", None
    if cmd == "/broadcast_on":
        repository.set_setting(db, "auto_broadcast", "true")
        return "Auto broadcast on.", None
    if cmd == "/broadcast_off":
        repository.set_setting(db, "auto_broadcast", "false")
        return "Auto broadcast off.", None
    if cmd == "/set_confidence" and len(parts) == 2:
        repository.set_setting(db, "min_confidence", parts[1])
        return f"Min confidence set to {parts[1]}", None
    if cmd == "/set_rr" and len(parts) == 2:
        repository.set_setting(db, "min_risk_reward", parts[1])
        return f"Min RR set to {parts[1]}", None
    if cmd == "/last_scan":
        scan = repository.latest_scan(db)
        return scan.summary_json if scan else "No scan yet.", None
    if cmd in {"/diagnose_market", "/diagnose_binance"}:
        return "Running market provider diagnostic...", "diagnose_market"
    return "Unknown command. Use /help", None
