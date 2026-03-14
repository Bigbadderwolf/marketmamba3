# data/binance_streamer.py
"""
Binance WebSocket streamer for Market Mamba.
Streams real-time kline/candlestick data via Binance WebSocket API.
Thread-safe — communicates with ChartView via Qt signals.
"""

import json
import time
import logging
import threading
import websocket

log = logging.getLogger(__name__)

BINANCE_WS_BASE = "wss://stream.binance.com:9443/ws"


class BinanceStreamer:
    """
    Connects to Binance WebSocket and streams live kline data.

    Usage:
        streamer = BinanceStreamer(chart_view, 'btcusdt', '1m')
        thread = threading.Thread(target=streamer.run, daemon=True)
        thread.start()
        ...
        streamer.stop()
    """

    def __init__(self, chart_view, symbol: str, interval: str):
        self.chart_view = chart_view
        self.symbol     = symbol.lower()
        self.interval   = interval
        self._running   = False
        self._ws        = None

    def run(self):
        """Start the WebSocket connection. Blocking — run in a thread."""
        self._running = True
        url = f"{BINANCE_WS_BASE}/{self.symbol}@kline_{self.interval}"
        log.info("Connecting to Binance WS: %s", url)

        self._ws = websocket.WebSocketApp(
            url,
            on_open    = self._on_open,
            on_message = self._on_message,
            on_error   = self._on_error,
            on_close   = self._on_close,
        )

        while self._running:
            try:
                self._ws.run_forever(ping_interval=20, ping_timeout=10)
            except Exception as e:
                log.error("WebSocket run_forever error: %s", e)

            if self._running:
                log.info("WebSocket disconnected — reconnecting in 3s...")
                time.sleep(3)

    def stop(self):
        """Gracefully stop the WebSocket stream."""
        self._running = False
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
        log.info("Streamer stopped: %s %s", self.symbol.upper(), self.interval)

    # ── WebSocket callbacks ───────────────────────────────────────────────────

    def _on_open(self, ws):
        log.info("WebSocket connected: %s@kline_%s", self.symbol, self.interval)

    def _on_message(self, ws, message: str):
        """Parse incoming kline message and emit to ChartView."""
        try:
            data = json.loads(message)
            k    = data.get("k", {})

            candle = {
                "time":   int(k["t"]) // 1000,   # ms → seconds
                "open":   float(k["o"]),
                "high":   float(k["h"]),
                "low":    float(k["l"]),
                "close":  float(k["c"]),
                "volume": float(k["v"]),
                "closed": bool(k["x"]),           # True when candle is finalised
            }

            # Emit via Qt signal (thread-safe)
            self.chart_view.candle_received.emit(candle)

        except Exception as e:
            log.error("Error parsing kline message: %s", e)

    def _on_error(self, ws, error):
        log.error("WebSocket error: %s", error)

    def _on_close(self, ws, close_status_code, close_msg):
        log.info(
            "WebSocket closed: %s %s (code=%s)",
            self.symbol.upper(), self.interval, close_status_code
        )# binance_streamer.py — kept intact from original
# binance_streamer.py — kept intact from original
# binance_streamer.py — kept intact from original

