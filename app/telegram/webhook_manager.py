import logging
import httpx
from pyngrok import conf, ngrok
from app.config import get_settings


logger = logging.getLogger(__name__)
ngrok_tunnel = None
public_url = ""


async def setup_public_webhook() -> str:
    settings = get_settings()
    url = settings.public_base_url.strip().rstrip("/")
    if settings.auto_ngrok:
        url = start_ngrok(settings.app_port)
    if not url:
        logger.info("Telegram webhook auto setup skipped: PUBLIC_BASE_URL empty and AUTO_NGROK=false")
        return ""
    if not settings.telegram_bot_token:
        logger.warning("Telegram webhook auto setup skipped: missing TELEGRAM_BOT_TOKEN")
        return url
    webhook_url = f"{url}/telegram/webhook"
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(f"https://api.telegram.org/bot{settings.telegram_bot_token}/setWebhook", params={"url": webhook_url})
        response.raise_for_status()
    logger.info("Telegram webhook set to %s", webhook_url)
    return webhook_url


def start_ngrok(port: int) -> str:
    global ngrok_tunnel, public_url
    if public_url:
        return public_url
    settings = get_settings()
    if settings.ngrok_authtoken:
        conf.get_default().auth_token = settings.ngrok_authtoken
    ngrok_tunnel = ngrok.connect(addr=port, proto="http")
    public_url = str(ngrok_tunnel.public_url).rstrip("/")
    logger.info("Ngrok tunnel started %s -> http://localhost:%s", public_url, port)
    return public_url


def stop_ngrok() -> None:
    global ngrok_tunnel, public_url
    if ngrok_tunnel:
        try:
            ngrok.disconnect(ngrok_tunnel.public_url)
            ngrok.kill()
            logger.info("Ngrok tunnel stopped")
        except Exception:  # noqa: BLE001
            logger.exception("Ngrok shutdown failed")
    ngrok_tunnel = None
    public_url = ""
