# gui/indicator_summary.py
"""
Persistent floating indicator + SMC summary panel.
Appears on hover of any indicator or SMC button in the strategy panel.
Stays fully visible until cursor leaves the button.

Shows a compact but complete summary:
  - Indicator name + current value + signal badge
  - Full description
  - Buy/sell conditions
  - For SMC: nearest detected zone details with price + distance
  - Pro tip

Uses the same tooltip_data content as FloatingTooltip but with
a richer two-column layout and NO auto-hide timer.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QScrollArea, QSizePolicy
)
from PyQt6.QtCore import Qt, QPoint, QTimer, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QLinearGradient, QBrush


SUMMARY_STYLE = """
QWidget#sum_root {
    background: transparent;
}
QFrame#sum_card {
    background-color: #080e1c;
    border: 1px solid #1a3060;
    border-radius: 12px;
}
QLabel#sum_name {
    color: #00c896;
    font-size: 13px;
    font-weight: bold;
    font-family: 'Segoe UI', sans-serif;
}
QLabel#sum_value {
    color: #ffffff;
    font-size: 13px;
    font-weight: bold;
    font-family: 'Consolas', monospace;
}
QLabel#sum_section {
    color: #4a9eff;
    font-size: 9px;
    font-weight: bold;
    letter-spacing: 2px;
    margin-top: 6px;
}
QLabel#sum_body {
    color: #b0b8cc;
    font-size: 11px;
    font-family: 'Segoe UI', sans-serif;
    line-height: 1.5;
}
QLabel#sum_buy {
    color: #00c896;
    font-size: 11px;
    font-family: 'Segoe UI', sans-serif;
    padding: 3px 6px;
    background: #0d2a22;
    border-radius: 4px;
}
QLabel#sum_sell {
    color: #ff5252;
    font-size: 11px;
    font-family: 'Segoe UI', sans-serif;
    padding: 3px 6px;
    background: #2a0d0d;
    border-radius: 4px;
}
QLabel#sum_tip {
    color: #ffb74d;
    font-size: 10px;
    font-style: italic;
    font-family: 'Segoe UI', sans-serif;
}
QLabel#sum_zone_bull {
    color: #00c896;
    font-size: 10px;
    font-weight: bold;
    background: #0d2a22;
    border: 1px solid #00c896;
    border-radius: 3px;
    padding: 2px 5px;
}
QLabel#sum_zone_bear {
    color: #ff5252;
    font-size: 10px;
    font-weight: bold;
    background: #2a0d0d;
    border: 1px solid #ff5252;
    border-radius: 3px;
    padding: 2px 5px;
}
QLabel#sum_zone_liq {
    color: #ffdd00;
    font-size: 10px;
    font-weight: bold;
    background: #2a2200;
    border: 1px solid #ffdd00;
    border-radius: 3px;
    padding: 2px 5px;
}
QLabel#sig_buy {
    color: #000;
    background: #00c896;
    font-size: 10px;
    font-weight: bold;
    border-radius: 3px;
    padding: 2px 8px;
}
QLabel#sig_sell {
    color: #fff;
    background: #ff5252;
    font-size: 10px;
    font-weight: bold;
    border-radius: 3px;
    padding: 2px 8px;
}
QLabel#sig_neutral {
    color: #fff;
    background: #333;
    font-size: 10px;
    font-weight: bold;
    border-radius: 3px;
    padding: 2px 8px;
}
QFrame#hdivider {
    background: #1a3060;
    max-height: 1px;
    margin: 4px 0;
}
"""


class FloatingSummary(QWidget):
    """
    Persistent floating summary panel.
    Shown on hover, hidden when cursor leaves the triggering button.
    No auto-hide timer — stays until dismiss() is called.
    """

    def __init__(self, parent=None):
        super().__init__(
            parent,
            Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet(SUMMARY_STYLE)
        self.setMaximumWidth(400)
        self.setMinimumWidth(340)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self.card = QFrame()
        self.card.setObjectName("sum_card")
        self._card_layout = QVBoxLayout(self.card)
        self._card_layout.setContentsMargins(14, 12, 14, 12)
        self._card_layout.setSpacing(3)
        root.addWidget(self.card)

    def _clear(self):
        while self._card_layout.count():
            item = self._card_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _divider(self) -> QFrame:
        d = QFrame(); d.setObjectName("hdivider")
        d.setFrameShape(QFrame.Shape.HLine)
        return d

    def _section(self, text: str) -> QLabel:
        l = QLabel(text.upper()); l.setObjectName("sum_section")
        return l

    def _body(self, text: str) -> QLabel:
        l = QLabel(text); l.setObjectName("sum_body")
        l.setWordWrap(True)
        return l

    def _signal_badge(self, signal: str) -> QLabel:
        obj = {"BUY": "sig_buy", "SELL": "sig_sell"}.get(signal, "sig_neutral")
        l = QLabel(f" {signal} "); l.setObjectName(obj)
        return l

    # ── Public API ────────────────────────────────────────────────────────────

    def show_indicator(
        self,
        key:           str,
        cursor_pos:    QPoint,
        current_value: float = None,
        signal:        str   = None,
        extra_values:  dict  = None,
    ):
        from gui.tooltip_data import INDICATOR_TOOLTIPS
        data = INDICATOR_TOOLTIPS.get(key)
        if not data:
            return
        self._clear()
        self._populate_indicator(data, key, current_value, signal, extra_values)
        self._show_near(cursor_pos)

    def show_smc(
        self,
        key:           str,
        cursor_pos:    QPoint,
        nearest_zones: dict  = None,
        current_price: float = None,
    ):
        from gui.tooltip_data import SMC_TOOLTIPS
        data = SMC_TOOLTIPS.get(key)
        if not data:
            return
        self._clear()
        self._populate_smc(data, nearest_zones, current_price)
        self._show_near(cursor_pos)

    def dismiss(self):
        """Hide immediately — called when cursor leaves the button."""
        self.hide()

    # ── Content builders ──────────────────────────────────────────────────────

    def _populate_indicator(self, data, key, value, signal, extra):
        cl = self._card_layout

        # Header row: name + signal badge
        hrow = QHBoxLayout()
        name_lbl = QLabel(data["name"])
        name_lbl.setObjectName("sum_name")
        name_lbl.setWordWrap(True)
        hrow.addWidget(name_lbl, 1)
        if signal:
            hrow.addWidget(self._signal_badge(signal))
        hw = QWidget(); hw.setLayout(hrow)
        cl.addWidget(hw)

        # Current value
        if value is not None and value != 0.0:
            val_row = QHBoxLayout()
            vl = QLabel("Now:"); vl.setObjectName("sum_section")
            vv = QLabel(self._fmt(key, value, extra)); vv.setObjectName("sum_value")
            val_row.addWidget(vl); val_row.addWidget(vv); val_row.addStretch()
            vw = QWidget(); vw.setLayout(val_row)
            cl.addWidget(vw)

        cl.addWidget(self._divider())

        # Description
        cl.addWidget(self._section("What it measures"))
        cl.addWidget(self._body(data["description"]))

        # How to read
        cl.addWidget(self._section("How to read"))
        cl.addWidget(self._body(data["how_to_read"]))

        cl.addWidget(self._divider())

        # Buy / sell two-column
        sig_row = QHBoxLayout()
        sig_row.setSpacing(8)

        buy_col = QVBoxLayout()
        buy_hdr = QLabel("✅ BUY"); buy_hdr.setObjectName("sum_section")
        buy_txt = QLabel(data["buy_signal"]); buy_txt.setObjectName("sum_buy")
        buy_txt.setWordWrap(True)
        buy_col.addWidget(buy_hdr); buy_col.addWidget(buy_txt)

        sell_col = QVBoxLayout()
        sell_hdr = QLabel("🔴 SELL"); sell_hdr.setObjectName("sum_section")
        sell_txt = QLabel(data["sell_signal"]); sell_txt.setObjectName("sum_sell")
        sell_txt.setWordWrap(True)
        sell_col.addWidget(sell_hdr); sell_col.addWidget(sell_txt)

        bw = QWidget(); bw.setLayout(buy_col)
        sw = QWidget(); sw.setLayout(sell_col)
        sig_row.addWidget(bw, 1); sig_row.addWidget(sw, 1)
        srw = QWidget(); srw.setLayout(sig_row)
        cl.addWidget(srw)

        # Tip
        cl.addWidget(self._divider())
        tip_row = QHBoxLayout()
        tip_row.addWidget(QLabel("💡"))
        tip_lbl = QLabel(data["tip"]); tip_lbl.setObjectName("sum_tip")
        tip_lbl.setWordWrap(True)
        tip_row.addWidget(tip_lbl, 1)
        tw = QWidget(); tw.setLayout(tip_row)
        cl.addWidget(tw)

    def _populate_smc(self, data, zones, price):
        cl = self._card_layout

        name_lbl = QLabel(data["name"]); name_lbl.setObjectName("sum_name")
        cl.addWidget(name_lbl)
        cl.addWidget(self._divider())

        # Nearest zones (if any)
        if zones and price:
            cl.addWidget(self._section("Nearest Detected Zones"))
            self._add_zones(zones, price)
            cl.addWidget(self._divider())

        cl.addWidget(self._section("What it is"))
        cl.addWidget(self._body(data["description"]))
        cl.addWidget(self._section("How to read"))
        cl.addWidget(self._body(data["how_to_read"]))
        cl.addWidget(self._divider())

        sig_row = QHBoxLayout(); sig_row.setSpacing(8)

        buy_col = QVBoxLayout()
        buy_hdr = QLabel("✅ LONG SETUP"); buy_hdr.setObjectName("sum_section")
        buy_txt = QLabel(data["buy_signal"]); buy_txt.setObjectName("sum_buy")
        buy_txt.setWordWrap(True)
        buy_col.addWidget(buy_hdr); buy_col.addWidget(buy_txt)

        sell_col = QVBoxLayout()
        sell_hdr = QLabel("🔴 SHORT SETUP"); sell_hdr.setObjectName("sum_section")
        sell_txt = QLabel(data["sell_signal"]); sell_txt.setObjectName("sum_sell")
        sell_txt.setWordWrap(True)
        sell_col.addWidget(sell_hdr); sell_col.addWidget(sell_txt)

        bw = QWidget(); bw.setLayout(buy_col)
        sw = QWidget(); sw.setLayout(sell_col)
        sig_row.addWidget(bw, 1); sig_row.addWidget(sw, 1)
        srw = QWidget(); srw.setLayout(sig_row)
        cl.addWidget(srw)

        cl.addWidget(self._divider())
        tip_row = QHBoxLayout()
        tip_row.addWidget(QLabel("💡"))
        tip_lbl = QLabel(data["tip"]); tip_lbl.setObjectName("sum_tip")
        tip_lbl.setWordWrap(True)
        tip_row.addWidget(tip_lbl, 1)
        tw = QWidget(); tw.setLayout(tip_row)
        cl.addWidget(tw)

    def _add_zones(self, zones: dict, price: float):
        cl = self._card_layout

        ob = zones.get("ob")
        if ob:
            mid  = (ob["top"] + ob["bottom"]) / 2
            dist = abs(price - mid) / price * 100
            obj  = "sum_zone_bull" if ob["type"] == "BULLISH_OB" else "sum_zone_bear"
            icon = "🟢" if ob["type"] == "BULLISH_OB" else "🔴"
            lbl  = QLabel(
                f"{icon} {'Bull' if obj=='sum_zone_bull' else 'Bear'} OB  "
                f"${ob['bottom']:,.2f}–${ob['top']:,.2f}  "
                f"({dist:.2f}% away)  {'★'*ob['strength']}"
            )
            lbl.setObjectName(obj); lbl.setWordWrap(True)
            cl.addWidget(lbl)

        fvg = zones.get("fvg")
        if fvg:
            dist = abs(price - fvg["mid"]) / price * 100
            lbl  = QLabel(
                f"🔵 {'Bull' if fvg['type']=='BULLISH_FVG' else 'Bear'} FVG  "
                f"${fvg['bottom']:,.2f}–${fvg['top']:,.2f}  "
                f"({dist:.2f}% away)  Filled: {fvg['fill_pct']:.0f}%"
            )
            lbl.setObjectName("sum_zone_liq"); lbl.setWordWrap(True)
            cl.addWidget(lbl)

        liq = zones.get("liq")
        if liq and "price" in liq:
            dist  = abs(price - liq["price"]) / price * 100
            swept = "✓ Swept" if liq.get("swept") else "Unswept"
            ltype = liq["type"].replace("_", " ").title()
            lbl   = QLabel(
                f"⚡ {ltype}  ${liq['price']:,.2f}  ({dist:.2f}% away)  {swept}"
            )
            lbl.setObjectName("sum_zone_liq"); lbl.setWordWrap(True)
            cl.addWidget(lbl)

        struct = zones.get("structure")
        if struct:
            icon = "🟢" if struct.get("direction") == "BULLISH" else "🔴"
            obj  = "sum_zone_bull" if struct.get("direction") == "BULLISH" else "sum_zone_bear"
            lbl  = QLabel(
                f"{icon} Recent {struct.get('type','?')} "
                f"({struct.get('direction','?')})  "
                f"${struct.get('price',0):,.2f}"
            )
            lbl.setObjectName(obj); lbl.setWordWrap(True)
            cl.addWidget(lbl)

    # ── Positioning ───────────────────────────────────────────────────────────

    def _show_near(self, cursor_pos: QPoint):
        self.adjustSize()

        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().geometry()

        x = cursor_pos.x() + 18
        y = cursor_pos.y()

        if x + self.width() > screen.right() - 10:
            x = cursor_pos.x() - self.width() - 10
        if y + self.height() > screen.bottom() - 10:
            y = screen.bottom() - self.height() - 10
        x = max(screen.left() + 5, x)
        y = max(screen.top() + 5, y)

        self.move(x, y)
        self.show()
        self.raise_()

    def _fmt(self, key: str, value: float, extra: dict = None) -> str:
        if key in ("RSI", "CCI"):
            return f"{value:.1f}"
        elif key == "STOCHRSI":
            k = extra.get("K", value) if extra else value
            d = extra.get("D", 0)     if extra else 0
            return f"K: {k:.1f}  D: {d:.1f}"
        elif key == "MACD":
            m = extra.get("MACD",   value) if extra else value
            s = extra.get("signal", 0)     if extra else 0
            h = extra.get("hist",   0)     if extra else 0
            return f"M:{m:.4f}  S:{s:.4f}  H:{h:.4f}"
        elif key in ("EMA_9","EMA_21","EMA_50","EMA_200","VWAP"):
            return f"${value:,.2f}"
        else:
            return f"{value:.4f}"

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(0, 200, 150, 20), 2)
        painter.setPen(pen)
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 12, 12)
