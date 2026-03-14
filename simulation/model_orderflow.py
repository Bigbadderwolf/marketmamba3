# simulation/model_orderflow.py
"""
Order Flow simulation model.
Drives price from simulated buy/sell pressure using
CVD (Cumulative Volume Delta) dynamics calibrated on history.

Models:
  - Buy pressure process: mean-reverting stochastic process
  - Sell pressure process: mean-reverting stochastic process
  - Price moves proportional to net delta imbalance
  - Volume clusters create support/resistance
  - Absorption zones: large volume but small price move
"""

import numpy as np
from typing import List, Dict
from simulation.base_model import BaseSimModel, GeneratedPath


class OrderFlowModel(BaseSimModel):

    MODEL_ID   = "order_flow"
    MODEL_NAME = "Order Flow"
    COLOR      = "#69f0ae"

    def __init__(self):
        super().__init__()
        self._avg_vol       = 10000.0
        self._vol_std       = 5000.0
        self._buy_ratio     = 0.5    # avg fraction of volume that is buying
        self._delta_std     = 0.1    # std of delta imbalance
        self._price_impact  = 0.001  # price move per unit net delta
        self._mean_reversion = 0.3   # delta mean-reversion speed
        self._atr_val       = 0.0
        self._vol_clusters  = []     # (price, volume) high-volume nodes

    def fit(self, candles: List[Dict]) -> None:
        if len(candles) < 20:
            return

        closes  = np.array([float(c["close"])           for c in candles])
        volumes = np.array([float(c.get("volume", 1))   for c in candles])
        opens   = np.array([float(c["open"])             for c in candles])

        self._avg_vol  = float(np.mean(volumes))
        self._vol_std  = float(np.std(volumes))
        self._atr_val  = self._atr(candles)

        # Estimate buy/sell split from candle direction
        bull_mask       = closes > opens
        bull_vol        = volumes[bull_mask].sum()
        total_vol       = volumes.sum()
        self._buy_ratio = float(bull_vol / max(total_vol, 1))

        # CVD-derived delta statistics
        delta = np.where(closes > opens, volumes, -volumes)
        self._delta_std     = max(float(np.std(delta / self._avg_vol)), 0.01)
        self._price_impact  = self._atr_val / max(self._avg_vol, 1) * 0.5

        # Find high-volume clusters (potential S/R zones)
        n_clusters = min(5, len(candles) // 10)
        vol_sorted = np.argsort(volumes)[-n_clusters:]
        self._vol_clusters = [
            (float(closes[i]), float(volumes[i]))
            for i in vol_sorted
        ]

        self._fitted = True

    def generate(self, n_candles: int, start_price: float,
                 last_time: int, timeframe_secs: int) -> GeneratedPath:

        if not self._fitted or start_price <= 0:
            return self._fallback(n_candles, start_price, last_time, timeframe_secs)

        rng      = np.random.default_rng()
        price    = start_price
        delta    = 0.0   # running delta imbalance
        candles  = []
        cvd_path = []

        for i in range(n_candles):
            # Simulate buy and sell volumes
            buy_vol  = max(0, rng.normal(
                self._avg_vol * self._buy_ratio,
                self._vol_std * 0.3
            ))
            sell_vol = max(0, rng.normal(
                self._avg_vol * (1 - self._buy_ratio),
                self._vol_std * 0.3
            ))

            # Absorption: near volume cluster → more opposing pressure
            for cluster_price, cluster_vol in self._vol_clusters:
                dist = abs(price - cluster_price) / max(price, 1)
                if dist < 0.005:
                    # Price is near a volume cluster → absorption
                    absorption = cluster_vol * 0.1
                    if price > cluster_price:
                        sell_vol += absorption
                    else:
                        buy_vol += absorption

            net_delta = buy_vol - sell_vol
            total_vol = buy_vol + sell_vol

            # Delta mean-reversion
            delta = (1 - self._mean_reversion) * delta + self._mean_reversion * net_delta

            # Price impact
            pct_move = delta * self._price_impact / max(price, 1)
            pct_move = float(np.clip(pct_move, -0.04, 0.04))

            open_  = price
            close  = price * (1 + pct_move)
            close  = max(close, price * 0.001)

            # Wicks based on order flow volatility
            atr    = self._atr_val if self._atr_val > 0 else price * 0.002
            high   = max(open_, close) + rng.exponential(atr * 0.15)
            low    = min(open_, close) - rng.exponential(atr * 0.15)
            low    = max(low, close * 0.0001)
            vol    = max(100.0, total_vol)
            ts     = last_time + (i + 1) * timeframe_secs

            candles.append(self._make_candle(open_, high, low, close, vol, ts))
            cvd_path.append(float(delta))
            price = close

        return GeneratedPath(
            candles    = candles,
            model_name = self.MODEL_NAME,
            model_id   = self.MODEL_ID,
            color      = self.COLOR,
            confidence_bands = None,
            metadata   = {
                "cvd_path":   cvd_path,
                "buy_ratio":  self._buy_ratio,
                "avg_volume": self._avg_vol,
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
