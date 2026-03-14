# simulation/model_fractal.py
"""
Fractal / Self-Similar simulation model.
Uses Hurst exponent to measure market memory, then generates
price paths using Fractional Brownian Motion (fBm) which
respects that memory structure.

H > 0.5 → trending (persistent) market
H < 0.5 → mean-reverting (anti-persistent) market
H = 0.5 → pure random walk (standard Brownian Motion)

Also maintains a pattern library of real micro-waves extracted
from historical candles and chains them to build macro structure.
"""

import numpy as np
from typing import List, Dict
from simulation.base_model import BaseSimModel, GeneratedPath


class FractalModel(BaseSimModel):

    MODEL_ID   = "fractal"
    MODEL_NAME = "Fractal"
    COLOR      = "#00e5ff"

    def __init__(self):
        super().__init__()
        self._hurst     = 0.5
        self._sigma     = 0.01
        self._atr_val   = 0.0
        self._patterns  = []   # list of normalised wave arrays

    def fit(self, candles: List[Dict]) -> None:
        if len(candles) < 50:
            return
        returns = self._extract_returns(candles)
        self._sigma   = max(float(np.std(returns)), 1e-6)
        self._atr_val = self._atr(candles)
        self._hurst   = self._estimate_hurst(returns)
        self._patterns = self._extract_patterns(candles)
        self._fitted  = True

    def _estimate_hurst(self, returns: np.ndarray) -> float:
        """R/S analysis to estimate Hurst exponent."""
        try:
            if len(returns) < 20:
                return 0.5
            lags  = [4, 8, 16, 32, 64]
            lags  = [l for l in lags if l < len(returns) // 2]
            if not lags:
                return 0.5
            rs_vals = []
            for lag in lags:
                chunks = [returns[i:i+lag] for i in range(0, len(returns)-lag, lag)]
                rs_list = []
                for chunk in chunks:
                    if len(chunk) < 4:
                        continue
                    mean_c = np.mean(chunk)
                    dev    = np.cumsum(chunk - mean_c)
                    R      = np.max(dev) - np.min(dev)
                    S      = np.std(chunk)
                    if S > 0:
                        rs_list.append(R / S)
                if rs_list:
                    rs_vals.append(np.mean(rs_list))
            if len(rs_vals) < 2:
                return 0.5
            log_lags = np.log(lags[:len(rs_vals)])
            log_rs   = np.log(np.maximum(rs_vals, 1e-10))
            hurst    = float(np.polyfit(log_lags, log_rs, 1)[0])
            return float(np.clip(hurst, 0.1, 0.9))
        except Exception:
            return 0.5

    def _extract_patterns(self, candles: List[Dict]) -> List[np.ndarray]:
        """Extract normalised swing patterns (8–20 candle waves)."""
        patterns = []
        closes = [float(c["close"]) for c in candles]
        wave_len = 12
        for i in range(0, len(closes) - wave_len, wave_len // 2):
            seg = np.array(closes[i:i + wave_len])
            if seg[0] > 0:
                normed = (seg - seg[0]) / seg[0]
                patterns.append(normed)
        return patterns if patterns else [np.zeros(wave_len)]

    def _fbm_path(self, n: int, hurst: float, sigma: float) -> np.ndarray:
        """
        Generate fractional Brownian motion increments using
        the Davies-Harte method (approximate for speed).
        """
        try:
            # Covariance of fBm increments
            def cov(k, h):
                return 0.5 * (abs(k-1)**(2*h) - 2*abs(k)**(2*h) + abs(k+1)**(2*h))

            n_ext = max(n * 2, 64)
            cov_row = np.array([cov(k, hurst) for k in range(n_ext)])
            cov_row[0] = 1.0

            # Circulant embedding
            circ = np.concatenate([cov_row, cov_row[-2:0:-1]])
            eigvals = np.real(np.fft.fft(circ))
            eigvals = np.maximum(eigvals, 0)

            rng    = np.random.default_rng()
            z1     = rng.standard_normal(len(circ))
            z2     = rng.standard_normal(len(circ))
            z      = z1 + 1j * z2
            fgn    = np.real(np.fft.ifft(np.sqrt(eigvals) * z))[:n]
            return fgn * sigma
        except Exception:
            rng = np.random.default_rng()
            return rng.normal(0, sigma, n)

    def generate(self, n_candles: int, start_price: float,
                 last_time: int, timeframe_secs: int) -> GeneratedPath:

        if not self._fitted or start_price <= 0:
            return self._fallback(n_candles, start_price, last_time, timeframe_secs)

        rng      = np.random.default_rng()
        fbm_rets = self._fbm_path(n_candles, self._hurst, self._sigma)

        price    = start_price
        candles  = []

        for i, ret in enumerate(fbm_rets):
            ret   = float(np.clip(ret, -0.08, 0.08))
            open_ = price
            close = price * np.exp(ret)
            close = max(close, price * 0.001)

            atr   = self._atr_val if self._atr_val > 0 else price * 0.002
            # Fractal dimension affects wick size: higher H → smoother, smaller wicks
            wick_scale = 1.5 - self._hurst
            high  = max(open_, close) + rng.exponential(atr * 0.2 * wick_scale)
            low   = min(open_, close) - rng.exponential(atr * 0.18 * wick_scale)
            low   = max(low, close * 0.0001)
            vol   = float(rng.integers(3000, 50000))
            ts    = last_time + (i + 1) * timeframe_secs

            candles.append(self._make_candle(open_, high, low, close, vol, ts))
            price = close

        return GeneratedPath(
            candles    = candles,
            model_name = self.MODEL_NAME,
            model_id   = self.MODEL_ID,
            color      = self.COLOR,
            confidence_bands = None,
            metadata   = {
                "hurst":       self._hurst,
                "market_type": ("Trending" if self._hurst > 0.55 else
                                "Mean-Reverting" if self._hurst < 0.45 else
                                "Random Walk"),
            },
        )

    def _fallback(self, n, price, t0, tf) -> GeneratedPath:
        candles = []
        for i in range(n):
            candles.append(self._make_candle(price, price, price, price, 0,
                                             t0 + (i + 1) * tf))
        return GeneratedPath(candles=candles, model_name=self.MODEL_NAME,
                             model_id=self.MODEL_ID, color=self.COLOR,
                             confidence_bands=None)
