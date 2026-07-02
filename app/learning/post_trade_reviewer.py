from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.config import get_settings
from app.database import repository
from app.learning.learning_models import normalize_review
from app.learning.learning_prompt_builder import build_review_messages
from app.learning.lesson_manager import create_lesson_from_review


logger = logging.getLogger(__name__)


async def review_signal(db, signal_id: int) -> tuple[Any | None, str | None]:
    settings = get_settings()
    signal = repository.get_signal_by_id(db, signal_id)
    outcome = repository.get_signal_outcome(db, signal_id)
    if not signal or not outcome:
        return None, "signal_or_outcome_not_found"
    if not settings.deepseek_api_key:
        repository.mark_signal_review_failed(db, signal_id, "missing_deepseek_api_key")
        return None, "missing_deepseek_api_key"
    payload = build_review_payload(signal, outcome)
    headers = {"Authorization": f"Bearer {settings.deepseek_api_key}", "Content-Type": "application/json"}
    body = {"model": settings.learning_review_model, "messages": build_review_messages(payload), "temperature": 0.1, "response_format": {"type": "json_object"}}
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post("https://api.deepseek.com/chat/completions", json=body, headers=headers)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        review = normalize_review(json.loads(content))
        row = repository.create_signal_review(db, signal_id, review, outcome.result)
        create_lesson_from_review(db, signal_id, review)
        return row, None
    except Exception as exc:  # noqa: BLE001
        logger.exception("Post-trade review failed signal_id=%s", signal_id)
        repository.mark_signal_review_failed(db, signal_id, str(exc))
        return None, str(exc)


async def review_pending_completed(db, limit: int = 10) -> dict[str, Any]:
    settings = get_settings()
    if not (settings.enable_signal_learning and settings.enable_auto_review):
        return {"status": "disabled", "reviewed": 0, "failed": 0}
    reviewed = 0
    failed = 0
    for signal in repository.get_closed_unreviewed_signals(db, limit):
        _, error = await review_signal(db, signal.id)
        if error:
            failed += 1
        else:
            reviewed += 1
    return {"status": "completed", "reviewed": reviewed, "failed": failed}


def build_review_payload(signal, outcome) -> dict[str, Any]:
    ai = safe_json(signal.ai_response_json, {})
    return {
        "signal": {
            "signal_id": signal.id,
            "symbol": signal.symbol,
            "decision": signal.decision,
            "confidence": signal.confidence,
            "market_regime": signal.market_regime,
            "analysis_method_used": safe_json(signal.analysis_method_json, []),
            "entry_zone": signal.entry_zone,
            "stop_loss": signal.stop_loss,
            "take_profit_1": signal.take_profit_1,
            "take_profit_2": signal.take_profit_2,
            "risk_reward": signal.risk_reward,
            "reason": signal.reason,
        },
        "original_context": {
            "timeframes": safe_json(ai.get("timeframes_json", "{}"), {}) if isinstance(ai, dict) else {},
            "orderflow": safe_json(signal.orderflow_summary_json, {}),
            "derivatives_data": safe_json(signal.derivatives_summary_json, {}),
            "risk_context": ai.get("risk", {}) if isinstance(ai, dict) else {},
        },
        "outcome": {
            "result": outcome.result,
            "close_reason": outcome.close_reason,
            "duration_minutes": outcome.duration_minutes,
            "max_favorable_excursion": outcome.max_favorable_excursion,
            "max_adverse_excursion": outcome.max_adverse_excursion,
            "hit_tp1": outcome.result in {"hit_tp1", "hit_tp2"},
            "hit_tp2": outcome.result == "hit_tp2",
            "hit_sl": outcome.result == "hit_sl",
        },
        "active_lessons_at_signal_time": safe_json(signal.active_lessons_json, []),
    }


def safe_json(value, default):
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value or "")
    except Exception:  # noqa: BLE001
        return default
