# data/binance_rest.py
"""
Binance REST API client for Market Mamba.
Handles:
  - Historical OHLCV candle fetching with full pagination
  - Account info (spot + futures)
  - Order book data
  - Exchange info (symbol metadata, tick sizes, lot sizes)
  - Server time sync

No authentication required for market data endpoints.
Authentication required for account/order endpoints (handled by binance_executor.py).
"""

import time
import logging
import requests
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta

from config.constants import (
    BINANCE_REST_URL, BINANCE_FUTURES_URL,
    CANDLE_HISTORY_DAYS, MAX_CANDLES_CACHE
)
from data.data_cache import cache_candles, load_cached_candles, is_data_fresh

log = logging.getLogger(__name__)

# Binance max candles per REST request
_BINANCE_LIMIT = 1000

# Interval → milliseconds mapping
_INTERVAL_MS = {
    "1m":  60_000,
    "3m":  180_000,
    "5m":  300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h":  3_600_000,
    "2h":  7_200_000,
    "4h":  14_400_000,
    "6h":  21_600_000,
    "12h": 43_200_000,
    "1d":  86_400_000,
    "3d":  259_200_000,
    "1w":  604_800_000,
}


# ── Session ───────────────────────────────────────────────────────────────────

_session = requests.Session()
_session.headers.update({
    "User-Agent": "MarketMamba/2.0",
    "Accept":     "application/json",
})


def _get(url: str, params: dict = None, timeout: int = 10) -> dict | list:
    """Make a GET request with error handling and rate limit awareness."""
    try:
        resp = _session.get(url, params=params, timeout=timeout)

        # Binance rate limit header check
        used = resp.headers.get("X-MBX-USED-WEIGHT-1M", "0")
        if int(used) > 1100:
            log.warning("Binance rate limit approaching: %s/1200 weight used", used)
            time.sleep(2)

        resp.raise_for_status()
        return resp.json()

    except requests.exceptions.Timeout:
        raise ConnectionError("Binance API timeout — check your connection.")
    except requests.exceptions.ConnectionError:
        raise ConnectionError("Cannot reach Binance API — check your internet.")
    except requests.exceptions.HTTPError as e:
        raise RuntimeError(f"Binance API error {resp.status_code}: {resp.text}")


# ── Server time ───────────────────────────────────────────────────────────────

def get_server_time() -> int:
    """Returns Binance server time in milliseconds."""
    data = _get(f"{BINANCE_REST_URL}/api/v3/time")
    return data["serverTime"]


def get_time_offset() -> int:
    """Returns local clock offset vs Binance server in ms."""
    local_ms = int(time.time() * 1000)
    server_ms = get_server_time()
    return server_ms - local_ms


# ── Exchange info ─────────────────────────────────────────────────────────────

_exchange_info_cache: dict = {}
_exchange_info_ts: float = 0


def get_exchange_info(symbol: str = None) -> dict:
    """
    Fetch exchange info. Cached for 1 hour.
    Returns full exchange info dict, or single symbol info if symbol provided.
    """
    global _exchange_info_cache, _exchange_info_ts

    if time.time() - _exchange_info_ts > 3600 or not _exchange_info_cache:
        data = _get(f"{BINANCE_REST_URL}/api/v3/exchangeInfo")
        _exchange_info_cache = {s["symbol"]: s for s in data.get("symbols", [])}
        _exchange_info_ts = time.time()
        log.debug("Exchange info refreshed: %d symbols", len(_exchange_info_cache))

    if symbol:
        return _exchange_info_cache.get(symbol.upper(), {})
    return _exchange_info_cache


def get_symbol_filters(symbol: str) -> dict:
    """
    Returns parsed filters for a symbol:
    tick_size, step_size, min_qty, min_notional
    """
    info = get_exchange_info(symbol)
    result = {
        "tick_size":     0.01,
        "step_size":     0.00001,
        "min_qty":       0.00001,
        "min_notional":  10.0,
        "base_asset":    info.get("baseAsset", ""),
        "quote_asset":   info.get("quoteAsset", ""),
    }
    for f in info.get("filters", []):
        ft = f.get("filterType", "")
        if ft == "PRICE_FILTER":
            result["tick_size"] = float(f.get("tickSize", 0.01))
        elif ft == "LOT_SIZE":
            result["step_size"] = float(f.get("stepSize", 0.00001))
            result["min_qty"]   = float(f.get("minQty",   0.00001))
        elif ft == "MIN_NOTIONAL":
            result["min_notional"] = float(f.get("minNotional", 10.0))
        elif ft == "NOTIONAL":
            result["min_notional"] = float(f.get("minNotional", 10.0))
    return result


# ── Candle fetching ───────────────────────────────────────────────────────────

def _parse_kline(k: list) -> dict:
    """Convert raw Binance kline array to candle dict."""
    return {
        "time":   int(k[0]) // 1000,   # convert ms → seconds
        "open":   float(k[1]),
        "high":   float(k[2]),
        "low":    float(k[3]),
        "close":  float(k[4]),
        "volume": float(k[5]),
    }


