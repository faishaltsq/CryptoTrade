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
    provider = Column(String(32), default="")
    market_type = Column(String(64), default="USDT Perpetual")
    decision = Column(String(16), default="WAIT")
    confidence = Column(Integer, default=0)
    setup_type = Column(String(64), default="none")
    entry_type = Column(String(32), default="limit")
    entry_zone = Column(String(128), default="")
    stop_loss = Column(String(64), default="")
    take_profit_1 = Column(String(64), default="")
    take_profit_2 = Column(String(64), default="")
    risk_reward = Column(Float, default=0.0)
    market_regime = Column(String(128), default="")
    analysis_method_json = Column(Text, default="[]")
    reason = Column(Text, default="")
    invalid_if = Column(Text, default="")
    broadcast_allowed = Column(Boolean, default=False)
    broadcast_status = Column(String(32), default="pending_admin")
    ai_response_json = Column(Text, default="{}")
    orderflow_summary_json = Column(Text, default="{}")
    derivatives_summary_json = Column(Text, default="{}")
    binance_endpoint_status = Column(String(64), default="")
    market_data_error = Column(Text, default="")
    technical_score = Column(Integer, default=0)
    orderflow_score = Column(Integer, default=0)
    risk_score = Column(Integer, default=0)
    final_confidence = Column(Integer, default=0)
    ai_prompt_version = Column(String(64), default="")
    active_lessons_json = Column(Text, default="[]")
    orderflow_bias = Column(String(32), default="")
    orderflow_conflict = Column(Boolean, default=False)
    absorption_signal = Column(String(64), default="none")
    status = Column(String(32), default="pending")
    outcome_status = Column(String(32), default="pending")
    review_status = Column(String(32), default="not_reviewed")
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class SignalOutcome(Base):
    __tablename__ = "signal_outcomes"

    id = Column(Integer, primary_key=True, index=True)
    signal_id = Column(Integer, index=True)
    symbol = Column(String(32), index=True)
    decision = Column(String(16), default="WAIT")
    entry_price = Column(Float, default=0.0)
    stop_loss = Column(Float, default=0.0)
    take_profit_1 = Column(Float, default=0.0)
    take_profit_2 = Column(Float, default=0.0)
    result = Column(String(32), default="pending", index=True)
    max_favorable_excursion = Column(Float, default=0.0)
    max_adverse_excursion = Column(Float, default=0.0)
    duration_minutes = Column(Integer, default=0)
    close_price = Column(Float, default=0.0)
    close_reason = Column(String(64), default="")
    first_tp_hit_at = Column(DateTime(timezone=True), nullable=True)
    second_tp_hit_at = Column(DateTime(timezone=True), nullable=True)
    stop_loss_hit_at = Column(DateTime(timezone=True), nullable=True)
    expired_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class SignalReview(Base):
    __tablename__ = "signal_reviews"

    id = Column(Integer, primary_key=True, index=True)
    signal_id = Column(Integer, index=True)
    result = Column(String(32), default="")
    result_quality = Column(String(32), default="inconclusive", index=True)
    main_failure_reason = Column(String(128), default="")
    warning_signs_json = Column(Text, default="[]")
    what_should_have_been_checked_json = Column(Text, default="[]")
    recommended_rule_adjustments_json = Column(Text, default="[]")
    confidence_penalty_conditions_json = Column(Text, default="[]")
    confidence_boost_conditions_json = Column(Text, default="[]")
    future_lesson = Column(Text, default="")
    ai_review_json = Column(Text, default="{}")
    reviewed_at = Column(DateTime(timezone=True), default=utc_now)
    created_at = Column(DateTime(timezone=True), default=utc_now)


