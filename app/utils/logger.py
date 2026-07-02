import logging
import sys
from app.config import get_settings


SENSITIVE_KEYS = ("api_key", "token", "secret", "authorization")


class SecretFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = str(record.getMessage())
        for key in SENSITIVE_KEYS:
            if key in msg.lower():
                record.msg = "Sensitive value redacted from log message"
                record.args = ()
                break
        return True


def setup_logging() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    secret_filter = SecretFilter()
    logging.getLogger().addFilter(secret_filter)
    for handler in logging.getLogger().handlers:
        handler.addFilter(secret_filter)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
