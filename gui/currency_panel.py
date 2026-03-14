# gui/currency_panel.py  — Phase 6 redesign
"""
Top bar: MARKETS button (opens floating symbol picker)
         current pair label  |  INTERVALS button (opens timeframe picker)
         current interval label
"""
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel,
    QFrame, QLineEdit, QScrollArea, QGridLayout,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont

from data.symbol_registry import ALL_SYMBOLS, SYMBOL_CATEGORIES, get_display_name

BG     = "#080c14"
BORDER = "#1a2a3a"
ACCENT = "#4a9eff"
GREEN  = "#00c896"

TIMEFRAMES = [
    ("1m","1m"),("3m","3m"),("5m","5m"),("15m","15m"),
    ("30m","30m"),("1h","1h"),("2h","2h"),("4h","4h"),
    ("6h","6h"),("12h","12h"),("1D","1d"),("3D","3d"),("1W","1w"),
]

PANEL_STYLE = f"""
QWidget {{ background:{BG}; color:#d1d4dc; font-size:11px; }}
QLabel  {{ background:transparent; border:none; }}
QLineEdit {{
    background:#0f1e30; color:#d1d4dc;
    border:1px solid {BORDER}; border-radius:3px; padding:4px 8px;
}}
QScrollArea {{ border:none; background:transparent; }}
QScrollBar:vertical {{ background:{BG}; width:5px; border-radius:2px; }}
QScrollBar::handle:vertical {{ background:#1a2a3a; border-radius:2px; min-height:14px; }}
"""

CAT_COLORS = {
    "🔥 Top Crypto":  "#ff9800",
    "📈 DeFi":        "#4a9eff",
    "🏗️ Layer 2":     "#e040fb",
    "🆕 New Listed":  "#00e5ff",
    "🐸 Meme":        "#69f0ae",
    "₿ BTC Pairs":    "#f7931a",
    "Ξ ETH Pairs":    "#627eea",
    "💛 Commodities": "#ffd700",
}


class _FloatingPanel(QFrame):
    """Base class for Markets / Intervals dropdown panels."""
    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setStyleSheet(PANEL_STYLE + f"""
            QFrame {{
                background:{BG}; border:1px solid {BORDER};
                border-radius:6px;
            }}
        """)
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def show_below(self, btn: QPushButton):
        pos = btn.mapToGlobal(btn.rect().bottomLeft())
        self.move(pos)
        self.show()
        self.raise_()


