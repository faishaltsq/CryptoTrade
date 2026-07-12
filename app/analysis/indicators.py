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
    out["volume_spike_soft"] = out["volume"] > (out["volume_sma20"] * 1.3)
    out["volume_surge"] = out["volume"] > (out["volume_sma20"] * 2.5)
    out["obv"] = obv(out)
    out["cvd"] = approximate_cvd(out)
    return out


def obv(df: pd.DataFrame) -> pd.Series:
    direction = np.where(df["close"] > df["close"].shift(1), 1, np.where(df["close"] < df["close"].shift(1), -1, 0))
    obv_vals = (direction * df["volume"]).cumsum()
    return pd.Series(obv_vals, index=df.index)


def approximate_cvd(df: pd.DataFrame, window: int = 20) -> pd.Series:
    body = df["close"] - df["open"]
    upper_wick = df["high"] - df[["close", "open"]].max(axis=1)
    lower_wick = df[["close", "open"]].min(axis=1) - df["low"]
    buy_volume = df["volume"] * (abs(body.clip(lower=0)) + upper_wick) / (df["high"] - df["low"]).replace(0, 1e-9)
    sell_volume = df["volume"] * (abs(body.clip(upper=0)) + lower_wick) / (df["high"] - df["low"]).replace(0, 1e-9)
    delta = buy_volume - sell_volume
    return delta.cumsum()


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
    vol_sma20 = float(last.volume_sma20) if not pd.isna(last.volume_sma20) else 0
    vol_ratio = round(float(last.volume) / vol_sma20, 2) if vol_sma20 > 0 else 1.0
    vol_trend = "rising" if float(last.volume) > vol_sma20 * 1.1 else "falling" if float(last.volume) < vol_sma20 * 0.9 else "stable"
    obv_trend = _obv_trend(df)
    cvd_divergence = _cvd_divergence(df)
    return {
        "price": float(last.close),
        "ema50": float(last.ema50),
        "ema200": float(last.ema200),
        "ema_bias": ema_bias,
        "rsi": round(float(last.rsi14), 2) if not pd.isna(last.rsi14) else 0,
        "atr": round(float(last.atr14), 6) if not pd.isna(last.atr14) else 0,
        "volume_spike": bool(last.volume_spike),
        "volume_spike_soft": bool(last.volume_spike_soft),
        "volume_surge": bool(last.volume_surge),
        "volume_ratio": vol_ratio,
        "volume_trend": vol_trend,
        "obv_trend": obv_trend,
        "cvd_divergence": cvd_divergence,
    }


def _obv_trend(df: pd.DataFrame) -> str:
    if len(df) < 10 or "obv" not in df.columns:
        return "flat"
    recent = df["obv"].iloc[-10:]
    obv_change = float(recent.iloc[-1] - recent.iloc[0])
    price_change = float(df["close"].iloc[-1] - df["close"].iloc[-10])
    if obv_change > 0 and price_change <= obv_change * 0.1:
        return "rising_divergent"
    if obv_change < 0 and price_change >= abs(obv_change) * 0.1:
        return "falling_divergent"
    if obv_change > abs(price_change) * 0.2:
        return "rising"
    if obv_change < -abs(price_change) * 0.2:
        return "falling"
    return "flat"


def _cvd_divergence(df: pd.DataFrame) -> str:
    if len(df) < 5 or "cvd" not in df.columns:
        return "none"
    recent = df["cvd"].iloc[-5:]
    price_recent = df["close"].iloc[-5:]
    cvd_change = float(recent.iloc[-1] - recent.iloc[0])
    price_change = float(price_recent.iloc[-1] - price_recent.iloc[0])
    if cvd_change > 0 and price_change < 0:
        return "bullish"
    if cvd_change < 0 and price_change > 0:
        return "bearish"
    return "none"
