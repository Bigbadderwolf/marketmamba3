# indicators/style_store.py
"""
Indicator style persistence.
Saves and loads per-user, per-symbol indicator style settings.
Stored as JSON in SQLite — one row per (user_id, symbol, indicator_key).
"""

import json
import logging
from typing import Dict, Optional

log = logging.getLogger(__name__)

# ── Default styles per indicator ─────────────────────────────────────────────
# Each indicator defines its "components" — each component is a drawable line/fill.
# These are the factory defaults (matches Phase 3 colours).

DEFAULT_STYLES: Dict[str, dict] = {

    "EMA_9": {
        "params": {"period": 9},
        "components": {
            "line": {"color": "#ff9800", "thickness": 1, "style": "solid",
                     "visible": True, "label": True},
        }
    },
    "EMA_21": {
        "params": {"period": 21},
        "components": {
            "line": {"color": "#2196f3", "thickness": 1, "style": "solid",
                     "visible": True, "label": True},
        }
    },
    "EMA_50": {
        "params": {"period": 50},
        "components": {
            "line": {"color": "#9c27b0", "thickness": 1, "style": "solid",
                     "visible": True, "label": True},
        }
    },
    "EMA_200": {
        "params": {"period": 200},
        "components": {
            "line": {"color": "#f44336", "thickness": 2, "style": "solid",
                     "visible": True, "label": True},
        }
    },
    "VWAP": {
        "params": {},
        "components": {
            "line": {"color": "#00bcd4", "thickness": 1, "style": "solid",
                     "visible": True, "label": True},
        }
    },
    "RSI": {
        "params": {"period": 14, "overbought": 70, "oversold": 30},
        "components": {
            "line":       {"color": "#ffeb3b", "thickness": 1, "style": "solid",
                           "visible": True, "label": True},
            "ob_line":    {"color": "#ff5252", "thickness": 1, "style": "dashed",
                           "visible": True, "label": True},
            "os_line":    {"color": "#00c896", "thickness": 1, "style": "dashed",
                           "visible": True, "label": True},
            "ob_fill":    {"color": "#ff525220", "visible": True},
            "os_fill":    {"color": "#00c89620", "visible": True},
        }
    },
    "STOCHRSI": {
        "params": {"period": 14, "smooth_k": 3, "smooth_d": 3},
        "components": {
            "k_line":  {"color": "#2196f3", "thickness": 1, "style": "solid",
                        "visible": True, "label": True},
            "d_line":  {"color": "#ff9800", "thickness": 1, "style": "solid",
                        "visible": True, "label": True},
            "ob_line": {"color": "#ff5252", "thickness": 1, "style": "dashed",
                        "visible": True, "label": False},
            "os_line": {"color": "#00c896", "thickness": 1, "style": "dashed",
                        "visible": True, "label": False},
        }
    },
    "MACD": {
        "params": {"fast": 12, "slow": 26, "signal": 9},
        "components": {
            "macd_line":   {"color": "#2196f3", "thickness": 1, "style": "solid",
                            "visible": True, "label": True},
            "signal_line": {"color": "#ff9800", "thickness": 1, "style": "solid",
                            "visible": True, "label": True},
            "histogram":   {"color_bull": "#00c896", "color_bear": "#ff5252",
                            "visible": True, "label": False},
            "zero_line":   {"color": "#555555", "thickness": 1, "style": "dashed",
                            "visible": True},
        }
    },
    "BB": {
        "params": {"period": 20, "std": 2.0},
        "components": {
            "upper":  {"color": "#607d8b", "thickness": 1, "style": "solid",
                       "visible": True, "label": False},
            "middle": {"color": "#607d8b", "thickness": 1, "style": "dashed",
                       "visible": True, "label": True},
            "lower":  {"color": "#607d8b", "thickness": 1, "style": "solid",
                       "visible": True, "label": False},
            "fill":   {"color": "#607d8b15", "visible": True},
        }
    },
    "ATR": {
        "params": {"period": 14},
        "components": {
            "line": {"color": "#795548", "thickness": 1, "style": "solid",
                     "visible": True, "label": True},
        }
    },
    "ICHIMOKU": {
        "params": {"tenkan": 9, "kijun": 26, "span_b": 52},
        "components": {
            "tenkan":    {"color": "#e91e63", "thickness": 1, "style": "solid",
                          "visible": True, "label": True},
            "kijun":     {"color": "#2196f3", "thickness": 1, "style": "solid",
                          "visible": True, "label": True},
            "chikou":    {"color": "#9c27b0", "thickness": 1, "style": "solid",
                          "visible": True, "label": False},
            "cloud_bull": {"color": "#00c89625", "visible": True},
            "cloud_bear": {"color": "#ff525225", "visible": True},
        }
    },
    "OBV": {
        "params": {},
        "components": {
            "line": {"color": "#009688", "thickness": 1, "style": "solid",
                     "visible": True, "label": True},
        }
    },
    "CVD": {
        "params": {},
        "components": {
            "line": {"color": "#3f51b5", "thickness": 1, "style": "solid",
                     "visible": True, "label": True},
        }
    },
}


def _ensure_table():
    """Create indicator_styles table if it doesn't exist."""
    from auth.db import get_conn
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS indicator_styles (
            user_id   INTEGER NOT NULL,
            symbol    TEXT    NOT NULL,
            ind_key   TEXT    NOT NULL,
            style_json TEXT   NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, symbol, ind_key)
        )
    """)
    conn.commit()
    conn.close()


def load_style(user_id: int, symbol: str, key: str) -> dict:
    """
    Load saved style for (user, symbol, indicator).
    Falls back to defaults if not saved yet.
    """
    import copy
    default = copy.deepcopy(DEFAULT_STYLES.get(key, {}))
    if not default:
        return {}

    try:
        _ensure_table()
        from auth.db import get_conn
        conn = get_conn()
        cur  = conn.cursor()
        cur.execute(
            "SELECT style_json FROM indicator_styles WHERE user_id=? AND symbol=? AND ind_key=?",
            (user_id, symbol.lower(), key)
        )
        row = cur.fetchone()
        conn.close()

        if row:
            saved = json.loads(row[0])
            # Deep merge saved over defaults
            for section in ("params", "components"):
                if section in saved:
                    if section not in default:
                        default[section] = {}
                    if section == "components":
                        for comp_key, comp_val in saved[section].items():
                            if comp_key in default[section]:
                                default[section][comp_key].update(comp_val)
                            else:
                                default[section][comp_key] = comp_val
                    else:
                        default[section].update(saved[section])
    except Exception as e:
        log.error("load_style failed: %s", e)

    return default


def save_style(user_id: int, symbol: str, key: str, style: dict):
    """Save indicator style for (user, symbol, indicator)."""
    try:
        _ensure_table()
        from auth.db import get_conn
        conn = get_conn()
        conn.execute("""
            INSERT OR REPLACE INTO indicator_styles
            (user_id, symbol, ind_key, style_json, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (user_id, symbol.lower(), key, json.dumps(style)))
        conn.commit()
        conn.close()
        log.debug("Saved style for %s/%s/%s", user_id, symbol, key)
    except Exception as e:
        log.error("save_style failed: %s", e)


def load_all_styles(user_id: int, symbol: str) -> Dict[str, dict]:
    """Load all saved styles for a user+symbol. Returns dict keyed by indicator."""
    result = {}
    for key in DEFAULT_STYLES:
        result[key] = load_style(user_id, symbol, key)
    return result