def fetch_candles_raw(
    symbol:     str,
    interval:   str,
    start_ms:   int = None,
    end_ms:     int = None,
    limit:      int = 1000,
) -> List[Dict]:
    """
    Fetch up to 1000 candles from Binance REST in one request.
    Returns list of candle dicts.
    """
    params = {
        "symbol":   symbol.upper(),
        "interval": interval,
        "limit":    min(limit, _BINANCE_LIMIT),
    }
    if start_ms:
        params["startTime"] = start_ms
    if end_ms:
        params["endTime"] = end_ms

    raw = _get(f"{BINANCE_REST_URL}/api/v3/klines", params=params)
    return [_parse_kline(k) for k in raw]


def fetch_historical_candles(
    symbol:     str,
    interval:   str = "1h",
    days:       int = None,
    start_time: int = None,
    end_time:   int = None,
    use_cache:  bool = True,
    progress_cb = None,   # optional callable(pct: int, msg: str)
) -> List[Dict]:
    """
    Fetch complete historical candles with automatic pagination.

    Args:
        symbol:      e.g. 'btcusdt'
        interval:    e.g. '1h', '4h', '1d'
        days:        number of days back from now (default: CANDLE_HISTORY_DAYS)
        start_time:  unix timestamp (seconds) — overrides days
        end_time:    unix timestamp (seconds) — defaults to now
        use_cache:   load from SQLite cache if available
        progress_cb: optional callback(pct, msg) for progress reporting

    Returns:
        List of candle dicts sorted by time ascending.
    """
    symbol   = symbol.lower()
    days     = days or CANDLE_HISTORY_DAYS
    now_ms   = int(time.time() * 1000)

    # Check cache first
    if use_cache and is_data_fresh(symbol, interval, max_age_hours=4):
        cached = load_cached_candles(symbol, interval, limit=MAX_CANDLES_CACHE)
        if len(cached) > 100:
            log.info("Loaded %d candles from cache: %s/%s", len(cached), symbol, interval)
            if progress_cb:
                progress_cb(100, f"Loaded {len(cached)} candles from cache")
            return cached

    # Calculate time range
    if start_time:
        start_ms = start_time * 1000
    else:
        start_ms = now_ms - (days * 24 * 3600 * 1000)

    end_ms = (end_time * 1000) if end_time else now_ms

    # Calculate expected candle count for progress
    interval_ms  = _INTERVAL_MS.get(interval, 3_600_000)
    total_candles = (end_ms - start_ms) // interval_ms
    log.info("Fetching ~%d candles for %s/%s", total_candles, symbol, interval)

    all_candles  = []
    current_ms   = start_ms
    fetched      = 0
    batch_num    = 0

    while current_ms < end_ms:
        batch_end = min(current_ms + (_BINANCE_LIMIT * interval_ms), end_ms)

        try:
            batch = fetch_candles_raw(
                symbol   = symbol,
                interval = interval,
                start_ms = current_ms,
                end_ms   = batch_end,
                limit    = _BINANCE_LIMIT,
            )
        except Exception as e:
            log.error("Fetch error at %s: %s — retrying once", current_ms, e)
            time.sleep(2)
            try:
                batch = fetch_candles_raw(
                    symbol=symbol, interval=interval,
                    start_ms=current_ms, end_ms=batch_end
                )
            except Exception as e2:
                log.error("Retry failed: %s", e2)
                break

        if not batch:
            break

        all_candles.extend(batch)
        fetched     += len(batch)
        batch_num   += 1

        # Advance start time to after last fetched candle
        last_time_ms = int(batch[-1]["time"]) * 1000
        current_ms   = last_time_ms + interval_ms

        # Progress reporting
        if progress_cb and total_candles > 0:
            pct = min(99, int((fetched / total_candles) * 100))
            progress_cb(pct, f"Fetched {fetched:,} / ~{total_candles:,} candles")

        # Rate limit courtesy sleep every 5 batches
        if batch_num % 5 == 0:
            time.sleep(0.2)

        # Stop if batch was partial (reached end)
        if len(batch) < _BINANCE_LIMIT:
            break

    # Deduplicate and sort
    seen = {}
    for c in all_candles:
        seen[c["time"]] = c
    all_candles = sorted(seen.values(), key=lambda x: x["time"])

    log.info("Fetched %d candles for %s/%s", len(all_candles), symbol, interval)

    # Cache to SQLite
    if all_candles:
        cache_candles(symbol, interval, all_candles)

    if progress_cb:
        progress_cb(100, f"Complete — {len(all_candles):,} candles")

    return all_candles


def fetch_recent_candles(
    symbol:   str,
    interval: str,
    limit:    int = 200,
) -> List[Dict]:
    """
    Fast fetch of the most recent N candles.
    Used for chart initialisation and backfill on symbol/timeframe switch.
    """
    symbol = symbol.lower()

    # Try cache first for recent data
    cached = load_cached_candles(symbol, interval, limit=limit)
    if len(cached) >= limit:
        return cached[-limit:]

    # Fetch from API
    try:
        candles = fetch_candles_raw(symbol, interval, limit=limit)
        if candles:
            cache_candles(symbol, interval, candles)
        return candles
    except Exception as e:
        log.error("fetch_recent_candles failed: %s", e)
        # Return cached even if stale
        return cached or []


