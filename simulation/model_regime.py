# simulation/model_regime.py
"""
Regime-Switching simulation model using Markov Chains.
Identifies 3 market regimes from historical data:
  0 = Trend-Up    (strong positive drift, moderate vol)
  1 = Ranging     (near-zero drift, low vol)
  2 = Trend-Down  (strong negative drift, moderate vol)

Builds a 3×3 transition matrix from observed regime sequences.
Simulates forward: each candle may switch regime per the matrix.
Path segments are coloured by active regime.
"""

import numpy as np
from typing import List, Dict
from simulation.base_model import BaseSimModel, GeneratedPath


N_REGIMES = 3
REGIME_NAMES  = ["Trend-Up", "Ranging", "Trend-Down"]
REGIME_COLORS = ["#00c896",  "#ffb74d", "#ff5252"]


class RegimeSwitchingModel(BaseSimModel):

    MODEL_ID   = "regime_switching"
    MODEL_NAME = "Regime-Switching"
    COLOR      = "#ffb74d"

    def __init__(self):
        super().__init__()
        # Per-regime (mu, sigma)
        self._regime_params = [
            ( 0.0008, 0.012),  # Trend-Up
            ( 0.0000, 0.006),  # Ranging
            (-0.0008, 0.012),  # Trend-Down
        ]
        # Transition matrix rows = from, cols = to
        self._trans = np.array([
            [0.70, 0.20, 0.10],
            [0.25, 0.50, 0.25],
            [0.10, 0.20, 0.70],
        ])
        self._current_regime = 0
        self._atr_val = 0.0

    def fit(self, candles: List[Dict]) -> None:
        if len(candles) < 30:
            return

        returns = self._extract_returns(candles)
        labels  = self._classify_regimes(returns)
        self._atr_val = self._atr(candles)

        # Build transition matrix from observed sequences
        counts = np.ones((N_REGIMES, N_REGIMES))  # Laplace smoothing
        for i in range(len(labels) - 1):
            counts[labels[i], labels[i + 1]] += 1
        self._trans = counts / counts.sum(axis=1, keepdims=True)

        # Fit per-regime (mu, sigma)
        for reg in range(N_REGIMES):
            mask = (labels == reg)
            reg_rets = returns[mask] if mask.sum() > 5 else returns
            mu    = float(np.mean(reg_rets))
            sigma = max(float(np.std(reg_rets)), 1e-6)
            self._regime_params[reg] = (mu, sigma)

        # Start in most recent regime
        self._current_regime = int(labels[-1]) if len(labels) else 0
        self._fitted = True

    def _classify_regimes(self, returns: np.ndarray) -> np.ndarray:
        """Simple threshold-based regime classification."""
        labels = np.full(len(returns), 1, dtype=int)  # default: Ranging
        threshold = np.std(returns) * 0.5
        for i, r in enumerate(returns):
            if r >  threshold:
                labels[i] = 0   # Trend-Up
            elif r < -threshold:
                labels[i] = 2   # Trend-Down
        return labels

    def generate(self, n_candles: int, start_price: float,
                 last_time: int, timeframe_secs: int) -> GeneratedPath:

        if not self._fitted or start_price <= 0:
            return self._fallback(n_candles, start_price, last_time, timeframe_secs)

        rng     = np.random.default_rng()
        regime  = self._current_regime
        price   = start_price
        candles = []
        regime_sequence = []

        for i in range(n_candles):
            # Transition
            regime = int(rng.choice(N_REGIMES, p=self._trans[regime]))
            mu, sigma = self._regime_params[regime]

            shock  = rng.normal(mu, sigma)
            close  = price * np.exp(shock)
            close  = max(close, price * 0.001)

            open_  = price
            atr    = self._atr_val * (1.2 if regime != 1 else 0.7)
            wick   = rng.exponential(atr * 0.2)
            high   = max(open_, close) + wick
            low    = min(open_, close) - rng.exponential(atr * 0.15)
            low    = max(low, close * 0.0001)
            vol    = float(rng.integers(3000, 60000))
            ts     = last_time + (i + 1) * timeframe_secs

            candles.append(self._make_candle(open_, high, low, close, vol, ts))
            regime_sequence.append(regime)
            price = close

        return GeneratedPath(
            candles    = candles,
            model_name = self.MODEL_NAME,
            model_id   = self.MODEL_ID,
            color      = self.COLOR,
            confidence_bands = None,
            metadata   = {
                "regime_sequence":  regime_sequence,
                "regime_names":     REGIME_NAMES,
                "regime_colors":    REGIME_COLORS,
                "transition_matrix": self._trans.tolist(),
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
