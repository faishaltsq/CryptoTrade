from __future__ import annotations

from app.config import get_settings
from app.database import repository


def create_lesson_from_review(db, signal_id: int, review: dict):
    if not review.get("should_create_strategy_lesson"):
        return None
    quality = review.get("result_quality")
    if quality == "inconclusive":
        return None
    suggested = review.get("suggested_lesson") or {}
    if not suggested.get("lesson_text") and review.get("future_lesson"):
        suggested["lesson_text"] = review["future_lesson"]
        suggested.setdefault("lesson_type", "warning_note")
    if not suggested.get("lesson_text"):
        return None
    if quality == "valid_loss" and suggested.get("lesson_type") not in {"warning_note", "prompt_context"}:
        suggested["lesson_type"] = "warning_note"
    if quality == "good_signal" and suggested.get("lesson_type") != "confidence_boost":
        return None
    suggested["evidence_count"] = max(1, int(suggested.get("evidence_count") or 1))
    return repository.create_strategy_lesson(db, suggested, signal_id)


def approve_lesson(db, lesson_id: int):
    return repository.update_lesson_status(db, lesson_id, "approved")


def reject_lesson(db, lesson_id: int):
    return repository.update_lesson_status(db, lesson_id, "rejected")


def disable_lesson(db, lesson_id: int):
    return repository.update_lesson_status(db, lesson_id, "disabled")


def active_lessons_for_prompt(db):
    settings = get_settings()
    return repository.get_active_lessons(db, settings.max_active_lessons_in_prompt)
