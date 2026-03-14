# gui/window.py
"""
MainWindow — master layout controller for Market Mamba v2.0
Accepts a user dict from the auth flow.
"""
from PyQt6.QtWidgets import (
    QMainWindow, QHBoxLayout, QVBoxLayout, QWidget,
    QLabel, QStatusBar, QPushButton, QFrame
)
from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QFont

from gui.chart_view import ChartView
from gui.currency_panel import CurrencyPanel
from gui.strategy_panel import StrategyPanel
from gui.prediction_panel import PredictionPanel
from gui.simulation_panel import SimulationPanel
from gui.setup_rerun_dialog import SetupRerunDialog
from ml.trainer_worker import TrainerWorker
from simulation.sim_manager import SimManager


class MainWindow(QMainWindow):
    def __init__(self, user: dict = None):
        super().__init__()
        self.user = user or {}
        self.setWindowTitle(f"Market Mamba  —  {self.user.get('username', 'Trader')}")
        self.setGeometry(80, 80, 1600, 900)
        self.setMinimumSize(1200, 700)
        self._build_ui()
        self._build_statusbar()

    def _build_ui(self):
        self.chart_view     = ChartView()
        self.currency_panel = CurrencyPanel(self.chart_view)
        self.strategy_panel = StrategyPanel(self.chart_view)

        self.prediction_panel = PredictionPanel()
        self._sim_manager     = SimManager()
        self.sim_panel        = SimulationPanel(self._sim_manager)

        # Wire prediction signal
        self.chart_view.prediction_updated.connect(
            self.prediction_panel.update_prediction
        )

        # Wire simulation signals
        self.sim_panel.replay_candle_ready.connect(self._on_replay_candle)
        self.sim_panel.paths_ready.connect(self._on_sim_paths_ready)
        self.sim_panel.clear_requested.connect(self._on_clear_simulation)

        # ── Left column: strategy panel ───────────────────────────────────
        left_col_w = QWidget()
        lc = QVBoxLayout(left_col_w)
        lc.setSpacing(0); lc.setContentsMargins(0, 0, 0, 0)
        lc.addWidget(self.strategy_panel, 1)
        left_col_w.setFixedWidth(175)

        # ── Right column: prediction panel + sim panel ────────────────────
        right_col_w = QWidget()
        right_col_w.setFixedWidth(310)
        right_col_w.setStyleSheet(
            f"background:#08101e; border-left:1px solid #1a2a3a;"
        )
        rc = QVBoxLayout(right_col_w)
        rc.setSpacing(0); rc.setContentsMargins(0, 0, 0, 0)
        rc.addWidget(self.prediction_panel)
        rc.addWidget(self.sim_panel, 1)

        # ── Centre row ────────────────────────────────────────────────────
        centre_row = QHBoxLayout()
        centre_row.setSpacing(0)
        centre_row.setContentsMargins(0, 0, 0, 0)
        centre_row.addWidget(left_col_w)
        centre_row.addWidget(self.chart_view, 1)
        centre_row.addWidget(right_col_w)

        root = QVBoxLayout()
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._build_topbar())
        root.addWidget(self.currency_panel)
        root.addLayout(centre_row, 1)

        QTimer.singleShot(1500, self._launch_startup_trainer)

        container = QWidget()
        container.setLayout(root)
        container.setStyleSheet("""
            QWidget {
                background-color: #0f0f0f;
                color: #d1d4dc;
                font-family: 'Segoe UI', sans-serif;
                font-size: 13px;
            }
            QPushButton {
                background-color: #1a1a1a;
                color: #d1d4dc;
                border: 1px solid #2a2a2a;
                border-radius: 5px;
                padding: 5px 10px;
            }
            QPushButton:hover { background-color: #252525; }
            QPushButton:checked { background-color: #00c896; color: #000; border: 1px solid #00c896; }
        """)
        self.setCentralWidget(container)

    def _launch_startup_trainer(self):
        """
        Launch ML training in a proper QThread.
        All signals connect to slots on the main thread —
        zero direct Qt calls from the worker thread.
        """
        symbol = self.chart_view.current_symbol

        # Keep a reference so it isn't garbage-collected
        self._trainer_worker = TrainerWorker(symbol, parent=self)

        # Progress → window title (safe: queued across threads)
        self._trainer_worker.progress.connect(self._on_train_progress)

        # Predictor built in worker, handed to main thread here
        self._trainer_worker.predictor_ready.connect(self._on_predictor_ready)

        # Training done → restore title
        self._trainer_worker.finished.connect(self._on_training_finished)

        # Error → status bar
        self._trainer_worker.error.connect(
            lambda msg: self.statusBar().showMessage(f"ML error: {msg}", 8000)
        )

        # Auto-cleanup when thread finishes
        self._trainer_worker.finished.connect(self._trainer_worker.deleteLater)

        self._trainer_worker.start()

    @pyqtSlot(int, str)
    def _on_train_progress(self, pct: int, msg: str):
        """Runs on main thread — updates title and status bar."""
        username = self.user.get("username", "Trader")
        self.setWindowTitle(f"Market Mamba  [{pct}%]  {msg}")
        self.statusBar().showMessage(f"ML Training: {msg}", 3000)

    @pyqtSlot(object)
    def _on_predictor_ready(self, predictor):
        """Attach the new predictor to the chart. Runs on main thread."""
        try:
            self.chart_view._predictor = predictor
            if hasattr(self.chart_view, "_worker") and self.chart_view._worker:
                self.chart_view._worker.set_predictor(predictor)
            self.chart_view._schedule_compute_now()
        except Exception as e:
            import logging
            logging.getLogger(__name__).error("Predictor attach error: %s", e)

    @pyqtSlot(str, float, float)
    def _on_training_finished(self, symbol: str, xgb_acc: float, lstm_acc: float):
        """Runs on main thread — restore title."""
        username = self.user.get("username", "Trader")
        self.setWindowTitle(f"Market Mamba  —  {username}")
        acc_str = f"XGB {xgb_acc:.1%}" + (f"  LSTM {lstm_acc:.1%}" if lstm_acc else "")
        self.statusBar().showMessage(
            f"ML ready for {symbol.upper()}  ({acc_str})", 6000
        )

    def _on_clear_simulation(self):
        self.chart_view.clear_simulation()

    @pyqtSlot(dict, int, int)
    def _on_replay_candle(self, candle: dict, idx: int, total: int):
        """Feed a replay candle into the live chart."""
        try:
            visible = self._sim_manager.replay_get_visible()
            # Replace chart candles with replay visible window
            self.chart_view.candles = list(visible)
            self.chart_view._recompute_indicators()
            self.chart_view.update()
        except Exception as e:
            import logging
            logging.getLogger(__name__).error("Replay feed error: %s", e)

    @pyqtSlot(list)
    def _on_sim_paths_ready(self, paths: list):
        """Push generated synthetic paths to chart overlay."""
        try:
            from simulation.sim_engine import SimScenario
            # Convert GeneratedPath → SimScenario for existing overlay
            scenarios = []
            for p in paths:
                sc = SimScenario(
                    name     = p.model_name,
                    color    = p.color,
                    candles  = p.candles,
                )
                scenarios.append(sc)
            self.chart_view.set_simulation_scenarios(scenarios)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error("Paths ready error: %s", e)

    def _build_topbar(self) -> QWidget:
        bar = QFrame()
        bar.setFixedHeight(42)
        bar.setStyleSheet("QFrame { background-color: #080808; border-bottom: 1px solid #1e1e1e; }")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 16, 0)

        logo = QLabel("🐍 MARKET MAMBA")
        logo.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        logo.setStyleSheet("color: #00c896; background: transparent; border: none;")

        self.mode_live = QPushButton("● LIVE")
        self.mode_live.setCheckable(True)
        self.mode_live.setChecked(True)
        self.mode_live.setFixedWidth(80)
        self.mode_live.setStyleSheet(
            "QPushButton { color: #00c896; background: #0d2a22; border: 1px solid #00c896;"
            " border-radius: 4px; font-size: 11px; }"
            "QPushButton:checked { background: #00c896; color: #000; }"
        )

        user_lbl = QLabel(f"👤 {self.user.get('username', 'Trader')}")
        user_lbl.setStyleSheet(
            "color: #666; background: transparent; border: none; font-size: 12px;"
        )

        self.clock_lbl = QLabel()
        self.clock_lbl.setStyleSheet(
            "color: #555; background: transparent; border: none; font-size: 11px;"
        )
        self._update_clock()
        t = QTimer(self); t.timeout.connect(self._update_clock); t.start(1000)

        setup_btn = QPushButton("⚙  Setup")
        setup_btn.setStyleSheet("""
            QPushButton {
                background:#0f1e30; color:#9a9ab0;
                border:1px solid #1a2a3a; border-radius:4px;
                padding:4px 12px; font-size:10px;
            }
            QPushButton:hover {
                background:#162840; color:#4a9eff; border-color:#4a9eff;
            }
        """)
        setup_btn.clicked.connect(self._open_setup_dialog)

        layout.addWidget(logo)
        layout.addSpacing(20)
        layout.addWidget(self.mode_live)
        layout.addStretch()
        layout.addWidget(user_lbl)
        layout.addSpacing(16)
        layout.addWidget(self.clock_lbl)
        layout.addSpacing(14)
        layout.addWidget(setup_btn)
        return bar

    def _open_setup_dialog(self):
        """Open the floating setup dialog centred over the chart."""
        dlg = SetupRerunDialog(self)
        # Centre over main window
        g  = self.geometry()
        dg = dlg.geometry()
        dlg.move(
            g.x() + (g.width()  - dg.width())  // 2,
            g.y() + (g.height() - dg.height()) // 2,
        )
        dlg.setup_requested.connect(self._run_setup_for_symbols)
        dlg.exec()

    def _run_setup_for_symbols(self, symbols: list):
        """Run data download + ML training for selected symbols."""
        import threading, logging
        log = logging.getLogger(__name__)

        # Find the open dialog to update its progress bar
        dlg = None
        for child in self.findChildren(SetupRerunDialog):
            dlg = child; break

        def _worker():
            total = len(symbols)
            for i, sym in enumerate(symbols):
                pct = int((i / total) * 90)
                if dlg:
                    from PyQt6.QtCore import QMetaObject, Q_ARG, Qt
                    QMetaObject.invokeMethod(
                        dlg, "set_progress",
                        Qt.ConnectionType.QueuedConnection,
                        Q_ARG(int,  pct),
                        Q_ARG(str, f"Setting up {sym.upper()}…"),
                    )
                try:
                    from data.binance_rest import BinanceRest
                    rest = BinanceRest()
                    candles = rest.get_historical_candles(sym.lower(), "1h", limit=500)
                    if candles:
                        from ml.trainer_worker import TrainerWorker
                        # lightweight: just cache candles; full train on next startup
                        from data.data_cache import DataCache
                        cache = DataCache()
                        cache.save_candles(sym.lower(), "1h", candles)
                except Exception as e:
                    log.warning("Setup failed for %s: %s", sym, e)

            if dlg:
                from PyQt6.QtCore import QMetaObject, Qt
                QMetaObject.invokeMethod(
                    dlg, "set_done",
                    Qt.ConnectionType.QueuedConnection,
                )
            self.statusBar().showMessage(
                f"Setup complete for {len(symbols)} symbol(s).", 6000
            )

        threading.Thread(target=_worker, daemon=True).start()

    def _build_statusbar(self):
        self.status = QStatusBar()
        self.status.setStyleSheet(
            "QStatusBar { background-color: #080808; color: #555; border-top: 1px solid #1a1a1a; font-size: 11px; }"
        )
        self.setStatusBar(self.status)
        self.status.showMessage(
            f"Market Mamba v2.0  |  User: {self.user.get('username', '—')}  |  Phase 1 Complete"
        )

    def _update_clock(self):
        import time
        self.clock_lbl.setText(time.strftime("UTC  %Y-%m-%d  %H:%M:%S"))
