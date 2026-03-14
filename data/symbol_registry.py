# data/symbol_registry.py
"""
Complete symbol registry for Market Mamba.
Covers all major Binance crypto pairs, forex, and commodities.
"""

# ── Crypto Pairs (USDT base) ──────────────────────────────────────────────────
CRYPTO_USDT = [
    # Large cap
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT",
    "SOLUSDT", "DOGEUSDT", "MATICUSDT", "DOTUSDT", "LTCUSDT",
    "AVAXUSDT", "LINKUSDT", "UNIUSDT", "ATOMUSDT", "XLMUSDT",
    "TRXUSDT", "ETCUSDT", "FILUSDT", "AAVEUSDT", "ALGOUSDT",
    # Mid cap
    "APTUSDT", "ARBUSDT", "OPUSDT", "INJUSDT", "SUIUSDT",
    "SEIUSDT", "TIAUSDT", "PYTHUSDT", "JITOUSDT", "JUPUSDT",
    "WLDUSDT", "STRKUSDT", "ALTUSDT", "BONKUSDT", "WIFUSDT",
    "PENDLEUSDT", "EIGENUSDT", "ENAUSDT", "REZUSDT", "ZKUSDT",
    # DeFi
    "MKRUSDT", "COMPUSDT", "CRVUSDT", "YFIUSDT", "SUSHIUSDT",
    "1INCHUSDT", "DYDXUSDT", "GMXUSDT", "SNXUSDT", "BALUSDT",
    # Layer 2 / infra
    "LDOUSDT", "RPLUSDT", "STXUSDT", "CFXUSDT", "NEARUSDT",
    "FTMUSDT", "HBARUSDT", "ICPUSDT", "VETUSDT", "EGLDUSDT",
    # Meme
    "SHIBUSDT", "PEPEUSDT", "FLOKIUSDT", "MEMEUSDT",
]

# ── Crypto Cross Pairs ────────────────────────────────────────────────────────
CRYPTO_BTC = [
    "ETHBTC", "ADABTC", "BNBBTC", "XRPBTC", "SOLBTC",
    "DOTBTC", "LTCBTC", "LINKBTC", "MATICBTC",
]

CRYPTO_ETH = [
    "ADAETH", "BNBETH", "DOTETH", "LINKETH", "MATICETH",
]

# ── Forex (via Binance tokenized) ─────────────────────────────────────────────
FOREX_USDT = [
    "EURUSDT", "GBPUSDT", "JPYUSDT", "AUDUSTD", "CADUSTD",
    "CHFUSDT", "NZDUSDT", "SGDUSTD",
]

# ── Commodities (via Binance tokenized) ───────────────────────────────────────
COMMODITIES = [
    "XAUUSDT",   # Gold
    "XAGUSDT",   # Silver
    "WBTCUSDT",  # Wrapped BTC (proxy)
]

# ── All pairs combined ────────────────────────────────────────────────────────
ALL_SYMBOLS = CRYPTO_USDT + CRYPTO_BTC + CRYPTO_ETH + COMMODITIES

# ── Timeframes ────────────────────────────────────────────────────────────────
TIMEFRAMES = {
    "1m":  {"label": "1m",  "seconds": 60,      "binance": "1m"},
    "3m":  {"label": "3m",  "seconds": 180,     "binance": "3m"},
    "5m":  {"label": "5m",  "seconds": 300,     "binance": "5m"},
    "15m": {"label": "15m", "seconds": 900,     "binance": "15m"},
    "30m": {"label": "30m", "seconds": 1800,    "binance": "30m"},
    "1h":  {"label": "1h",  "seconds": 3600,    "binance": "1h"},
    "2h":  {"label": "2h",  "seconds": 7200,    "binance": "2h"},
    "4h":  {"label": "4h",  "seconds": 14400,   "binance": "4h"},
    "6h":  {"label": "6h",  "seconds": 21600,   "binance": "6h"},
    "12h": {"label": "12h", "seconds": 43200,   "binance": "12h"},
    "1d":  {"label": "1D",  "seconds": 86400,   "binance": "1d"},
    "3d":  {"label": "3D",  "seconds": 259200,  "binance": "3d"},
    "1w":  {"label": "1W",  "seconds": 604800,  "binance": "1w"},
}

# ── Categorised display ───────────────────────────────────────────────────────
SYMBOL_CATEGORIES = {
    "🔥 Top Crypto":     ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
                          "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "MATICUSDT", "DOTUSDT"],
    "📈 DeFi":           ["AAVEUSDT", "UNIUSDT", "MKRUSDT", "COMPUSDT", "CRVUSDT",
                          "GMXUSDT", "DYDXUSDT", "1INCHUSDT", "SUSHIUSDT"],
    "🏗️ Layer 2":        ["ARBUSDT", "OPUSDT", "MATICUSDT", "STRKUSDT", "ZKUSDT",
                          "LDOUSDT"],
    "🆕 New Listed":     ["APTUSDT", "SUIUSDT", "SEIUSDT", "INJUSDT", "WLDUSDT",
                          "PYTHUSDT", "JUPUSDT", "ENAUSDT"],
    "🐸 Meme":           ["DOGEUSDT", "SHIBUSDT", "PEPEUSDT", "FLOKIUSDT",
                          "BONKUSDT", "WIFUSDT", "MEMEUSDT"],
    "₿ BTC Pairs":       CRYPTO_BTC,
    "Ξ ETH Pairs":       CRYPTO_ETH,
    "💛 Commodities":    COMMODITIES,
}


def get_category(symbol: str) -> str:
    """Return the category name for a symbol."""
    sym = symbol.upper()
    for cat, symbols in SYMBOL_CATEGORIES.items():
        if sym in [s.upper() for s in symbols]:
            return cat
    return "Other"


def search_symbols(query: str) -> list:
    """Search all symbols by substring match."""
    q = query.upper().strip()
    return [s for s in ALL_SYMBOLS if q in s.upper()]


def get_display_name(symbol: str) -> str:
    """Return formatted display name: BTC/USDT"""
    s = symbol.upper()
    for quote in ["USDT", "BTC", "ETH", "BUSD", "BNB"]:
        if s.endswith(quote):
            base = s[:-len(quote)]
            return f"{base}/{quote}"
    return s