class MarketsPanel(_FloatingPanel):
    symbol_chosen = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(480, 420)
        vl = QVBoxLayout(self); vl.setContentsMargins(10,10,10,10); vl.setSpacing(6)

        self._search = QLineEdit()
        self._search.setPlaceholderText("🔍  Search  (BTC, ETH, SOL…)")
        self._search.textChanged.connect(self._on_search)
        vl.addWidget(self._search)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        self._grid_w = QWidget(); self._grid_w.setStyleSheet("background:transparent;")
        self._grid_vl = QVBoxLayout(self._grid_w)
        self._grid_vl.setContentsMargins(0,0,0,0); self._grid_vl.setSpacing(6)
        scroll.setWidget(self._grid_w)
        vl.addWidget(scroll, 1)
        self._populate(ALL_SYMBOLS)

    def _populate(self, symbols):
        while self._grid_vl.count():
            item = self._grid_vl.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        shown = set(symbols)
        grouped = {}; already = set()
        for cat, syms in SYMBOL_CATEGORIES.items():
            cs = [s for s in syms if s in shown]
            if cs: grouped[cat] = cs; already.update(cs)
        leftover = [s for s in symbols if s not in already]
        if leftover: grouped["Other"] = leftover

        for cat, syms in grouped.items():
            hdr = QLabel(cat)
            col = CAT_COLORS.get(cat, "#668")
            hdr.setStyleSheet(f"color:{col};font-size:9px;font-weight:bold;"
                              f"letter-spacing:1.5px;padding:2px 0;")
            self._grid_vl.addWidget(hdr)

            gw = QWidget(); gw.setStyleSheet("background:transparent;")
            g  = QGridLayout(gw); g.setSpacing(3); g.setContentsMargins(0,0,0,0)
            for i, sym in enumerate(syms):
                btn = QPushButton(get_display_name(sym))
                btn.setFixedHeight(24)
                btn.setStyleSheet(f"""
                    QPushButton {{ background:#0f1820; color:#9a9ab0;
                        border:1px solid #1a2a3a; border-radius:3px;
                        font-size:10px; padding:2px 6px; }}
                    QPushButton:hover {{ background:#162840; color:#fff;
                        border-color:{ACCENT}; }}
                """)
                btn.clicked.connect(lambda _, s=sym: self._pick(s))
                g.addWidget(btn, i // 4, i % 4)
            self._grid_vl.addWidget(gw)

        self._grid_vl.addStretch()

    def _on_search(self, text):
        q = text.strip().upper()
        self._populate([s for s in ALL_SYMBOLS if q in s] if q else ALL_SYMBOLS)

    def _pick(self, sym):
        self.symbol_chosen.emit(sym.lower())
        self.hide()


class IntervalsPanel(_FloatingPanel):
    interval_chosen = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(260, 130)
        vl = QVBoxLayout(self); vl.setContentsMargins(10,10,10,10); vl.setSpacing(4)

        hdr = QLabel("TIMEFRAME")
        hdr.setStyleSheet(f"color:{ACCENT};font-size:9px;font-weight:bold;letter-spacing:2px;")
        vl.addWidget(hdr)

        gw = QWidget(); gw.setStyleSheet("background:transparent;")
        g  = QGridLayout(gw); g.setSpacing(4); g.setContentsMargins(0,0,0,0)
        for i, (label, val) in enumerate(TIMEFRAMES):
            btn = QPushButton(label)
            btn.setFixedHeight(24)
            btn.setStyleSheet(f"""
                QPushButton {{ background:#0f1820; color:#9a9ab0;
                    border:1px solid #1a2a3a; border-radius:3px; font-size:10px; }}
                QPushButton:hover {{ background:#162840; color:#fff;
                    border-color:{GREEN}; }}
            """)
            btn.clicked.connect(lambda _, v=val: self._pick(v))
            g.addWidget(btn, i // 7, i % 7)
        vl.addWidget(gw)
        vl.addStretch()

    def _pick(self, val):
        self.interval_chosen.emit(val)
        self.hide()


class CurrencyPanel(QWidget):
    def __init__(self, chart_view):
        super().__init__()
        self.chart_view = chart_view
        self._current_sym = "BTCUSDT"
        self._current_tf  = "1h"

        self.setFixedHeight(42)
        self.setStyleSheet(
            f"background:{BG}; border-bottom:1px solid {BORDER};"
        )

        hl = QHBoxLayout(self)
        hl.setContentsMargins(12, 0, 12, 0); hl.setSpacing(8)

        # MARKETS button
        self._mkts_btn = QPushButton("📊  MARKETS  ▾")
        self._mkts_btn.setStyleSheet(f"""
            QPushButton {{ background:#0f1e30; color:{ACCENT};
                border:1px solid {ACCENT}; border-radius:4px;
                padding:5px 12px; font-size:11px; font-weight:bold; }}
            QPushButton:hover {{ background:#162840; }}
        """)
        self._mkts_btn.clicked.connect(self._open_markets)
        hl.addWidget(self._mkts_btn)

        # Active pair label
        self._sym_lbl = QLabel("BTC/USDT")
        self._sym_lbl.setStyleSheet(
            f"color:{GREEN};font-size:13px;font-weight:bold;"
        )
        hl.addWidget(self._sym_lbl)

        # Divider
        d = QFrame(); d.setFrameShape(QFrame.Shape.VLine)
        d.setStyleSheet(f"color:{BORDER};")
        hl.addWidget(d)

        # INTERVALS button
        self._int_btn = QPushButton("⏱  INTERVALS  ▾")
        self._int_btn.setStyleSheet(f"""
            QPushButton {{ background:#0f1e30; color:{ACCENT};
                border:1px solid {ACCENT}; border-radius:4px;
                padding:5px 12px; font-size:11px; font-weight:bold; }}
            QPushButton:hover {{ background:#162840; }}
        """)
        self._int_btn.clicked.connect(self._open_intervals)
        hl.addWidget(self._int_btn)

        # Active interval label
        self._tf_lbl = QLabel("1h")
        self._tf_lbl.setStyleSheet("color:#9a9ab0;font-size:12px;")
        hl.addWidget(self._tf_lbl)

        hl.addStretch()

        # Floating panels (created once, shown on demand)
        self._mkts_panel  = MarketsPanel(self)
        self._mkts_panel.symbol_chosen.connect(self.change_symbol)
        self._ints_panel  = IntervalsPanel(self)
        self._ints_panel.interval_chosen.connect(self.change_interval)

    def _open_markets(self):
        self._mkts_panel.show_below(self._mkts_btn)

    def _open_intervals(self):
        self._ints_panel.show_below(self._int_btn)

    def change_symbol(self, symbol: str):
        self._current_sym = symbol.upper()
        self._sym_lbl.setText(get_display_name(symbol.upper()))
        self.chart_view.change_symbol(symbol)

    def change_interval(self, interval: str):
        self._current_tf = interval
        self._tf_lbl.setText(interval)
        if hasattr(self.chart_view, "change_interval"):
            self.chart_view.change_interval(interval)
