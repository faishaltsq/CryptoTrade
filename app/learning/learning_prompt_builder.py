import json
from typing import Any

from app.config import get_settings


REVIEW_SYSTEM_PROMPT = """You are a crypto signal performance reviewer.

Review this completed signal using original market context, AI decision, final confidence, orderflow summary, derivatives data, risk plan, actual outcome, max favorable excursion, max adverse excursion, duration, and active lessons used at the time.

Do not make excuses. Be objective and conservative.

Classify result_quality as one of: good_signal, valid_loss, avoidable_loss, bad_signal, inconclusive.

Identify main_failure_reason using one of these when applicable: late_entry, weak_trend, poor_risk_reward, orderflow_conflict, spread_or_liquidity_issue, overextended_price, false_breakout, volatility_spike, bad_market_regime, funding_or_oi_warning, low_volume_pair, resistance_support_too_close, insufficient_data, reasonable_loss_despite_valid_setup.

Return strict JSON only. Do not return markdown.

Output JSON:
{"result_quality":"good_signal | valid_loss | avoidable_loss | bad_signal | inconclusive","main_failure_reason":"","warning_signs":[],"what_should_have_been_checked":[],"recommended_rule_adjustments":[],"confidence_penalty_conditions":[],"confidence_boost_conditions":[],"future_lesson":"","should_create_strategy_lesson":true,"suggested_lesson":{"lesson_type":"avoid_condition | confidence_penalty | confidence_boost | filter_rule | risk_adjustment | prompt_context | warning_note","lesson_text":"","affected_condition":"","confidence_adjustment":0,"filter_rule":{}}}"""


def build_review_messages(payload: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, separators=(",", ":"), default=str)},
    ]


def learning_context(active_lessons: list[Any], performance: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    lessons = [getattr(x, "lesson_text", str(x)) for x in active_lessons[: settings.max_active_lessons_in_prompt]]
    return {
        "active_lessons": lessons,
        "recent_performance_summary": {
            "lookback_days": settings.performance_lookback_days,
            "total_signals": performance.get("total_signals", 0),
            "winrate": performance.get("winrate", 0),
            "best_conditions": performance.get("best_conditions", []),
            "worst_conditions": performance.get("worst_conditions", []),
        },
    }
