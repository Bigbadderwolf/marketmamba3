# gui/indicator_settings.py
"""
TradingView-style indicator settings dialog.
Opens when user clicks ⚙ on any indicator in the strategy panel.

Tabs:
  1. Inputs    — period, overbought/oversold levels etc.
  2. Style     — colour, thickness, line style, fill, visibility, labels
  3. Visibility — show/hide on specific timeframes (future)

All settings saved per user per symbol via indicators/style_store.py
"""

import json
import copy
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QSpinBox, QDoubleSpinBox, QPushButton, QCheckBox,
    QComboBox, QColorDialog, QFrame, QScrollArea, QFormLayout,
    QDialogButtonBox, QSizePolicy, QSlider, QGroupBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QFont, QPixmap, QIcon

from indicators.style_store import DEFAULT_STYLES, load_style, save_style


DIALOG_STYLE = """
QDialog {
    background-color: #1a1a2e;
    color: #d1d4dc;
    font-family: 'Segoe UI', sans-serif;
    font-size: 12px;
}
QTabWidget::pane {
    border: 1px solid #2a2a4a;
    background: #16213e;
    border-radius: 4px;
}
QTabBar::tab {
    background: #0f3460;
    color: #888;
    padding: 8px 18px;
    border: none;
    font-size: 12px;
}
QTabBar::tab:selected {
    background: #16213e;
    color: #00c896;
    border-bottom: 2px solid #00c896;
}
QTabBar::tab:hover { color: #d1d4dc; }
QLabel {
    color: #9a9ab0;
    font-size: 12px;
}
QLabel#section_title {
    color: #d1d4dc;
    font-size: 13px;
    font-weight: bold;
    padding: 6px 0 2px 0;
}
QLabel#comp_label {
    color: #c0c0d0;
    font-size: 12px;
    min-width: 100px;
}
QSpinBox, QDoubleSpinBox, QComboBox {
    background: #0f3460;
    color: #d1d4dc;
    border: 1px solid #2a2a5a;
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 24px;
}
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid #00c896;
}
QComboBox::drop-down { border: none; }
QComboBox QAbstractItemView {
    background: #0f3460;
    color: #d1d4dc;
    selection-background-color: #00c896;
    selection-color: #000;
}
QCheckBox {
    color: #d1d4dc;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 16px; height: 16px;
    border: 1px solid #444;
    border-radius: 3px;
    background: #0f3460;
}
QCheckBox::indicator:checked {
    background: #00c896;
    border: 1px solid #00c896;
}
QPushButton#color_btn {
    border: 2px solid #2a2a5a;
    border-radius: 4px;
    min-width: 32px;
    min-height: 24px;
    max-width: 48px;
}
QPushButton#color_btn:hover { border: 2px solid #00c896; }
QPushButton#ok_btn {
    background: #00c896;
    color: #000;
    border: none;
    border-radius: 5px;
    padding: 8px 24px;
    font-weight: bold;
    font-size: 13px;
}
QPushButton#ok_btn:hover { background: #00e5ad; }
QPushButton#cancel_btn {
    background: #1e1e3a;
    color: #888;
    border: 1px solid #2a2a5a;
    border-radius: 5px;
    padding: 8px 20px;
}
QPushButton#cancel_btn:hover { color: #d1d4dc; }
QPushButton#reset_btn {
    background: transparent;
    color: #555;
    border: none;
    font-size: 11px;
    text-decoration: underline;
}
QPushButton#reset_btn:hover { color: #888; }
QFrame#row_frame {
    background: #0f1a2e;
    border: 1px solid #1e2a4e;
    border-radius: 6px;
}
QFrame#divider {
    background: #2a2a4a;
    max-height: 1px;
}
QGroupBox {
    color: #9a9ab0;
    border: 1px solid #2a2a4a;
    border-radius: 6px;
    margin-top: 8px;
    padding-top: 8px;
    font-size: 11px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    color: #00c896;
}
"""

