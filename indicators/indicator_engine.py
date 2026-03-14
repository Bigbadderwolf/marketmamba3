# indicators/indicator_engine.py
"""
Master indicator computation engine.
Takes raw candle data and computes all indicators.
All calculations are pure numpy/pandas — no external TA library dependency.
Outputs are used by:
  - Chart overlay rendering (Phase 6)
  - ML feature engineering (Phase 4)
  - SMC confluence scoring
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Optional
import logging

log = logging.getLogger(__name__)


def candles_to_df(candles: List[Dict]) -> pd.DataFrame:
    """Convert list of candle dicts to a pandas DataFrame."""
    if not candles:
        return pd.DataFrame()
    df = pd.DataFrame(candles)
    df = df.sort_values("time").reset_index(drop=True)
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


class IndicatorEngine:
    """
    Computes all indicators for a given candle dataset.
    Instantiate once per symbol/timeframe, call compute() on new candles.
    All results stored in self.result dict.
    """

    def __init__(self, params: dict = None):
        """
        params: dict of indicator parameters (from config/settings.py)
        Falls back to defaults if not provided.
        """
        from config.constants import DEFAULT_INDICATOR_PARAMS
        self.params = params or DEFAULT_INDICATOR_PARAMS
        self.result: Dict[str, np.ndarray] = {}
        self.df: Optional[pd.DataFrame] = None

    def compute(self, candles: List[Dict]) -> Dict[str, np.ndarray]:
        """
        Compute all active indicators from candle data.
        Returns dict of indicator_name → numpy array (same length as candles).
        """
        if len(candles) < 2:
            return {}

        self.df = candles_to_df(candles)
        close  = self.df["close"].values
        high   = self.df["high"].values
        low    = self.df["low"].values
        open_  = self.df["open"].values
        volume = self.df["volume"].values if "volume" in self.df.columns else np.zeros(len(close))

        result = {}

        # ── Moving Averages ───────────────────────────────────────────────────
        for period in [9, 21, 50, 200]:
            key = f"EMA_{period}"
            p   = self.params.get(key, {}).get("period", period)
            result[key] = self._ema(close, p)

        result["SMA_20"] = self._sma(close, 20)
        result["SMA_50"] = self._sma(close, 50)

        # ── VWAP ──────────────────────────────────────────────────────────────
        result["VWAP"] = self._vwap(high, low, close, volume)

        # ── RSI ───────────────────────────────────────────────────────────────
        rsi_period = self.params.get("RSI", {}).get("period", 14)
        result["RSI"] = self._rsi(close, rsi_period)

        # ── Stochastic RSI ────────────────────────────────────────────────────
        srsi_params = self.params.get("STOCHRSI", {})
        k, d = self._stoch_rsi(
            result["RSI"],
            srsi_params.get("period", 14),
            srsi_params.get("smooth_k", 3),
            srsi_params.get("smooth_d", 3),
        )
        result["STOCHRSI_K"] = k
        result["STOCHRSI_D"] = d

        # ── MACD ──────────────────────────────────────────────────────────────
        macd_p = self.params.get("MACD", {})
        macd, signal, hist = self._macd(
            close,
            macd_p.get("fast",   12),
            macd_p.get("slow",   26),
            macd_p.get("signal",  9),
        )
        result["MACD"]        = macd
        result["MACD_SIGNAL"] = signal
        result["MACD_HIST"]   = hist

        # ── Bollinger Bands ───────────────────────────────────────────────────
        bb_p = self.params.get("BB", {})
        upper, mid, lower = self._bollinger(
            close,
            bb_p.get("period", 20),
            bb_p.get("std",    2.0),
        )
        result["BB_UPPER"] = upper
        result["BB_MID"]   = mid
        result["BB_LOWER"] = lower

        # ── ATR ───────────────────────────────────────────────────────────────
        atr_period = self.params.get("ATR", {}).get("period", 14)
        result["ATR"] = self._atr(high, low, close, atr_period)

        # ── Keltner Channel ───────────────────────────────────────────────────
        kc_upper, kc_mid, kc_lower = self._keltner(
            high, low, close, result["EMA_21"], result["ATR"]
        )
        result["KC_UPPER"] = kc_upper
        result["KC_MID"]   = kc_mid
        result["KC_LOWER"] = kc_lower

        # ── Ichimoku Cloud ────────────────────────────────────────────────────
        tenkan, kijun, span_a, span_b, chikou = self._ichimoku(high, low, close)
        result["ICHI_TENKAN"]  = tenkan
        result["ICHI_KIJUN"]   = kijun
        result["ICHI_SPAN_A"]  = span_a
        result["ICHI_SPAN_B"]  = span_b
        result["ICHI_CHIKOU"]  = chikou

        # ── Volume indicators ─────────────────────────────────────────────────
        result["OBV"] = self._obv(close, volume)
        result["CVD"] = self._cvd(open_, close, volume)

        # ── CCI ───────────────────────────────────────────────────────────────
        result["CCI"] = self._cci(high, low, close, 20)

        # ── ADX ───────────────────────────────────────────────────────────────
        adx, plus_di, minus_di = self._adx(high, low, close, 14)
        result["ADX"]       = adx
        result["PLUS_DI"]   = plus_di
        result["MINUS_DI"]  = minus_di

        self.result = result
        return result

    def get_latest(self, indicator: str) -> float:
        """Get the most recent value of an indicator."""
        arr = self.result.get(indicator)
        if arr is None or len(arr) == 0:
            return 0.0
        val = arr[-1]
        return float(val) if not np.isnan(val) else 0.0

    def get_series(self, indicator: str, n: int = None) -> np.ndarray:
        """Get last N values of an indicator."""
        arr = self.result.get(indicator, np.array([]))
        if n:
            return arr[-n:]
        return arr

    # ── Computation methods ───────────────────────────────────────────────────

    @staticmethod
    def _sma(data: np.ndarray, period: int) -> np.ndarray:
        result = np.full(len(data), np.nan)
        if len(data) < period:
            return result
        for i in range(period - 1, len(data)):
            result[i] = np.mean(data[i - period + 1:i + 1])
        return result

    @staticmethod
    def _ema(data: np.ndarray, period: int) -> np.ndarray:
        result = np.full(len(data), np.nan)
        if len(data) < period:
            return result
        k = 2.0 / (period + 1)
        # Seed with SMA
        result[period - 1] = np.mean(data[:period])
        for i in range(period, len(data)):
            result[i] = data[i] * k + result[i - 1] * (1 - k)
        return result

    @staticmethod
    def _vwap(high: np.ndarray, low: np.ndarray,
              close: np.ndarray, volume: np.ndarray) -> np.ndarray:
        typical = (high + low + close) / 3
        cum_vol = np.cumsum(volume)
        cum_tp_vol = np.cumsum(typical * volume)
        with np.errstate(divide="ignore", invalid="ignore"):
            vwap = np.where(cum_vol > 0, cum_tp_vol / cum_vol, typical)
        return vwap

    @staticmethod
    def _rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
        result = np.full(len(close), np.nan)
        if len(close) < period + 1:
            return result
        deltas = np.diff(close)
        gains  = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)

        avg_gain = np.mean(gains[:period])
        avg_loss = np.mean(losses[:period])

        for i in range(period, len(close)):
            avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
            if avg_loss == 0:
                result[i] = 100.0
            else:
                rs = avg_gain / avg_loss
                result[i] = 100.0 - (100.0 / (1.0 + rs))
        return result

    def _stoch_rsi(self, rsi: np.ndarray, period: int = 14,
                   smooth_k: int = 3, smooth_d: int = 3):
        stoch = np.full(len(rsi), np.nan)
        for i in range(period - 1, len(rsi)):
            window = rsi[i - period + 1:i + 1]
            valid  = window[~np.isnan(window)]
            if len(valid) < period:
                continue
            lo = np.min(valid)
            hi = np.max(valid)
            if hi - lo == 0:
                stoch[i] = 0.0
            else:
                stoch[i] = (rsi[i] - lo) / (hi - lo) * 100

        k = self._sma(stoch, smooth_k)
        d = self._sma(k,     smooth_d)
        return k, d

    def _macd(self, close: np.ndarray,
              fast: int = 12, slow: int = 26, signal: int = 9):
        ema_fast   = self._ema(close, fast)
        ema_slow   = self._ema(close, slow)
        macd_line  = ema_fast - ema_slow
        signal_line = self._ema(macd_line, signal)
        histogram  = macd_line - signal_line
        return macd_line, signal_line, histogram

    def _bollinger(self, close: np.ndarray, period: int = 20, std: float = 2.0):
        mid   = self._sma(close, period)
        sigma = np.full(len(close), np.nan)
        for i in range(period - 1, len(close)):
            sigma[i] = np.std(close[i - period + 1:i + 1], ddof=0)
        upper = mid + std * sigma
        lower = mid - std * sigma
        return upper, mid, lower

    @staticmethod
    def _atr(high: np.ndarray, low: np.ndarray,
             close: np.ndarray, period: int = 14) -> np.ndarray:
        result = np.full(len(close), np.nan)
        if len(close) < 2:
            return result
        tr = np.maximum(
            high[1:] - low[1:],
            np.maximum(
                np.abs(high[1:] - close[:-1]),
                np.abs(low[1:]  - close[:-1])
            )
        )
        if len(tr) < period:
            return result
        result[period] = np.mean(tr[:period])
        for i in range(period + 1, len(close)):
            result[i] = (result[i - 1] * (period - 1) + tr[i - 1]) / period
        return result

    @staticmethod
    def _keltner(high, low, close, ema21, atr, multiplier=2.0):
        upper = ema21 + multiplier * atr
        lower = ema21 - multiplier * atr
        return upper, ema21.copy(), lower

    @staticmethod
    def _ichimoku(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                  tenkan_p=9, kijun_p=26, span_b_p=52, displacement=26):
        n = len(close)
        tenkan = np.full(n, np.nan)
        kijun  = np.full(n, np.nan)
        span_a = np.full(n, np.nan)
        span_b = np.full(n, np.nan)
        chikou = np.full(n, np.nan)

        for i in range(tenkan_p - 1, n):
            tenkan[i] = (np.max(high[i-tenkan_p+1:i+1]) +
                         np.min(low[i-tenkan_p+1:i+1])) / 2

        for i in range(kijun_p - 1, n):
            kijun[i] = (np.max(high[i-kijun_p+1:i+1]) +
                        np.min(low[i-kijun_p+1:i+1])) / 2

        for i in range(kijun_p - 1, n):
            if not np.isnan(tenkan[i]) and not np.isnan(kijun[i]):
                idx = min(i + displacement, n - 1)
                span_a[idx] = (tenkan[i] + kijun[i]) / 2

        for i in range(span_b_p - 1, n):
            idx = min(i + displacement, n - 1)
            span_b[idx] = (np.max(high[i-span_b_p+1:i+1]) +
                           np.min(low[i-span_b_p+1:i+1])) / 2

        for i in range(n):
            idx = i - displacement
            if 0 <= idx < n:
                chikou[idx] = close[i]

        return tenkan, kijun, span_a, span_b, chikou

    @staticmethod
    def _obv(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
        obv = np.zeros(len(close))
        for i in range(1, len(close)):
            if close[i] > close[i - 1]:
                obv[i] = obv[i - 1] + volume[i]
            elif close[i] < close[i - 1]:
                obv[i] = obv[i - 1] - volume[i]
            else:
                obv[i] = obv[i - 1]
        return obv

    @staticmethod
    def _cvd(open_: np.ndarray, close: np.ndarray,
             volume: np.ndarray) -> np.ndarray:
        """Cumulative Volume Delta — approximated from candle direction."""
        delta = np.where(close >= open_, volume, -volume)
        return np.cumsum(delta)

    @staticmethod
    def _cci(high, low, close, period=20):
        result = np.full(len(close), np.nan)
        typical = (high + low + close) / 3
        for i in range(period - 1, len(close)):
            tp_window = typical[i - period + 1:i + 1]
            mean_tp   = np.mean(tp_window)
            mean_dev  = np.mean(np.abs(tp_window - mean_tp))
            if mean_dev == 0:
                result[i] = 0.0
            else:
                result[i] = (typical[i] - mean_tp) / (0.015 * mean_dev)
        return result

    @staticmethod
    def _adx(high, low, close, period=14):
        n      = len(close)
        adx    = np.full(n, np.nan)
        pdi    = np.full(n, np.nan)
        mdi    = np.full(n, np.nan)

        if n < period + 1:
            return adx, pdi, mdi

        tr_arr  = np.full(n, np.nan)
        pdm_arr = np.full(n, np.nan)
        mdm_arr = np.full(n, np.nan)

        for i in range(1, n):
            tr_arr[i]  = max(high[i] - low[i],
                             abs(high[i] - close[i-1]),
                             abs(low[i]  - close[i-1]))
            up_move   = high[i] - high[i-1]
            down_move = low[i-1] - low[i]
            pdm_arr[i] = up_move   if up_move > down_move and up_move > 0 else 0
            mdm_arr[i] = down_move if down_move > up_move and down_move > 0 else 0

        atr14  = np.full(n, np.nan)
        pdm14  = np.full(n, np.nan)
        mdm14  = np.full(n, np.nan)

        atr14[period]  = np.sum(tr_arr[1:period+1])
        pdm14[period]  = np.sum(pdm_arr[1:period+1])
        mdm14[period]  = np.sum(mdm_arr[1:period+1])

        for i in range(period + 1, n):
            atr14[i]  = atr14[i-1]  - atr14[i-1]/period  + tr_arr[i]
            pdm14[i]  = pdm14[i-1]  - pdm14[i-1]/period  + pdm_arr[i]
            mdm14[i]  = mdm14[i-1]  - mdm14[i-1]/period  + mdm_arr[i]

        dx = np.full(n, np.nan)
        for i in range(period, n):
            if atr14[i] == 0:
                continue
            pdi[i] = 100 * pdm14[i] / atr14[i]
            mdi[i] = 100 * mdm14[i] / atr14[i]
            dsum   = pdi[i] + mdi[i]
            if dsum == 0:
                dx[i] = 0
            else:
                dx[i] = 100 * abs(pdi[i] - mdi[i]) / dsum

        adx[2*period] = np.nanmean(dx[period:2*period+1])
        for i in range(2*period + 1, n):
            if not np.isnan(dx[i]):
                adx[i] = (adx[i-1] * (period-1) + dx[i]) / period

        return adx, pdi, mdi

    # ── Signal generation ─────────────────────────────────────────────────────

    def get_signals(self) -> Dict[str, str]:
        """
        Generate buy/sell/neutral signals from current indicator values.
        Returns dict of indicator_name → "BUY" | "SELL" | "NEUTRAL"
        """
        signals = {}
        r = self.result
        if not r:
            return signals

        # RSI signals
        rsi = self.get_latest("RSI")
        ob  = self.params.get("RSI", {}).get("overbought", 70)
        os_ = self.params.get("RSI", {}).get("oversold",   30)
        if rsi > 0:
            if rsi >= ob:
                signals["RSI"] = "SELL"
            elif rsi <= os_:
                signals["RSI"] = "BUY"
            else:
                signals["RSI"] = "NEUTRAL"

        # MACD signals
        macd   = self.get_latest("MACD")
        sig    = self.get_latest("MACD_SIGNAL")
        hist   = self.get_latest("MACD_HIST")
        if macd != 0:
            if hist > 0 and macd > sig:
                signals["MACD"] = "BUY"
            elif hist < 0 and macd < sig:
                signals["MACD"] = "SELL"
            else:
                signals["MACD"] = "NEUTRAL"

        # EMA trend signals (price vs EMA 200)
        close  = self.df["close"].iloc[-1] if self.df is not None else 0
        ema200 = self.get_latest("EMA_200")
        ema50  = self.get_latest("EMA_50")
        ema21  = self.get_latest("EMA_21")
        if ema200 > 0:
            if close > ema200 and ema21 > ema50:
                signals["EMA_TREND"] = "BUY"
            elif close < ema200 and ema21 < ema50:
                signals["EMA_TREND"] = "SELL"
            else:
                signals["EMA_TREND"] = "NEUTRAL"

        # Stoch RSI signals
        stoch_k = self.get_latest("STOCHRSI_K")
        stoch_d = self.get_latest("STOCHRSI_D")
        if stoch_k > 0:
            if stoch_k < 20 and stoch_d < 20:
                signals["STOCHRSI"] = "BUY"
            elif stoch_k > 80 and stoch_d > 80:
                signals["STOCHRSI"] = "SELL"
            else:
                signals["STOCHRSI"] = "NEUTRAL"

        # Bollinger Band signals
        bb_upper = self.get_latest("BB_UPPER")
        bb_lower = self.get_latest("BB_LOWER")
        if bb_upper > 0 and close > 0:
            if close <= bb_lower:
                signals["BB"] = "BUY"
            elif close >= bb_upper:
                signals["BB"] = "SELL"
            else:
                signals["BB"] = "NEUTRAL"

        # ADX trend strength
        adx = self.get_latest("ADX")
        if adx > 0:
            signals["ADX_STRENGTH"] = (
                "STRONG" if adx > 25 else
                "WEAK"   if adx < 20 else
                "NEUTRAL"
            )

        return signals

    def get_confluence_score(self) -> int:
        """
        Calculate overall confluence score: -100 to +100.
        Positive = bullish confluence, Negative = bearish confluence.
        Used by ML feature engineering and prediction overlay.
        """
        signals = self.get_signals()
        score   = 0
        weights = {
            "RSI":        15,
            "MACD":       20,
            "EMA_TREND":  25,
            "STOCHRSI":   15,
            "BB":         15,
        }
        for key, weight in weights.items():
            sig = signals.get(key, "NEUTRAL")
            if sig == "BUY":
                score += weight
            elif sig == "SELL":
                score -= weight

        return max(-100, min(100, score))
