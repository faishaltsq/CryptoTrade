import logging
import httpx
from app.ai.prompt_builder import build_messages
from app.ai.response_parser import parse_ai_response
from app.config import get_settings


logger = logging.getLogger(__name__)


class DeepSeekClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def analyze(self, market_summary: dict) -> tuple[dict, str | None]:
        if not self.settings.deepseek_api_key:
            return fallback_wait(market_summary), "missing_deepseek_api_key"
        headers = {"Authorization": f"Bearer {self.settings.deepseek_api_key}", "Content-Type": "application/json"}
        body = {"model": "deepseek-chat", "messages": build_messages(market_summary), "temperature": 0.1, "response_format": {"type": "json_object"}}
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post("https://api.deepseek.com/chat/completions", json=body, headers=headers)
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                return parse_ai_response(content)
        except Exception as exc:  # noqa: BLE001
            logger.exception("DeepSeek request failed")
            return fallback_wait(market_summary), f"deepseek_error: {exc}"


def fallback_wait(market_summary: dict) -> dict:
    orderflow = market_summary.get("orderflow", {}) or {}
    return {
        "symbol": market_summary.get("symbol", ""),
        "decision": "WAIT",
        "confidence": 0,
        "setup_type": "none",
        "bias": {"D1": "neutral", "H4": "neutral", "H1": "neutral", "M15": "neutral"},
        "reason": "AI validation unavailable.",
        "entry": {"type": "none", "zone": ""},
        "risk": {"stop_loss": "", "take_profit_1": "", "take_profit_2": "", "risk_reward": 0},
        "invalid_if": "",
        "broadcast_allowed": False,
        "orderflow": {
            "bias": orderflow.get("orderflow_bias", "insufficient_data"),
            "confirmation": False,
            "conflict": bool(orderflow.get("orderflow_conflict", False)),
            "score": int(orderflow.get("orderflow_score", 0) or 0),
            "absorption_signal": orderflow.get("absorption_signal", "none"),
            "interpretation": orderflow.get("flow_interpretation", "AI validation unavailable."),
        },
    }
