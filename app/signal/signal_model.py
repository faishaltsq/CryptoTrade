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
    orderflow_summary: dict = {}
