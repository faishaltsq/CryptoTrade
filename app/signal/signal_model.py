from pydantic import BaseModel


class SignalDecision(BaseModel):
    symbol: str
    decision: str
    confidence: int
    setup_type: str
    entry_zone: str
    stop_loss: str
    take_profit_1: str
    take_profit_2: str
    risk_reward: float
    reason: str
    invalid_if: str
    broadcast_allowed: bool
    technical_score: int = 0
    orderflow_score: int = 0
    risk_score: int = 0
    final_confidence: int = 0
    orderflow_bias: str = "insufficient_data"
    orderflow_conflict: bool = False
    absorption_signal: str = "none"
    orderflow_summary: dict = {}