# Line style options
LINE_STYLES = ["solid", "dashed", "dotted", "dash-dot"]
THICKNESS_OPTIONS = [1, 2, 3, 4, 5]

# Human-readable component names
COMPONENT_LABELS = {
    "line":        "Line",
    "k_line":      "K Line",
    "d_line":      "D Line",
    "macd_line":   "MACD Line",
    "signal_line": "Signal Line",
    "histogram":   "Histogram",
    "zero_line":   "Zero Line",
    "upper":       "Upper Band",
    "middle":      "Middle Band",
    "lower":       "Lower Band",
    "fill":        "Band Fill",
    "ob_line":     "Overbought Level",
    "os_line":     "Oversold Level",
    "ob_fill":     "Overbought Fill",
    "os_fill":     "Oversold Fill",
    "tenkan":      "Tenkan (Conversion)",
    "kijun":       "Kijun (Base)",
    "chikou":      "Chikou (Lagging)",
    "cloud_bull":  "Cloud (Bullish Fill)",
    "cloud_bear":  "Cloud (Bearish Fill)",
}

# Indicators whose components are fills only (no thickness/style)
FILL_ONLY_COMPONENTS = {"fill", "ob_fill", "os_fill", "cloud_bull", "cloud_bear"}

# Param definitions: (label, field_key, type, default, min, max, step)
PARAM_DEFS = {
    "EMA_9":    [("Period", "period", "int", 9, 1, 500, 1)],
    "EMA_21":   [("Period", "period", "int", 21, 1, 500, 1)],
    "EMA_50":   [("Period", "period", "int", 50, 1, 500, 1)],
    "EMA_200":  [("Period", "period", "int", 200, 1, 500, 1)],
    "RSI": [
        ("Period",      "period",      "int", 14, 2, 100, 1),
        ("Overbought",  "overbought",  "int", 70, 50, 95, 1),
        ("Oversold",    "oversold",    "int", 30, 5,  50, 1),
    ],
    "STOCHRSI": [
        ("Period",    "period",   "int", 14, 2, 50, 1),
        ("Smooth K",  "smooth_k", "int",  3, 1, 10, 1),
        ("Smooth D",  "smooth_d", "int",  3, 1, 10, 1),
    ],
    "MACD": [
        ("Fast",   "fast",   "int", 12, 2, 50,  1),
        ("Slow",   "slow",   "int", 26, 5, 200, 1),
        ("Signal", "signal", "int",  9, 2, 50,  1),
    ],
    "BB": [
        ("Period",  "period", "int",   20, 5,  200, 1),
        ("Std Dev", "std",    "float", 2.0, 0.5, 5.0, 0.5),
    ],
    "ATR": [("Period", "period", "int", 14, 2, 100, 1)],
    "ICHIMOKU": [
        ("Tenkan Period", "tenkan",  "int", 9,  2, 100, 1),
        ("Kijun Period",  "kijun",   "int", 26, 5, 200, 1),
        ("Span B Period", "span_b",  "int", 52, 10,300, 1),
    ],
}


