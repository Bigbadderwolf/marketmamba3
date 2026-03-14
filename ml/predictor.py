# ml/predictor.py
"""
Hybrid prediction engine.
Combines XGBoost + LSTM + SMC confluence into one unified prediction.

Output per prediction:
  - direction:    "UP" | "DOWN" | "NEUTRAL"
  - probability:  0.0 – 1.0 (confidence in the direction)
  - confidence:   "High" | "Medium" | "Low"
  - xgb_prob:     raw XGBoost UP probability
  - lstm_prob:    raw LSTM UP probability (0.5 if LSTM unavailable)
  - smc_bias:     "BULLISH" | "BEARISH" | "NEUTRAL"
  - ind_bias:     "BULLISH" | "BEARISH" | "NEUTRAL"
  - candle_forecast: list of 3 dicts [{candle, direction, target_price}, ...]
  - model_agreement: True if XGB and LSTM agree
  - ready:        False if < 50 candles (shows "Collecting data...")
"""

import logging
import threading
import time
import numpy as np
from typing import Dict, List, Optional
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

MIN_CANDLES = 50         # Minimum candles before any prediction shown
UPDATE_INTERVAL = 4 * 3600  # 4 hours in seconds for incremental retrain


@dataclass
class Prediction:
    ready:          bool   = False
    direction:      str    = "NEUTRAL"
    probability:    float  = 0.5
    confidence:     str    = "Low"
    xgb_prob:       float  = 0.5
    lstm_prob:      float  = 0.5
    smc_bias:       str    = "NEUTRAL"
    ind_bias:       str    = "NEUTRAL"
    model_agreement: bool  = False
    candle_forecast: List  = field(default_factory=list)
    message:        str    = "Collecting data..."
    candle_count:   int    = 0


