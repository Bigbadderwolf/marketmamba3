# simulation/model_agent.py
"""
Agent-Based simulation model.
Three agent types interact to produce emergent price movement:

  Retail (60%)     — momentum-chasers, buy highs, sell lows,
                     cluster around round numbers, panic on drops
  Institutional (30%) — contrarian accumulators, fade extremes,
                        large iceberg orders near value zones
  Market Maker (10%)  — always quotes both sides, profits spread,
                         hunts stop clusters, causes wicks

Price each step = start_price + net_delta / liquidity_factor
"""

import numpy as np
from typing import List, Dict
from simulation.base_model import BaseSimModel, GeneratedPath


class AgentBasedModel(BaseSimModel):

    MODEL_ID   = "agent_based"
    MODEL_NAME = "Agent-Based"
    COLOR      = "#e040fb"

    def __init__(self):
        super().__init__()
        self._volatility   = 0.01
        self._trend_bias   = 0.0
        self._atr_val      = 0.0
        self._avg_volume   = 10000.0
        self._round_levels = []

    def fit(self, candles: List[Dict]) -> None:
        if len(candles) < 20:
            return
        returns = self._extract_returns(candles)
        self._volatility  = max(float(np.std(returns)), 1e-5)
        self._trend_bias  = float(np.mean(returns[-20:]))
        self._atr_val     = self._atr(candles)
        closes = [float(c["close"]) for c in candles]
        self._avg_volume  = float(np.mean([float(c.get("volume", 10000))
                                           for c in candles[-50:]]))
        # Round number levels (psychological S/R)
        price = closes[-1]
        mag   = 10 ** (len(str(int(price))) - 2)
        self._round_levels = [round(price / mag) * mag + i * mag
                               for i in range(-5, 6)]
        self._fitted = True

    def generate(self, n_candles: int, start_price: float,
                 last_time: int, timeframe_secs: int) -> GeneratedPath:

        if not self._fitted or start_price <= 0:
            return self._fallback(n_candles, start_price, last_time, timeframe_secs)

        rng   = np.random.default_rng()
        price = start_price
        candles = []
        momentum = 0.0   # rolling momentum signal

        for i in range(n_candles):

            # ── Retail agents ─────────────────────────────────────────────
            # Momentum-chasing: buy when price going up, sell when going down
            retail_bias    = momentum * 0.6 + rng.normal(0, self._volatility * 0.5)
            retail_volume  = self._avg_volume * rng.uniform(0.3, 1.2) * 0.6
            retail_delta   = retail_bias * retail_volume

            # ── Institutional agents ──────────────────────────────────────
            # Contrarian: fade momentum, accumulate at extremes
            inst_bias      = -momentum * 0.4 + self._trend_bias * 2
            # Larger orders near round levels
            near_round = any(abs(price - lvl) / price < 0.002
                             for lvl in self._round_levels)
            inst_mult      = 2.5 if near_round else 1.0
            inst_volume    = self._avg_volume * rng.uniform(0.5, 2.0) * 0.3 * inst_mult
            inst_delta     = inst_bias * inst_volume

            # ── Market maker ──────────────────────────────────────────────
            # Creates spread + occasional stop hunts (sharp wicks)
            mm_delta       = rng.normal(0, self._avg_volume * 0.02)
            stop_hunt      = rng.random() < 0.05   # 5% chance of stop hunt

            # ── Net price move ────────────────────────────────────────────
            net_delta  = retail_delta + inst_delta + mm_delta
            liq_factor = self._avg_volume * 2.0
            pct_move   = net_delta / liq_factor * self._volatility * 10

            # Clamp extreme moves
            pct_move   = np.clip(pct_move, -0.05, 0.05)

            open_   = price
            close   = price * (1 + pct_move)
            close   = max(close, price * 0.001)

            # Wicks
            base_wick = self._atr_val * 0.15
            if stop_hunt:
                # Market maker creates large wick
                hunt_dir  = 1 if rng.random() > 0.5 else -1
                wick_size = self._atr_val * rng.uniform(0.5, 1.5)
                if hunt_dir > 0:
                    high = max(open_, close) + wick_size
                    low  = min(open_, close) - rng.exponential(base_wick)
                else:
                    high = max(open_, close) + rng.exponential(base_wick)
                    low  = min(open_, close) - wick_size
            else:
                high = max(open_, close) + rng.exponential(base_wick)
                low  = min(open_, close) - rng.exponential(base_wick)

            low  = max(low, close * 0.0001)
            vol  = abs(net_delta) / max(price, 1) * 1e6
            vol  = max(100.0, min(vol, self._avg_volume * 5))
            ts   = last_time + (i + 1) * timeframe_secs

            candles.append(self._make_candle(open_, high, low, close, vol, ts))

            # Update momentum (EMA of returns)
            ret      = (close - open_) / open_
            momentum = 0.8 * momentum + 0.2 * ret
            price    = close

        return GeneratedPath(
            candles    = candles,
            model_name = self.MODEL_NAME,
            model_id   = self.MODEL_ID,
            color      = self.COLOR,
            confidence_bands = None,
            metadata   = {
                "volatility":  self._volatility,
                "trend_bias":  self._trend_bias,
                "avg_volume":  self._avg_volume,
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
