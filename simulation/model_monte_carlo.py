# simulation/model_monte_carlo.py
"""
Monte Carlo simulation model.
Runs N random walks using GBM (Geometric Brownian Motion).
Calibrated on historical log-returns (drift + volatility).
Outputs median path + confidence bands (p10/p25/p75/p90).
"""

import numpy as np
from typing import List, Dict
from simulation.base_model import BaseSimModel, GeneratedPath


class MonteCarloModel(BaseSimModel):

    MODEL_ID   = "monte_carlo"
    MODEL_NAME = "Monte Carlo"
    COLOR      = "#4a9eff"

    N_SIMS     = 500   # number of simulation paths

    def __init__(self):
        super().__init__()
        self._mu    = 0.0   # mean log-return (drift)
        self._sigma = 0.001 # volatility (std of log-returns)
        self._atr_val = 0.0

    def fit(self, candles: List[Dict]) -> None:
        if len(candles) < 10:
            return
        returns      = self._extract_returns(candles)
        self._mu     = float(np.mean(returns))
        self._sigma  = max(float(np.std(returns)), 1e-6)
        self._atr_val = self._atr(candles)
        self._fitted  = True

    def generate(self, n_candles: int, start_price: float,
                 last_time: int, timeframe_secs: int) -> GeneratedPath:

        if not self._fitted or start_price <= 0:
            return self._empty(n_candles, start_price, last_time, timeframe_secs)

        rng = np.random.default_rng()

        # Run N_SIMS paths
        # Shape: (N_SIMS, n_candles)
        shocks   = rng.normal(self._mu, self._sigma,
                              size=(self.N_SIMS, n_candles))
        log_rets = shocks  # already drift-adjusted
        prices   = np.zeros((self.N_SIMS, n_candles + 1))
        prices[:, 0] = start_price
        for t in range(n_candles):
            prices[:, t + 1] = prices[:, t] * np.exp(log_rets[:, t])

        # Percentile bands at each step
        close_paths = prices[:, 1:]  # (N_SIMS, n_candles)
        p10  = np.percentile(close_paths, 10,  axis=0)
        p25  = np.percentile(close_paths, 25,  axis=0)
        p50  = np.percentile(close_paths, 50,  axis=0)
        p75  = np.percentile(close_paths, 75,  axis=0)
        p90  = np.percentile(close_paths, 90,  axis=0)

        # Build median candles
        candles = []
        atr     = self._atr_val
        prev    = start_price

        for i in range(n_candles):
            close = float(p50[i])
            open_ = prev
            wick  = abs(float(p75[i]) - float(p25[i])) * 0.3
            high  = max(open_, close) + rng.exponential(wick * 0.5)
            low   = min(open_, close) - rng.exponential(wick * 0.5)
            low   = max(low, close * 0.0001)
            vol   = float(rng.integers(5000, 80000))
            ts    = last_time + (i + 1) * timeframe_secs
            candles.append(self._make_candle(open_, high, low, close, vol, ts))
            prev  = close

        return GeneratedPath(
            candles          = candles,
            model_name       = self.MODEL_NAME,
            model_id         = self.MODEL_ID,
            color            = self.COLOR,
            confidence_bands = {
                "p10": p10.tolist(), "p25": p25.tolist(),
                "p75": p75.tolist(), "p90": p90.tolist(),
            },
            metadata = {
                "mu": self._mu, "sigma": self._sigma,
                "n_sims": self.N_SIMS,
            },
        )

    def _empty(self, n, price, t0, tf) -> GeneratedPath:
        candles = []
        for i in range(n):
            ts = t0 + (i + 1) * tf
            candles.append(self._make_candle(price, price, price, price, 0, ts))
        return GeneratedPath(candles=candles, model_name=self.MODEL_NAME,
                             model_id=self.MODEL_ID, color=self.COLOR,
                             confidence_bands=None)
