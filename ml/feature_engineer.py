# ml/feature_engineer.py
"""
Feature engineering pipeline for ML prediction.
Extracts a 42-feature vector from raw candles + indicator results + SMC results.
Called by both training pipeline and live inference.

Feature groups:
  1.  Price action          (8 features)
  2.  Trend / EMAs          (8 features)
  3.  Momentum oscillators  (8 features)
  4.  Volatility            (4 features)
  5.  Volume                (4 features)
  6.  SMC confluence        (10 features)

Total: 42 features
"""

import numpy as np
from typing import List, Dict, Optional


FEATURE_NAMES = [
    # ── Price action (8) ─────────────────────────────────────────────────────
    "returns_1",          # 1-candle return
    "returns_3",          # 3-candle return
    "returns_6",          # 6-candle return
    "candle_body_ratio",  # body / total range
    "upper_wick_ratio",   # upper wick / total range
    "lower_wick_ratio",   # lower wick / total range
    "is_bullish",         # 1 if close > open
    "hl_range_norm",      # (high-low) / close — normalised range

    # ── Trend / EMAs (8) ─────────────────────────────────────────────────────
    "price_vs_ema9",      # (close - ema9)  / close
    "price_vs_ema21",     # (close - ema21) / close
    "price_vs_ema50",     # (close - ema50) / close
    "price_vs_ema200",    # (close - ema200)/ close
    "ema9_vs_ema21",      # (ema9  - ema21) / close — slope direction
    "ema21_vs_ema50",     # (ema21 - ema50) / close
    "price_vs_vwap",      # (close - vwap)  / close
    "adx_norm",           # adx / 100 — trend strength 0-1

    # ── Momentum oscillators (8) ─────────────────────────────────────────────
    "rsi_norm",           # rsi / 100
    "rsi_delta",          # rsi change last 3 candles
    "stochrsi_k_norm",    # stochrsi_k / 100
    "stochrsi_kd_diff",   # k - d (momentum direction)
    "macd_norm",          # macd / close
    "macd_hist_norm",     # histogram / close
    "macd_hist_delta",    # histogram change (acceleration)
    "cci_norm",           # cci / 200 — clamped

    # ── Volatility (4) ───────────────────────────────────────────────────────
    "atr_norm",           # atr / close
    "bb_width_norm",      # (bb_upper - bb_lower) / close
    "bb_position",        # (close - bb_lower) / (bb_upper - bb_lower)
    "atr_delta",          # atr change — expanding or contracting

    # ── Volume (4) ───────────────────────────────────────────────────────────
    "volume_norm",        # volume / 20-period avg volume
    "volume_delta",       # volume change vs previous candle
    "obv_slope",          # obv trend: (obv[-1] - obv[-5]) / abs(obv[-5]+1)
    "cvd_norm",           # cvd direction: positive = buying pressure

    # ── SMC confluence (10) ──────────────────────────────────────────────────
    "smc_bullish_score",
    "smc_bearish_score",
    "smc_net_score",
    "nearest_ob_distance",
    "nearest_ob_strength",
    "nearest_ob_is_bullish",
    "nearest_fvg_distance",
    "nearest_fvg_is_bullish",
    "recent_bos_bullish",
    "recent_bos_bearish",
]

assert len(FEATURE_NAMES) == 42, f"Expected 42 features, got {len(FEATURE_NAMES)}"


def safe(val, fallback=0.0) -> float:
    """Return float, replacing NaN/inf with fallback."""
    try:
        v = float(val)
        if np.isnan(v) or np.isinf(v):
            return fallback
        return v
    except Exception:
        return fallback


def clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


