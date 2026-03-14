from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QThread
from PyQt6.QtGui import QPainter, QPen, QColor, QFont, QPainterPath
import time
import random
import threading
from data.binance_streamer import BinanceStreamer
from indicators.indicator_engine import IndicatorEngine
from indicators.style_store import load_all_styles, DEFAULT_STYLES
from smc.detector import SMCDetector
from ml.predictor import PredictionEngine, Prediction
from gui.prediction_badge import draw_prediction_badge
from gui.sim_overlay import draw_simulation
from simulation.sim_engine import SimScenario


# ── Background worker: runs indicator + SMC + prediction off the main thread ──

class _ComputeWorker(QObject):
    """
    Runs indicator computation, SMC detection, and ML prediction
    entirely on a background QThread.
    Results are emitted as signals — Qt delivers them to the main thread
    automatically and safely.
    """
    indicators_done = pyqtSignal(dict)   # indicator_results
    smc_done        = pyqtSignal(dict)   # smc_results
    prediction_done = pyqtSignal(object) # Prediction

    def __init__(self):
        super().__init__()
        self._ind_engine = IndicatorEngine()
        self._smc_det    = SMCDetector()
        self._predictor  = None          # set from main thread
        self._lock       = threading.Lock()
        self._pending    = False          # coalesce rapid requests

    def set_predictor(self, predictor):
        self._predictor = predictor

    def request_compute(self, candles: list, ind_params: dict,
                        active_ind: set, active_smc: set,
                        run_prediction: bool):
        """Called from main thread — schedules one compute cycle."""
        with self._lock:
            if self._pending:
                return           # already queued; will pick up latest candles
            self._pending = True
        # Use invokeMethod so the slot runs on THIS object's thread
        from PyQt6.QtCore import QMetaObject, Qt as _Qt
        QMetaObject.invokeMethod(
            self, "_do_compute",
            _Qt.ConnectionType.QueuedConnection,
            # Pass args via closure — store them temporarily
        )
        self._next_args = (list(candles), dict(ind_params),
                           set(active_ind), set(active_smc), run_prediction)

    def _do_compute(self):
        """Runs on background thread."""
        with self._lock:
            self._pending = False
            args = getattr(self, "_next_args", None)
        if args is None:
            return
        candles, ind_params, active_ind, active_smc, run_pred = args
        if len(candles) < 2:
            return

        # ── Indicators ────────────────────────────────────────────────────
        try:
            self._ind_engine._params.update(ind_params)
            ind_res = self._ind_engine.compute(candles)
            self.indicators_done.emit(ind_res)
        except Exception as e:
            import logging; logging.getLogger(__name__).error("Indicator error: %s", e)
            ind_res = {}

        # ── SMC ───────────────────────────────────────────────────────────
        if len(candles) >= 20:
            try:
                smc_res = self._smc_det.detect(candles)
                self.smc_done.emit(smc_res)
            except Exception as e:
                import logging; logging.getLogger(__name__).error("SMC error: %s", e)

        # ── ML Prediction ─────────────────────────────────────────────────
        if run_pred and self._predictor and len(candles) >= 50:
            try:
                pred = self._predictor.predict(candles, ind_res, {})
                self.prediction_done.emit(pred)
            except Exception as e:
                import logging; logging.getLogger(__name__).error("Prediction error: %s", e)