class ColorButton(QPushButton):
    """A button that displays a colour and opens a colour picker on click."""
    color_changed = pyqtSignal(str)  # emits hex string

    def __init__(self, color: str = "#ffffff", alpha_support: bool = False):
        super().__init__()
        self.setObjectName("color_btn")
        self._color       = color
        self._alpha_support = alpha_support
        self._update_swatch()
        self.clicked.connect(self._pick_color)

    def _update_swatch(self):
        # Parse hex — handle 8-char (with alpha) and 6-char
        hex_clean = self._color.lstrip("#")
        if len(hex_clean) == 8:
            r = int(hex_clean[0:2], 16)
            g = int(hex_clean[2:4], 16)
            b = int(hex_clean[4:6], 16)
            a = int(hex_clean[6:8], 16)
        elif len(hex_clean) == 6:
            r = int(hex_clean[0:2], 16)
            g = int(hex_clean[2:4], 16)
            b = int(hex_clean[4:6], 16)
            a = 255
        else:
            r, g, b, a = 128, 128, 128, 255

        pix = QPixmap(32, 20)
        p   = QPainter(pix)
        # Checkerboard for alpha
        p.fillRect(0, 0, 32, 20, QColor(80, 80, 80))
        p.fillRect(0, 0, 16, 10, QColor(120, 120, 120))
        p.fillRect(16, 10, 16, 10, QColor(120, 120, 120))
        p.fillRect(0, 0, 32, 20, QColor(r, g, b, a))
        p.end()
        self.setIcon(QIcon(pix))
        self.setIconSize(pix.size())
        self.setToolTip(self._color)

    def _pick_color(self):
        hex_clean = self._color.lstrip("#")
        if len(hex_clean) == 8:
            r, g, b, a = (int(hex_clean[i:i+2], 16) for i in (0,2,4,6))
        else:
            r, g, b = (int(hex_clean[i:i+2], 16) for i in (0,2,4))
            a = 255

        initial = QColor(r, g, b, a)
        options = QColorDialog.ColorDialogOption.ShowAlphaChannel if self._alpha_support else QColorDialog.ColorDialogOption(0)
        color   = QColorDialog.getColor(initial, self, "Choose Colour", options)

        if color.isValid():
            if self._alpha_support:
                self._color = "#{:02x}{:02x}{:02x}{:02x}".format(
                    color.red(), color.green(), color.blue(), color.alpha()
                )
            else:
                self._color = color.name()
            self._update_swatch()
            self.color_changed.emit(self._color)

    def get_color(self) -> str:
        return self._color

    def set_color(self, color: str):
        self._color = color
        self._update_swatch()


