import numpy as np
import pandas as pd


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["ema50"] = out["close"].ewm(span=50, adjust=False).mean()
    out["ema200"] = out["close"].ewm(span=200, adjust=False).mean()
    out["rsi14"] = rsi(out["close"], 14)
    out["atr14"] = atr(out, 14)
    out["volume_sma20"] = out["volume"].rolling(20).mean()
    out["volume_spike"] = out["volume"] > (out["volume_sma20"] * 1.8)
    return out


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    avg_gain = pd.Series(gain, index=close.index).rolling(period).mean()
    avg_loss = pd.Series(loss, index=close.index).rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([(df["high"] - df["low"]), (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def summarize_indicators(df: pd.DataFrame) -> dict:
    last = df.iloc[-1]
    ema_bias = "bullish" if last.close > last.ema50 > last.ema200 else "bearish" if last.close < last.ema50 < last.ema200 else "neutral"
    return {
        "price": float(last.close),
        "ema50": float(last.ema50),
        "ema200": float(last.ema200),
        "ema_bias": ema_bias,
        "rsi": round(float(last.rsi14), 2) if not pd.isna(last.rsi14) else 0,
        "atr": round(float(last.atr14), 6) if not pd.isna(last.atr14) else 0,
        "volume_spike": bool(last.volume_spike),
    }
