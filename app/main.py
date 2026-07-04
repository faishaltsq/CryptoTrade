import asyncio
import json
import os
import subprocess
import sys
from fastapi import Depends, FastAPI, Request
from sqlalchemy.orm import Session
from app.config import get_settings
from app.database import repository
from app.database.session import SessionLocal, get_db, init_db
from app.market_data.provider_diagnostic import run_market_diagnostic
from app.learning.post_trade_reviewer import review_signal
from app.scheduler import run_scan_now, scan_job, scan_state, scheduler_info, start_scheduler, stop_scheduler
from app.telegram.admin_bot import TelegramBot
from app.telegram.callbacks import handle_callback
from app.telegram.commands import command_from_callback, command_keyboard, handle_command, is_admin, pagination_keyboard, signal_list_keyboard
from app.telegram.message_formatter import format_access_denied_message, format_diagnose_provider_message, format_no_setup_message, format_restarting_message, format_scan_result_message, format_signal_review_message
from app.telegram.webhook_manager import setup_public_webhook, stop_ngrok
from app.utils.logger import setup_logging


setup_logging()
app = FastAPI(title="Crypto AI Signal Bot", version="0.1.0")


@app.on_event("startup")
async def startup() -> None:
    init_db()
    enable_auto_broadcast_on_launch()
    start_scheduler()
    await setup_public_webhook()


def enable_auto_broadcast_on_launch() -> None:
    db = SessionLocal()
    try:
        repository.set_setting(db, "auto_broadcast", "true")
    finally:
        db.close()


@app.on_event("shutdown")
async def shutdown() -> None:
    stop_scheduler()
    stop_ngrok()


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/scan")
async def manual_scan() -> dict:
    asyncio.create_task(scan_job())
    return {"status": "queued"}


@app.post("/scan/run")
async def manual_scan_run() -> dict:
    return await run_scan_now()


@app.get("/scan/state")
async def api_scan_state() -> dict:
    return {**scan_state, **scheduler_info()}


@app.get("/status")
async def api_status(db: Session = Depends(get_db)) -> dict:
    settings = get_settings()
    scan = repository.latest_scan(db)
    return {
        "bot": "active",
        "max_pairs": settings.max_pairs,
        "auto_broadcast": settings.auto_broadcast,
        "min_confidence": settings.min_confidence,
        "min_risk_reward": settings.min_risk_reward,
        "auto_ngrok": settings.auto_ngrok,
        "public_base_url": settings.public_base_url,
        "last_scan": row_to_dict(scan) if scan else None,
    }


@app.get("/last_scan")
async def api_last_scan(db: Session = Depends(get_db)) -> dict:
    scan = repository.latest_scan(db)
    return row_to_dict(scan) if scan else {"message": "No scan yet."}


@app.get("/signals")
async def api_signals(limit: int = 10, db: Session = Depends(get_db)) -> list[dict]:
    return [row_to_dict(row) for row in repository.latest_signals(db, limit)]


@app.get("/rejected")
async def api_rejected(limit: int = 20, db: Session = Depends(get_db)) -> list[dict]:
    return [row_to_dict(row) for row in repository.latest_rejected(db, limit)]


@app.get("/orderflow/{symbol}")
async def api_orderflow(symbol: str, limit: int = 10, db: Session = Depends(get_db)) -> list[dict]:
    return [row_to_dict(row) for row in repository.latest_orderflow(db, symbol, limit)]


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request, db: Session = Depends(get_db)) -> dict:
    try:
        update = await request.json()
    except json.JSONDecodeError:
        return {"ok": False, "error": "telegram webhook expects Telegram JSON update; use /scan for manual scan"}
    if not isinstance(update, dict) or not update:
        return {"ok": False, "error": "empty webhook body"}
    bot = TelegramBot()
    if "message" in update:
        message = update["message"]
        chat_id = str(message.get("chat", {}).get("id", ""))
        text = message.get("text", "")
        if not is_admin(chat_id):
            await bot.send_message(chat_id, format_access_denied_message())
            return {"ok": True}
        reply, action = handle_command(db, text)
        await bot.send_admin(reply, keyboard_for_action(action))
        if action == "scan_now":
            asyncio.create_task(run_scan_and_notify(bot))
        if action == "diagnose_market":
            rows = await run_market_diagnostic()
            await bot.send_admin(format_diagnose_provider_message(rows), command_keyboard())
        if action and action.startswith("review_signal:"):
            asyncio.create_task(run_signal_review_and_notify(bot, int(action.split(":", 1)[1])))
        return {"ok": True}
    if "callback_query" in update:
        callback = update["callback_query"]
        chat_id = str(callback.get("message", {}).get("chat", {}).get("id", ""))
        if not is_admin(chat_id):
            await bot.send_message(chat_id, format_access_denied_message())
            return {"ok": True}
        callback_data = callback.get("data", "")
        if callback_data == "restart_confirm":
            await bot.send_admin(format_restarting_message())
            await asyncio.sleep(0.5)
            try:
                stop_ngrok()
            except Exception:
                pass
            subprocess.Popen([sys.executable] + sys.argv, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0)
            os._exit(0)
            return {"ok": True}
        command = command_from_callback(callback_data)
        if command:
            reply, action = handle_command(db, command)
            await bot.send_admin(reply, keyboard_for_action(action))
            if action == "scan_now":
                asyncio.create_task(run_scan_and_notify(bot))
            if action == "diagnose_market":
                rows = await run_market_diagnostic()
                await bot.send_admin(format_diagnose_provider_message(rows), command_keyboard())
            if action and action.startswith("review_signal:"):
                asyncio.create_task(run_signal_review_and_notify(bot, int(action.split(":", 1)[1])))
            return {"ok": True}
        reply = await handle_callback(db, callback_data, bot)
        await bot.send_admin(reply, command_keyboard())
        return {"ok": True}
    return {"ok": True}


async def run_scan_and_notify(bot: TelegramBot) -> None:
    result = await run_scan_now()
    scan_result = result.get("result", result)
    message = format_scan_result_message(scan_result) if scan_result.get("valid_signals", 0) else format_no_setup_message(scan_result)
    await bot.send_admin(message, command_keyboard())


async def run_signal_review_and_notify(bot: TelegramBot, signal_id: int) -> None:
    db = SessionLocal()
    try:
        review, error = await review_signal(db, signal_id)
        await bot.send_admin(format_signal_review_message(review, error), command_keyboard())
    finally:
        db.close()


def keyboard_for_action(action: str | None) -> dict:
    if not action:
        return command_keyboard()
    if action == "restart_prompt":
        return {"inline_keyboard": [[{"text": "Yes, Restart", "callback_data": "restart_confirm"}, {"text": "Cancel", "callback_data": "cmd:help"}]]}
    if action == "settings":
        buttons = command_keyboard().get("inline_keyboard", [])
        buttons.append([{"text": "Restart Server", "callback_data": "cmd:restart"}])
        return {"inline_keyboard": buttons}
    if action.startswith("keyboard:"):
        parts = action.split(":")
        kind, page, total = parts[1], int(parts[2]), int(parts[3])
        if kind == "signals":
            first_id = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else None
            return signal_list_keyboard(page, total, first_id)
        return pagination_keyboard(kind, page, total)
    return command_keyboard()


def row_to_dict(row) -> dict:
    data = {column.name: getattr(row, column.name) for column in row.__table__.columns}
    for key, value in list(data.items()):
        if key.endswith("_json") and isinstance(value, str):
            try:
                data[key] = json.loads(value)
            except json.JSONDecodeError:
                pass
        elif hasattr(value, "isoformat"):
            data[key] = value.isoformat()
    return data
