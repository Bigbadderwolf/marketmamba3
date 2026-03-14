# config/constants.py
import os

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR       = os.path.join(BASE_DIR, "app_data")
DB_PATH        = os.path.join(DATA_DIR, "market_mamba.db")
MODELS_DIR     = os.path.join(DATA_DIR, "models")
CACHE_DIR      = os.path.join(DATA_DIR, "cache")
EXPORTS_DIR    = os.path.join(DATA_DIR, "exports")
KEY_FILE       = os.path.join(DATA_DIR, ".keystore")
LOG_FILE       = os.path.join(DATA_DIR, "app.log")

# Create all dirs on import
for _d in [DATA_DIR, MODELS_DIR, CACHE_DIR, EXPORTS_DIR]:
    os.makedirs(_d, exist_ok=True)

# ── App ────────────────────────────────────────────────────────────────────────
APP_NAME       = "Market Mamba"
APP_VERSION    = "2.0.0"
WINDOW_W       = 1600
WINDOW_H       = 900

# ── Binance ────────────────────────────────────────────────────────────────────
BINANCE_WS_URL      = "wss://stream.binance.com:9443/ws"
BINANCE_REST_URL    = "https://api.binance.com"
BINANCE_FUTURES_URL = "https://fapi.binance.com"
MAX_CANDLES_CACHE   = 1000
CANDLE_HISTORY_DAYS = 730   # 2 years for ML training

# ── Chart ──────────────────────────────────────────────────────────────────────
DEFAULT_SYMBOL      = "btcusdt"
DEFAULT_INTERVAL    = "1m"
DEFAULT_CANDLES_VIEW = 60
MAX_CANDLES_VIEW    = 200
MIN_CANDLES_VIEW    = 10
CHART_BG            = "#0f0f0f"
CANDLE_GREEN        = "#00967c"
CANDLE_RED          = "#ff5252"
PRICE_LINE_COLOR    = "#64c8ff"
SIM_HIGHLIGHT_COLOR = "#ff9800"   # Amber for simulation overlay
GRID_COLOR          = "#1a1a1a"
TEXT_COLOR          = "#d1d4dc"

# ── SMC Colors ────────────────────────────────────────────────────────────────
OB_BULL_COLOR   = "#1a472a"   # Dark green fill
OB_BEAR_COLOR   = "#4a1020"   # Dark red fill
FVG_COLOR       = "#1a3a4a"   # Dark blue fill
BOS_COLOR       = "#00ff88"   # Bright green line
CHOCH_COLOR     = "#ff4444"   # Bright red line
LIQ_COLOR       = "#ffdd00"   # Yellow sweep line

# ── Indicators ────────────────────────────────────────────────────────────────
DEFAULT_INDICATOR_PARAMS = {
    "EMA_9":   {"period": 9,   "color": "#ff9800", "width": 1},
    "EMA_21":  {"period": 21,  "color": "#2196f3", "width": 1},
    "EMA_50":  {"period": 50,  "color": "#9c27b0", "width": 1},
    "EMA_200": {"period": 200, "color": "#f44336", "width": 2},
    "RSI":     {"period": 14,  "overbought": 70, "oversold": 30},
    "MACD":    {"fast": 12, "slow": 26, "signal": 9},
    "STOCHRSI":{"period": 14,  "smooth_k": 3, "smooth_d": 3},
    "BB":      {"period": 20,  "std": 2.0},
    "ATR":     {"period": 14},
    "VWAP":    {},
}

# ── ML ─────────────────────────────────────────────────────────────────────────
ML_RETRAIN_HOURS        = 4
ML_MIN_ACCURACY_TARGET  = 0.60
ML_LOOKBACK_CANDLES     = 50
ML_TRAIN_SPLIT          = 0.8
ML_FEATURE_COUNT        = 42

# ── Risk ───────────────────────────────────────────────────────────────────────
DEFAULT_RISK_PCT        = 1.0   # % of balance per trade
MAX_LEVERAGE            = 125
DEFAULT_LEVERAGE        = 10
MAX_DRAWDOWN_PCT        = 10.0  # Kill switch threshold

# ── Simulation ────────────────────────────────────────────────────────────────
SIM_MODELS = [
    "Monte Carlo",
    "Regime-Switching",
    "Agent-Based",
    "GAN-Generated",
    "Fractal",
    "Order Flow",
]
MAX_SIM_COMPARISON      = 4
SIM_CANDLE_LIMIT        = 1440  # 24hrs at 1m
