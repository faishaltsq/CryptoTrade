import asyncio
import logging
from app.utils.time import iso_utc
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.config import get_settings
from app.orderflow.orderflow_aggregator import orderflow_aggregator
from app.scanner import scanner


logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()
scan_lock = asyncio.Lock()
scan_state = {"running": False, "last_started": None, "last_finished": None, "last_result": None, "last_error": None}


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
        await run_scan_now()
    except Exception:  # noqa: BLE001
        logger.exception("Scheduled scan failed")


def start_scheduler() -> None:
    settings = get_settings()
    if not scheduler.running:
        scheduler.add_job(scan_job, "interval", minutes=settings.scan_interval_minutes, id="market_scan", replace_existing=True, next_run_time=None)
        scheduler.start()
        logger.info("Scheduler started interval=%s minutes", settings.scan_interval_minutes)


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
    if orderflow_aggregator.provider:
        asyncio.create_task(orderflow_aggregator.provider.stop())
