import json
from typing import Any


def apply_adaptive_scoring(candidate: dict[str, Any], lessons: list[Any], performance: dict[str, Any]) -> dict[str, Any]:
    adjustment = 0
    applied = []
    reject_reason = ""
    rr = float((candidate.get("risk_context", {}) or {}).get("estimated_risk_reward") or 0)
    orderflow = candidate.get("orderflow", {}) or {}
    for lesson in lessons:
        if not lesson_applies(candidate, lesson):
            continue
        lesson_type = getattr(lesson, "lesson_type", "")
        amount = int(getattr(lesson, "confidence_adjustment", 0) or 0)
        if lesson_type in {"avoid_condition", "filter_rule"}:
            reject_reason = getattr(lesson, "affected_condition", "active_lesson_filter") or "active_lesson_filter"
            applied.append(lesson_payload(lesson))
            break
        if lesson_type == "confidence_penalty":
            adjustment += min(0, amount) if amount < 0 else -abs(amount or 5)
            applied.append(lesson_payload(lesson))
        if lesson_type == "confidence_boost" and rr >= 2 and not orderflow.get("orderflow_conflict") and orderflow.get("orderflow_bias") != "insufficient_data":
            adjustment += max(0, amount)
            applied.append(lesson_payload(lesson))
    adjustment = max(-25, min(10, adjustment))
    if reject_reason:
        candidate["adaptive_reject_reason"] = reject_reason
    candidate["adaptive_scoring"] = {"confidence_adjustment": adjustment, "applied_lessons": applied, "reject_reason": reject_reason}
    return candidate


def lesson_applies(candidate: dict[str, Any], lesson: Any) -> bool:
    text = (getattr(lesson, "affected_condition", "") + " " + getattr(lesson, "lesson_text", "")).lower()
    direction = candidate.get("candidate_direction", "").lower()
    if direction and direction in text:
        return True
    orderflow = candidate.get("orderflow", {}) or {}
    if "orderflow" in text and orderflow.get("orderflow_conflict"):
        return True
    if "low-volume" in text or "low volume" in text:
        return int((candidate.get("derivatives_data", {}) or {}).get("volume_24h_rank") or 0) > 50
    rule = json.loads(getattr(lesson, "filter_rule_json", "{}") or "{}")
    if rule.get("direction") and str(rule.get("direction")).upper() != candidate.get("candidate_direction"):
        return False
    return not rule or bool(text.strip())


def lesson_payload(lesson: Any) -> dict[str, Any]:
    return {"id": getattr(lesson, "id", 0), "type": getattr(lesson, "lesson_type", ""), "text": getattr(lesson, "lesson_text", ""), "adjustment": getattr(lesson, "confidence_adjustment", 0)}