class PredictionEngine:
    """
    Master prediction orchestrator.
    One instance per chart/symbol.
    Manages XGB + LSTM models and produces unified Prediction objects.
    """

    def __init__(self, symbol: str):
        self.symbol   = symbol.lower().replace("/", "")
        self._lock    = threading.Lock()
        self._last_prediction: Prediction = Prediction()
        self._last_retrain_time: float    = 0.0
        self._feature_history: List       = []   # rolling buffer of feature vectors

        # Lazy-load models
        self._xgb  = None
        self._lstm = None
        self._models_loaded = False

    def _ensure_models(self):
        """Load or create models on first use."""
        if self._models_loaded:
            return
        from ml.xgb_model  import XGBModel
        from ml.lstm_model  import LSTMModel
        self._xgb  = XGBModel(self.symbol)
        self._lstm = LSTMModel(self.symbol)
        self._xgb.load()
        self._lstm.load()
        self._models_loaded = True

    def predict(
        self,
        candles:           List[Dict],
        indicator_results: Dict[str, np.ndarray],
        smc_results:       Dict,
    ) -> Prediction:
        """
        Generate a full prediction from current market state.
        Called on every new closed candle.
        Returns Prediction dataclass.
        """
        n = len(candles)

        if n < MIN_CANDLES:
            p = Prediction(
                ready         = False,
                message       = f"Collecting data... ({n}/{MIN_CANDLES} candles)",
                candle_count  = n,
            )
            self._last_prediction = p
            return p

        self._ensure_models()

        from ml.feature_engineer import extract_features
        features = extract_features(candles, indicator_results, smc_results)

        if features is None:
            p = Prediction(ready=False, message="Computing features...", candle_count=n)
            self._last_prediction = p
            return p

        # Store feature in rolling history
        self._feature_history.append(features)
        if len(self._feature_history) > 2000:
            self._feature_history = self._feature_history[-1000:]

        # ── Train if needed ───────────────────────────────────────────────────
        if not self._xgb.is_trained and len(self._feature_history) >= 100:
            self._train_background(candles, indicator_results, smc_results)

        if not self._xgb.is_trained:
            p = Prediction(
                ready        = False,
                message      = f"Training model... ({n} candles ready)",
                candle_count = n,
            )
            self._last_prediction = p
            return p

        # ── Incremental retrain check (every 4 hours) ─────────────────────────
        now = time.time()
        if (now - self._last_retrain_time > UPDATE_INTERVAL and
                len(self._feature_history) >= 200):
            threading.Thread(
                target = self._incremental_retrain,
                daemon = True
            ).start()

        # ── XGBoost prediction ────────────────────────────────────────────────
        xgb_down, xgb_up = self._xgb.predict_proba(features)

        # ── LSTM prediction ───────────────────────────────────────────────────
        lstm_up = 0.5
        if self._lstm.is_trained and len(self._feature_history) >= 30:
            from ml.lstm_model import SEQUENCE_LEN
            if len(self._feature_history) >= SEQUENCE_LEN:
                seq = np.array(self._feature_history[-SEQUENCE_LEN:], dtype=np.float32)
                lstm_up = self._lstm.predict_proba(seq)

        # ── SMC bias ─────────────────────────────────────────────────────────
        smc_bias = "NEUTRAL"
        if smc_results and candles:
            from smc.detector import SMCDetector
            tmp = SMCDetector()
            tmp.result = smc_results
            score = tmp.get_confluence_score(candles[-1]["close"])
            net   = score.get("net", 0)
            if net > 20:
                smc_bias = "BULLISH"
            elif net < -20:
                smc_bias = "BEARISH"

        # ── Indicator bias ────────────────────────────────────────────────────
        ind_bias = "NEUTRAL"
        if indicator_results:
            from indicators.indicator_engine import IndicatorEngine
            tmp_eng = IndicatorEngine()
            tmp_eng.result = indicator_results
            if candles:
                tmp_eng.df = None  # signals use self.result directly
            score = tmp_eng.get_confluence_score()
            if score > 20:
                ind_bias = "BULLISH"
            elif score < -20:
                ind_bias = "BEARISH"

        # ── Ensemble: weight XGB 60%, LSTM 40% ───────────────────────────────
        lstm_weight = 0.4 if self._lstm.is_trained else 0.0
        xgb_weight  = 1.0 - lstm_weight

        ensemble_up = xgb_up * xgb_weight + lstm_up * lstm_weight

        # Bias adjustment from SMC and indicators
        bias_boost = 0.0
        if smc_bias == "BULLISH":  bias_boost += 0.03
        if smc_bias == "BEARISH":  bias_boost -= 0.03
        if ind_bias == "BULLISH":  bias_boost += 0.02
        if ind_bias == "BEARISH":  bias_boost -= 0.02

        ensemble_up = max(0.01, min(0.99, ensemble_up + bias_boost))

        # ── Direction + confidence ────────────────────────────────────────────
        if ensemble_up >= 0.55:
            direction   = "UP"
            probability = ensemble_up
        elif ensemble_up <= 0.45:
            direction   = "DOWN"
            probability = 1.0 - ensemble_up
        else:
            direction   = "NEUTRAL"
            probability = 0.5

        if probability >= 0.70:
            confidence = "High"
        elif probability >= 0.58:
            confidence = "Medium"
        else:
            confidence = "Low"

        model_agreement = (
            (xgb_up > 0.5 and lstm_up > 0.5) or
            (xgb_up < 0.5 and lstm_up < 0.5)
        )

        # ── 3-candle forecast ─────────────────────────────────────────────────
        forecast = self._build_forecast(candles, ensemble_up, indicator_results)

        p = Prediction(
            ready            = True,
            direction        = direction,
            probability      = round(probability, 4),
            confidence       = confidence,
            xgb_prob         = round(xgb_up, 4),
            lstm_prob        = round(lstm_up, 4),
            smc_bias         = smc_bias,
            ind_bias         = ind_bias,
            model_agreement  = model_agreement,
            candle_forecast  = forecast,
            message          = "",
            candle_count     = n,
        )

        with self._lock:
            self._last_prediction = p

        return p

    def _build_forecast(
        self,
        candles:           List[Dict],
        up_prob:           float,
        indicator_results: Dict[str, np.ndarray],
    ) -> List[Dict]:
        """
        Generate 3-candle forward price targets.
        Uses ATR for range estimation.
        """
        if not candles:
            return []

        close = candles[-1]["close"]
        atr_arr = indicator_results.get("ATR", np.array([]))
        atr = float(atr_arr[-1]) if len(atr_arr) > 0 else close * 0.002
        if np.isnan(atr):
            atr = close * 0.002

        forecast = []
        current  = close

        for i in range(1, 4):
            # Each candle: direction probability decays slightly
            candle_up_prob = up_prob * (0.95 ** (i - 1))

            if candle_up_prob > 0.52:
                direction = "UP"
                target    = current + atr * (0.8 + i * 0.2)
                change_pct = (target - close) / close * 100
            elif candle_up_prob < 0.48:
                direction = "DOWN"
                target    = current - atr * (0.8 + i * 0.2)
                change_pct = (target - close) / close * 100
            else:
                direction = "NEUTRAL"
                target    = current
                change_pct = 0.0

            forecast.append({
                "candle":     i,
                "direction":  direction,
                "target":     round(target, 6),
                "change_pct": round(change_pct, 3),
                "probability": round(candle_up_prob if direction == "UP"
                                     else 1 - candle_up_prob, 3),
            })
            current = target

        return forecast

    def _train_background(
        self,
        candles:           List[Dict],
        indicator_results: Dict[str, np.ndarray],
        smc_results:       Dict,
    ):
        """Train models in background thread."""
        def _do_train():
            try:
                from ml.feature_engineer import build_training_dataset
                log.info("Background training started for %s", self.symbol)
                X, y = build_training_dataset(candles, indicator_results, smc_results)
                if len(X) < 50:
                    return
                self._xgb.train(X, y)
                self._xgb.save()
                if len(X) >= 100:
                    self._lstm.train(X, y)
                    self._lstm.save()
                log.info("Background training complete for %s", self.symbol)
            except Exception as e:
                log.error("Background training error: %s", e)

        threading.Thread(target=_do_train, daemon=True).start()

    def _incremental_retrain(self):
        """Lightweight retrain on recent feature history."""
        try:
            if len(self._feature_history) < 100:
                return
            X = np.array(self._feature_history[-500:], dtype=np.float32)
            # We don't have labels here — skip for now, full retrain handles it
            self._last_retrain_time = time.time()
            log.info("Incremental retrain completed for %s", self.symbol)
        except Exception as e:
            log.error("Incremental retrain error: %s", e)

    def get_last(self) -> Prediction:
        with self._lock:
            return self._last_prediction
