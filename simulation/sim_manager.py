# simulation/sim_manager.py
"""
Simulation Manager.
Coordinates all 6 models, accuracy tracking, best-model selection,
and historical replay engine.

Provides:
  - fit_all(candles)            — calibrate all models
  - generate_all(n, price, t)  — run all active models
  - get_best_model()            — returns model with best accuracy
  - accuracy_table()            — full stats for all models
  - Historical replay state machine
"""

import time
import logging
import threading
import numpy as np
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass, field

from simulation.base_model import GeneratedPath, AccuracyRecord
from simulation.model_monte_carlo import MonteCarloModel
from simulation.model_regime      import RegimeSwitchingModel
from simulation.model_agent       import AgentBasedModel
from simulation.model_gan         import GANModel
from simulation.model_fractal     import FractalModel
from simulation.model_orderflow   import OrderFlowModel

log = logging.getLogger(__name__)


# ── Historical replay state ───────────────────────────────────────────────────

@dataclass
class ReplayState:
    candles:       List[Dict] = field(default_factory=list)
    current_idx:   int  = 0
    total:         int  = 0
    playing:       bool = False
    speed:         float = 1.0    # 1x = real-time, 10x = 10× faster
    start_time_ms: int  = 0
    end_time_ms:   int  = 0
    symbol:        str  = ""
    timeframe:     str  = ""


