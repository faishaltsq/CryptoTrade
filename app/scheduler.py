import asyncio
import logging
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from app.utils.time import iso_utc
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.config import get_settings
from app.database import repository
from app.database.session import SessionLocal
from app.learning.outcome_tracker import track_pending_outcomes
from app.learning.post_trade_reviewer import review_pending_completed
from app.orderflow.orderflow_aggregator import orderflow_aggregator
from app.scanner import scanner
from app.telegram.admin_bot import TelegramBot
from app.telegram.message_formatter import format_daily_signal_recap_message


logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()
scan_lock = asyncio.Lock()
scan_state = {"running": False, "last_started": None, "last_finished": None, "last_result": None, "last_error": None}


def scheduler_info() -> dict:
    job = scheduler.get_job("market_scan")
    next_run = job.next_run_time.isoformat() if job and job.next_run_time else None
    return {"scheduler_running": scheduler.running, "next_run_time": next_run}


async def run_scan_now() -> dict:
    if scan_lock.locked():
        return {"status": "already_running", **scan_state}
    async with scan_lock:
        scan_state.update({"running": True, "last_started": iso_utc(), "last_error": None})
        try:
            result = await scanner.scan()
            scan_state.update({"running": False, "last_finished": iso_utc(), "last_result": result})
            logger.info("Scan completed: %s", result)
            return {"status": "completed", "result": result}
        except Exception as exc:  # noqa: BLE001
            scan_state.update({"running": False, "last_finished": iso_utc(), "last_error": str(exc)})
            logger.exception("Scan failed")
            return {"status": "failed", "error": str(exc)}


async def scan_job() -> None:
    try:
        await run_outcome_tracker()
        await run_auto_review()
        await run_scan_now()
        await run_outcome_tracker()
        await run_auto_review()
    except Exception:  # noqa: BLE001
        logger.exception("Scheduled scan failed")


async def run_outcome_tracker() -> dict:
    db = SessionLocal()
    try:
        result = await track_pending_outcomes(db)
        logger.info("Outcome tracking completed: %s", result)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("Outcome tracking failed")
        return {"status": "failed", "error": str(exc)}
    finally:
        db.close()


async def run_auto_review() -> dict:
    db = SessionLocal()
    try:
        result = await review_pending_completed(db)
        logger.info("Auto review completed: %s", result)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("Auto review failed")
        return {"status": "failed", "error": str(exc)}
    finally:
        db.close()


def start_scheduler() -> None:
    settings = get_settings()
    db = SessionLocal()
    try:
        db_interval = repository.get_setting(db, "scan_interval_minutes", "")
        interval = int(db_interval) if db_interval and db_interval.isdigit() and int(db_interval) >= 1 else settings.scan_interval_minutes
    finally:
        db.close()
    if not scheduler.running:
        scheduler.add_job(scan_job, "interval", minutes=interval, id="market_scan", replace_existing=True, next_run_time=datetime.now(timezone.utc))
        scheduler.add_job(daily_signal_recap_job, "cron", hour=21, minute=0, timezone=ZoneInfo("Asia/Jakarta"), id="daily_signal_recap", replace_existing=True)
        scheduler.start()
        logger.info("Scheduler started interval=%s minutes", interval)


async def daily_signal_recap_job() -> None:
    db = SessionLocal()
    try:
        start, end, label = today_wib_range()
        message = format_daily_signal_recap_message(repository.get_signals_between(db, start, end), label)
        bot = TelegramBot()
        await bot.send_admin(message)
        await bot.send_channel(message)
        logger.info("Daily signal recap sent label=%s", label)
    except Exception:  # noqa: BLE001
        logger.exception("Daily signal recap failed")
    finally:
        db.close()


def today_wib_range() -> tuple[datetime, datetime, str]:
    wib = ZoneInfo("Asia/Jakarta")
    now = datetime.now(wib)
    start_wib = datetime.combine(now.date(), time.min, tzinfo=wib)
    end_wib = start_wib + timedelta(days=1)
    return start_wib.astimezone(timezone.utc), end_wib.astimezone(timezone.utc), now.strftime("%d %b %Y WIB")


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
    if orderflow_aggregator.provider:
        asyncio.create_task(orderflow_aggregator.provider.stop())
