# ml/startup_trainer.py
"""
Startup ML trainer.
On app launch, loads cached historical candles from SQLite,
runs indicator + SMC computation, builds training dataset,
trains XGBoost (and LSTM if TF available), saves models.

Runs entirely in a background thread so the UI is never blocked.
Emits progress via a callback function.
"""

import threading
import logging
import time
import numpy as np
from typing import Callable, Optional, List, Dict

log = logging.getLogger(__name__)

# Minimum candles needed to train a useful model
MIN_TRAIN_CANDLES = 200
# Training timeframe — 1h gives best signal-to-noise for ML
TRAIN_TIMEFRAME   = "1h"


class StartupTrainer:
    """
    Loads cached candles → computes indicators + SMC →
    builds feature dataset → trains XGB + LSTM → saves.

    progress_cb(symbol, step, pct, message) called throughout.
    done_cb(symbol, xgb_acc, lstm_acc) called on completion.
    """

    def __init__(
        self,
        symbols:     List[str],
        progress_cb: Optional[Callable] = None,
        done_cb:     Optional[Callable] = None,
    ):
        self.symbols     = [s.lower() for s in symbols]
        self.progress_cb = progress_cb or (lambda *a: None)
        self.done_cb     = done_cb     or (lambda *a: None)
        self._thread:    Optional[threading.Thread] = None
        self._cancelled  = False

    def start(self):
        """Launch training in background thread."""
        self._thread = threading.Thread(
            target  = self._run,
            daemon  = True,
            name    = "StartupTrainer",
        )
        self._thread.start()
        log.info("StartupTrainer started for %d symbols", len(self.symbols))

    def cancel(self):
        self._cancelled = True

    def _emit(self, symbol: str, step: str, pct: int, msg: str):
        try:
            self.progress_cb(symbol, step, pct, msg)
        except Exception:
            pass

    def _run(self):
        for symbol in self.symbols:
            if self._cancelled:
                break
            try:
                self._train_symbol(symbol)
            except Exception as e:
                log.error("StartupTrainer error for %s: %s", symbol, e)

    def _train_symbol(self, symbol: str):
        from data.data_cache import load_cached_candles, get_cache_range
        from indicators.indicator_engine import IndicatorEngine
        from smc.detector import SMCDetector
        from ml.feature_engineer import build_training_dataset
        from ml.xgb_model import XGBModel
        from ml.lstm_model import LSTMModel

        # ── Step 1: Check cache ───────────────────────────────────────────────
        self._emit(symbol, "cache", 0, f"Checking candle cache for {symbol}...")

        rng = get_cache_range(symbol, TRAIN_TIMEFRAME)
        if not rng or rng[2] < MIN_TRAIN_CANDLES:
            # Try 1m as fallback
            rng = get_cache_range(symbol, "1m")
            tf  = "1m"
        else:
            tf  = TRAIN_TIMEFRAME

        if not rng or rng[2] < MIN_TRAIN_CANDLES:
            self._emit(symbol, "cache", 5,
                       f"{symbol}: only {rng[2] if rng else 0} candles cached "
                       f"(need {MIN_TRAIN_CANDLES}) — skipping training")
            log.warning("Insufficient cache for %s, skipping", symbol)
            return

        count = rng[2]
        self._emit(symbol, "cache", 5, f"{symbol}: {count:,} candles found in cache")
        time.sleep(0.1)

        # ── Step 2: Load candles ──────────────────────────────────────────────
        self._emit(symbol, "load", 10, f"Loading {count:,} candles...")
        candles = load_cached_candles(symbol, tf, limit=min(count, 20000))

        if len(candles) < MIN_TRAIN_CANDLES:
            self._emit(symbol, "load", 15, f"Not enough candles after load ({len(candles)})")
            return

        self._emit(symbol, "load", 15, f"Loaded {len(candles):,} candles ✓")
        time.sleep(0.05)

        # ── Step 3: Compute indicators ────────────────────────────────────────
        self._emit(symbol, "indicators", 20, "Computing indicators...")
        engine = IndicatorEngine()
        try:
            indicator_results = engine.compute(candles)
        except Exception as e:
            log.error("Indicator compute failed for %s: %s", symbol, e)
            indicator_results = {}

        self._emit(symbol, "indicators", 35, f"Indicators computed ✓")
        time.sleep(0.05)

        # ── Step 4: Compute SMC ───────────────────────────────────────────────
        self._emit(symbol, "smc", 38, "Computing SMC features...")
        detector = SMCDetector()
        try:
            smc_results = detector.detect(candles)
        except Exception as e:
            log.error("SMC detect failed for %s: %s", symbol, e)
            smc_results = {}

        self._emit(symbol, "smc", 45, "SMC features computed ✓")
        time.sleep(0.05)

        # ── Step 5: Build feature dataset ────────────────────────────────────
        self._emit(symbol, "features", 48, "Engineering features...")
        try:
            X, y = build_training_dataset(candles, indicator_results, smc_results)
        except Exception as e:
            log.error("Feature build failed for %s: %s", symbol, e)
            return

        if len(X) < 50:
            self._emit(symbol, "features", 50,
                       f"Too few training samples ({len(X)}) — skipping")
            return

        self._emit(symbol, "features", 55,
                   f"Built {len(X):,} training samples "
                   f"({int(np.sum(y==1))} UP / {int(np.sum(y==0))} DOWN) ✓")
        time.sleep(0.05)

        # ── Step 6: Train XGBoost ─────────────────────────────────────────────
        self._emit(symbol, "xgb", 58, "Training XGBoost model...")
        xgb = XGBModel(symbol)
        if xgb.load():
            self._emit(symbol, "xgb", 72,
                       f"XGBoost loaded from disk (acc={xgb.train_accuracy:.3f}) ✓")
        else:
            t0      = time.time()
            xgb_acc = xgb.train(X, y)
            elapsed = time.time() - t0
            xgb.save()
            self._emit(symbol, "xgb", 72,
                       f"XGBoost trained: acc={xgb_acc:.3f} in {elapsed:.1f}s ✓")

        # ── Step 7: Train LSTM ────────────────────────────────────────────────
        lstm_acc = 0.0
        lstm = LSTMModel(symbol)
        if not lstm._available:
            self._emit(symbol, "lstm", 95,
                       "TensorFlow not installed — LSTM skipped")
        elif lstm.load():
            self._emit(symbol, "lstm", 95,
                       f"LSTM loaded from disk (acc={lstm.train_accuracy:.3f}) ✓")
            lstm_acc = lstm.train_accuracy
        elif len(X) >= 200:
            self._emit(symbol, "lstm", 75, "Training LSTM model (this takes a few minutes)...")
            t0       = time.time()
            lstm_acc = lstm.train(X, y)
            elapsed  = time.time() - t0
            lstm.save()
            self._emit(symbol, "lstm", 95,
                       f"LSTM trained: acc={lstm_acc:.3f} in {elapsed:.1f}s ✓")
        else:
            self._emit(symbol, "lstm", 95,
                       f"Too few samples for LSTM ({len(X)}) — skipped")

        self._emit(symbol, "done", 100,
                   f"{symbol.upper()} ready — "
                   f"XGB acc={xgb.train_accuracy:.3f}"
                   + (f"  LSTM acc={lstm_acc:.3f}" if lstm_acc else ""))

        try:
            self.done_cb(symbol, xgb.train_accuracy, lstm_acc)
        except Exception:
            pass