class SimManager:

    ALL_MODELS = [
        MonteCarloModel,
        RegimeSwitchingModel,
        AgentBasedModel,
        GANModel,
        FractalModel,
        OrderFlowModel,
    ]

    def __init__(self):
        self._models: Dict[str, object] = {}
        self._active_ids: List[str]     = []
        self._fitted                    = False
        self._fit_candles: List[Dict]   = []

        # Replay
        self._replay                = ReplayState()
        self._replay_timer: Optional[threading.Timer] = None
        self._replay_cb: Optional[Callable] = None  # called with (candle, idx, total)

        # Accuracy records per model
        self._session_start = time.time()

        self._init_models()

    def _init_models(self):
        for cls in self.ALL_MODELS:
            m = cls()
            self._models[m.MODEL_ID] = m
        # All active by default
        self._active_ids = [m for m in self._models]

    # ── Fitting ───────────────────────────────────────────────────────────────

    def fit_all(self, candles: List[Dict], async_fit: bool = True):
        """Calibrate all active models on historical candles."""
        self._fit_candles = candles

        def _do_fit():
            for mid in self._active_ids:
                try:
                    self._models[mid].fit(candles)
                    log.info("Model %s fitted on %d candles", mid, len(candles))
                except Exception as e:
                    log.error("Model %s fit error: %s", mid, e)
            self._fitted = True

        if async_fit:
            threading.Thread(target=_do_fit, daemon=True).start()
        else:
            _do_fit()

    # ── Generation ───────────────────────────────────────────────────────────

    def generate_all(
        self,
        n_candles:      int,
        start_price:    float,
        last_time:      int,
        timeframe_secs: int,
        model_ids:      Optional[List[str]] = None,
    ) -> List[GeneratedPath]:
        """Run up to 4 active models and return their paths."""
        ids = model_ids or self._active_ids
        ids = ids[:4]   # max 4 for comparison grid
        paths = []
        for mid in ids:
            m = self._models.get(mid)
            if m is None:
                continue
            try:
                path = m.generate(n_candles, start_price, last_time, timeframe_secs)
                paths.append(path)
            except Exception as e:
                log.error("Model %s generate error: %s", mid, e)
        return paths

    def generate_one(
        self,
        model_id:       str,
        n_candles:      int,
        start_price:    float,
        last_time:      int,
        timeframe_secs: int,
    ) -> Optional[GeneratedPath]:
        m = self._models.get(model_id)
        if m is None:
            return None
        try:
            return m.generate(n_candles, start_price, last_time, timeframe_secs)
        except Exception as e:
            log.error("Model %s generate error: %s", model_id, e)
            return None

    # ── Accuracy ─────────────────────────────────────────────────────────────

    def record_outcome(
        self,
        model_id:   str,
        symbol:     str,
        timeframe:  str,
        predicted:  List[Dict],  # generated candles
        actual:     List[Dict],  # real candles for same window
    ):
        """Compare predicted path to actual candles and record accuracy."""
        m = self._models.get(model_id)
        if m is None or not predicted or not actual:
            return

        n = min(len(predicted), len(actual))
        if n < 3:
            return

        pred_close   = float(predicted[-1]["close"])
        actual_close = float(actual[min(n-1, len(actual)-1)]["close"])
        start_price  = float(predicted[0]["open"])

        pred_dir  = "UP" if pred_close > start_price else "DOWN"
        act_dir   = "UP" if actual_close > start_price else "DOWN"
        win       = pred_dir == act_dir
        err_pct   = abs(pred_close - actual_close) / max(actual_close, 1) * 100

        import datetime
        rec = AccuracyRecord(
            model_id             = model_id,
            symbol               = symbol,
            timeframe            = timeframe,
            session_date         = datetime.date.today().isoformat(),
            predicted_direction  = pred_dir,
            actual_direction     = act_dir,
            price_error_pct      = err_pct,
            win                  = win,
        )
        m.record_accuracy(rec)

    def accuracy_table(self) -> List[Dict]:
        """Return accuracy stats for all models, sorted by win rate desc."""
        rows = []
        for mid, m in self._models.items():
            stats = m.get_accuracy()
            rows.append({
                "model_id":   mid,
                "model_name": m.MODEL_NAME,
                "color":      m.COLOR,
                "win_rate":   stats["win_rate"],
                "sessions":   stats["sessions"],
                "avg_error":  stats["avg_price_error"],
                "fitted":     m._fitted,
            })
        rows.sort(key=lambda r: r["win_rate"], reverse=True)
        return rows

    def get_best_model(self) -> Optional[str]:
        """Return model_id with highest win rate (min 3 sessions)."""
        table = self.accuracy_table()
        qualified = [r for r in table if r["sessions"] >= 3 and r["fitted"]]
        if not qualified:
            # Return first fitted model
            for r in table:
                if r["fitted"]:
                    return r["model_id"]
            return list(self._models.keys())[0]
        return qualified[0]["model_id"]

    def get_model_info(self, model_id: str) -> Dict:
        m = self._models.get(model_id)
        if not m:
            return {}
        return {
            "model_id":   m.MODEL_ID,
            "model_name": m.MODEL_NAME,
            "color":      m.COLOR,
            "fitted":     m._fitted,
            "accuracy":   m.get_accuracy(),
        }

    # ── Historical replay ─────────────────────────────────────────────────────

    def load_replay(
        self,
        symbol:    str,
        timeframe: str,
        start_ts:  int,
        end_ts:    int,
    ) -> int:
        """
        Load candles from cache for replay.
        Returns number of candles loaded.
        """
        from data.data_cache import load_cached_candles
        candles = load_cached_candles(
            symbol    = symbol,
            timeframe = timeframe,
            start_time = start_ts,
            end_time   = end_ts,
            limit      = 5000,
        )
        self._replay = ReplayState(
            candles       = candles,
            current_idx   = 0,
            total         = len(candles),
            playing       = False,
            speed         = 1.0,
            start_time_ms = start_ts,
            end_time_ms   = end_ts,
            symbol        = symbol,
            timeframe     = timeframe,
        )
        log.info("Replay loaded: %d candles for %s/%s", len(candles), symbol, timeframe)
        return len(candles)

    def replay_play_pause(self):
        self._replay.playing = not self._replay.playing
        if self._replay.playing:
            self._replay_tick()

    def replay_set_speed(self, speed: float):
        self._replay.speed = max(0.1, min(20.0, speed))

    def replay_step(self) -> Optional[Dict]:
        """Advance one candle. Returns revealed candle or None."""
        r = self._replay
        if r.current_idx >= r.total:
            return None
        candle = r.candles[r.current_idx]
        r.current_idx += 1
        if self._replay_cb:
            try:
                self._replay_cb(candle, r.current_idx, r.total)
            except Exception:
                pass
        return candle

    def replay_jump(self, idx: int):
        self._replay.current_idx = max(0, min(idx, self._replay.total - 1))

    def replay_jump_start(self):
        self._replay.current_idx = 0

    def replay_jump_end(self):
        self._replay.current_idx = max(0, self._replay.total - 1)

    def replay_scrub(self, fraction: float):
        """Scrub to position 0.0–1.0."""
        idx = int(fraction * self._replay.total)
        self.replay_jump(idx)

    def replay_get_visible(self) -> List[Dict]:
        """Return all candles revealed so far."""
        return self._replay.candles[:self._replay.current_idx]

    def replay_get_state(self) -> ReplayState:
        return self._replay

    def set_replay_callback(self, cb: Callable):
        """cb(candle, current_idx, total) called on each tick."""
        self._replay_cb = cb

    def _replay_tick(self):
        """Internal timer tick — advance one candle then reschedule."""
        if not self._replay.playing:
            return
        if self._replay.current_idx >= self._replay.total:
            self._replay.playing = False
            return

        self.replay_step()

        # Base interval: 1 candle per second at 1x
        interval = 1.0 / max(self._replay.speed, 0.1)
        self._replay_timer = threading.Timer(interval, self._replay_tick)
        self._replay_timer.daemon = True
        self._replay_timer.start()

    def stop_replay(self):
        self._replay.playing = False
        if self._replay_timer:
            self._replay_timer.cancel()

    # ── Model toggle ─────────────────────────────────────────────────────────

    def set_active_models(self, model_ids: List[str]):
        self._active_ids = [mid for mid in model_ids if mid in self._models]

    def get_all_model_ids(self) -> List[str]:
        return list(self._models.keys())

    def get_model_color(self, model_id: str) -> str:
        m = self._models.get(model_id)
        return m.COLOR if m else "#888888"

    def get_model_name(self, model_id: str) -> str:
        m = self._models.get(model_id)
        return m.MODEL_NAME if m else model_id

    def is_fitted(self) -> bool:
        return self._fitted
