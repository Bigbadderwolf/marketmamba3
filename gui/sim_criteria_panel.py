# gui/sim_criteria_panel.py
"""
Simulation criteria panel.
User configures all simulation parameters, clicks Run,
sees results update on chart + equity panel.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QDoubleSpinBox, QSpinBox, QCheckBox,
    QFrame, QScrollArea, QGroupBox, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from simulation.sim_engine import SimCriteria


STYLE = """
QWidget { background-color: #0a0e1a; color: #d1d4dc; font-size: 11px; }
QGroupBox {
    color: #4a9eff;
    border: 1px solid #1a2a3a;
    border-radius: 6px;
    margin-top: 8px;
    padding-top: 8px;
    font-size: 10px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    color: #4a9eff;
    letter-spacing: 1px;
}
QLabel { color: #9a9ab0; font-size: 11px; }
QLabel#section { color: #4a9eff; font-size: 10px; font-weight: bold; letter-spacing: 1px; }
QComboBox, QDoubleSpinBox, QSpinBox {
    background: #0f1e30;
    color: #d1d4dc;
    border: 1px solid #1a2a3a;
    border-radius: 4px;
    padding: 3px 6px;
    min-height: 22px;
}
QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus {
    border: 1px solid #4a9eff;
}
QComboBox QAbstractItemView {
    background: #0f1e30;
    color: #d1d4dc;
    selection-background-color: #4a9eff;
    selection-color: #000;
}
QCheckBox { color: #9a9ab0; spacing: 5px; }
QCheckBox::indicator {
    width: 14px; height: 14px;
    border: 1px solid #2a3a4a;
    border-radius: 3px;
    background: #0f1e30;
}
QCheckBox::indicator:checked { background: #00c896; border: 1px solid #00c896; }
QPushButton#run_btn {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 #00c896, stop:1 #00a878);
    color: #000;
    border: none;
    border-radius: 6px;
    padding: 10px;
    font-weight: bold;
    font-size: 13px;
    letter-spacing: 1px;
}
QPushButton#run_btn:hover { background: #00e5ad; }
QPushButton#run_btn:pressed { background: #009060; }
QPushButton#clear_btn {
    background: transparent;
    color: #555;
    border: 1px solid #1a2a3a;
    border-radius: 4px;
    padding: 6px;
    font-size: 11px;
}
QPushButton#clear_btn:hover { color: #ff5252; border-color: #ff5252; }
QFrame#divider { background: #1a2a3a; max-height: 1px; margin: 4px 0; }
"""


class SimCriteriaPanel(QWidget):
    """Left-side criteria panel for the simulation tab."""

    run_requested   = pyqtSignal(object)   # emits SimCriteria
    clear_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setStyleSheet(STYLE)
        self.setFixedWidth(200)
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        inner  = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Title
        title = QLabel("SIMULATION SETUP")
        title.setObjectName("section")
        title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        layout.addWidget(title)

        # ── Trade criteria ────────────────────────────────────────────────────
        trade_grp = QGroupBox("TRADE CRITERIA")
        tl = QVBoxLayout(trade_grp)
        tl.setSpacing(6)

        self.direction_box = self._combo("Direction",
            ["Both (Long & Short)", "Long Only", "Short Only"], tl)
        self.min_conf_box  = self._combo("Min Confidence",
            ["Low", "Medium", "High"], tl, default=1)
        self.min_prob_spin = self._dspin("Min Probability %",
            50, 95, 60, tl)
        self.risk_spin     = self._dspin("Risk per Trade %",
            0.1, 10.0, 1.0, tl, step=0.1)
        layout.addWidget(trade_grp)

        # ── Filter criteria ────────────────────────────────────────────────────
        filter_grp = QGroupBox("FILTERS")
        fl = QVBoxLayout(filter_grp)
        fl.setSpacing(6)

        self.smc_check = QCheckBox("Require SMC confirmation")
        self.smc_check.setChecked(True)
        self.ind_check = QCheckBox("Require indicator confluence")
        self.ind_check.setChecked(True)
        fl.addWidget(self.smc_check)
        fl.addWidget(self.ind_check)
        layout.addWidget(filter_grp)

        # ── Stop Loss ─────────────────────────────────────────────────────────
        sl_grp = QGroupBox("STOP LOSS")
        sl = QVBoxLayout(sl_grp)
        sl.setSpacing(6)

        self.sl_method_box = self._combo("Method",
            ["ATR-Based", "Fixed %", "Swing High/Low"], sl)
        self.sl_atr_spin   = self._dspin("ATR Multiplier",
            0.5, 5.0, 1.5, sl, step=0.1)
        self.sl_pct_spin   = self._dspin("Fixed % SL",
            0.1, 10.0, 1.0, sl, step=0.1)

        self.sl_method_box.currentIndexChanged.connect(self._on_sl_method_change)
        self._on_sl_method_change(0)
        layout.addWidget(sl_grp)

        # ── Take Profit ───────────────────────────────────────────────────────
        tp_grp = QGroupBox("TAKE PROFIT")
        tp = QVBoxLayout(tp_grp)
        tp.setSpacing(6)

        self.tp_method_box = self._combo("Method",
            ["Risk:Reward Ratio", "ATR-Based", "Fixed %"], tp)
        self.tp_rr_spin    = self._dspin("RR Ratio",
            0.5, 10.0, 2.0, tp, step=0.5)
        self.tp_atr_spin   = self._dspin("ATR Multiplier",
            1.0, 10.0, 3.0, tp, step=0.5)
        self.tp_pct_spin   = self._dspin("Fixed % TP",
            0.1, 20.0, 2.0, tp, step=0.1)

        self.tp_method_box.currentIndexChanged.connect(self._on_tp_method_change)
        self._on_tp_method_change(0)
        layout.addWidget(tp_grp)

        # ── Simulation settings ────────────────────────────────────────────────
        sim_grp = QGroupBox("SIMULATION")
        sm = QVBoxLayout(sim_grp)
        sm.setSpacing(6)

        self.candles_spin  = self._ispin("Forward Candles",
            10, 500, 50, sm)
        self.equity_spin   = self._dspin("Starting Equity $",
            100, 1000000, 10000, sm, step=1000)
        self.scenarios_box = self._combo("Scenarios",
            ["1 Scenario", "2 Scenarios", "3 Scenarios", "4 Scenarios"], sm, default=3)
        layout.addWidget(sim_grp)

        layout.addStretch()
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_frame = QFrame()
        bl = QVBoxLayout(btn_frame)
        bl.setContentsMargins(10, 6, 10, 10)
        bl.setSpacing(6)

        run_btn = QPushButton("▶  RUN SIMULATION")
        run_btn.setObjectName("run_btn")
        run_btn.clicked.connect(self._on_run)

        clear_btn = QPushButton("Clear Results")
        clear_btn.setObjectName("clear_btn")
        clear_btn.clicked.connect(self.clear_requested)

        bl.addWidget(run_btn)
        bl.addWidget(clear_btn)
        outer.addWidget(btn_frame)

    # ── Widget helpers ────────────────────────────────────────────────────────

    def _combo(self, label: str, options: list, layout,
               default: int = 0) -> QComboBox:
        lbl = QLabel(label)
        box = QComboBox()
        for o in options:
            box.addItem(o)
        box.setCurrentIndex(default)
        layout.addWidget(lbl)
        layout.addWidget(box)
        return box

    def _dspin(self, label: str, mn: float, mx: float,
               default: float, layout, step: float = 1.0) -> QDoubleSpinBox:
        lbl  = QLabel(label)
        spin = QDoubleSpinBox()
        spin.setRange(mn, mx)
        spin.setValue(default)
        spin.setSingleStep(step)
        layout.addWidget(lbl)
        layout.addWidget(spin)
        return spin

    def _ispin(self, label: str, mn: int, mx: int,
               default: int, layout) -> QSpinBox:
        lbl  = QLabel(label)
        spin = QSpinBox()
        spin.setRange(mn, mx)
        spin.setValue(default)
        layout.addWidget(lbl)
        layout.addWidget(spin)
        return spin

    # ── Visibility toggles ────────────────────────────────────────────────────

    def _on_sl_method_change(self, idx: int):
        self.sl_atr_spin.setVisible(idx == 0)
        self.sl_pct_spin.setVisible(idx == 1)

    def _on_tp_method_change(self, idx: int):
        self.tp_rr_spin.setVisible(idx == 0)
        self.tp_atr_spin.setVisible(idx == 1)
        self.tp_pct_spin.setVisible(idx == 2)

    # ── Build criteria + emit ─────────────────────────────────────────────────

    def _on_run(self):
        dir_map = {0: "BOTH", 1: "LONG", 2: "SHORT"}
        sl_map  = {0: "ATR",  1: "FIXED_PCT", 2: "SWING"}
        tp_map  = {0: "RR",   1: "ATR",       2: "FIXED_PCT"}
        conf_map = {0: "Low", 1: "Medium",    2: "High"}

        criteria = SimCriteria(
            direction       = dir_map[self.direction_box.currentIndex()],
            risk_pct        = self.risk_spin.value(),
            min_confidence  = conf_map[self.min_conf_box.currentIndex()],
            min_probability = self.min_prob_spin.value() / 100,
            require_smc     = self.smc_check.isChecked(),
            require_ind     = self.ind_check.isChecked(),
            sl_method       = sl_map[self.sl_method_box.currentIndex()],
            sl_atr_mult     = self.sl_atr_spin.value(),
            sl_fixed_pct    = self.sl_pct_spin.value(),
            tp_method       = tp_map[self.tp_method_box.currentIndex()],
            tp_rr           = self.tp_rr_spin.value(),
            tp_atr_mult     = self.tp_atr_spin.value(),
            tp_fixed_pct    = self.tp_pct_spin.value(),
            num_candles     = self.candles_spin.value(),
            starting_equity = self.equity_spin.value(),
        )

        self._n_scenarios = self.scenarios_box.currentIndex() + 1
        self.run_requested.emit(criteria)

    def get_n_scenarios(self) -> int:
        return self.scenarios_box.currentIndex() + 1
