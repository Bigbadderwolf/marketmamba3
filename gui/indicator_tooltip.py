# gui/indicator_tooltip.py
"""
Floating tooltip popup for indicators and SMC concepts.
Appears next to the cursor on hover.
Shows: full description, current value, buy/sell signal interpretation,
and nearest SMC zone details where applicable.
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from PyQt6.QtCore import Qt, QPoint, QTimer, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QLinearGradient


TOOLTIP_STYLE = """
QWidget#tooltip_root {
    background-color: transparent;
}
QFrame#tooltip_card {
    background-color: #0e1621;
    border: 1px solid #1e3a5f;
    border-radius: 10px;
}
QLabel#tt_title {
    color: #00c896;
    font-size: 13px;
    font-weight: bold;
    font-family: 'Segoe UI', sans-serif;
}
QLabel#tt_section {
    color: #4a9eff;
    font-size: 10px;
    font-weight: bold;
    font-family: 'Segoe UI', sans-serif;
    margin-top: 6px;
}
QLabel#tt_body {
    color: #c0c8d8;
    font-size: 11px;
    font-family: 'Segoe UI', sans-serif;
    line-height: 1.4;
}
QLabel#tt_value {
    color: #ffffff;
    font-size: 12px;
    font-weight: bold;
    font-family: 'Consolas', monospace;
}
QLabel#tt_buy {
    color: #00c896;
    font-size: 11px;
    font-family: 'Segoe UI', sans-serif;
}
QLabel#tt_sell {
    color: #ff5252;
    font-size: 11px;
    font-family: 'Segoe UI', sans-serif;
}
QLabel#tt_tip {
    color: #ffb74d;
    font-size: 10px;
    font-style: italic;
    font-family: 'Segoe UI', sans-serif;
}
QLabel#tt_zone_bull {
    color: #00c896;
    font-size: 11px;
    font-weight: bold;
    background-color: #0d2a22;
    border: 1px solid #00c896;
    border-radius: 4px;
    padding: 3px 6px;
}
QLabel#tt_zone_bear {
    color: #ff5252;
    font-size: 11px;
    font-weight: bold;
    background-color: #2a0d0d;
    border: 1px solid #ff5252;
    border-radius: 4px;
    padding: 3px 6px;
}
QLabel#tt_zone_neutral {
    color: #ffdd00;
    font-size: 11px;
    font-weight: bold;
    background-color: #2a2200;
    border: 1px solid #ffdd00;
    border-radius: 4px;
    padding: 3px 6px;
}
QFrame#tt_divider {
    background-color: #1e3a5f;
    max-height: 1px;
    margin: 4px 0;
}
"""


class FloatingTooltip(QWidget):
    """
    A floating, styled tooltip that follows the cursor.
    Parent should be the main window or screen root so it can
    appear over all other widgets.
    """

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet(TOOLTIP_STYLE)
        self.setMaximumWidth(380)
        self.setMinimumWidth(320)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

        self._build_ui()

    def _build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        self.card = QFrame()
        self.card.setObjectName("tooltip_card")
        self.card_layout = QVBoxLayout(self.card)
        self.card_layout.setContentsMargins(14, 12, 14, 12)
        self.card_layout.setSpacing(2)

        root_layout.addWidget(self.card)

    def _clear(self):
        """Remove all widgets from card layout."""
        while self.card_layout.count():
            item = self.card_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _divider(self):
        d = QFrame()
        d.setObjectName("tt_divider")
        d.setFrameShape(QFrame.Shape.HLine)
        return d

    def _section(self, text: str) -> QLabel:
        lbl = QLabel(text.upper())
        lbl.setObjectName("tt_section")
        return lbl

    def _body(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("tt_body")
        lbl.setWordWrap(True)
        return lbl

    def show_indicator(
        self,
        key:          str,
        cursor_pos:   QPoint,
        current_value: float = None,
        signal:       str = None,       # "BUY", "SELL", "NEUTRAL"
        extra_values: dict = None,      # e.g. {"K": 23.4, "D": 18.2}
    ):
        """Show tooltip for an indicator."""
        from gui.tooltip_data import INDICATOR_TOOLTIPS
        data = INDICATOR_TOOLTIPS.get(key)
        if not data:
            return

        self._clear()

        # Title
        title = QLabel(data["name"])
        title.setObjectName("tt_title")
        title.setWordWrap(True)
        self.card_layout.addWidget(title)
        self.card_layout.addWidget(self._divider())

        # Current value
        if current_value is not None and current_value != 0.0:
            val_row = QHBoxLayout()
            val_lbl = QLabel("Current Value:")
            val_lbl.setObjectName("tt_section")
            val_num = QLabel(self._fmt_value(key, current_value, extra_values))
            val_num.setObjectName("tt_value")

            # Signal badge
            if signal:
                sig_lbl = self._signal_badge(signal)
                val_row.addWidget(val_lbl)
                val_row.addWidget(val_num)
                val_row.addStretch()
                val_row.addWidget(sig_lbl)
            else:
                val_row.addWidget(val_lbl)
                val_row.addWidget(val_num)
                val_row.addStretch()

            container = QWidget()
            container.setLayout(val_row)
            self.card_layout.addWidget(container)
            self.card_layout.addWidget(self._divider())

        # Description
        self.card_layout.addWidget(self._section("What it measures"))
        self.card_layout.addWidget(self._body(data["description"]))

        # How to read
        self.card_layout.addWidget(self._section("How to read"))
        self.card_layout.addWidget(self._body(data["how_to_read"]))

        # Buy signal
        self.card_layout.addWidget(self._section("✅ Buy Signal"))
        buy_lbl = QLabel(data["buy_signal"])
        buy_lbl.setObjectName("tt_buy")
        buy_lbl.setWordWrap(True)
        self.card_layout.addWidget(buy_lbl)

        # Sell signal
        self.card_layout.addWidget(self._section("🔴 Sell Signal"))
        sell_lbl = QLabel(data["sell_signal"])
        sell_lbl.setObjectName("tt_sell")
        sell_lbl.setWordWrap(True)
        self.card_layout.addWidget(sell_lbl)

        # Pro tip
        self.card_layout.addWidget(self._divider())
        tip_row = QHBoxLayout()
        tip_icon = QLabel("💡")
        tip_text = QLabel(data["tip"])
        tip_text.setObjectName("tt_tip")
        tip_text.setWordWrap(True)
        tip_row.addWidget(tip_icon)
        tip_row.addWidget(tip_text, 1)
        tip_container = QWidget()
        tip_container.setLayout(tip_row)
        self.card_layout.addWidget(tip_container)

        self._position_and_show(cursor_pos)

    def show_smc(
        self,
        key:           str,
        cursor_pos:    QPoint,
        nearest_zones: dict = None,    # {"ob": {...}, "fvg": {...}, "liq": {...}}
        current_price: float = None,
    ):
        """Show tooltip for an SMC concept."""
        from gui.tooltip_data import SMC_TOOLTIPS
        data = SMC_TOOLTIPS.get(key)
        if not data:
            return

        self._clear()

        # Title
        title = QLabel(data["name"])
        title.setObjectName("tt_title")
        title.setWordWrap(True)
        self.card_layout.addWidget(title)
        self.card_layout.addWidget(self._divider())

        # Nearest zones (SMC-specific)
        if nearest_zones and current_price:
            self._add_zone_details(nearest_zones, current_price)
            self.card_layout.addWidget(self._divider())

        # Description
        self.card_layout.addWidget(self._section("What it is"))
        self.card_layout.addWidget(self._body(data["description"]))

        # How to read
        self.card_layout.addWidget(self._section("How to read"))
        self.card_layout.addWidget(self._body(data["how_to_read"]))

        # Buy signal
        self.card_layout.addWidget(self._section("✅ Long Setup"))
        buy_lbl = QLabel(data["buy_signal"])
        buy_lbl.setObjectName("tt_buy")
        buy_lbl.setWordWrap(True)
        self.card_layout.addWidget(buy_lbl)

        # Sell signal
        self.card_layout.addWidget(self._section("🔴 Short Setup"))
        sell_lbl = QLabel(data["sell_signal"])
        sell_lbl.setObjectName("tt_sell")
        sell_lbl.setWordWrap(True)
        self.card_layout.addWidget(sell_lbl)

        # Pro tip
        self.card_layout.addWidget(self._divider())
        tip_row = QHBoxLayout()
        tip_icon = QLabel("💡")
        tip_text = QLabel(data["tip"])
        tip_text.setObjectName("tt_tip")
        tip_text.setWordWrap(True)
        tip_row.addWidget(tip_icon)
        tip_row.addWidget(tip_text, 1)
        tip_container = QWidget()
        tip_container.setLayout(tip_row)
        self.card_layout.addWidget(tip_container)

        self._position_and_show(cursor_pos)

    def _add_zone_details(self, zones: dict, current_price: float):
        """Add nearest detected zone details to tooltip."""
        self.card_layout.addWidget(self._section("Nearest Detected Zones"))

        added = False

        # Order block
        ob = zones.get("ob")
        if ob:
            mid   = (ob["top"] + ob["bottom"]) / 2
            dist  = abs(current_price - mid) / current_price * 100
            ob_type = "Bull OB" if ob["type"] == "BULLISH_OB" else "Bear OB"
            obj_name = "tt_zone_bull" if ob["type"] == "BULLISH_OB" else "tt_zone_bear"
            lbl = QLabel(
                f"{'🟢' if ob['type'] == 'BULLISH_OB' else '🔴'} {ob_type}: "
                f"${ob['bottom']:,.2f} – ${ob['top']:,.2f}  "
                f"({dist:.2f}% away)  Strength: {'★' * ob['strength']}"
            )
            lbl.setObjectName(obj_name)
            lbl.setWordWrap(True)
            self.card_layout.addWidget(lbl)
            added = True

        # FVG
        fvg = zones.get("fvg")
        if fvg:
            dist = abs(current_price - fvg["mid"]) / current_price * 100
            fvg_type = "Bull FVG" if fvg["type"] == "BULLISH_FVG" else "Bear FVG"
            lbl = QLabel(
                f"{'🔵' } {fvg_type}: "
                f"${fvg['bottom']:,.2f} – ${fvg['top']:,.2f}  "
                f"({dist:.2f}% away)  Filled: {fvg['fill_pct']:.0f}%"
            )
            lbl.setObjectName("tt_zone_neutral")
            lbl.setWordWrap(True)
            self.card_layout.addWidget(lbl)
            added = True

        # Liquidity
        liq = zones.get("liq")
        if liq and "price" in liq:
            dist  = abs(current_price - liq["price"]) / current_price * 100
            swept = "✓ Swept" if liq.get("swept") else "Unswept"
            ltype = liq["type"].replace("_", " ").title()
            lbl   = QLabel(
                f"⚡ {ltype}: ${liq['price']:,.2f}  "
                f"({dist:.2f}% away)  {swept}"
            )
            lbl.setObjectName("tt_zone_neutral")
            lbl.setWordWrap(True)
            self.card_layout.addWidget(lbl)
            added = True

        # Recent structure event
        struct = zones.get("structure")
        if struct:
            direction = struct.get("direction", "")
            etype     = struct.get("type", "")
            price     = struct.get("price", 0)
            icon      = "🟢" if direction == "BULLISH" else "🔴"
            obj_name  = "tt_zone_bull" if direction == "BULLISH" else "tt_zone_bear"
            lbl = QLabel(
                f"{icon} Recent {etype} ({direction}): ${price:,.2f}"
            )
            lbl.setObjectName(obj_name)
            lbl.setWordWrap(True)
            self.card_layout.addWidget(lbl)
            added = True

        if not added:
            lbl = QLabel("No zones detected in current view.")
            lbl.setObjectName("tt_body")
            self.card_layout.addWidget(lbl)

    def _signal_badge(self, signal: str) -> QLabel:
        lbl = QLabel(f" {signal} ")
        if signal == "BUY":
            lbl.setStyleSheet(
                "color: #000; background: #00c896; border-radius: 4px; "
                "font-weight: bold; font-size: 10px; padding: 2px 6px;"
            )
        elif signal == "SELL":
            lbl.setStyleSheet(
                "color: #fff; background: #ff5252; border-radius: 4px; "
                "font-weight: bold; font-size: 10px; padding: 2px 6px;"
            )
        else:
            lbl.setStyleSheet(
                "color: #fff; background: #444; border-radius: 4px; "
                "font-weight: bold; font-size: 10px; padding: 2px 6px;"
            )
        return lbl

    def _fmt_value(self, key: str, value: float, extra: dict = None) -> str:
        """Format indicator value for display."""
        if key == "RSI" or key == "CCI":
            return f"{value:.1f}"
        elif key in ("STOCHRSI",):
            k = extra.get("K", value) if extra else value
            d = extra.get("D", 0)     if extra else 0
            return f"K: {k:.1f}  D: {d:.1f}"
        elif key == "MACD":
            macd   = extra.get("MACD",   value) if extra else value
            signal = extra.get("signal", 0)      if extra else 0
            hist   = extra.get("hist",   0)      if extra else 0
            return f"MACD: {macd:.4f}  Sig: {signal:.4f}  H: {hist:.4f}"
        elif key == "ATR":
            return f"{value:.4f}  (${value:,.2f})"
        elif key in ("EMA_9", "EMA_21", "EMA_50", "EMA_200", "VWAP"):
            return f"${value:,.2f}"
        else:
            return f"{value:.4f}"

    def _position_and_show(self, cursor_pos: QPoint):
        """Position tooltip near cursor, adjusting to stay on screen."""
        self.adjustSize()

        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().geometry()

        x = cursor_pos.x() + 16
        y = cursor_pos.y() + 16

        # Prevent going off right edge
        if x + self.width() > screen.right() - 10:
            x = cursor_pos.x() - self.width() - 10

        # Prevent going off bottom edge
        if y + self.height() > screen.bottom() - 10:
            y = cursor_pos.y() - self.height() - 10

        # Prevent going off left/top
        x = max(screen.left() + 5, x)
        y = max(screen.top() + 5, y)

        self.move(x, y)
        self.show()
        self.raise_()

        # Stop any pending hide — stays visible until cursor leaves button
        self._hide_timer.stop()

    def keep_alive(self):
        """Called while cursor is still hovering — keep tooltip visible."""
        self._hide_timer.stop()

    def dismiss(self):
        """Called when cursor leaves a button — hide immediately."""
        self._hide_timer.stop()
        self.hide()

    def paintEvent(self, event):
        """Custom paint for subtle drop shadow effect."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Draw subtle glow border
        pen = QPen(QColor(0, 200, 150, 30), 2)
        painter.setPen(pen)
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 10, 10)
