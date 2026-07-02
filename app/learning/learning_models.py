RESULT_QUALITIES = {"good_signal", "valid_loss", "avoidable_loss", "bad_signal", "inconclusive"}
LESSON_TYPES = {"avoid_condition", "confidence_penalty", "confidence_boost", "filter_rule", "risk_adjustment", "prompt_context", "warning_note"}
LESSON_STATUSES = {"suggested", "approved", "rejected", "active", "disabled"}
FINAL_OUTCOMES = {"hit_tp1", "hit_tp2", "hit_sl", "break_even", "expired", "invalidated", "manually_closed"}


def normalize_review(data: dict) -> dict:
    quality = data.get("result_quality", "inconclusive")
    if quality not in RESULT_QUALITIES:
        quality = "inconclusive"
    lesson = data.get("suggested_lesson") or {}
    lesson_type = lesson.get("lesson_type", "warning_note")
    if lesson_type not in LESSON_TYPES:
        lesson_type = "warning_note"
    lesson["lesson_type"] = lesson_type
    lesson["confidence_adjustment"] = int(lesson.get("confidence_adjustment") or 0)
    data["result_quality"] = quality
    data["suggested_lesson"] = lesson
    data["warning_signs"] = data.get("warning_signs") or []
    data["what_should_have_been_checked"] = data.get("what_should_have_been_checked") or []
    data["recommended_rule_adjustments"] = data.get("recommended_rule_adjustments") or []
    data["confidence_penalty_conditions"] = data.get("confidence_penalty_conditions") or []
    data["confidence_boost_conditions"] = data.get("confidence_boost_conditions") or []
    return data
