import json
from pydantic import BaseModel, Field, ValidationError


class Bias(BaseModel):
    D1: str = "neutral"
    H4: str = "neutral"
    H1: str = "neutral"
    M15: str = "neutral"


class Entry(BaseModel):
    type: str = "none"
    zone: str = ""


class Risk(BaseModel):
    stop_loss: str = ""
    take_profit_1: str = ""
    take_profit_2: str = ""
    risk_reward: float = 0


class AIOrderflow(BaseModel):
    bias: str = "insufficient_data"
    confirmation: bool = False
    conflict: bool = False
    score: int = 0
    absorption_signal: str = "none"
    interpretation: str = ""


class AIAnalysis(BaseModel):
    symbol: str
    decision: str = Field(pattern="^(BUY|SELL|WAIT)$")
    confidence: int = Field(ge=0, le=100)
    setup_type: str = "none"
    bias: Bias
    orderflow: AIOrderflow = Field(default_factory=AIOrderflow)
    reason: str = ""
    entry: Entry
    risk: Risk
    invalid_if: str = ""
    broadcast_allowed: bool = False


def parse_ai_response(content: str) -> tuple[dict, str | None]:
    try:
        payload = json.loads(content.strip())
        parsed = AIAnalysis.model_validate(payload)
        return parsed.model_dump(), None
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        return {}, f"invalid_ai_json: {exc}"
