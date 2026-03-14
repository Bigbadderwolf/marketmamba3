# gui/prediction_panel.py
"""
ML Prediction Panel — full breakdown display.
Sits below/beside the chart.
Shows: direction, probability, confidence, XGB vs LSTM breakdown,
       SMC bias, indicator bias, 3-candle forecast table.
Updates on every new candle.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QGridLayout, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QColor, QPainter, QPen, QFont, QLinearGradient, QBrush

from ml.predictor import Prediction


PANEL_STYLE = """
QWidget#pred_panel {
    background-color: #0a0e1a;
    border-top: 1px solid #1a2a3a;
}
QLabel#pred_title {
    color: #4a9eff;
    font-size: 10px;
    font-weight: bold;
    letter-spacing: 2px;
}
QLabel#direction_up {
    color: #00c896;
    font-size: 22px;
    font-weight: bold;
    font-family: 'Consolas', monospace;
}
QLabel#direction_down {
    color: #ff5252;
    font-size: 22px;
    font-weight: bold;
    font-family: 'Consolas', monospace;
}
QLabel#direction_neutral {
    color: #888;
    font-size: 22px;
    font-weight: bold;
    font-family: 'Consolas', monospace;
}
QLabel#prob_label {
    color: #ffffff;
    font-size: 18px;
    font-weight: bold;
    font-family: 'Consolas', monospace;
}
QLabel#conf_high   { color: #00c896; font-size: 11px; font-weight: bold; }
QLabel#conf_medium { color: #ffb74d; font-size: 11px; font-weight: bold; }
QLabel#conf_low    { color: #ff5252; font-size: 11px; font-weight: bold; }
QLabel#model_label {
    color: #555;
    font-size: 10px;
    letter-spacing: 1px;
}
QLabel#model_value {
    color: #9a9ab0;
    font-size: 11px;
    font-family: 'Consolas', monospace;
}
QLabel#bias_bull { color: #00c896; font-size: 11px; font-weight: bold; }
QLabel#bias_bear { color: #ff5252; font-size: 11px; font-weight: bold; }
QLabel#bias_neut { color: #666;    font-size: 11px; }
QLabel#fc_header {
    color: #4a9eff;
    font-size: 10px;
    font-weight: bold;
    letter-spacing: 1px;
}
QLabel#fc_up    { color: #00c896; font-size: 11px; font-family: 'Consolas', monospace; }
QLabel#fc_down  { color: #ff5252; font-size: 11px; font-family: 'Consolas', monospace; }
QLabel#fc_neut  { color: #666;    font-size: 11px; font-family: 'Consolas', monospace; }
QLabel#waiting  { color: #444;    font-size: 11px; font-style: italic; }
QLabel#agree    { color: #00c896; font-size: 10px; }
QLabel#disagree { color: #ff9800; font-size: 10px; }
QFrame#divider_v {
    background-color: #1a2a3a;
    max-width: 1px;
    margin: 4px 8px;
}
QFrame#divider_h {
    background-color: #1a2a3a;
    max-height: 1px;
}
"""


class ProbabilityBar(QWidget):
    """Animated probability bar — green for UP, red for DOWN."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(6)
        self.setMinimumWidth(120)
        self._prob      = 0.5
        self._direction = "NEUTRAL"

    def set_prediction(self, direction: str, probability: float):
        self._direction = direction
        self._prob      = probability
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # Background
        p.fillRect(0, 0, w, h, QColor("#1a2a3a"))

        # Fill
        fill_w = int(w * self._prob)
        if self._direction == "UP":
            color = QColor("#00c896")
        elif self._direction == "DOWN":
            color = QColor("#ff5252")
        else:
            color = QColor("#555")
            fill_w = w // 2

        grad = QLinearGradient(0, 0, fill_w, 0)
        grad.setColorAt(0, color)
        grad.setColorAt(1, color.lighter(120))
        p.fillRect(0, 0, fill_w, h, QBrush(grad))


