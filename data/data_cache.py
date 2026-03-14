# data/data_cache.py
"""
Local SQLite candle cache.
Avoids re-fetching historical data on every startup.
Cache is keyed by (symbol, timeframe, open_time).
"""
import logging
from typing import List, Dict, Optional
from auth.db import get_conn

log = logging.getLogger(__name__)


def cache_candles(symbol: str, timeframe: str, candles: List[Dict]):
    """
    Upsert a list of candle dicts into the local cache.
    Each candle must have: time, open, high, low, close, volume
    """
    if not candles:
        return
    symbol    = symbol.lower()
    conn      = get_conn()
    try:
        conn.executemany("""
            INSERT OR REPLACE INTO candle_cache
            (symbol, timeframe, open_time, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (
                symbol, timeframe,
                int(c.get("time", c.get("open_time", 0))),
                float(c.get("open",   0)),
                float(c.get("high",   0)),
                float(c.get("low",    0)),
                float(c.get("close",  0)),
                float(c.get("volume", 0)),
            )
            for c in candles
        ])
        conn.commit()
        log.debug("Cached %d candles for %s/%s", len(candles), symbol, timeframe)
    finally:
        conn.close()


def load_cached_candles(
    symbol: str,
    timeframe: str,
    limit: int = 1000,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
) -> List[Dict]:
    """
    Load candles from local cache.
    Returns list of dicts sorted by open_time ascending.
    """
    symbol = symbol.lower()
    conn   = get_conn()
    try:
        query  = """
            SELECT open_time as time, open, high, low, close, volume
            FROM candle_cache
            WHERE symbol=? AND timeframe=?
        """
        params = [symbol, timeframe]

        if start_time:
            query  += " AND open_time >= ?"
            params.append(start_time)
        if end_time:
            query  += " AND open_time <= ?"
            params.append(end_time)

        query += " ORDER BY open_time ASC"

        if limit:
            query  += f" LIMIT {int(limit)}"

        cur = conn.cursor()
        cur.execute(query, params)
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_cache_range(symbol: str, timeframe: str) -> Optional[tuple]:
    """
    Returns (min_time, max_time, count) of cached candles for a pair.
    Returns None if no data cached.
    """
    symbol = symbol.lower()
    conn   = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT MIN(open_time), MAX(open_time), COUNT(*)
            FROM candle_cache
            WHERE symbol=? AND timeframe=?
        """, (symbol, timeframe))
        row = cur.fetchone()
        if not row or row[2] == 0:
            return None
        return (row[0], row[1], row[2])
    finally:
        conn.close()


def clear_cache(symbol: str = None, timeframe: str = None):
    """Clear cache for a specific pair or all pairs."""
    conn = get_conn()
    try:
        if symbol and timeframe:
            conn.execute(
                "DELETE FROM candle_cache WHERE symbol=? AND timeframe=?",
                (symbol.lower(), timeframe)
            )
        elif symbol:
            conn.execute(
                "DELETE FROM candle_cache WHERE symbol=?",
                (symbol.lower(),)
            )
        else:
            conn.execute("DELETE FROM candle_cache")
        conn.commit()
    finally:
        conn.close()


def is_data_fresh(symbol: str, timeframe: str, max_age_hours: int = 24) -> bool:
    """Check if cached data is recent enough to skip re-fetching."""
    import time
    rng = get_cache_range(symbol, timeframe)
    if not rng:
        return False
    _, max_time, count = rng
    if count < 100:
        return False
    age_hours = (time.time() - max_time) / 3600
    return age_hours < max_age_hours