class StrategyLesson(Base):
    __tablename__ = "strategy_lessons"

    id = Column(Integer, primary_key=True, index=True)
    lesson_text = Column(Text, default="")
    lesson_type = Column(String(64), default="warning_note", index=True)
    affected_condition = Column(String(128), default="")
    affected_symbols_json = Column(Text, default="[]")
    affected_timeframes_json = Column(Text, default="[]")
    confidence_adjustment = Column(Integer, default=0)
    filter_rule_json = Column(Text, default="{}")
    evidence_count = Column(Integer, default=1)
    winrate_before = Column(Float, default=0.0)
    status = Column(String(32), default="suggested", index=True)
    source_signal_id = Column(Integer, default=0, index=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    rejected_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class PerformanceSnapshot(Base):
    __tablename__ = "performance_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    period = Column(String(32), default="30d", index=True)
    total_signals = Column(Integer, default=0)
    winrate = Column(Float, default=0.0)
    tp1_rate = Column(Float, default=0.0)
    tp2_rate = Column(Float, default=0.0)
    sl_rate = Column(Float, default=0.0)
    expired_rate = Column(Float, default=0.0)
    average_rr = Column(Float, default=0.0)
    average_mfe = Column(Float, default=0.0)
    average_mae = Column(Float, default=0.0)
    profit_factor_estimate = Column(Float, default=0.0)
    best_symbols_json = Column(Text, default="[]")
    worst_symbols_json = Column(Text, default="[]")
    best_conditions_json = Column(Text, default="[]")
    worst_conditions_json = Column(Text, default="[]")
    summary_json = Column(Text, default="{}")
    created_at = Column(DateTime(timezone=True), default=utc_now)


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
    price = Column(Float, default=0.0)
    buy_volume = Column(Float, default=0.0)
    sell_volume = Column(Float, default=0.0)
    volume_delta = Column(Float, default=0.0)
    cumulative_volume_delta = Column(Float, default=0.0)
    delta_ratio = Column(Float, default=0.0)
    trade_count = Column(Integer, default=0)
    trade_intensity = Column(String(16), default="low")
    average_trade_size = Column(Float, default=0.0)
    large_trade_count = Column(Integer, default=0)
    large_trade_buy_volume = Column(Float, default=0.0)
    large_trade_sell_volume = Column(Float, default=0.0)
    large_trade_buy_notional = Column(Float, default=0.0)
    large_trade_sell_notional = Column(Float, default=0.0)
    best_bid = Column(Float, default=0.0)
    best_ask = Column(Float, default=0.0)
    spread = Column(Float, default=0.0)
    bid_depth = Column(Float, default=0.0)
    ask_depth = Column(Float, default=0.0)
    orderbook_imbalance = Column(Float, default=0.0)
    liquidity_wall_side = Column(String(16), default="none")
    liquidity_wall_price = Column(Float, default=0.0)
    liquidation_buy_notional = Column(Float, default=0.0)
    liquidation_sell_notional = Column(Float, default=0.0)
    liquidation_spike_detected = Column(Boolean, default=False)
    open_interest = Column(Float, default=0.0)
    open_interest_change = Column(Float, default=0.0)
    absorption_signal = Column(String(64), default="none")
    orderflow_bias = Column(String(32), default="insufficient_data")
    orderflow_conflict = Column(Boolean, default=False)
    orderflow_score = Column(Integer, default=0)
    flow_interpretation = Column(Text, default="")
    raw_summary_json = Column(Text, default="{}")
    created_at = Column(DateTime(timezone=True), default=utc_now)


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(32), index=True)
    direction = Column(String(8), default="")
    market_state = Column(String(24), default="WATCHING")
    setup_type = Column(String(32), default="")
    confidence = Column(Integer, default=0)
    quality_score = Column(Integer, default=0)
    priority_score = Column(Integer, default=0)
    opportunity_score = Column(Integer, default=0)
    risk_reward = Column(Float, default=0.0)
    current_price = Column(Float, default=0.0)
    entry_zone = Column(String(32), default="")
    trigger_distance_pct = Column(Float, default=0.0)
    state = Column(String(16), default="WATCHING", index=True)
    previous_probability = Column(Integer, default=0)
    probability_delta = Column(Integer, default=0)
    prob_change_reason = Column(String(120), default="")
    analysis_count = Column(Integer, default=1)
    reason = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    expires_at = Column(DateTime(timezone=True), nullable=True)


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String(64), primary_key=True, index=True)
    value = Column(String(255), default="")
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