class IndicatorSettingsDialog(QDialog):
    """
    Full TradingView-style indicator settings dialog.
    Two tabs: Inputs (parameters) and Style (visual properties).
    """
    settings_applied = pyqtSignal(str, dict)  # key, full style dict

    def __init__(self, key: str, user_id: int = 1,
                 symbol: str = "btcusdt", parent=None):
        super().__init__(parent)
        self.key      = key
        self.user_id  = user_id
        self.symbol   = symbol

        # Load current saved style (or defaults)
        self.style = load_style(user_id, symbol, key)
        if not self.style:
            self.style = copy.deepcopy(DEFAULT_STYLES.get(key, {}))

        self._working = copy.deepcopy(self.style)
        self._param_widgets:    dict = {}
        self._component_widgets: dict = {}

        self._setup_window()
        self._build_ui()

    def _setup_window(self):
        name = DEFAULT_STYLES.get(self.key, {})
        self.setWindowTitle(f"Indicator Settings — {self.key.replace('_', ' ')}")
        self.setMinimumWidth(500)
        self.setMinimumHeight(480)
        self.setStyleSheet(DIALOG_STYLE)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header
        header = QLabel(f"⚙  {self.key.replace('_', ' ')} Settings")
        header.setObjectName("section_title")
        header.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        layout.addWidget(header)

        # Tabs
        tabs = QTabWidget()
        tabs.addTab(self._build_inputs_tab(),  "Inputs")
        tabs.addTab(self._build_style_tab(),   "Style")
        layout.addWidget(tabs, 1)

        # Buttons
        btn_row = QHBoxLayout()

        reset_btn = QPushButton("Reset to defaults")
        reset_btn.setObjectName("reset_btn")
        reset_btn.clicked.connect(self._reset_defaults)

        ok_btn     = QPushButton("Apply")
        ok_btn.setObjectName("ok_btn")
        ok_btn.clicked.connect(self._apply)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("cancel_btn")
        cancel_btn.clicked.connect(self.reject)

        btn_row.addWidget(reset_btn)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

    # ── Inputs tab ────────────────────────────────────────────────────────────

    def _build_inputs_tab(self) -> QWidget:
        page   = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        param_defs = PARAM_DEFS.get(self.key, [])
        current_params = self._working.get("params", {})

        if not param_defs:
            lbl = QLabel("This indicator has no configurable inputs.")
            lbl.setStyleSheet("color: #555;")
            layout.addWidget(lbl)
            layout.addStretch()
            return page

        group = QGroupBox("Parameters")
        form  = QFormLayout(group)
        form.setVerticalSpacing(10)
        form.setHorizontalSpacing(16)

        for label_text, field_key, ftype, default, mn, mx, step in param_defs:
            current_val = current_params.get(field_key, default)

            if ftype == "int":
                widget = QSpinBox()
                widget.setRange(mn, mx)
                widget.setValue(int(current_val))
                widget.setSingleStep(step)
            else:
                widget = QDoubleSpinBox()
                widget.setRange(mn, mx)
                widget.setValue(float(current_val))
                widget.setSingleStep(step)
                widget.setDecimals(1)

            self._param_widgets[field_key] = widget
            form.addRow(QLabel(label_text), widget)

        layout.addWidget(group)
        layout.addStretch()
        return page

    # ── Style tab ─────────────────────────────────────────────────────────────

    def _build_style_tab(self) -> QWidget:
        page   = QWidget()
        outer  = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        inner  = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        components = self._working.get("components", {})

        if not components:
            lbl = QLabel("No style options available.")
            lbl.setStyleSheet("color: #555;")
            layout.addWidget(lbl)
            layout.addStretch()
            scroll.setWidget(inner)
            outer.addWidget(scroll)
            return page

        for comp_key, comp_val in components.items():
            frame = self._build_component_row(comp_key, comp_val)
            layout.addWidget(frame)

        layout.addStretch()
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        return page

    def _build_component_row(self, comp_key: str, comp_val: dict) -> QFrame:
        """Build one component style row (e.g. 'MACD Line')."""
        frame  = QFrame()
        frame.setObjectName("row_frame")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        is_fill = comp_key in FILL_ONLY_COMPONENTS
        label   = COMPONENT_LABELS.get(comp_key, comp_key.replace("_", " ").title())

        # Row header — label + visibility toggle
        header_row = QHBoxLayout()
        comp_lbl   = QLabel(label)
        comp_lbl.setObjectName("comp_label")
        comp_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))

        vis_check = QCheckBox("Visible")
        vis_check.setChecked(comp_val.get("visible", True))

        label_check = QCheckBox("Show Label") if "label" in comp_val else None

        header_row.addWidget(comp_lbl)
        header_row.addStretch()
        if label_check:
            label_check.setChecked(comp_val.get("label", True))
            header_row.addWidget(label_check)
        header_row.addWidget(vis_check)
        layout.addLayout(header_row)

        # Style controls row
        controls_row = QHBoxLayout()
        controls_row.setSpacing(12)

        widgets = {"visible": vis_check}
        if label_check:
            widgets["label"] = label_check

        # Histogram has dual colour (bull/bear)
        if comp_key == "histogram":
            bull_lbl  = QLabel("Bull:")
            bull_lbl.setStyleSheet("color: #666; font-size: 11px;")
            bull_btn  = ColorButton(comp_val.get("color_bull", "#00c896"), alpha_support=False)
            bear_lbl  = QLabel("Bear:")
            bear_lbl.setStyleSheet("color: #666; font-size: 11px;")
            bear_btn  = ColorButton(comp_val.get("color_bear", "#ff5252"), alpha_support=False)
            controls_row.addWidget(bull_lbl)
            controls_row.addWidget(bull_btn)
            controls_row.addWidget(bear_lbl)
            controls_row.addWidget(bear_btn)
            controls_row.addStretch()
            widgets["color_bull"] = bull_btn
            widgets["color_bear"] = bear_btn

        elif is_fill:
            # Fill-only: just colour with alpha
            col_lbl = QLabel("Fill Colour:")
            col_lbl.setStyleSheet("color: #666; font-size: 11px;")
            col_btn = ColorButton(comp_val.get("color", "#00c89620"), alpha_support=True)
            controls_row.addWidget(col_lbl)
            controls_row.addWidget(col_btn)
            controls_row.addStretch()
            widgets["color"] = col_btn

        else:
            # Regular line: colour + thickness + style
            col_lbl = QLabel("Colour:")
            col_lbl.setStyleSheet("color: #666; font-size: 11px;")
            col_btn = ColorButton(comp_val.get("color", "#ffffff"), alpha_support=False)

            thick_lbl = QLabel("Width:")
            thick_lbl.setStyleSheet("color: #666; font-size: 11px;")
            thick_box = QComboBox()
            thick_box.setFixedWidth(55)
            for t in THICKNESS_OPTIONS:
                thick_box.addItem(f"{t}px", t)
            cur_thick = comp_val.get("thickness", 1)
            idx = THICKNESS_OPTIONS.index(cur_thick) if cur_thick in THICKNESS_OPTIONS else 0
            thick_box.setCurrentIndex(idx)

            style_lbl = QLabel("Style:")
            style_lbl.setStyleSheet("color: #666; font-size: 11px;")
            style_box = QComboBox()
            style_box.setFixedWidth(90)
            for s in LINE_STYLES:
                style_box.addItem(s.capitalize(), s)
            cur_style = comp_val.get("style", "solid")
            if cur_style in LINE_STYLES:
                style_box.setCurrentIndex(LINE_STYLES.index(cur_style))

            controls_row.addWidget(col_lbl)
            controls_row.addWidget(col_btn)
            controls_row.addWidget(thick_lbl)
            controls_row.addWidget(thick_box)
            controls_row.addWidget(style_lbl)
            controls_row.addWidget(style_box)
            controls_row.addStretch()

            widgets["color"]     = col_btn
            widgets["thickness"] = thick_box
            widgets["style"]     = style_box

        layout.addLayout(controls_row)
        self._component_widgets[comp_key] = widgets
        return frame

    # ── Actions ───────────────────────────────────────────────────────────────

    def _collect(self) -> dict:
        """Collect all widget values into a style dict."""
        result = copy.deepcopy(self._working)

        # Params
        for field_key, widget in self._param_widgets.items():
            result.setdefault("params", {})[field_key] = widget.value()

        # Components
        for comp_key, widgets in self._component_widgets.items():
            comp = result.setdefault("components", {}).setdefault(comp_key, {})

            for prop, widget in widgets.items():
                if isinstance(widget, QCheckBox):
                    comp[prop] = widget.isChecked()
                elif isinstance(widget, ColorButton):
                    comp[prop] = widget.get_color()
                elif isinstance(widget, QComboBox):
                    comp[prop] = widget.currentData()

        return result

    def _apply(self):
        """Collect, save, emit and close."""
        result = self._collect()
        save_style(self.user_id, self.symbol, self.key, result)
        self.settings_applied.emit(self.key, result)
        self.accept()

    def _reset_defaults(self):
        """Reset to factory defaults and rebuild UI."""
        self._working = copy.deepcopy(DEFAULT_STYLES.get(self.key, {}))
        # Rebuild param widgets
        for field_key, widget in self._param_widgets.items():
            for label_text, fk, ftype, default, mn, mx, step in PARAM_DEFS.get(self.key, []):
                if fk == field_key:
                    widget.setValue(default)

        # Rebuild component widgets
        defaults = DEFAULT_STYLES.get(self.key, {}).get("components", {})
        for comp_key, widgets in self._component_widgets.items():
            def_comp = defaults.get(comp_key, {})
            for prop, widget in widgets.items():
                if prop not in def_comp:
                    continue
                val = def_comp[prop]
                if isinstance(widget, QCheckBox):
                    widget.setChecked(bool(val))
                elif isinstance(widget, ColorButton):
                    widget.set_color(str(val))
                elif isinstance(widget, QComboBox):
                    if prop == "thickness":
                        idx = THICKNESS_OPTIONS.index(val) if val in THICKNESS_OPTIONS else 0
                        widget.setCurrentIndex(idx)
                    elif prop == "style":
                        idx = LINE_STYLES.index(val) if val in LINE_STYLES else 0
                        widget.setCurrentIndex(idx)
