import json
from pydantic import BaseModel, Field, ValidationError


class MarketSummary(BaseModel):
    higher_timeframe_bias: str = "neutral"
    lower_timeframe_context: str = "neutral"
    market_regime: str = "unclear"
    main_reason: str = ""


class AIOrderflow(BaseModel):
    bias: str = "insufficient_data"
    confirmation: bool = False
    conflict: bool = False
    interpretation: str = ""


class Risk(BaseModel):
    entry_type: str = "none"
    entry_zone: str = ""
    stop_loss: str = ""
    take_profit_1: str = ""
    take_profit_2: str = ""
    risk_reward: float = 0


class AIAnalysis(BaseModel):
    symbol: str
    decision: str = Field(pattern="^(BUY|SELL|WAIT)$")
    confidence: int = Field(ge=0, le=100)
    analysis_method_used: list[str] = Field(default_factory=list)
    market_summary: MarketSummary = Field(default_factory=MarketSummary)
    setup_type: str = "no_trade"
    orderflow: AIOrderflow = Field(default_factory=AIOrderflow)
    reason: str = ""
    risk: Risk = Field(default_factory=Risk)
    invalid_if: str = ""
    broadcast_allowed: bool = False


def parse_ai_response(content: str) -> tuple[dict, str | None]:
    try:
        payload = json.loads(content.strip())
        parsed = AIAnalysis.model_validate(payload)
        return parsed.model_dump(), None
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        return {}, f"invalid_ai_json: {exc}"