class ChartView(QWidget):
    
    candle_received  = pyqtSignal(dict)
    prediction_updated = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.candles = []
        self.streamer = None
        self.stream_thread = None
        self.current_symbol = 'btcusdt'
        self.current_interval = '1m'
        self.candles_per_view = 60
        self.view_offset = 0
        self._dragging = False
        self._drag_start_x = 0
        self._drag_start_offset = 0
        self.setMinimumHeight(400)
        self.setStyleSheet("background-color: #0f0f0f; color: #d1d4dc;")

        self.candle_received.connect(self._on_candle)

        # Phase 3: indicator / SMC state (results set from worker signals)
        self._indicator_engine  = IndicatorEngine()   # kept for style/param access
        self._smc_detector      = SMCDetector()
        self._active_indicators = set()
        self._active_smc        = set()
        self._indicator_results = {}
        self._smc_results       = {}
        self._indicator_params  = {}
        self._indicator_styles  = {}
        self._current_user_id   = 1

        # Phase 4: ML prediction
        self._predictor       = PredictionEngine(self.current_symbol)
        self._last_prediction = Prediction()
        self._prediction_enabled = True

        # Phase 5: simulation overlay + split divider
        self._sim_scenarios: list = []
        self._sim_active:    bool = False
        # Draggable split: fraction of chart_width where live ends / sim begins
        self._sim_split:          float = 0.5
        self._dragging_divider:   bool  = False

        # ── Background worker ──────────────────────────────────────────────
        self._worker        = _ComputeWorker()
        self._worker_thread = QThread()
        self._worker.moveToThread(self._worker_thread)
        self._worker.set_predictor(self._predictor)
        self._worker.indicators_done.connect(self._on_indicators_done)
        self._worker.smc_done.connect(self._on_smc_done)
        self._worker.prediction_done.connect(self._on_prediction_done)
        self._worker_thread.start()

        # Repaint throttle: schedule at most one repaint per 50ms (20 fps)
        self._repaint_pending = False
        self._repaint_timer   = QTimer()
        self._repaint_timer.setSingleShot(True)
        self._repaint_timer.setInterval(50)
        self._repaint_timer.timeout.connect(self._do_repaint)

        # Compute throttle: don't re-run compute more than once per 200ms
        self._compute_timer = QTimer()
        self._compute_timer.setSingleShot(True)
        self._compute_timer.setInterval(200)
        self._compute_timer.timeout.connect(self._trigger_compute)

        # Seed chart with placeholder candles
        base_time  = (int(time.time()) // 60) * 60
        base_price = 88000
        for i in range(20):
            ts = base_time - (19 - i) * 60
            op = base_price if i == 0 else self.candles[-1]['close']
            ch = random.uniform(-0.002, 0.002)
            cl = op * (1 + ch)
            self.candles.append({
                'time': ts, 'open': op,
                'high': max(op, cl) * (1 + random.uniform(0, 0.001)),
                'low':  min(op, cl) * (1 - random.uniform(0, 0.001)),
                'close': cl,
            })

        self.start_streaming()

        # Legacy update_timer kept for compatibility
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_chart)
        self.update_timer.start(1000)
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if not self.candles:
            return

        width  = self.width()
        height = self.height()
        padding     = 40
        chart_width  = width  - 2 * padding
        chart_height = height - 2 * padding

        if len(self.candles) < 2:
            return

        # ── Visible window ────────────────────────────────────────────────────
        visible_candles = min(len(self.candles), self.candles_per_view)
        max_scroll = max(0, len(self.candles) - visible_candles)
        self.view_offset = max(0, min(self.view_offset, max_scroll))
        start_index = max(0, len(self.candles) - visible_candles - self.view_offset)
        end_index   = min(len(self.candles), start_index + visible_candles)
        visible_slice = self.candles[start_index:end_index]
        n_live = len(visible_slice)

        # ── Unified price range (live + sim candles together) ─────────────────
        prices = []
        for c in visible_slice:
            prices.extend([c['open'], c['high'], c['low'], c['close']])
        if self._sim_active and self._sim_scenarios:
            for sc in self._sim_scenarios:
                for c in sc.candles:
                    prices.extend([c['high'], c['low']])

        min_price = min(prices)
        max_price = max(prices)
        pr        = max_price - min_price
        pad_pr    = pr * 0.1
        min_price -= pad_pr
        max_price += pad_pr
        price_range = max(max_price - min_price, 1)

        # ── Background ────────────────────────────────────────────────────────
        painter.fillRect(0, 0, width, height, QColor(15, 15, 15))

        # ── Sim zone background (right half, amber tint) ──────────────────────
        sim_active = self._sim_active and bool(self._sim_scenarios)
        if sim_active:
            split_x = padding + int(chart_width * max(0.1, min(0.9, self._sim_split)))
            from PyQt6.QtGui import QLinearGradient, QBrush
            from PyQt6.QtCore import QRectF
            grad = QLinearGradient(split_x, 0, width - padding, 0)
            grad.setColorAt(0, QColor(255, 152, 0, 22))
            grad.setColorAt(1, QColor(255, 152, 0, 8))
            painter.fillRect(QRectF(split_x, padding,
                                    width - padding - split_x, chart_height),
                             QBrush(grad))

        # ── Grid lines ────────────────────────────────────────────────────────
        painter.setPen(QPen(QColor(30, 30, 30), 1))
        for i in range(8):
            y = padding + i * chart_height / 7
            painter.drawLine(int(padding), int(y), int(width - padding), int(y))
            price = max_price - (i * price_range / 7)
            painter.setFont(QFont("Arial", 9))
            painter.setPen(QPen(QColor(150, 150, 150), 1))
            painter.drawText(5, int(y) + 3, f"${price:.0f}")

        if n_live > 0:
            for i in range(0, n_live, 5):
                x = padding + i * chart_width / max(n_live, 1)
                painter.setPen(QPen(QColor(30, 30, 30), 1))
                painter.drawLine(int(x), int(padding), int(x), int(height - padding))

        if n_live <= 0:
            return

        # ── Candle geometry ───────────────────────────────────────────────────
        def p2y(price):
            return padding + (1 - (price - min_price) / price_range) * chart_height

        if sim_active:
            # Live candles fill the LEFT portion only
            split_x      = padding + int(chart_width * max(0.1, min(0.9, self._sim_split)))
            live_width   = split_x - padding
            candle_spacing = live_width / max(n_live, 1)
        else:
            candle_spacing = chart_width / max(n_live, 1)

        candle_width = max(1.0, candle_spacing * 0.8)

        # ── Draw live candles ─────────────────────────────────────────────────
        for idx, candle in enumerate(visible_slice):
            x       = padding + idx * candle_spacing
            open_y  = p2y(candle['open'])
            close_y = p2y(candle['close'])
            high_y  = p2y(candle['high'])
            low_y   = p2y(candle['low'])

            bull = candle['close'] >= candle['open']
            body_color = QColor(0, 150, 136) if bull else QColor(255, 82, 82)

            painter.setPen(QPen(body_color, 1))
            wick_x = int(x + candle_spacing / 2)
            painter.drawLine(wick_x, int(high_y), wick_x, int(low_y))

            body_h = max(1.0, abs(close_y - open_y))
            body_y = min(open_y, close_y)
            body_x = int(x + (candle_spacing - candle_width) / 2)
            painter.fillRect(body_x, int(body_y),
                             int(candle_width), int(body_h), body_color)

        # ── SMC overlays ──────────────────────────────────────────────────────
        if self._active_smc and self._smc_results:
            self._draw_smc(painter, padding, chart_width, chart_height,
                           min_price, price_range, visible_slice, start_index)

        # ── Indicator overlays ────────────────────────────────────────────────
        if self._active_indicators and self._indicator_results:
            self._draw_indicators(painter, padding, chart_width, chart_height,
                                  min_price, price_range, candle_spacing, visible_slice)

        # ── Simulation candles (right half) ───────────────────────────────────
        if sim_active:
            split_x   = padding + int(chart_width * max(0.1, min(0.9, self._sim_split)))
            sim_width = (width - padding) - split_x
            draw_simulation(
                painter        = painter,
                widget_rect    = self.rect(),
                live_candles   = visible_slice,
                scenarios      = self._sim_scenarios,
                padding        = padding,
                candle_spacing = candle_spacing,
                min_price      = min_price,
                price_range    = price_range,
                visible_count  = n_live,
                split_x        = split_x,
                sim_width      = sim_width,
                chart_height   = chart_height,
                p2y_fn         = p2y,
            )

            # ── Draggable divider line ────────────────────────────────────────
            div_col = QColor(255, 152, 0, 200) \
                      if self._dragging_divider else QColor(255, 152, 0, 120)
            painter.setPen(QPen(div_col, 2, Qt.PenStyle.DashLine))
            painter.drawLine(split_x, padding, split_x, padding + chart_height)

            # Drag handle
            handle_col = QColor(255, 152, 0, 220)
            painter.setBrush(QBrush(handle_col))
            painter.setPen(QPen(QColor(255, 200, 0), 1))
            mid_y = padding + chart_height // 2
            from PyQt6.QtCore import QRect as _QRect
            painter.drawRoundedRect(
                _QRect(split_x - 6, mid_y - 14, 12, 28), 4, 4
            )
            painter.setPen(QPen(QColor(20, 10, 0), 1))
            painter.setFont(QFont("Arial", 7))
            painter.drawText(split_x - 3, mid_y - 3, "↔")

            # Zone labels
            painter.setFont(QFont("Arial", 8, QFont.Weight.Bold))
            painter.setPen(QPen(QColor(100, 200, 150, 160), 1))
            painter.drawText(padding + 6, padding + 16, "◀ LIVE")
            painter.setPen(QPen(QColor(255, 152, 0, 160), 1))
            painter.drawText(split_x + 8, padding + 16, "SIMULATION ▶")

        # ── ML prediction badge ───────────────────────────────────────────────
        if self._prediction_enabled:
            draw_prediction_badge(painter, self.rect(), self._last_prediction)

        # ── Current price line ────────────────────────────────────────────────
        if self.candles:
            cp    = self.candles[-1]['close']
            cp_y  = p2y(cp)
            painter.setPen(QPen(QColor(100, 200, 255), 1))
            painter.drawLine(int(padding), int(cp_y), int(width - padding), int(cp_y))
            painter.fillRect(int(width - padding - 60), int(cp_y - 8),
                             60, 16, QColor(100, 200, 255))
            painter.setPen(QPen(QColor(0, 0, 0), 1))
            painter.setFont(QFont("Arial", 8, QFont.Weight.Bold))
            painter.drawText(int(width - padding - 55), int(cp_y + 5), f"${cp:,.2f}")

        # ── Symbol + time ─────────────────────────────────────────────────────
        painter.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        painter.setPen(QPen(QColor(255, 255, 255), 1))
        painter.drawText(int(padding), 25, f"{self.current_symbol.upper()}")
        painter.setFont(QFont("Arial", 10))
        painter.setPen(QPen(QColor(150, 150, 150), 1))
        painter.drawText(int(width - 100), 25, time.strftime("%H:%M:%S"))

    def update_chart(self):
        """Legacy timer callback — use throttled repaint."""
        self._schedule_repaint()

    def send_candle(self, candle):
        """Send candle data to the chart."""
        self.candle_received.emit(candle)

    def _on_candle(self, candle):
        if not self.candles:
            self.candles.append(candle)
            self._schedule_repaint()
            return

        last_time = int(self.candles[-1]['time'])
        new_time  = int(candle['time'])

        if new_time == last_time:
            # Update current candle in place
            self.candles[-1] = candle
        elif new_time > last_time:
            self.candles.append(candle)
            if len(self.candles) > 500:
                self.candles.pop(0)

        self._schedule_repaint()
        # Kick off background compute (debounced 200ms)
        if not self._compute_timer.isActive():
            self._compute_timer.start()
    
    def add_candle(self, candle):
        self.candles.append(candle)
        if len(self.candles) > 500:
            self.candles.pop(0)
        self._schedule_repaint()
        # Throttle compute: schedule a compute 200ms after last candle
        if not self._compute_timer.isActive():
            self._compute_timer.start()

    # ── Thread-safe repaint ───────────────────────────────────────────────────

    def _schedule_repaint(self):
        if not self._repaint_pending:
            self._repaint_pending = True
            self._repaint_timer.start()

    def _do_repaint(self):
        self._repaint_pending = False
        self.update()

    # ── Compute scheduling ────────────────────────────────────────────────────

    def _trigger_compute(self):
        """Dispatch compute to background worker — never blocks main thread."""
        if len(self.candles) < 2:
            return
        self._worker.request_compute(
            candles        = self.candles,
            ind_params     = self._indicator_params,
            active_ind     = self._active_indicators,
            active_smc     = self._active_smc,
            run_prediction = self._prediction_enabled,
        )

    # ── Worker result slots (always called on main thread by Qt) ─────────────

    def _on_indicators_done(self, results: dict):
        self._indicator_results = results
        self._schedule_repaint()

    def _on_smc_done(self, results: dict):
        self._smc_results = results
        self._schedule_repaint()

    def _on_prediction_done(self, pred):
        self._last_prediction = pred
        try:
            self.prediction_updated.emit(pred)
        except Exception:
            pass
        self._schedule_repaint()

    def set_overlay(self, overlay_name):
        pass

    def set_active_indicators(self, active: set):
        self._active_indicators = active
        self._schedule_compute_now()

    def set_active_smc(self, active: set):
        self._active_smc = active
        self._schedule_compute_now()

    def update_indicator_params(self, key: str, params: dict):
        self._indicator_params[key] = params
        self._schedule_compute_now()

    def _schedule_compute_now(self):
        """Immediate compute request (user interaction — don't wait 200ms)."""
        self._compute_timer.stop()
        self._trigger_compute()

    def _recompute_indicators(self):
        """Legacy shim — now just schedules a background compute."""
        self._schedule_compute_now()

    def _recompute_smc(self):
        """Legacy shim."""
        self._schedule_compute_now()

    def apply_indicator_style(self, key: str, style: dict):
        """Called when user applies settings from IndicatorSettingsDialog."""
        self._indicator_styles[key] = style
        params = style.get("params", {})
        if params:
            self._indicator_params[key] = params
        self._schedule_compute_now()
        self._schedule_repaint()

    def set_simulation_scenarios(self, scenarios: list):
        """Called by window when simulation completes."""
        self._sim_scenarios = scenarios
        self._sim_active    = bool(scenarios)
        self.update()

    def clear_simulation(self):
        self._sim_scenarios = []
        self._sim_active    = False
        self.update()

    def load_styles_for_symbol(self):
        """Load saved styles for current symbol/user from DB."""
        try:
            self._indicator_styles = load_all_styles(
                self._current_user_id, self.current_symbol
            )
        except Exception:
            self._indicator_styles = {}

    def get_confluence_scores(self) -> dict:
        if not self.candles:
            return {"bullish": 0, "bearish": 0}
        current_price = self.candles[-1]["close"]
        ind_score  = self._indicator_engine.get_confluence_score()
        smc_scores = self._smc_detector.get_confluence_score(current_price)
        return {
            "bullish": min(100, smc_scores.get("bullish", 0) + max(0, ind_score)),
            "bearish": min(100, smc_scores.get("bearish", 0) + max(0, -ind_score)),
        }

    def change_symbol(self, symbol):
        """Change the trading symbol, backfill history, restart streaming."""
        self.current_symbol = symbol
        self.stop_streaming()
        self.candles = []
        self.view_offset = 0
        self._backfill_history()
        self.start_streaming()

    def change_interval(self, interval):
        """Change timeframe, backfill history, restart streaming."""
        self.current_interval = interval
        self.stop_streaming()
        self.candles = []
        self.view_offset = 0
        self._backfill_history()
        self.start_streaming()

    def _backfill_history(self):
        """Fetch recent historical candles from Binance REST to populate chart."""
        def _fetch():
            try:
                from data.binance_rest import fetch_recent_candles
                candles = fetch_recent_candles(
                    symbol=self.current_symbol,
                    interval=self.current_interval,
                    limit=200,
                )
                if candles:
                    self.candles = candles
                    self.update()
                    print(f"Backfilled {len(candles)} candles for {self.current_symbol.upper()} {self.current_interval}")
            except Exception as e:
                print(f"Backfill warning: {e}")
        threading.Thread(target=_fetch, daemon=True).start()

    def start_streaming(self):
        """Start the Binance WebSocket stream."""
        if self.streamer:
            self.stop_streaming()
        self.streamer = BinanceStreamer(self, self.current_symbol, self.current_interval)
        self.stream_thread = threading.Thread(target=self.streamer.run, daemon=True)
        self.stream_thread.start()
        print(f"Started streaming {self.current_symbol.upper()}")

    def stop_streaming(self):
        """Stop the current stream"""
        if self.streamer:
            self.streamer.stop()
        if self.stream_thread and self.stream_thread.is_alive():
            self.stream_thread.join(timeout=1)
        self.streamer = None
        self.stream_thread = None
        print("Stopped streaming")


    def _price_to_y(self, price, padding, chart_height, min_price, price_range):
        return padding + (1 - (price - min_price) / price_range) * chart_height

    def _draw_smc(self, painter, padding, chart_width, chart_height,
                  min_price, price_range, visible_slice, start_index):
        """Render SMC features on the chart."""
        width = self.width()

        def p2y(price):
            return self._price_to_y(price, padding, chart_height, min_price, price_range)

        # Order Blocks
        if "OB" in self._active_smc:
            for ob in self._smc_results.get("order_blocks", []):
                idx = ob["index"] - start_index
                if idx < 0 or idx >= len(visible_slice):
                    continue
                top_y = p2y(ob["top"])
                bot_y = p2y(ob["bottom"])
                if ob["type"] == "BULLISH_OB":
                    col = QColor(0, 150, 80, 40 + ob["strength"] * 15)
                    border = QColor(0, 200, 100, 180)
                else:
                    col = QColor(200, 50, 50, 40 + ob["strength"] * 15)
                    border = QColor(255, 80, 80, 180)
                x_start = padding + idx * (chart_width / max(1, len(visible_slice)))
                painter.fillRect(int(x_start), int(top_y),
                                 int(width - padding - x_start), int(abs(bot_y - top_y)), col)
                painter.setPen(QPen(border, 1))
                painter.drawRect(int(x_start), int(top_y),
                                 int(width - padding - x_start), int(abs(bot_y - top_y)))
                painter.setFont(QFont("Arial", 8))
                painter.setPen(QPen(border, 1))
                lbl = "Bull OB" if ob["type"] == "BULLISH_OB" else "Bear OB"
                painter.drawText(int(x_start) + 2, int(top_y) - 2, lbl)

        # Fair Value Gaps
        if "FVG" in self._active_smc:
            for fvg in self._smc_results.get("fvgs", []):
                idx = fvg["index"] - start_index
                if idx < 0 or idx >= len(visible_slice):
                    continue
                top_y = p2y(fvg["top"])
                bot_y = p2y(fvg["bottom"])
                col   = QColor(30, 100, 180, 35)
                border = QColor(100, 180, 255, 150)
                x_start = padding + idx * (chart_width / max(1, len(visible_slice)))
                painter.fillRect(int(x_start), int(top_y),
                                 int(width - padding - x_start), int(abs(bot_y - top_y)), col)
                painter.setPen(QPen(border, 1, Qt.PenStyle.DashLine))
                painter.drawRect(int(x_start), int(top_y),
                                 int(width - padding - x_start), int(abs(bot_y - top_y)))

        # BOS / CHoCH
        if "BOS" in self._active_smc:
            for event in self._smc_results.get("structure", []):
                idx = event["index"] - start_index
                if idx < 0 or idx >= len(visible_slice):
                    continue
                y   = p2y(event["price"])
                col = QColor(0, 255, 136) if event["direction"] == "BULLISH" else QColor(255, 68, 68)
                lbl = event["type"]
                painter.setPen(QPen(col, 1, Qt.PenStyle.DashLine))
                x   = padding + idx * (chart_width / max(1, len(visible_slice)))
                painter.drawLine(int(x), int(y), int(width - padding), int(y))
                painter.setFont(QFont("Arial", 8))
                painter.setPen(QPen(col, 1))
                painter.drawText(int(x) + 4, int(y) - 3, lbl)

        # Liquidity levels
        if "LIQ" in self._active_smc:
            for liq in self._smc_results.get("liquidity", []):
                if "price" not in liq:
                    continue
                y   = p2y(liq["price"])
                if y < padding or y > padding + chart_height:
                    continue
                col = QColor(255, 221, 0, 180)
                painter.setPen(QPen(col, 1, Qt.PenStyle.DotLine))
                painter.drawLine(int(padding), int(y), int(width - padding), int(y))
                painter.setFont(QFont("Arial", 8))
                ltype = liq["type"].replace("_", " ")
                painter.drawText(int(padding) + 4, int(y) - 2, ltype[:12])

    def _draw_indicators(self, painter, padding, chart_width, chart_height,
                         min_price, price_range, candle_spacing, visible_slice):
        """
        Render all indicator overlays.

        Price-overlay indicators (EMAs, VWAP, BB, Keltner, Ichimoku) draw
        directly on the main chart using the price axis.

        Oscillator indicators (RSI, Stoch RSI, MACD, ATR, OBV, CVD, CCI, ADX)
        each get their own sub-panel drawn below the main chart, stacked
        vertically. The main chart is shrunk to leave room.
        """
        import math
        import numpy as np
        from indicators.style_store import DEFAULT_STYLES

        n = len(visible_slice)
        if n < 2:
            return

        r = self._indicator_results
        if not r:
            return

        # ── Determine which oscillators are active ────────────────────────────
        OSCILLATORS = ["RSI", "STOCHRSI", "MACD", "ATR", "OBV", "CVD", "CCI", "ADX"]
        active_osc  = [k for k in OSCILLATORS if k in self._active_indicators]
        n_panels    = len(active_osc)

        # Sub-panel layout: each panel gets equal height below main chart
        sub_panel_h = 60 if n_panels > 0 else 0
        sub_gap     = 4
        total_sub_h = n_panels * (sub_panel_h + sub_gap)

        # Effective main chart height shrinks if oscillators are active
        main_h = chart_height - total_sub_h

        # ── Helper: price → Y on main chart ──────────────────────────────────
        def p2y(price):
            return padding + (1.0 - (price - min_price) / price_range) * main_h

        # ── Helper: value → Y within a sub-panel ─────────────────────────────
        def v2y(val, v_min, v_max, panel_top, panel_h):
            v_range = max(v_max - v_min, 1e-10)
            return panel_top + (1.0 - (val - v_min) / v_range) * panel_h

        # ── Helper: hex color → QColor ────────────────────────────────────────
        def hex2col(hex_str, alpha=200):
            h = hex_str.lstrip("#")
            if len(h) == 8:
                return QColor(int(h[0:2],16), int(h[2:4],16),
                              int(h[4:6],16), int(h[6:8],16))
            elif len(h) == 6:
                return QColor(int(h[0:2],16), int(h[2:4],16),
                              int(h[4:6],16), alpha)
            return QColor(128, 128, 128, alpha)

        # ── Helper: get saved style component ────────────────────────────────
        def get_style(key, comp="line"):
            saved = self._indicator_styles.get(key, {})
            comps = saved.get("components",
                              DEFAULT_STYLES.get(key, {}).get("components", {}))
            return comps.get(comp, {})

        # ── Helper: pen style string → Qt enum ───────────────────────────────
        def pen_style(s):
            return {"solid": Qt.PenStyle.SolidLine,
                    "dashed": Qt.PenStyle.DashLine,
                    "dotted": Qt.PenStyle.DotLine,
                    "dash-dot": Qt.PenStyle.DashDotLine
                    }.get(s, Qt.PenStyle.SolidLine)

        # ── Helper: draw a line series on the main price chart ────────────────
        def draw_price_line(arr, color="#888888", thickness=1,
                            style="solid", visible=True, label=None):
            if not visible or arr is None:
                return
            data = arr[-n:] if len(arr) >= n else arr
            col  = hex2col(color)
            painter.setPen(QPen(col, thickness, pen_style(style)))
            prev_pt = None
            for i, v in enumerate(data):
                try:
                    fv = float(v)
                    if math.isnan(fv) or math.isinf(fv):
                        prev_pt = None
                        continue
                except (TypeError, ValueError):
                    prev_pt = None
                    continue
                x = padding + i * candle_spacing + candle_spacing / 2
                y = p2y(fv)
                if padding <= y <= padding + main_h:
                    if prev_pt:
                        painter.drawLine(int(prev_pt[0]), int(prev_pt[1]),
                                         int(x), int(y))
                    prev_pt = (x, y)
                else:
                    prev_pt = None
            # Label at right edge
            if label and len(data) > 0:
                try:
                    last_v = float(data[-1])
                    if not math.isnan(last_v):
                        lx = padding + (len(data) - 1) * candle_spacing + candle_spacing / 2
                        ly = p2y(last_v)
                        if padding <= ly <= padding + main_h:
                            painter.setFont(QFont("Arial", 8))
                            painter.setPen(QPen(col, 1))
                            painter.drawText(int(lx) + 4, int(ly) + 4, label)
                except (TypeError, ValueError):
                    pass

        # ── Helper: draw oscillator sub-panel ────────────────────────────────
        def draw_sub_panel(panel_idx, arr, color="#888888", label="",
                           v_min=None, v_max=None, thickness=1,
                           ref_lines=None, hist=False,
                           arr2=None, color2="#ff5252"):
            """
            Draw a single oscillator in its sub-panel slot.
            panel_idx: 0-based index into active_osc list.
            ref_lines: list of (value, color, label) for horizontal references.
            hist: True = draw as histogram bars.
            arr2: optional second line (e.g. MACD signal).
            """
            top = padding + main_h + sub_gap + panel_idx * (sub_panel_h + sub_gap)
            bot = top + sub_panel_h

            # Background
            painter.fillRect(int(padding), int(top),
                             int(chart_width), int(sub_panel_h),
                             QColor(15, 18, 30))
            painter.setPen(QPen(QColor(30, 40, 60), 1))
            painter.drawRect(int(padding), int(top),
                             int(chart_width), int(sub_panel_h))

            # Panel label
            painter.setPen(QPen(hex2col(color, 160), 1))
            painter.setFont(QFont("Arial", 8, QFont.Weight.Bold))
            painter.drawText(int(padding) + 4, int(top) + 12, label)

            if arr is None or len(arr) < 2:
                return

            data = list(arr[-n:]) if len(arr) >= n else list(arr)
            data_clean = []
            for v in data:
                try:
                    fv = float(v)
                    data_clean.append(None if (math.isnan(fv) or math.isinf(fv)) else fv)
                except (TypeError, ValueError):
                    data_clean.append(None)

            valid = [v for v in data_clean if v is not None]
            if not valid:
                return

            lo = v_min if v_min is not None else min(valid)
            hi = v_max if v_max is not None else max(valid)
            if lo == hi:
                hi = lo + 1

            # Reference lines (e.g. RSI 70/30)
            if ref_lines:
                for rv, rc, rl in ref_lines:
                    ry = v2y(rv, lo, hi, top, sub_panel_h)
                    if top <= ry <= bot:
                        painter.setPen(QPen(hex2col(rc, 80), 1, Qt.PenStyle.DashLine))
                        painter.drawLine(int(padding), int(ry),
                                         int(padding + chart_width), int(ry))
                        painter.setPen(QPen(hex2col(rc, 100), 1))
                        painter.setFont(QFont("Arial", 7))
                        painter.drawText(int(padding) + 4,
                                         int(ry) - 2, str(rl))

            col = hex2col(color)

            if hist:
                # Histogram bars
                zero_y = v2y(0.0, lo, hi, top, sub_panel_h)
                zero_y = max(top, min(bot, zero_y))
                for i, v in enumerate(data_clean):
                    if v is None:
                        continue
                    bx = padding + i * candle_spacing
                    vy = v2y(v, lo, hi, top, sub_panel_h)
                    bar_h = abs(vy - zero_y)
                    bar_y = min(vy, zero_y)
                    bc = hex2col("#00c896", 180) if v >= 0 else hex2col("#ff5252", 180)
                    painter.fillRect(int(bx), int(bar_y),
                                     max(1, int(candle_spacing * 0.8)), int(bar_h), bc)
            else:
                # Line
                painter.setPen(QPen(col, thickness))
                prev_pt = None
                for i, v in enumerate(data_clean):
                    if v is None:
                        prev_pt = None
                        continue
                    x = padding + i * candle_spacing + candle_spacing / 2
                    y = v2y(v, lo, hi, top, sub_panel_h)
                    y = max(top + 1, min(bot - 1, y))
                    if prev_pt:
                        painter.drawLine(int(prev_pt[0]), int(prev_pt[1]),
                                         int(x), int(y))
                    prev_pt = (x, y)

            # Optional second line (signal line etc.)
            if arr2 is not None:
                data2 = list(arr2[-n:]) if len(arr2) >= n else list(arr2)
                painter.setPen(QPen(hex2col(color2, 200), 1))
                prev_pt = None
                for i, v in enumerate(data2):
                    try:
                        fv = float(v)
                        if math.isnan(fv) or math.isinf(fv):
                            prev_pt = None
                            continue
                    except (TypeError, ValueError):
                        prev_pt = None
                        continue
                    x = padding + i * candle_spacing + candle_spacing / 2
                    y = v2y(fv, lo, hi, top, sub_panel_h)
                    y = max(top + 1, min(bot - 1, y))
                    if prev_pt:
                        painter.drawLine(int(prev_pt[0]), int(prev_pt[1]),
                                         int(x), int(y))
                    prev_pt = (x, y)

            # Current value label (right edge)
            if valid:
                last_v = valid[-1]
                painter.setFont(QFont("Consolas", 8))
                painter.setPen(QPen(col, 1))
                painter.drawText(int(padding + chart_width) - 55,
                                 int(top) + 12, f"{last_v:.2f}")

        # ════════════════════════════════════════════════════════════════════
        # PRICE-OVERLAY INDICATORS
        # ════════════════════════════════════════════════════════════════════

        # ── EMAs ─────────────────────────────────────────────────────────────
        EMA_DEFAULTS = {
            "EMA_9":  "#ff9800", "EMA_21": "#2196f3",
            "EMA_50": "#9c27b0", "EMA_200": "#f44336",
        }
        for key, default_col in EMA_DEFAULTS.items():
            if key in self._active_indicators and key in r:
                s   = get_style(key)
                col = s.get("color", default_col)
                thk = s.get("thickness", 1)
                sty = s.get("style", "solid")
                vis = s.get("visible", True)
                arr = r[key]
                if len(arr) > 0:
                    last_val = arr[-1]
                    try:
                        lv = float(last_val)
                        lbl = f"{key.replace('_', ' ')} ${lv:,.0f}" if not math.isnan(lv) else None
                    except (TypeError, ValueError):
                        lbl = None
                    draw_price_line(arr, col, thk, sty, vis, label=lbl)

        # ── VWAP ─────────────────────────────────────────────────────────────
        if "VWAP" in self._active_indicators and "VWAP" in r:
            s = get_style("VWAP")
            draw_price_line(r["VWAP"],
                            s.get("color", "#00bcd4"),
                            s.get("thickness", 1),
                            s.get("style", "solid"),
                            s.get("visible", True),
                            label="VWAP")

        # ── Bollinger Bands ───────────────────────────────────────────────────
        if "BB" in self._active_indicators:
            for comp, rkey, def_col, def_sty in [
                ("upper",  "BB_UPPER", "#607d8b", "solid"),
                ("middle", "BB_MID",   "#607d8b", "dashed"),
                ("lower",  "BB_LOWER", "#607d8b", "solid"),
            ]:
                if rkey in r:
                    s = get_style("BB", comp)
                    draw_price_line(r[rkey],
                                    s.get("color", def_col),
                                    s.get("thickness", 1),
                                    s.get("style", def_sty),
                                    s.get("visible", True))

        # ── Keltner Channel ───────────────────────────────────────────────────
        if "KELTNER" in self._active_indicators:
            for comp, rkey in [("upper","KC_UPPER"),("mid","KC_MID"),("lower","KC_LOWER")]:
                if rkey in r:
                    s = get_style("KELTNER", comp)
                    draw_price_line(r[rkey],
                                    s.get("color", "#ff9800"),
                                    s.get("thickness", 1),
                                    s.get("style", "dashed"),
                                    s.get("visible", True))

        # ── Ichimoku ─────────────────────────────────────────────────────────
        if "ICHIMOKU" in self._active_indicators:
            ichi_map = [
                ("tenkan",  "ICHI_TENKAN", "#e91e63"),
                ("kijun",   "ICHI_KIJUN",  "#2196f3"),
                ("senkou_a","ICHI_SPAN_A","#00c896"),
                ("senkou_b","ICHI_SPAN_B","#ff5252"),
                ("chikou",  "ICHI_CHIKOU", "#ffeb3b"),
            ]
            for comp, rkey, def_col in ichi_map:
                if rkey in r:
                    s = get_style("ICHIMOKU", comp)
                    draw_price_line(r[rkey],
                                    s.get("color", def_col),
                                    s.get("thickness", 1),
                                    s.get("style", "solid"),
                                    s.get("visible", True))

        # ════════════════════════════════════════════════════════════════════
        # OSCILLATOR SUB-PANELS
        # ════════════════════════════════════════════════════════════════════

        for panel_idx, osc_key in enumerate(active_osc):

            if osc_key == "RSI":
                arr = r.get("RSI")
                if arr is not None:
                    s = get_style("RSI")
                    draw_sub_panel(
                        panel_idx, arr,
                        color     = s.get("color", "#ffeb3b"),
                        label     = "RSI",
                        v_min     = 0, v_max = 100,
                        thickness = s.get("thickness", 1),
                        ref_lines = [
                            (70, "#ff5252", "70"),
                            (50, "#888888", "50"),
                            (30, "#00c896", "30"),
                        ],
                    )

            elif osc_key == "STOCHRSI":
                arr_k = r.get("STOCHRSI_K")
                arr_d = r.get("STOCHRSI_D")
                if arr_k is not None:
                    draw_sub_panel(
                        panel_idx, arr_k,
                        color     = "#ff9800",
                        label     = "Stoch RSI  K/D",
                        v_min     = 0, v_max = 100,
                        ref_lines = [(80,"#ff5252","80"),(20,"#00c896","20")],
                        arr2      = arr_d,
                        color2    = "#2196f3",
                    )

            elif osc_key == "MACD":
                arr_hist = r.get("MACD_HIST")
                arr_macd = r.get("MACD")
                arr_sig  = r.get("MACD_SIGNAL")
                if arr_hist is not None and arr_macd is not None:
                    # Compute combined range
                    vals = []
                    for a in [arr_hist, arr_macd, arr_sig]:
                        if a is not None:
                            for v in a[-n:]:
                                try:
                                    fv = float(v)
                                    if not math.isnan(fv): vals.append(fv)
                                except (TypeError, ValueError):
                                    pass
                    lo = min(vals) if vals else -1
                    hi = max(vals) if vals else 1
                    # Draw histogram first
                    draw_sub_panel(
                        panel_idx, arr_hist,
                        color     = "#4caf50",
                        label     = "MACD",
                        v_min     = lo, v_max = hi,
                        hist      = True,
                        ref_lines = [(0, "#888888", "0")],
                    )
                    # Draw MACD line + signal line on top
                    if arr_macd is not None and arr_sig is not None:
                        top_y = padding + main_h + sub_gap + panel_idx * (sub_panel_h + sub_gap)
                        data_m = list(arr_macd[-n:]) if len(arr_macd) >= n else list(arr_macd)
                        data_s = list(arr_sig[-n:])  if len(arr_sig)  >= n else list(arr_sig)
                        for data, col_hex in [(data_m, "#4caf50"), (data_s, "#ff9800")]:
                            painter.setPen(QPen(hex2col(col_hex, 220), 1))
                            prev = None
                            for i, v in enumerate(data):
                                try:
                                    fv = float(v)
                                    if math.isnan(fv): prev = None; continue
                                except (TypeError, ValueError):
                                    prev = None; continue
                                x = padding + i * candle_spacing + candle_spacing / 2
                                y = v2y(fv, lo, hi, top_y, sub_panel_h)
                                y = max(top_y+1, min(top_y+sub_panel_h-1, y))
                                if prev:
                                    painter.drawLine(int(prev[0]), int(prev[1]),
                                                     int(x), int(y))
                                prev = (x, y)

            elif osc_key == "ATR":
                arr = r.get("ATR")
                if arr is not None:
                    s = get_style("ATR")
                    draw_sub_panel(
                        panel_idx, arr,
                        color     = s.get("color", "#795548"),
                        label     = "ATR",
                        thickness = s.get("thickness", 1),
                    )

            elif osc_key == "OBV":
                arr = r.get("OBV")
                if arr is not None:
                    draw_sub_panel(
                        panel_idx, arr,
                        color = "#009688",
                        label = "OBV",
                    )

            elif osc_key == "CVD":
                arr = r.get("CVD")
                if arr is not None:
                    draw_sub_panel(
                        panel_idx, arr,
                        color     = "#3f51b5",
                        label     = "CVD",
                        ref_lines = [(0, "#888888", "0")],
                        hist      = True,
                    )

            elif osc_key == "CCI":
                arr = r.get("CCI")
                if arr is not None:
                    s = get_style("CCI") if hasattr(self, '_indicator_styles') else {}
                    draw_sub_panel(
                        panel_idx, arr,
                        color     = "#9c27b0",
                        label     = "CCI",
                        ref_lines = [
                            ( 100, "#ff5252", "+100"),
                            (   0, "#888888",    "0"),
                            (-100, "#00c896", "-100"),
                        ],
                    )

            elif osc_key == "ADX":
                arr = r.get("ADX")
                if arr is not None:
                    draw_sub_panel(
                        panel_idx, arr,
                        color     = "#ff5722",
                        label     = "ADX",
                        v_min     = 0, v_max = 100,
                        ref_lines = [(25, "#ffeb3b", "25")],
                    )
    def _divider_x(self) -> int:
        """Return current pixel X of the sim split divider."""
        padding     = 40
        chart_width = max(1, self.width() - 2 * padding)
        return padding + int(chart_width * max(0.1, min(0.9, self._sim_split)))

    def _near_divider(self, px: int) -> bool:
        """True if pixel x is within 8px of the divider."""
        return self._sim_active and abs(px - self._divider_x()) <= 8

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta == 0:
            return
        step = 5
        if delta > 0:
            self.candles_per_view = max(10, self.candles_per_view - step)
        else:
            self.candles_per_view = min(200, self.candles_per_view + step)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            px = int(event.position().x())
            if self._near_divider(px):
                self._dragging_divider = True
                event.accept()
                return
            self._dragging = True
            self._drag_start_x = px
            self._drag_start_offset = self.view_offset
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        px = int(event.position().x())

        # Update cursor shape near divider
        if self._sim_active and self._near_divider(px):
            self.setCursor(Qt.CursorShape.SplitHCursor)
        elif not self._dragging_divider:
            self.setCursor(Qt.CursorShape.ArrowCursor)

        # Drag the divider
        if self._dragging_divider:
            padding     = 40
            chart_width = max(1, self.width() - 2 * padding)
            frac = (px - padding) / chart_width
            self._sim_split = max(0.1, min(0.9, frac))
            self.update()
            event.accept()
            return

        if not self._dragging:
            super().mouseMoveEvent(event)
            return

        width = self.width()
        padding = 40
        chart_width = max(1, width - 2 * padding)
        visible_candles = max(1, min(len(self.candles), self.candles_per_view))
        if self._sim_active:
            live_width = chart_width * max(0.1, min(0.9, self._sim_split))
            candle_spacing = live_width / visible_candles
        else:
            candle_spacing = chart_width / visible_candles

        x     = px
        dx    = x - self._drag_start_x
        shift = int((-dx) / max(1, candle_spacing))
        visible    = min(len(self.candles), self.candles_per_view)
        max_scroll = max(0, len(self.candles) - visible)
        self.view_offset = max(0, min(self._drag_start_offset + shift, max_scroll))
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._dragging_divider:
                self._dragging_divider = False
                self.setCursor(Qt.CursorShape.ArrowCursor)
                event.accept()
                return
            self._dragging = False
            event.accept()
        else:
            super().mouseReleaseEvent(event)
