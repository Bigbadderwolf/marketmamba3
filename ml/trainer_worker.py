# ml/trainer_worker.py
"""
QThread-based ML training worker.

Runs ALL heavy computation (candle load, indicator engine,
SMC detection, XGBoost + LSTM training) inside a dedicated
OS thread, communicating back to the UI exclusively through
Qt signals — never touching Qt widgets directly.

Key design decisions that eliminate the UI freeze:
  1. QThread (not threading.Thread) — Qt manages the event loop
     for this thread properly.
  2. Cap training candles at MAX_TRAIN_CANDLES (3000) so
     IndicatorEngine never runs on 20k rows.
  3. Emit progress signals between every heavy step so the main
     thread's event loop stays alive.
  4. PredictionEngine is constructed here, then handed to the
     main thread via a signal — never built on the main thread.
"""

import logging
import time
import numpy as np

from PyQt6.QtCore import QThread, pyqtSignal

log = logging.getLogger(__name__)

# Cap: enough data for excellent ML accuracy, not so much that
# pure-Python indicator loops freeze a 4-core i5 for 10+ seconds.
MAX_TRAIN_CANDLES = 3000
MIN_TRAIN_CANDLES = 200
TRAIN_TIMEFRAME   = "1h"


class TrainerWorker(QThread):
    """
    Signals
    -------
    progress(pct: int, message: str)
        Emitted at each step so the window title / status bar
        can update without blocking.
    finished(symbol: str, xgb_acc: float, lstm_acc: float)
        Emitted once when training completes successfully.
    error(message: str)
        Emitted if something goes wrong.
    predictor_ready(predictor_obj)
        Emitted with the constructed PredictionEngine so the
        main thread can attach it to the chart without importing
        heavy ML libs on the main thread.
    """

    progress        = pyqtSignal(int, str)      # pct, message
    finished        = pyqtSignal(str, float, float)  # symbol, xgb_acc, lstm_acc
    error           = pyqtSignal(str)
    predictor_ready = pyqtSignal(object)        # PredictionEngine instance

    def __init__(self, symbol: str, parent=None):
        super().__init__(parent)
        self.symbol   = symbol.lower()
        self._abort   = False

    def abort(self):
        self._abort = True

    # ── QThread entry point ───────────────────────────────────────────────────

    def run(self):
        try:
            self._train()
        except Exception as e:
            log.exception("TrainerWorker fatal error")
            self.error.emit(str(e))

    def _emit(self, pct: int, msg: str):
        if not self._abort:
            self.progress.emit(pct, msg)
            log.debug("[ML %d%%] %s", pct, msg)

    def _train(self):
        from data.data_cache import load_cached_candles, get_cache_range
        from indicators.indicator_engine import IndicatorEngine
        from smc.detector import SMCDetector
        from ml.feature_engineer import build_training_dataset
        from ml.xgb_model import XGBModel
        from ml.lstm_model import LSTMModel
        from ml.predictor import PredictionEngine

        symbol = self.symbol

        # ── 1. Check cache ────────────────────────────────────────────────────
        self._emit(2, f"Checking candle cache for {symbol.upper()}…")
        if self._abort: return

        rng = get_cache_range(symbol, TRAIN_TIMEFRAME)
        tf  = TRAIN_TIMEFRAME
        if not rng or rng[2] < MIN_TRAIN_CANDLES:
            rng = get_cache_range(symbol, "1m")
            tf  = "1m"

        if not rng or rng[2] < MIN_TRAIN_CANDLES:
            cached = rng[2] if rng else 0
            self._emit(100, f"Insufficient cache ({cached} candles). "
                            f"Run setup wizard to download data.")
            self.finished.emit(symbol, 0.0, 0.0)
            return

        n_available = rng[2]
        self._emit(5, f"{n_available:,} candles available ({symbol.upper()} {tf})")

        # ── 2. Load candles (capped) ──────────────────────────────────────────
        n_load = min(n_available, MAX_TRAIN_CANDLES)
        self._emit(8, f"Loading {n_load:,} candles for training…")
        if self._abort: return

        candles = load_cached_candles(symbol, tf, limit=n_load)
        if len(candles) < MIN_TRAIN_CANDLES:
            self._emit(100, f"Only {len(candles)} candles loaded — need {MIN_TRAIN_CANDLES}.")
            self.finished.emit(symbol, 0.0, 0.0)
            return

        self._emit(15, f"Loaded {len(candles):,} candles ✓")
        if self._abort: return

        # ── 3. Indicator computation (chunked) ────────────────────────────────
        self._emit(18, "Computing indicators…")
        engine = IndicatorEngine()
        try:
            # Chunked: yield control every 500 candles via msleep
            # (indicators run on full array but we emit progress
            #  so the Qt event loop sees activity)
            indicator_results = engine.compute(candles)
            self._emit(38, "Indicators computed ✓")
        except Exception as e:
            log.error("Indicator compute failed: %s", e)
            indicator_results = {}
            self._emit(38, f"Indicator compute partial: {e}")

        if self._abort: return
        self.msleep(10)  # yield — lets Qt process queued events

        # ── 4. SMC detection ──────────────────────────────────────────────────
        self._emit(40, "Detecting SMC features…")
        detector = SMCDetector()
        try:
            smc_results = detector.detect(candles)
            self._emit(48, "SMC features computed ✓")
        except Exception as e:
            log.error("SMC detect failed: %s", e)
            smc_results = {}

        if self._abort: return
        self.msleep(10)

        # ── 5. Feature engineering ────────────────────────────────────────────
        self._emit(50, "Engineering feature vectors…")
        try:
            X, y = build_training_dataset(candles, indicator_results, smc_results)
        except Exception as e:
            log.error("Feature build failed: %s", e)
            self.error.emit(f"Feature engineering failed: {e}")
            return

        if len(X) < 50:
            self._emit(100, f"Too few training samples ({len(X)}) — skipping.")
            self.finished.emit(symbol, 0.0, 0.0)
            return

        n_up   = int(np.sum(y == 1))
        n_down = int(np.sum(y == 0))
        self._emit(55, f"{len(X):,} samples ready  ({n_up} UP / {n_down} DOWN) ✓")
        if self._abort: return
        self.msleep(10)

        # ── 6. XGBoost ────────────────────────────────────────────────────────
        self._emit(58, "Training XGBoost model…")
        xgb = XGBModel(symbol)
        if xgb.load():
            self._emit(72, f"XGBoost loaded from disk (acc={xgb.train_accuracy:.3f}) ✓")
        else:
            t0      = time.time()
            xgb_acc = xgb.train(X, y)
            elapsed = time.time() - t0
            xgb.save()
            self._emit(72, f"XGBoost trained: acc={xgb_acc:.3f} in {elapsed:.1f}s ✓")

        if self._abort: return
        self.msleep(10)

        # ── 7. LSTM ───────────────────────────────────────────────────────────
        lstm_acc = 0.0
        lstm     = LSTMModel(symbol)

        if not lstm._available:
            self._emit(90, "TensorFlow not installed — LSTM skipped")
        elif lstm.load():
            lstm_acc = lstm.train_accuracy
            self._emit(90, f"LSTM loaded from disk (acc={lstm_acc:.3f}) ✓")
        elif len(X) >= 200:
            self._emit(75, "Training LSTM (background, may take 2–5 min)…")
            t0       = time.time()
            lstm_acc = lstm.train(X, y)
            elapsed  = time.time() - t0
            lstm.save()
            self._emit(90, f"LSTM trained: acc={lstm_acc:.3f} in {elapsed:.1f}s ✓")
        else:
            self._emit(90, f"Insufficient samples for LSTM ({len(X)}) — skipped")

        if self._abort: return

        # ── 8. Build predictor and ship to main thread ────────────────────────
        self._emit(95, "Building prediction engine…")
        try:
            predictor = PredictionEngine(symbol)
            self.predictor_ready.emit(predictor)
        except Exception as e:
            log.error("PredictionEngine build failed: %s", e)
            self.error.emit(f"Predictor build failed: {e}")
            return

        self._emit(100,
            f"{symbol.upper()} ready — "
            f"XGB acc={xgb.train_accuracy:.3f}"
            + (f"  LSTM acc={lstm_acc:.3f}" if lstm_acc else "")
        )
        self.finished.emit(symbol, float(xgb.train_accuracy), float(lstm_acc))
