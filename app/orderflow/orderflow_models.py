from pydantic import BaseModel, Field
from app.utils.time import iso_utc


class OrderflowSummary(BaseModel):
    symbol: str
    window: str = "1m"
    timestamp: str = Field(default_factory=iso_utc)
    price: float = 0.0
    buy_volume: float = 0.0
    sell_volume: float = 0.0
    volume_delta: float = 0.0
    cumulative_volume_delta: float = 0.0
    delta_ratio: float = 0.0
    trade_count: int = 0
    trade_intensity: str = "low"
    average_trade_size: float = 0.0
    large_trade_count: int = 0
    best_bid: float = 0.0
    best_ask: float = 0.0
    spread: float = 0.0
    bid_depth: float = 0.0
    ask_depth: float = 0.0
    orderbook_imbalance: float = 0.0
    liquidity_wall_side: str = "none"
    liquidity_wall_price: float = 0.0
    liquidity_pull_detected: bool = False
    liquidation_buy_notional: float = 0.0
    liquidation_sell_notional: float = 0.0
    liquidation_spike_detected: bool = False
    open_interest: float = 0.0
    open_interest_change: float = 0.0
    absorption_signal: str = "none"
    orderflow_bias: str = "insufficient_data"
    orderflow_conflict: bool = False
    orderflow_score: int = 0
    flow_interpretation: str = "Insufficient realtime orderflow data."
