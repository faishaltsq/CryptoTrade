from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.database.models import SignalLog, SignalOutcome


def analyze_performance(db: Session, period: str = "30d") -> dict[str, Any]:
    query = db.query(SignalOutcome, SignalLog).join(SignalLog, SignalLog.id == SignalOutcome.signal_id).filter(SignalLog.broadcast_status == "broadcasted")
    if period != "all":
        days = int(period[:-1]) if period.endswith("d") and period[:-1].isdigit() else 30
        query = query.filter(SignalOutcome.created_at >= datetime.now(timezone.utc) - timedelta(days=days))
    rows = query.all()
    closed = [(o, s) for o, s in rows if o.result not in {"pending", "manually_closed"}]
    wins = [(o, s) for o, s in closed if o.result in {"hit_tp1", "hit_tp2"}]
    losses = [(o, s) for o, s in closed if o.result == "hit_sl"]
    total = len(closed)
    counts = Counter(o.result for o, _ in closed)
    rr_values = [float(s.risk_reward or 0) for _, s in closed if s.risk_reward]
    by_symbol = grouped_winrate(closed, lambda o, s: s.symbol)
    by_direction = grouped_winrate(closed, lambda o, s: s.decision)
    by_regime = grouped_winrate(closed, lambda o, s: s.market_regime or "unknown")
    by_conf = grouped_winrate(closed, lambda o, s: confidence_bucket(s.confidence))
    by_orderflow = grouped_winrate(closed, lambda o, s: s.orderflow_bias or "unknown")
    by_setup = grouped_winrate(closed, lambda o, s: s.setup_type or "unknown")
    return {
        "period": period,
        "total_signals": total,
        "winrate": pct(len(wins), total),
        "tp1_rate": pct(counts.get("hit_tp1", 0), total),
        "tp2_rate": pct(counts.get("hit_tp2", 0), total),
        "sl_rate": pct(counts.get("hit_sl", 0), total),
        "expired_rate": pct(counts.get("expired", 0), total),
        "average_rr": round(sum(rr_values) / len(rr_values), 2) if rr_values else 0,
        "average_mfe": round(avg([o.max_favorable_excursion for o, _ in closed]), 4),
        "average_mae": round(avg([o.max_adverse_excursion for o, _ in closed]), 4),
        "profit_factor_estimate": round((len(wins) or 0) / (len(losses) or 1), 2),
        "best_symbols": by_symbol[:5],
        "worst_symbols": list(reversed(by_symbol[-5:])),
        "by_direction": by_direction,
        "by_market_regime": by_regime,
        "by_confidence_range": by_conf,
        "by_orderflow_bias": by_orderflow,
        "by_setup_label": by_setup,
        "best_conditions": [x["name"] for x in (by_regime + by_orderflow + by_setup) if x["sample"] >= 2 and x["winrate"] >= 60][:5],
        "worst_conditions": [x["name"] for x in (by_regime + by_orderflow + by_setup) if x["sample"] >= 2 and x["winrate"] <= 40][:5],
        "sample_warning": "Small samples are not statistically reliable." if total < 20 else "",
    }


def grouped_winrate(rows, key_fn):
    groups = defaultdict(list)
    for outcome, signal in rows:
        groups[key_fn(outcome, signal)].append(outcome.result)
    result = []
    for name, values in groups.items():
        sample = len(values)
        wins = sum(1 for x in values if x in {"hit_tp1", "hit_tp2"})
        result.append({"name": name, "sample": sample, "winrate": pct(wins, sample)})
    return sorted(result, key=lambda x: (x["winrate"], x["sample"]), reverse=True)


def confidence_bucket(confidence: int) -> str:
    if confidence >= 80:
        return "80+"
    if confidence >= 75:
        return "75-79"
    if confidence >= 70:
        return "70-74"
    if confidence >= 65:
        return "65-69"
    return "50-64"


def pct(part: int, total: int) -> float:
    return round(part / total * 100, 1) if total else 0.0


def avg(values) -> float:
    rows = [float(x or 0) for x in values]
    return sum(rows) / len(rows) if rows else 0.0