def extract_features(
    candles:          List[Dict],
    indicator_results: Dict[str, np.ndarray],
    smc_results:      Dict,
) -> Optional[np.ndarray]:
    """
    Extract 42-feature vector from the latest candle state.
    Returns None if insufficient data.
    """
    if len(candles) < 20:
        return None

    closes  = np.array([c["close"]  for c in candles], dtype=float)
    highs   = np.array([c["high"]   for c in candles], dtype=float)
    lows    = np.array([c["low"]    for c in candles], dtype=float)
    opens   = np.array([c["open"]   for c in candles], dtype=float)
    volumes = np.array([c.get("volume", 0) for c in candles], dtype=float)

    r     = indicator_results
    close = closes[-1]
    if close <= 0:
        return None

    def ind(key: str, offset: int = -1) -> float:
        arr = r.get(key)
        if arr is None or len(arr) < abs(offset):
            return 0.0
        return safe(arr[offset])

    features = np.zeros(42, dtype=np.float32)
    i = 0

    # ── Price action ─────────────────────────────────────────────────────────
    features[i] = safe((closes[-1] - closes[-2]) / closes[-2]); i += 1
    features[i] = safe((closes[-1] - closes[-4]) / closes[-4]) if len(closes) >= 4 else 0; i += 1
    features[i] = safe((closes[-1] - closes[-7]) / closes[-7]) if len(closes) >= 7 else 0; i += 1

    candle_range = highs[-1] - lows[-1]
    body         = abs(closes[-1] - opens[-1])
    upper_wick   = highs[-1] - max(closes[-1], opens[-1])
    lower_wick   = min(closes[-1], opens[-1]) - lows[-1]

    features[i] = safe(body / candle_range) if candle_range > 0 else 0.5; i += 1
    features[i] = safe(upper_wick / candle_range) if candle_range > 0 else 0; i += 1
    features[i] = safe(lower_wick / candle_range) if candle_range > 0 else 0; i += 1
    features[i] = 1.0 if closes[-1] >= opens[-1] else 0.0; i += 1
    features[i] = safe(candle_range / close); i += 1

    # ── Trend / EMAs ─────────────────────────────────────────────────────────
    for ema_key in ("EMA_9", "EMA_21", "EMA_50", "EMA_200"):
        v = ind(ema_key)
        features[i] = clamp(safe((close - v) / close if v > 0 else 0), -0.2, 0.2); i += 1

    ema9  = ind("EMA_9")
    ema21 = ind("EMA_21")
    ema50 = ind("EMA_50")

    features[i] = clamp(safe((ema9  - ema21) / close if close > 0 else 0), -0.1, 0.1); i += 1
    features[i] = clamp(safe((ema21 - ema50) / close if close > 0 else 0), -0.1, 0.1); i += 1

    vwap = ind("VWAP")
    features[i] = clamp(safe((close - vwap) / close if vwap > 0 else 0), -0.05, 0.05); i += 1

    adx = ind("ADX")
    features[i] = clamp(safe(adx / 100), 0, 1); i += 1

    # ── Momentum ─────────────────────────────────────────────────────────────
    rsi = ind("RSI")
    features[i] = safe(rsi / 100); i += 1

    rsi_arr = r.get("RSI", np.array([50.0]))
    rsi_prev = safe(rsi_arr[-4]) if len(rsi_arr) >= 4 else rsi
    features[i] = clamp(safe((rsi - rsi_prev) / 100), -0.3, 0.3); i += 1

    stoch_k = ind("STOCHRSI_K")
    stoch_d = ind("STOCHRSI_D")
    features[i] = safe(stoch_k / 100); i += 1
    features[i] = clamp(safe((stoch_k - stoch_d) / 100), -1, 1); i += 1

    macd     = ind("MACD")
    macd_sig = ind("MACD_SIGNAL")
    macd_h   = ind("MACD_HIST")
    features[i] = clamp(safe(macd / close if close > 0 else 0), -0.05, 0.05); i += 1
    features[i] = clamp(safe(macd_h / close if close > 0 else 0), -0.05, 0.05); i += 1

    hist_arr  = r.get("MACD_HIST", np.array([0.0]))
    hist_prev = safe(hist_arr[-2]) if len(hist_arr) >= 2 else macd_h
    features[i] = clamp(safe((macd_h - hist_prev) / close if close > 0 else 0), -0.02, 0.02); i += 1

    cci = ind("CCI")
    features[i] = clamp(safe(cci / 200), -1.5, 1.5); i += 1

    # ── Volatility ───────────────────────────────────────────────────────────
    atr      = ind("ATR")
    bb_upper = ind("BB_UPPER")
    bb_lower = ind("BB_LOWER")

    features[i] = clamp(safe(atr / close if close > 0 else 0), 0, 0.1); i += 1

    bb_width = bb_upper - bb_lower
    features[i] = clamp(safe(bb_width / close if close > 0 else 0), 0, 0.1); i += 1
    features[i] = clamp(safe((close - bb_lower) / bb_width if bb_width > 0 else 0.5), 0, 1); i += 1

    atr_arr  = r.get("ATR", np.array([0.0]))
    atr_prev = safe(atr_arr[-4]) if len(atr_arr) >= 4 else atr
    features[i] = clamp(safe((atr - atr_prev) / close if close > 0 else 0), -0.01, 0.01); i += 1

    # ── Volume ───────────────────────────────────────────────────────────────
    vol_avg = np.mean(volumes[-20:]) if len(volumes) >= 20 else volumes[-1]
    features[i] = clamp(safe(volumes[-1] / vol_avg if vol_avg > 0 else 1), 0, 5); i += 1

    vol_prev    = volumes[-2] if len(volumes) >= 2 else volumes[-1]
    features[i] = clamp(safe((volumes[-1] - vol_prev) / (vol_prev + 1)), -3, 3); i += 1

    obv_arr = r.get("OBV", np.array([0.0]))
    if len(obv_arr) >= 6:
        obv_slope = (obv_arr[-1] - obv_arr[-6]) / (abs(obv_arr[-6]) + 1)
        features[i] = clamp(safe(obv_slope), -1, 1)
    i += 1

    cvd_arr = r.get("CVD", np.array([0.0]))
    if len(cvd_arr) >= 5:
        cvd_recent = cvd_arr[-1] - cvd_arr[-6] if len(cvd_arr) >= 6 else cvd_arr[-1]
        features[i] = clamp(safe(np.sign(cvd_recent)), -1, 1)
    i += 1

    # ── SMC ──────────────────────────────────────────────────────────────────
    if smc_results:
        from smc.detector import SMCDetector
        tmp = SMCDetector()
        tmp.result = smc_results
        smc_vec = tmp.get_feature_vector(close)
        features[i]   = smc_vec.get("smc_bullish_score", 0); i += 1
        features[i]   = smc_vec.get("smc_bearish_score", 0); i += 1
        features[i]   = smc_vec.get("smc_net_score", 0); i += 1
        features[i]   = smc_vec.get("nearest_ob_distance", 1); i += 1
        features[i]   = smc_vec.get("nearest_ob_strength", 0); i += 1
        features[i]   = smc_vec.get("nearest_ob_is_bullish", 0); i += 1
        features[i]   = smc_vec.get("nearest_fvg_distance", 1); i += 1
        features[i]   = smc_vec.get("nearest_fvg_is_bullish", 0); i += 1
        features[i]   = smc_vec.get("recent_bos_bullish", 0); i += 1
        features[i]   = smc_vec.get("recent_bos_bearish", 0); i += 1
    else:
        i += 10

    assert i == 42, f"Feature count mismatch: {i}"
    return features


