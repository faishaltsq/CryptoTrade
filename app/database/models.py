from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text
from app.database.session import Base
from app.utils.time import utc_now


class ScanLog(Base):
    __tablename__ = "scan_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), default=utc_now, index=True)
    total_pairs = Column(Integer, default=0)
    candidates_count = Column(Integer, default=0)
    valid_signals_count = Column(Integer, default=0)
    rejected_count = Column(Integer, default=0)
    summary_json = Column(Text, default="{}")


class SignalLog(Base):
    __tablename__ = "signal_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), default=utc_now, index=True)
    symbol = Column(String(32), index=True)
    decision = Column(String(16), default="WAIT")
    confidence = Column(Integer, default=0)
    setup_type = Column(String(64), default="none")
    entry_zone = Column(String(128), default="")
    stop_loss = Column(String(64), default="")
    take_profit_1 = Column(String(64), default="")
    take_profit_2 = Column(String(64), default="")
    risk_reward = Column(Float, default=0.0)
    reason = Column(Text, default="")
    invalid_if = Column(Text, default="")
    broadcast_allowed = Column(Boolean, default=False)
    broadcast_status = Column(String(32), default="pending")
    ai_response_json = Column(Text, default="{}")
    orderflow_summary_json = Column(Text, default="{}")
    binance_endpoint_status = Column(String(64), default="")
    market_data_error = Column(Text, default="")
    status = Column(String(32), default="pending")
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class RejectedSetup(Base):
    __tablename__ = "rejected_setups"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), default=utc_now, index=True)
    symbol = Column(String(32), index=True)
    reason = Column(String(64), index=True)
    timeframe_summary_json = Column(Text, default="{}")
    created_at = Column(DateTime(timezone=True), default=utc_now)


class OrderflowSnapshot(Base):
    __tablename__ = "orderflow_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), default=utc_now, index=True)
    symbol = Column(String(32), index=True)
    window = Column(String(8), index=True)
    buy_volume = Column(Float, default=0.0)
    sell_volume = Column(Float, default=0.0)
    volume_delta = Column(Float, default=0.0)
    cumulative_volume_delta = Column(Float, default=0.0)
    delta_ratio = Column(Float, default=0.0)
    trade_count = Column(Integer, default=0)
    trade_intensity = Column(String(16), default="low")
    average_trade_size = Column(Float, default=0.0)
    large_trade_count = Column(Integer, default=0)
    best_bid = Column(Float, default=0.0)
    best_ask = Column(Float, default=0.0)
    spread = Column(Float, default=0.0)
    orderbook_imbalance = Column(Float, default=0.0)
    liquidity_wall_side = Column(String(16), default="none")
    liquidity_wall_price = Column(Float, default=0.0)
    liquidation_buy_notional = Column(Float, default=0.0)
    liquidation_sell_notional = Column(Float, default=0.0)
    liquidation_spike_detected = Column(Boolean, default=False)
    raw_summary_json = Column(Text, default="{}")
    created_at = Column(DateTime(timezone=True), default=utc_now)


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String(64), primary_key=True, index=True)
    value = Column(String(255), default="")
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
