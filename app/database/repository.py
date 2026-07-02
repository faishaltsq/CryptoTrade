import json
from typing import Any
from sqlalchemy import desc, func
from sqlalchemy.orm import Session
from app.database.models import OrderflowSnapshot, PerformanceSnapshot, RejectedSetup, ScanLog, Setting, SignalLog, SignalOutcome, SignalReview, StrategyLesson


FINAL_OUTCOMES = {"hit_tp1", "hit_tp2", "hit_sl", "break_even", "expired", "invalidated", "manually_closed"}
ALLOWED_OUTCOMES = {"pending", *FINAL_OUTCOMES}
LESSON_STATUSES = {"suggested", "approved", "rejected", "active", "disabled"}


def save_scan_log(db: Session, total_pairs: int, candidates_count: int, valid_signals_count: int, rejected_count: int, summary: dict[str, Any]) -> ScanLog:
    row = ScanLog(
        total_pairs=total_pairs,
        candidates_count=candidates_count,
        valid_signals_count=valid_signals_count,
        rejected_count=rejected_count,
        summary_json=json.dumps(summary, default=str),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def save_signal_log(db: Session, payload: dict[str, Any], ai_response: dict[str, Any], status: str = "pending") -> SignalLog:
    return create_signal_log(db, payload, ai_response, status)


def create_signal_log(db: Session, payload: dict[str, Any], ai_response: dict[str, Any], status: str = "pending", broadcast_status: str | None = None) -> SignalLog:
    risk = ai_response.get("risk", {}) or {}
    scores = payload.get("scores", {}) or {}
    orderflow = payload.get("orderflow", {}) or {}
    market = ai_response.get("market_summary", {}) or payload.get("market_summary", {}) or {}
    entry_zone = risk.get("entry_zone", "") or (ai_response.get("entry", {}) or {}).get("zone", "")
    decision = ai_response.get("decision", "WAIT")
    resolved_broadcast_status = broadcast_status or ("pending_admin" if status == "pending" and decision in {"BUY", "SELL"} else "skipped")
    row = SignalLog(
        symbol=ai_response.get("symbol") or payload.get("symbol", ""),
        provider=payload.get("provider", ""),
        market_type=payload.get("market_type") or payload.get("market", "USDT Perpetual"),
        decision=decision,
        confidence=int(ai_response.get("confidence") or 0),
        setup_type=ai_response.get("setup_type", "none"),
        entry_type=risk.get("entry_type", "limit"),
        entry_zone=entry_zone,
        stop_loss=str(risk.get("stop_loss", "")),
        take_profit_1=str(risk.get("take_profit_1", "")),
        take_profit_2=str(risk.get("take_profit_2", "")),
        risk_reward=float(risk.get("risk_reward") or 0),
        market_regime=market.get("market_regime", ""),
        analysis_method_json=json.dumps(ai_response.get("analysis_method_used", []), default=str),
        reason=ai_response.get("reason", ""),
        invalid_if=ai_response.get("invalid_if", ""),
        broadcast_allowed=bool(ai_response.get("broadcast_allowed", False)),
        broadcast_status=resolved_broadcast_status,
        ai_response_json=json.dumps(ai_response, default=str),
        orderflow_summary_json=json.dumps(payload.get("orderflow", {}), default=str),
        derivatives_summary_json=json.dumps(payload.get("derivatives_data", payload.get("futures_data", {})), default=str),
        binance_endpoint_status=payload.get("binance_endpoint_status", "ok"),
        market_data_error=payload.get("market_data_error", ""),
        technical_score=int(scores.get("technical_score") or 0),
        orderflow_score=int(scores.get("orderflow_score") or orderflow.get("orderflow_score") or 0),
        risk_score=int(scores.get("risk_score") or 0),
        final_confidence=int(scores.get("final_confidence") or ai_response.get("confidence") or 0),
        ai_prompt_version=payload.get("ai_prompt_version", ""),
        active_lessons_json=json.dumps(payload.get("active_lessons", []), default=str),
        orderflow_bias=orderflow.get("orderflow_bias") or (ai_response.get("orderflow", {}) or {}).get("bias", ""),
        orderflow_conflict=bool(orderflow.get("orderflow_conflict") or (ai_response.get("orderflow", {}) or {}).get("conflict", False)),
        absorption_signal=orderflow.get("absorption_signal", "none"),
        status=status,
        outcome_status="pending",
        review_status="not_reviewed",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    if decision in {"BUY", "SELL"}:
        create_signal_outcome(db, row.id, {})
    return row


def create_signal_outcome(db: Session, signal_id: int, outcome_data: dict[str, Any] | None = None) -> SignalOutcome | None:
    signal = get_signal_by_id(db, signal_id)
    if not signal:
        return None
    existing = get_signal_outcome(db, signal_id)
    if existing:
        return existing
    data = outcome_data or {}
    row = SignalOutcome(
        signal_id=signal.id,
        symbol=signal.symbol,
        decision=signal.decision,
        entry_price=parse_entry_price(signal.entry_zone),
        stop_loss=parse_float(signal.stop_loss),
        take_profit_1=parse_float(signal.take_profit_1),
        take_profit_2=parse_float(signal.take_profit_2),
        result=data.get("result", "pending"),
        close_reason=data.get("close_reason", ""),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def save_rejected_setup(db: Session, symbol: str, reason: str, summary: dict[str, Any]) -> RejectedSetup:
    row = RejectedSetup(symbol=symbol, reason=reason, timeframe_summary_json=json.dumps(summary, default=str))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def save_orderflow_snapshot(db: Session, summary: dict[str, Any]) -> OrderflowSnapshot:
    row = OrderflowSnapshot(
        symbol=summary.get("symbol", ""),
        window=summary.get("window", ""),
        price=float(summary.get("price") or summary.get("best_ask") or summary.get("best_bid") or 0),
        buy_volume=float(summary.get("buy_volume") or 0),
        sell_volume=float(summary.get("sell_volume") or 0),
        volume_delta=float(summary.get("volume_delta") or 0),
        cumulative_volume_delta=float(summary.get("cumulative_volume_delta") or 0),
        delta_ratio=float(summary.get("delta_ratio") or 0),
        trade_count=int(summary.get("trade_count") or 0),
        trade_intensity=summary.get("trade_intensity", "low"),
        average_trade_size=float(summary.get("average_trade_size") or 0),
        large_trade_count=int(summary.get("large_trade_count") or 0),
        best_bid=float(summary.get("best_bid") or 0),
        best_ask=float(summary.get("best_ask") or 0),
        spread=float(summary.get("spread") or 0),
        bid_depth=float(summary.get("bid_depth") or summary.get("bid_qty_top_levels") or 0),
        ask_depth=float(summary.get("ask_depth") or summary.get("ask_qty_top_levels") or 0),
        orderbook_imbalance=float(summary.get("orderbook_imbalance") or 0),
        liquidity_wall_side=summary.get("liquidity_wall_side", "none"),
        liquidity_wall_price=float(summary.get("liquidity_wall_price") or 0),
        liquidation_buy_notional=float(summary.get("liquidation_buy_notional") or 0),
        liquidation_sell_notional=float(summary.get("liquidation_sell_notional") or 0),
        liquidation_spike_detected=bool(summary.get("liquidation_spike_detected", False)),
        open_interest=float(summary.get("open_interest") or 0),
        open_interest_change=float(summary.get("open_interest_change") or 0),
        absorption_signal=summary.get("absorption_signal", "none"),
        orderflow_bias=summary.get("orderflow_bias", "insufficient_data"),
        orderflow_conflict=bool(summary.get("orderflow_conflict", False)),
        orderflow_score=int(summary.get("orderflow_score") or 0),
        flow_interpretation=summary.get("flow_interpretation", summary.get("interpretation", "")),
        raw_summary_json=json.dumps(summary, default=str),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_setting(db: Session, key: str, default: str = "") -> str:
    row = db.get(Setting, key)
    return row.value if row else default


def set_setting(db: Session, key: str, value: str) -> Setting:
    row = db.get(Setting, key) or Setting(key=key)
    row.value = value
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def latest_scan(db: Session) -> ScanLog | None:
    return db.query(ScanLog).order_by(desc(ScanLog.timestamp)).first()


def latest_signals(db: Session, limit: int = 10) -> list[SignalLog]:
    sub = db.query(SignalLog.symbol, func.max(SignalLog.timestamp).label("max_ts")).filter(SignalLog.decision.in_(["BUY", "SELL"])).group_by(SignalLog.symbol).subquery()
    return db.query(SignalLog).join(sub, (SignalLog.symbol == sub.c.symbol) & (SignalLog.timestamp == sub.c.max_ts)).order_by(desc(SignalLog.timestamp)).limit(limit).all()


def get_recent_signals(db: Session, limit: int = 10) -> list[SignalLog]:
    return db.query(SignalLog).filter(SignalLog.decision.in_(["BUY", "SELL"])).order_by(desc(SignalLog.timestamp)).limit(limit).all()


def get_pending_signals(db: Session) -> list[SignalLog]:
    return db.query(SignalLog).filter(SignalLog.outcome_status == "pending", SignalLog.decision.in_(["BUY", "SELL"])).order_by(desc(SignalLog.timestamp)).all()


def waiting_signals(db: Session, limit: int = 10) -> list[SignalLog]:
    return db.query(SignalLog).filter(SignalLog.decision == "WAIT").order_by(desc(SignalLog.timestamp)).limit(limit).all()


def latest_rejected(db: Session, limit: int = 20) -> list[RejectedSetup]:
    return db.query(RejectedSetup).order_by(desc(RejectedSetup.timestamp)).limit(limit).all()


def latest_orderflow(db: Session, symbol: str, limit: int = 10) -> list[OrderflowSnapshot]:
    return db.query(OrderflowSnapshot).filter(OrderflowSnapshot.symbol == symbol.upper()).order_by(desc(OrderflowSnapshot.timestamp)).limit(limit).all()


def latest_orderflow_activity(db: Session, limit: int = 30) -> list[OrderflowSnapshot]:
    return db.query(OrderflowSnapshot).filter(OrderflowSnapshot.window == "1m", OrderflowSnapshot.trade_count > 0).order_by(desc(OrderflowSnapshot.timestamp)).limit(limit).all()


def get_signal(db: Session, signal_id: int) -> SignalLog | None:
    return db.get(SignalLog, signal_id)


def get_signal_by_id(db: Session, signal_id: int) -> SignalLog | None:
    return get_signal(db, signal_id)


def update_signal_broadcast_status(db: Session, signal_id: int, status: str) -> SignalLog | None:
    row = get_signal_by_id(db, signal_id)
    if not row:
        return None
    row.broadcast_status = status
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_signal_outcome(db: Session, signal_id: int) -> SignalOutcome | None:
    return db.query(SignalOutcome).filter(SignalOutcome.signal_id == signal_id).order_by(desc(SignalOutcome.id)).first()


def get_recent_outcomes(db: Session, limit: int = 10) -> list[SignalOutcome]:
    return db.query(SignalOutcome).order_by(desc(SignalOutcome.updated_at)).limit(limit).all()


def get_closed_unreviewed_signals(db: Session, limit: int = 20) -> list[SignalLog]:
    return db.query(SignalLog).filter(SignalLog.outcome_status.in_(list(FINAL_OUTCOMES)), SignalLog.review_status.in_(["not_reviewed", "failed"])).order_by(desc(SignalLog.updated_at)).limit(limit).all()


def update_signal_outcome(db: Session, signal_id: int, result: str, close_reason: str | None = None, close_price: float | None = None) -> SignalOutcome | None:
    if result not in ALLOWED_OUTCOMES:
        raise ValueError(f"invalid outcome result: {result}")
    row = get_signal_outcome(db, signal_id) or create_signal_outcome(db, signal_id, {})
    signal = get_signal_by_id(db, signal_id)
    if not row or not signal:
        return None
    row.result = result
    if close_reason:
        row.close_reason = close_reason
    if close_price is not None:
        row.close_price = float(close_price)
    signal.outcome_status = result
    if result != "pending":
        signal.review_status = "not_reviewed"
    db.add(row)
    db.add(signal)
    db.commit()
    db.refresh(row)
    return row


def create_signal_review(db: Session, signal_id: int, review: dict[str, Any], result: str = "") -> SignalReview:
    row = SignalReview(
        signal_id=signal_id,
        result=result,
        result_quality=review.get("result_quality", "inconclusive"),
        main_failure_reason=review.get("main_failure_reason", ""),
        warning_signs_json=json.dumps(review.get("warning_signs", []), default=str),
        what_should_have_been_checked_json=json.dumps(review.get("what_should_have_been_checked", []), default=str),
        recommended_rule_adjustments_json=json.dumps(review.get("recommended_rule_adjustments", []), default=str),
        confidence_penalty_conditions_json=json.dumps(review.get("confidence_penalty_conditions", []), default=str),
        confidence_boost_conditions_json=json.dumps(review.get("confidence_boost_conditions", []), default=str),
        future_lesson=review.get("future_lesson", ""),
        ai_review_json=json.dumps(review, default=str),
    )
    db.add(row)
    signal = get_signal_by_id(db, signal_id)
    if signal:
        signal.review_status = "reviewed"
        db.add(signal)
    db.commit()
    db.refresh(row)
    return row


def mark_signal_review_failed(db: Session, signal_id: int, raw_error: str) -> SignalReview | None:
    signal = get_signal_by_id(db, signal_id)
    if signal:
        signal.review_status = "failed"
        db.add(signal)
    row = SignalReview(signal_id=signal_id, result_quality="inconclusive", main_failure_reason="review_failed", ai_review_json=json.dumps({"error": raw_error}, default=str))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_signal_review(db: Session, signal_id: int) -> SignalReview | None:
    return db.query(SignalReview).filter(SignalReview.signal_id == signal_id).order_by(desc(SignalReview.id)).first()


def create_strategy_lesson(db: Session, lesson: dict[str, Any], source_signal_id: int = 0) -> StrategyLesson:
    row = StrategyLesson(
        lesson_text=lesson.get("lesson_text", ""),
        lesson_type=lesson.get("lesson_type", "warning_note"),
        affected_condition=lesson.get("affected_condition", ""),
        affected_symbols_json=json.dumps(lesson.get("affected_symbols", []), default=str),
        affected_timeframes_json=json.dumps(lesson.get("affected_timeframes", []), default=str),
        confidence_adjustment=int(lesson.get("confidence_adjustment") or 0),
        filter_rule_json=json.dumps(lesson.get("filter_rule", {}), default=str),
        evidence_count=int(lesson.get("evidence_count") or 1),
        winrate_before=float(lesson.get("winrate_before") or 0),
        status="suggested",
        source_signal_id=source_signal_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_lessons(db: Session, status: str | None = None, limit: int = 50) -> list[StrategyLesson]:
    query = db.query(StrategyLesson)
    if status:
        query = query.filter(StrategyLesson.status == status)
    return query.order_by(desc(StrategyLesson.updated_at)).limit(limit).all()


def get_active_lessons(db: Session, limit: int = 10) -> list[StrategyLesson]:
    return db.query(StrategyLesson).filter(StrategyLesson.status == "active").order_by(desc(StrategyLesson.evidence_count), desc(StrategyLesson.updated_at)).limit(limit).all()


def get_lesson(db: Session, lesson_id: int) -> StrategyLesson | None:
    return db.get(StrategyLesson, lesson_id)


def update_lesson_status(db: Session, lesson_id: int, status: str) -> StrategyLesson | None:
    if status not in LESSON_STATUSES:
        raise ValueError(f"invalid lesson status: {status}")
    from app.utils.time import utc_now

    row = get_lesson(db, lesson_id)
    if not row:
        return None
    row.status = "active" if status == "approved" else status
    if status == "approved":
        row.approved_at = utc_now()
    if status == "rejected":
        row.rejected_at = utc_now()
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def save_performance_snapshot(db: Session, period: str, stats: dict[str, Any]) -> PerformanceSnapshot:
    row = PerformanceSnapshot(
        period=period,
        total_signals=int(stats.get("total_signals") or 0),
        winrate=float(stats.get("winrate") or 0),
        tp1_rate=float(stats.get("tp1_rate") or 0),
        tp2_rate=float(stats.get("tp2_rate") or 0),
        sl_rate=float(stats.get("sl_rate") or 0),
        expired_rate=float(stats.get("expired_rate") or 0),
        average_rr=float(stats.get("average_rr") or 0),
        average_mfe=float(stats.get("average_mfe") or 0),
        average_mae=float(stats.get("average_mae") or 0),
        profit_factor_estimate=float(stats.get("profit_factor_estimate") or 0),
        best_symbols_json=json.dumps(stats.get("best_symbols", []), default=str),
        worst_symbols_json=json.dumps(stats.get("worst_symbols", []), default=str),
        best_conditions_json=json.dumps(stats.get("best_conditions", []), default=str),
        worst_conditions_json=json.dumps(stats.get("worst_conditions", []), default=str),
        summary_json=json.dumps(stats, default=str),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_signal_outcome_status(db: Session, signal_id: int, outcome_status: str) -> SignalLog | None:
    if outcome_status not in ALLOWED_OUTCOMES:
        raise ValueError(f"invalid outcome status: {outcome_status}")
    row = get_signal_by_id(db, signal_id)
    if not row:
        return None
    row.outcome_status = outcome_status
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_signal_status(db: Session, signal_id: int, status: str, broadcast_status: str | None = None) -> SignalLog | None:
    row = db.get(SignalLog, signal_id)
    if not row:
        return None
    row.status = status
    if broadcast_status:
        row.broadcast_status = broadcast_status
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def parse_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def parse_entry_price(entry_zone: str) -> float:
    cleaned = str(entry_zone or "").replace(" ", "")
    if not cleaned:
        return 0.0
    parts = [x for x in cleaned.replace("–", "-").split("-") if x]
    values = [parse_float(x) for x in parts]
    values = [x for x in values if x > 0]
    if not values:
        return 0.0
    return sum(values) / len(values)