class PredictionPanel(QWidget):
    """
    Full prediction breakdown panel.
    Updated via update_prediction() on every new candle.
    """

    def __init__(self):
        super().__init__()
        self.setObjectName("pred_panel")
        self.setStyleSheet(PANEL_STYLE)
        self.setFixedHeight(130)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._build_ui()

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 8)
        root.setSpacing(0)

        # ── Column 1: Main direction + probability ────────────────────────────
        col1 = QVBoxLayout()
        col1.setSpacing(2)

        title1 = QLabel("ML PREDICTION")
        title1.setObjectName("pred_title")
        col1.addWidget(title1)

        dir_row = QHBoxLayout()
        self.direction_lbl = QLabel("--")
        self.direction_lbl.setObjectName("direction_neutral")
        self.prob_lbl = QLabel("")
        self.prob_lbl.setObjectName("prob_label")
        dir_row.addWidget(self.direction_lbl)
        dir_row.addWidget(self.prob_lbl)
        dir_row.addStretch()
        col1.addLayout(dir_row)

        self.prob_bar = ProbabilityBar()
        col1.addWidget(self.prob_bar)

        self.conf_lbl = QLabel("")
        col1.addWidget(self.conf_lbl)

        self.agree_lbl = QLabel("")
        col1.addWidget(self.agree_lbl)

        self.waiting_lbl = QLabel("Collecting data...")
        self.waiting_lbl.setObjectName("waiting")
        col1.addWidget(self.waiting_lbl)

        col1.addStretch()
        col1_w = QWidget()
        col1_w.setLayout(col1)
        col1_w.setFixedWidth(160)
        root.addWidget(col1_w)

        root.addWidget(self._vdivider())

        # ── Column 2: Model breakdown ─────────────────────────────────────────
        col2 = QVBoxLayout()
        col2.setSpacing(3)

        title2 = QLabel("MODEL BREAKDOWN")
        title2.setObjectName("pred_title")
        col2.addWidget(title2)

        grid = QGridLayout()
        grid.setSpacing(4)
        grid.setHorizontalSpacing(10)

        for row, (lbl_text, attr) in enumerate([
            ("XGBoost",   "_xgb_lbl"),
            ("LSTM",      "_lstm_lbl"),
            ("SMC Bias",  "_smc_lbl"),
            ("Ind. Bias", "_ind_lbl"),
        ]):
            key_lbl = QLabel(lbl_text)
            key_lbl.setObjectName("model_label")
            val_lbl = QLabel("--")
            val_lbl.setObjectName("model_value")
            setattr(self, attr, val_lbl)
            grid.addWidget(key_lbl, row, 0)
            grid.addWidget(val_lbl, row, 1)

        col2.addLayout(grid)
        col2.addStretch()
        col2_w = QWidget()
        col2_w.setLayout(col2)
        col2_w.setFixedWidth(170)
        root.addWidget(col2_w)

        root.addWidget(self._vdivider())

        # ── Column 3: 3-candle forecast ───────────────────────────────────────
        col3 = QVBoxLayout()
        col3.setSpacing(3)

        title3 = QLabel("3-CANDLE FORECAST")
        title3.setObjectName("pred_title")
        col3.addWidget(title3)

        self._fc_labels = []
        for i in range(3):
            lbl = QLabel(f"C+{i+1}  --")
            lbl.setObjectName("fc_neut")
            col3.addWidget(lbl)
            self._fc_labels.append(lbl)

        col3.addStretch()
        col3_w = QWidget()
        col3_w.setLayout(col3)
        col3_w.setMinimumWidth(200)
        root.addWidget(col3_w)

        root.addStretch()

    def _vdivider(self) -> QFrame:
        d = QFrame()
        d.setObjectName("divider_v")
        d.setFrameShape(QFrame.Shape.VLine)
        return d

    @pyqtSlot(object)
    def update_prediction(self, pred: Prediction):
        """Called on every new candle with latest prediction."""
        if not pred.ready:
            self.waiting_lbl.setVisible(True)
            self.waiting_lbl.setText(pred.message)
            self.direction_lbl.setText("--")
            self.direction_lbl.setObjectName("direction_neutral")
            self.prob_lbl.setText("")
            self.conf_lbl.setText("")
            self.agree_lbl.setText("")
            self.prob_bar.set_prediction("NEUTRAL", 0.5)
            for lbl in self._fc_labels:
                lbl.setText("--")
                lbl.setObjectName("fc_neut")
            self._xgb_lbl.setText("--")
            self._lstm_lbl.setText("--")
            self._smc_lbl.setText("--")
            self._ind_lbl.setText("--")
            self._refresh_styles()
            return

        self.waiting_lbl.setVisible(False)

        # Direction + probability
        dir_map = {"UP": "direction_up", "DOWN": "direction_down", "NEUTRAL": "direction_neutral"}
        self.direction_lbl.setText(pred.direction)
        self.direction_lbl.setObjectName(dir_map.get(pred.direction, "direction_neutral"))
        self.prob_lbl.setText(f"{pred.probability * 100:.1f}%")
        self.prob_bar.set_prediction(pred.direction, pred.probability)

        # Confidence
        conf_map = {"High": "conf_high", "Medium": "conf_medium", "Low": "conf_low"}
        self.conf_lbl.setText(f"Confidence: {pred.confidence}")
        self.conf_lbl.setObjectName(conf_map.get(pred.confidence, "conf_low"))

        # Model agreement
        if pred.model_agreement:
            self.agree_lbl.setText("✓ Models agree")
            self.agree_lbl.setObjectName("agree")
        else:
            self.agree_lbl.setText("⚠ Models diverge")
            self.agree_lbl.setObjectName("disagree")

        # XGB / LSTM
        self._xgb_lbl.setText(
            f"{'▲' if pred.xgb_prob > 0.5 else '▼'} {pred.xgb_prob * 100:.1f}%"
        )
        self._lstm_lbl.setText(
            f"{'▲' if pred.lstm_prob > 0.5 else '▼'} {pred.lstm_prob * 100:.1f}%"
            if pred.lstm_prob != 0.5 else "Not trained"
        )

        # Biases
        bias_obj = {"BULLISH": "bias_bull", "BEARISH": "bias_bear", "NEUTRAL": "bias_neut"}
        self._smc_lbl.setText(pred.smc_bias)
        self._smc_lbl.setObjectName(bias_obj.get(pred.smc_bias, "bias_neut"))
        self._ind_lbl.setText(pred.ind_bias)
        self._ind_lbl.setObjectName(bias_obj.get(pred.ind_bias, "bias_neut"))

        # Forecast
        for i, fc in enumerate(pred.candle_forecast[:3]):
            sign   = "+" if fc["change_pct"] >= 0 else ""
            text   = (f"C+{fc['candle']}  {fc['direction']}  "
                      f"${fc['target']:,.2f}  ({sign}{fc['change_pct']:.2f}%)")
            obj = {"UP": "fc_up", "DOWN": "fc_down"}.get(fc["direction"], "fc_neut")
            self._fc_labels[i].setText(text)
            self._fc_labels[i].setObjectName(obj)

        self._refresh_styles()

    def _refresh_styles(self):
        """Force Qt to re-apply object name style changes."""
        for w in self.findChildren(QLabel):
            w.style().unpolish(w)
            w.style().polish(w)
