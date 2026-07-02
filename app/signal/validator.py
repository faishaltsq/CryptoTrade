from app.config import get_settings
from app.orderflow.volume_delta import conflicts_with_direction


def validate_for_broadcast(ai_response: dict) -> tuple[bool, str]:
    settings = get_settings()
    if ai_response.get("decision") not in {"BUY", "SELL"}:
        return False, "decision_wait"
    if int(ai_response.get("confidence") or 0) < settings.min_confidence:
        return False, "confidence_below_minimum"
    risk = ai_response.get("risk", {}) or {}
    if float(risk.get("risk_reward") or 0) < settings.min_risk_reward:
        return False, "risk_reward_below_minimum"
    if not ai_response.get("broadcast_allowed"):
        return False, "ai_broadcast_not_allowed"
    if (ai_response.get("orderflow") or {}).get("conflict") is True:
        return False, "orderflow_conflict"
    required = [risk.get("entry_zone"), risk.get("stop_loss"), risk.get("take_profit_1"), risk.get("take_profit_2")]
    if any(not x for x in required):
        return False, "missing_entry_sl_tp"
    orderflow = ai_response.get("orderflow") or {}
    if orderflow.get("bias") == "insufficient_data":
        return False, "orderflow_insufficient_data"
    if orderflow and conflicts_with_direction(ai_response.get("decision", ""), orderflow):
        return False, "orderflow_conflict"
    return True, "valid"
