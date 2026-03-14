# config/settings.py
import json, os
from config.constants import DATA_DIR, DEFAULT_INDICATOR_PARAMS

SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")

_DEFAULTS = {
    "theme": "dark",
    "default_symbol": "btcusdt",
    "default_interval": "1m",
    "candles_per_view": 60,
    "indicators": DEFAULT_INDICATOR_PARAMS,
    "active_indicators": [],
    "risk_pct": 1.0,
    "default_leverage": 10,
    "max_drawdown_pct": 10.0,
    "sim_model": "Monte Carlo",
    "sim_speed": 1.0,
    "show_volume": True,
    "show_crosshair": True,
    "ml_auto_recommend": True,
}

class Settings:
    def __init__(self, user_id: int):
        self.user_id = user_id
        self._path = os.path.join(DATA_DIR, f"settings_{user_id}.json")
        self._data = dict(_DEFAULTS)
        self._load()

    def _load(self):
        if os.path.exists(self._path):
            try:
                with open(self._path) as f:
                    saved = json.load(f)
                self._data.update(saved)
            except Exception:
                pass

    def save(self):
        with open(self._path, "w") as f:
            json.dump(self._data, f, indent=2)

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value
        self.save()

    def get_indicator_param(self, indicator: str, param: str):
        return self._data["indicators"].get(indicator, {}).get(param)

    def set_indicator_param(self, indicator: str, param: str, value):
        if indicator not in self._data["indicators"]:
            self._data["indicators"][indicator] = {}
        self._data["indicators"][indicator][param] = value
        self.save()
