import json
from typing import Any
from sqlalchemy import desc, func
from sqlalchemy.orm import Session
from app.database.models import OrderflowSnapshot, RejectedSetup, ScanLog, Setting, SignalLog


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
    risk = ai_response.get("risk", {}) or {}
    scores = payload.get("scores", {}) or {}
    orderflow = payload.get("orderflow", {}) or {}
    entry_zone = risk.get("entry_zone", "") or (ai_response.get("entry", {}) or {}).get("zone", "")
    row = SignalLog(
        symbol=ai_response.get("symbol") or payload.get("symbol", ""),
        decision=ai_response.get("decision", "WAIT"),
        confidence=int(ai_response.get("confidence") or 0),
        setup_type=ai_response.get("setup_type", "none"),
        entry_zone=entry_zone,
        stop_loss=str(risk.get("stop_loss", "")),
        take_profit_1=str(risk.get("take_profit_1", "")),
        take_profit_2=str(risk.get("take_profit_2", "")),
        risk_reward=float(risk.get("risk_reward") or 0),
        reason=ai_response.get("reason", ""),
        invalid_if=ai_response.get("invalid_if", ""),
        broadcast_allowed=bool(ai_response.get("broadcast_allowed", False)),
        broadcast_status="pending",
        ai_response_json=json.dumps(ai_response, default=str),
        orderflow_summary_json=json.dumps(payload.get("orderflow", {}), default=str),
        binance_endpoint_status=payload.get("binance_endpoint_status", "ok"),
        market_data_error=payload.get("market_data_error", ""),
        technical_score=int(scores.get("technical_score") or 0),
        orderflow_score=int(scores.get("orderflow_score") or orderflow.get("orderflow_score") or 0),
        risk_score=int(scores.get("risk_score") or 0),
        final_confidence=int(scores.get("final_confidence") or ai_response.get("confidence") or 0),
        orderflow_bias=orderflow.get("orderflow_bias") or (ai_response.get("orderflow", {}) or {}).get("bias", ""),
        orderflow_conflict=bool(orderflow.get("orderflow_conflict") or (ai_response.get("orderflow", {}) or {}).get("conflict", False)),
        absorption_signal=orderflow.get("absorption_signal", "none"),
        status=status,
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