def build_training_dataset(
    candles:          List[Dict],
    indicator_results: Dict[str, np.ndarray],
    smc_results:      Dict,
    lookahead:        int = 3,
    threshold:        float = 0.002,
) -> tuple:
    """
    Build X (features) and y (labels) arrays for model training.

    Label logic:
      Look ahead `lookahead` candles.
      If future close > current close * (1 + threshold) → 1 (UP)
      If future close < current close * (1 - threshold) → 0 (DOWN)
      Otherwise → dropped (no weak labels)

    Returns (X, y) as numpy arrays.
    """
    X_list = []
    y_list = []

    closes = np.array([c["close"] for c in candles], dtype=float)
    n      = len(candles)

    # We need at least 50 candles to start extracting
    start = 50

    for idx in range(start, n - lookahead):
        # Slice candles and indicator arrays up to this point
        candle_slice = candles[:idx + 1]

        # Slice indicator arrays
        ind_slice = {}
        for key, arr in indicator_results.items():
            if len(arr) >= idx + 1:
                ind_slice[key] = arr[:idx + 1]
            else:
                ind_slice[key] = arr

        feat = extract_features(candle_slice, ind_slice, smc_results)
        if feat is None:
            continue

        # Label: direction over next `lookahead` candles
        future_close   = closes[idx + lookahead]
        current_close  = closes[idx]
        change         = (future_close - current_close) / current_close

        if change > threshold:
            label = 1
        elif change < -threshold:
            label = 0
        else:
            continue   # skip ambiguous

        X_list.append(feat)
        y_list.append(label)

    if not X_list:
        return np.array([]), np.array([])

    return np.array(X_list, dtype=np.float32), np.array(y_list, dtype=np.int32)
