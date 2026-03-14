# simulation/base_model.py
"""
Base interface for all simulation models.
Every model must implement fit(), generate(), and get_accuracy().
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Optional
import numpy as np


@dataclass
class GeneratedPath:
    """Output of a model's generate() call."""
    candles:      List[Dict]          # synthetic OHLCV candles
    model_name:   str                 # e.g. "Monte Carlo"
    model_id:     str                 # e.g. "monte_carlo"
    color:        str                 # hex colour for this model
    confidence_bands: Optional[Dict]  # {"p10":[], "p25":[], "p75":[], "p90":[]}
    metadata:     Dict = field(default_factory=dict)  # model-specific extras


@dataclass
class AccuracyRecord:
    model_id:     str
    symbol:       str
    timeframe:    str
    session_date: str
    predicted_direction: str   # "UP" or "DOWN"
    actual_direction:    str
    price_error_pct:     float
    win:                 bool


class BaseSimModel(ABC):

    MODEL_ID   = "base"
    MODEL_NAME = "Base"
    COLOR      = "#888888"

    def __init__(self):
        self._fitted      = False
        self._candles     = []
        self._accuracy_records: List[AccuracyRecord] = []

    @abstractmethod
    def fit(self, candles: List[Dict]) -> None:
        """Calibrate model on historical candles."""

    @abstractmethod
    def generate(self, n_candles: int, start_price: float,
                 last_time: int, timeframe_secs: int) -> GeneratedPath:
        """Generate a synthetic forward path of n_candles."""

    def get_accuracy(self) -> Dict:
        """Return accuracy stats dict."""
        if not self._accuracy_records:
            return {"win_rate": 0.0, "sessions": 0, "avg_price_error": 0.0}
        wins = sum(1 for r in self._accuracy_records if r.win)
        errs = [r.price_error_pct for r in self._accuracy_records]
        return {
            "win_rate":        wins / len(self._accuracy_records),
            "sessions":        len(self._accuracy_records),
            "avg_price_error": float(np.mean(errs)) if errs else 0.0,
        }

    def record_accuracy(self, record: AccuracyRecord):
        self._accuracy_records.append(record)
        # Keep last 500 records
        if len(self._accuracy_records) > 500:
            self._accuracy_records = self._accuracy_records[-500:]

    def _make_candle(self, open_p, high_p, low_p, close_p,
                     volume, timestamp) -> Dict:
        return {
            "time":      int(timestamp),
            "open":      round(float(open_p),  8),
            "high":      round(float(high_p),  8),
            "low":       round(float(low_p),   8),
            "close":     round(float(close_p), 8),
            "volume":    round(float(volume),  2),
            "synthetic": True,
        }

    def _safe_float(self, v, fallback=0.0) -> float:
        try:
            f = float(v)
            return fallback if (np.isnan(f) or np.isinf(f)) else f
        except Exception:
            return fallback

    def _extract_returns(self, candles: List[Dict]) -> np.ndarray:
        closes = np.array([float(c["close"]) for c in candles], dtype=float)
        closes = closes[closes > 0]
        if len(closes) < 2:
            return np.array([0.0])
        return np.diff(np.log(closes))

    def _atr(self, candles: List[Dict], period: int = 14) -> float:
        if len(candles) < period + 1:
            c = candles[-1]
            return float(c["high"]) - float(c["low"])
        trs = []
        for i in range(1, len(candles)):
            h = float(candles[i]["high"])
            l = float(candles[i]["low"])
            pc = float(candles[i-1]["close"])
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        return float(np.mean(trs[-period:]))