# ── Market data ───────────────────────────────────────────────────────────────

def get_ticker_price(symbol: str) -> float:
    """Get current price for a symbol."""
    try:
        data = _get(
            f"{BINANCE_REST_URL}/api/v3/ticker/price",
            params={"symbol": symbol.upper()}
        )
        return float(data["price"])
    except Exception as e:
        log.error("get_ticker_price failed: %s", e)
        return 0.0


def get_ticker_24h(symbol: str) -> dict:
    """
    Get 24h stats for a symbol.
    Returns: price, change_pct, high, low, volume
    """
    try:
        data = _get(
            f"{BINANCE_REST_URL}/api/v3/ticker/24hr",
            params={"symbol": symbol.upper()}
        )
        return {
            "price":      float(data["lastPrice"]),
            "change":     float(data["priceChange"]),
            "change_pct": float(data["priceChangePercent"]),
            "high":       float(data["highPrice"]),
            "low":        float(data["lowPrice"]),
            "volume":     float(data["volume"]),
            "quote_vol":  float(data["quoteVolume"]),
        }
    except Exception as e:
        log.error("get_ticker_24h failed: %s", e)
        return {}


def get_order_book(symbol: str, depth: int = 20) -> dict:
    """
    Fetch order book bids and asks.
    Returns: {"bids": [[price, qty], ...], "asks": [[price, qty], ...]}
    """
    try:
        data = _get(
            f"{BINANCE_REST_URL}/api/v3/depth",
            params={"symbol": symbol.upper(), "limit": depth}
        )
        return {
            "bids": [[float(p), float(q)] for p, q in data.get("bids", [])],
            "asks": [[float(p), float(q)] for p, q in data.get("asks", [])],
        }
    except Exception as e:
        log.error("get_order_book failed: %s", e)
        return {"bids": [], "asks": []}


def get_recent_trades(symbol: str, limit: int = 50) -> List[Dict]:
    """Fetch recent trades for a symbol."""
    try:
        raw = _get(
            f"{BINANCE_REST_URL}/api/v3/trades",
            params={"symbol": symbol.upper(), "limit": limit}
        )
        return [
            {
                "time":     int(t["time"]) // 1000,
                "price":    float(t["price"]),
                "qty":      float(t["qty"]),
                "is_buyer": t["isBuyerMaker"],
            }
            for t in raw
        ]
    except Exception as e:
        log.error("get_recent_trades failed: %s", e)
        return []


# ── Futures market data ───────────────────────────────────────────────────────

def get_futures_ticker(symbol: str) -> dict:
    """Get futures ticker with mark price and funding rate."""
    try:
        mark = _get(
            f"{BINANCE_FUTURES_URL}/fapi/v1/premiumIndex",
            params={"symbol": symbol.upper()}
        )
        ticker = _get(
            f"{BINANCE_FUTURES_URL}/fapi/v1/ticker/24hr",
            params={"symbol": symbol.upper()}
        )
        return {
            "mark_price":    float(mark.get("markPrice", 0)),
            "index_price":   float(mark.get("indexPrice", 0)),
            "funding_rate":  float(mark.get("lastFundingRate", 0)),
            "next_funding":  int(mark.get("nextFundingTime", 0)) // 1000,
            "change_pct":    float(ticker.get("priceChangePercent", 0)),
            "volume":        float(ticker.get("volume", 0)),
        }
    except Exception as e:
        log.error("get_futures_ticker failed: %s", e)
        return {}


def get_futures_candles(
    symbol:   str,
    interval: str,
    limit:    int = 200,
) -> List[Dict]:
    """Fetch futures OHLCV candles."""
    try:
        params = {
            "symbol":   symbol.upper(),
            "interval": interval,
            "limit":    min(limit, _BINANCE_LIMIT),
        }
        raw = _get(f"{BINANCE_FUTURES_URL}/fapi/v1/klines", params=params)
        return [_parse_kline(k) for k in raw]
    except Exception as e:
        log.error("get_futures_candles failed: %s", e)
        return []


# ── Utility ───────────────────────────────────────────────────────────────────

def ping() -> bool:
    """Test connectivity to Binance REST API."""
    try:
        _get(f"{BINANCE_REST_URL}/api/v3/ping")
        return True
    except Exception:
        return False


def get_all_symbols() -> List[str]:
    """Return list of all active USDT trading pairs on Binance."""
    try:
        info = _get(f"{BINANCE_REST_URL}/api/v3/exchangeInfo")
        return [
            s["symbol"] for s in info.get("symbols", [])
            if s.get("status") == "TRADING"
            and s.get("quoteAsset") == "USDT"
        ]
    except Exception as e:
        log.error("get_all_symbols failed: %s", e)
        return []
