# gui/strategy_panel.py  — Phase 6 redesign
"""
Left panel — replaces old strategy panel entirely.

Layout (top to bottom):
  ┌─────────────────────────────────┐
  │  [▼ INDICATORS]  [▼ SMC]        │  ← two dropdown-toggle buttons
  │  ┄ expanded content if open ┄   │
  ├─────────────────────────────────┤
  │  DRAW TOOLS  (icon toolbar)     │
  ├─────────────────────────────────┤
  │  CONFLUENCE  (bull/bear score)  │
  ├─────────────────────────────────┤
  │  TRADE  (entry/SL/TP/leverage)  │
  ├─────────────────────────────────┤
  │  HISTORY  (collapsible trades)  │
  └─────────────────────────────────┘
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFrame, QScrollArea, QDoubleSpinBox, QSpinBox, QComboBox,
    QStackedWidget, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor, QCursor

from gui.indicator_tooltip import FloatingTooltip
from gui.indicator_summary import FloatingSummary

# ── palette ──────────────────────────────────────────────────────────────────
BG     = "#0c0c0c"
BG2    = "#101820"
BORDER = "#1a2a2a"
GREEN  = "#00c896"
RED    = "#ff5252"
ACCENT = "#4a9eff"
AMBER  = "#ff9800"

BASE = f"""
QWidget   {{ background:{BG}; color:#d1d4dc; font-size:11px; }}
QLabel    {{ background:transparent; border:none; }}
QScrollArea {{ border:none; background:transparent; }}
QScrollBar:vertical {{ background:{BG}; width:4px; border-radius:2px; }}
QScrollBar::handle:vertical {{ background:#1a2a3a; border-radius:2px; min-height:16px; }}
QSpinBox, QDoubleSpinBox, QComboBox {{
    background:#141414; color:#d1d4dc;
    border:1px solid #2a2a2a; border-radius:3px; padding:3px 6px; }}
QComboBox QAbstractItemView {{ background:#141414; color:#d1d4dc; }}
"""

def _div(h=1, col=BORDER):
    d = QFrame(); d.setFixedHeight(h)
    d.setStyleSheet(f"background:{col};border:none;")
    return d

def _sec_lbl(text):
    l = QLabel(text)
    l.setStyleSheet(f"color:{ACCENT};font-size:9px;font-weight:bold;"
                    f"letter-spacing:2px;padding:3px 0 2px 0;")
    return l

# ─────────────────────────────────────────────────────────────────────────────
# Dropdown section widget (used for both INDICATORS and SMC)
# ─────────────────────────────────────────────────────────────────────────────
class _DropSection(QWidget):
    """A big toggle button that reveals a content widget below when clicked."""

    def __init__(self, label: str, color: str, content: QWidget):
        super().__init__()
        self.setStyleSheet("background:transparent;")
        vl = QVBoxLayout(self)
        vl.setContentsMargins(0,0,0,0); vl.setSpacing(0)

        self._btn = QPushButton(f"▸  {label}")
        self._btn.setCheckable(True)
        self._btn.setStyleSheet(f"""
            QPushButton {{
                background:#101418; color:#9a9ab0;
                border:1px solid #1a2a2a; border-radius:5px;
                padding:7px 10px; font-size:11px; font-weight:bold;
                text-align:left; letter-spacing:1px;
            }}
            QPushButton:checked {{
                background:{BG2}; color:{color};
                border:1px solid {color}; border-bottom-left-radius:0;
                border-bottom-right-radius:0;
            }}
            QPushButton:hover:!checked {{ color:#ccc; background:#141414; }}
        """)
        self._btn.toggled.connect(self._toggle)
        vl.addWidget(self._btn)

        self._body = content
        self._body.setVisible(False)
        self._body.setStyleSheet(
            f"background:{BG2}; border:1px solid {color};"
            f"border-top:none; border-bottom-left-radius:5px;"
            f"border-bottom-right-radius:5px;"
        )
        vl.addWidget(self._body)

    def _toggle(self, checked: bool):
        self._btn.setText(
            f"{'▾' if checked else '▸'}  {self._btn.text()[2:].strip()}"
        )
        self._body.setVisible(checked)


# ─────────────────────────────────────────────────────────────────────────────
# Main panel
# ─────────────────────────────────────────────────────────────────────────────
class StrategyPanel(QWidget):
    indicator_toggled = pyqtSignal(str, bool)
    smc_toggled       = pyqtSignal(str, bool)
    params_changed    = pyqtSignal(str, dict)
    # Drawing tool selected: tool name or None to cancel
    draw_tool_selected = pyqtSignal(str)

    INDICATORS = [
        ("EMA 9",     "EMA_9",    "#ff9800"),
        ("EMA 21",    "EMA_21",   "#2196f3"),
        ("EMA 50",    "EMA_50",   "#9c27b0"),
        ("EMA 200",   "EMA_200",  "#f44336"),
        ("VWAP",      "VWAP",     "#00bcd4"),
        ("RSI",       "RSI",      "#ffeb3b"),
        ("Stoch RSI", "STOCHRSI", "#ff9800"),
        ("MACD",      "MACD",     "#4caf50"),
        ("BB",        "BB",       "#607d8b"),
        ("ATR",       "ATR",      "#795548"),
        ("Ichimoku",  "ICHIMOKU", "#e91e63"),
        ("OBV",       "OBV",      "#009688"),
        ("CVD",       "CVD",      "#3f51b5"),
    ]

    SMC = [
        ("Order Blocks",   "OB",    "#4a9eff"),
        ("Fair Val. Gaps", "FVG",   "#00bcd4"),
        ("BOS / CHoCH",    "BOS",   "#00ff88"),
        ("Liquidity",      "LIQ",   "#ffdd00"),
        ("Swings",         "SWING", "#888888"),
    ]

    DRAW_TOOLS = [
        ("—",  "hline",   "Horizontal Line"),
        ("|",  "vline",   "Vertical Line"),
        ("╱",  "trend",   "Trend Line (click 2 pts)"),
        ("↗",  "arrow",   "Arrow"),
        ("𝑇",  "text",    "Text Label"),
        ("≋",  "fib",     "Fibonacci Levels"),
    ]

    def __init__(self, chart_view):
        super().__init__()
        self.chart_view = chart_view
        self.setStyleSheet(BASE)
        self.setFixedWidth(175)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        self._indicator_buttons: dict = {}
        self._smc_buttons:       dict = {}
        self._active_indicators: set  = set()
        self._active_smc:        set  = set()
        self._tooltip  = FloatingTooltip()
        self._summary  = FloatingSummary()
        self._active_draw_tool: str | None = None
        self._draw_btns: dict = {}

        # Trade state
        self._trade_history: list = []

        self._build_ui()

        # Refresh confluence every 2s
        self._conf_timer = QTimer()
        self._conf_timer.timeout.connect(self._refresh_scores)
        self._conf_timer.start(2000)

    # ── Root ──────────────────────────────────────────────────────────────────
    def _build_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        inner = QWidget()
        inner.setStyleSheet(f"background:{BG};")
        vl = QVBoxLayout(inner)
        vl.setContentsMargins(8, 8, 8, 8); vl.setSpacing(6)

        # 1. INDICATORS dropdown
        vl.addWidget(_DropSection("INDICATORS", GREEN,
                                  self._build_indicator_content()))

        # 2. SMC dropdown
        vl.addWidget(_DropSection("SMC", ACCENT,
                                  self._build_smc_content()))

        vl.addWidget(_div())

        # 3. Drawing tools
        vl.addWidget(_sec_lbl("DRAW TOOLS"))
        vl.addWidget(self._build_draw_tools())

        vl.addWidget(_div())

        # 4. Confluence
        vl.addWidget(_sec_lbl("CONFLUENCE"))
        vl.addWidget(self._build_confluence())

        vl.addWidget(_div())

        # 5. Trade panel
        vl.addWidget(_sec_lbl("TRADE"))
        vl.addWidget(self._build_trade_panel())

        vl.addWidget(_div())

        # 6. History
        vl.addWidget(self._build_history_section())

        vl.addStretch()
        scroll.setWidget(inner)

        root = QVBoxLayout(self)
        root.setContentsMargins(0,0,0,0); root.setSpacing(0)
        root.addWidget(scroll)

    # ── Indicator content ─────────────────────────────────────────────────────
    def _build_indicator_content(self) -> QWidget:
        w = QWidget()
        vl = QVBoxLayout(w); vl.setContentsMargins(6,6,6,6); vl.setSpacing(3)
        for label, key, color in self.INDICATORS:
            vl.addWidget(self._make_ind_row(label, key, color))
        return w

    def _make_ind_row(self, label, key, color) -> QWidget:
        row = QWidget(); row.setStyleSheet("background:transparent;")
        hl  = QHBoxLayout(row); hl.setContentsMargins(0,0,0,0); hl.setSpacing(2)

        btn = QPushButton(label)
        btn.setCheckable(True)
        btn.setStyleSheet(f"""
            QPushButton {{
                background:#141414; color:#777;
                border:1px solid #222; border-radius:3px;
                padding:4px 6px; font-size:10px; text-align:left;
            }}
            QPushButton:checked {{
                background:#0d1e18; color:{color};
                border:1px solid {color}; border-left:3px solid {color};
            }}
            QPushButton:hover {{ background:#1a1a1a; color:#ccc; }}
        """)
        btn.toggled.connect(lambda c, k=key: self._on_ind_toggle(k, c))
        btn.setMouseTracking(True)
        btn.enterEvent = lambda e, k=key: self._on_ind_hover(k, e)
        btn.leaveEvent = lambda e: self._on_leave()
        self._indicator_buttons[key] = btn

        cfg = QPushButton("⚙")
        cfg.setFixedWidth(18); cfg.setFixedHeight(22)
        cfg.setStyleSheet("QPushButton{background:transparent;color:#333;border:none;font-size:10px;}"
                          "QPushButton:hover{color:#888;}")
        cfg.setToolTip(f"{label} settings")
        cfg.clicked.connect(lambda _, k=key, l=label: self._open_params(k, l))

        hl.addWidget(btn, 1); hl.addWidget(cfg)
        return row

    # ── SMC content ───────────────────────────────────────────────────────────
    def _build_smc_content(self) -> QWidget:
        w = QWidget()
        vl = QVBoxLayout(w); vl.setContentsMargins(6,6,6,6); vl.setSpacing(3)
        for label, key, color in self.SMC:
            vl.addWidget(self._make_smc_row(label, key, color))
        return w

    def _make_smc_row(self, label, key, color) -> QWidget:
        row = QWidget(); row.setStyleSheet("background:transparent;")
        hl  = QHBoxLayout(row); hl.setContentsMargins(0,0,0,0); hl.setSpacing(2)

        btn = QPushButton(label)
        btn.setCheckable(True)
        btn.setStyleSheet(f"""
            QPushButton {{
                background:#141414; color:#777;
                border:1px solid #222; border-radius:3px;
                padding:4px 6px; font-size:10px; text-align:left;
            }}
            QPushButton:checked {{
                background:#0a1a20; color:{color};
                border:1px solid {color}; border-left:3px solid {color};
            }}
            QPushButton:hover {{ background:#1a1a1a; color:#ccc; }}
        """)
        btn.toggled.connect(lambda c, k=key: self._on_smc_toggle(k, c))
        btn.setMouseTracking(True)
        btn.enterEvent = lambda e, k=key: self._on_smc_hover(k, e)
        btn.leaveEvent = lambda e: self._on_leave()
        self._smc_buttons[key] = btn

        hl.addWidget(btn, 1)
        return row

    # ── Drawing tools ─────────────────────────────────────────────────────────
    def _build_draw_tools(self) -> QWidget:
        w = QWidget(); w.setStyleSheet("background:transparent;")
        gl = QHBoxLayout(w); gl.setContentsMargins(0,0,0,0); gl.setSpacing(4)
        gl.setAlignment(Qt.AlignmentFlag.AlignLeft)

        for sym, tool_id, tip in self.DRAW_TOOLS:
            btn = QPushButton(sym)
            btn.setCheckable(True)
            btn.setFixedSize(26, 26)
            btn.setToolTip(tip)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background:#141414; color:#666;
                    border:1px solid #222; border-radius:4px;
                    font-size:13px; font-weight:bold;
                }}
                QPushButton:checked {{
                    background:#0d1e30; color:{ACCENT};
                    border:1px solid {ACCENT};
                }}
                QPushButton:hover {{ background:#1e1e1e; color:#aaa; }}
            """)
            btn.clicked.connect(lambda checked, t=tool_id: self._on_draw_tool(t, checked))
            self._draw_btns[tool_id] = btn
            gl.addWidget(btn)

        # Clear drawings button
        clr = QPushButton("✕")
        clr.setFixedSize(26, 26)
        clr.setToolTip("Clear all drawings")
        clr.setStyleSheet("""
            QPushButton { background:#1a0a0a; color:#554; border:1px solid #2a1a1a;
                          border-radius:4px; font-size:12px; }
            QPushButton:hover { background:#2a1010; color:#ff5252; border-color:#ff5252; }
        """)
        clr.clicked.connect(self._clear_drawings)
        gl.addWidget(clr)
        gl.addStretch()
        return w

    def _on_draw_tool(self, tool_id: str, checked: bool):
        # Uncheck all others
        for tid, btn in self._draw_btns.items():
            if tid != tool_id:
                btn.blockSignals(True)
                btn.setChecked(False)
                btn.blockSignals(False)
        self._active_draw_tool = tool_id if checked else None
        if hasattr(self.chart_view, "set_draw_tool"):
            self.chart_view.set_draw_tool(self._active_draw_tool)
        self.draw_tool_selected.emit(tool_id if checked else "")

    def _clear_drawings(self):
        for btn in self._draw_btns.values():
            btn.blockSignals(True); btn.setChecked(False); btn.blockSignals(False)
        self._active_draw_tool = None
        if hasattr(self.chart_view, "clear_drawings"):
            self.chart_view.clear_drawings()

    # ── Confluence ────────────────────────────────────────────────────────────
    def _build_confluence(self) -> QWidget:
        w = QWidget(); w.setStyleSheet("background:transparent;")
        hl = QHBoxLayout(w); hl.setContentsMargins(4,2,4,2); hl.setSpacing(8)

        bull_col = QVBoxLayout()
        self.bull_score_lbl = QLabel("--")
        self.bull_score_lbl.setStyleSheet(
            f"color:{GREEN};font-size:14px;font-weight:bold;")
        self.bull_score_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bull_lbl = QLabel("BULL")
        bull_lbl.setStyleSheet("color:#445;font-size:9px;")
        bull_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bull_col.addWidget(self.bull_score_lbl); bull_col.addWidget(bull_lbl)

        bear_col = QVBoxLayout()
        self.bear_score_lbl = QLabel("--")
        self.bear_score_lbl.setStyleSheet(
            f"color:{RED};font-size:14px;font-weight:bold;")
        self.bear_score_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bear_lbl = QLabel("BEAR")
        bear_lbl.setStyleSheet("color:#445;font-size:9px;")
        bear_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bear_col.addWidget(self.bear_score_lbl); bear_col.addWidget(bear_lbl)

        hl.addStretch(); hl.addLayout(bull_col)
        hl.addLayout(bear_col); hl.addStretch()
        return w

    # ── Trade panel ───────────────────────────────────────────────────────────
    def _build_trade_panel(self) -> QWidget:
        w = QWidget(); w.setStyleSheet("background:transparent;")
        vl = QVBoxLayout(w); vl.setContentsMargins(0,2,0,2); vl.setSpacing(5)

        # Entry price
        ep_row = QHBoxLayout()
        ep_row.addWidget(QLabel("Entry"))
        self._entry_price = QDoubleSpinBox()
        self._entry_price.setRange(0, 10_000_000)
        self._entry_price.setDecimals(2); self._entry_price.setSingleStep(1)
        self._entry_price.setFixedHeight(24)
        ep_row.addWidget(self._entry_price, 1)
        vl.addLayout(ep_row)

        # SL / TP
        sl_row = QHBoxLayout()
        sl_row.addWidget(QLabel("SL"))
        self._sl = QDoubleSpinBox()
        self._sl.setRange(0, 10_000_000); self._sl.setDecimals(2)
        self._sl.setFixedHeight(24)
        sl_row.addWidget(self._sl, 1)
        vl.addLayout(sl_row)

        tp_row = QHBoxLayout()
        tp_row.addWidget(QLabel("TP"))
        self._tp = QDoubleSpinBox()
        self._tp.setRange(0, 10_000_000); self._tp.setDecimals(2)
        self._tp.setFixedHeight(24)
        tp_row.addWidget(self._tp, 1)
        vl.addLayout(tp_row)

        # Leverage
        lev_row = QHBoxLayout()
        lev_row.addWidget(QLabel("Lev"))
        self._lev = QComboBox()
        for lv in ["1×","2×","3×","5×","10×","20×","25×","50×","75×","100×","125×"]:
            self._lev.addItem(lv)
        self._lev.setFixedHeight(24)
        lev_row.addWidget(self._lev, 1)
        vl.addLayout(lev_row)

        # Buy / Sell buttons
        bs_row = QHBoxLayout(); bs_row.setSpacing(4)
        buy_btn = QPushButton("BUY / LONG")
        buy_btn.setStyleSheet(f"""
            QPushButton {{ background:{GREEN}; color:#000; border:none;
                border-radius:4px; padding:7px 4px; font-weight:bold; font-size:11px; }}
            QPushButton:hover {{ background:#00e5ad; }}
        """)
        buy_btn.clicked.connect(lambda: self._place_order("BUY"))

        sell_btn = QPushButton("SELL / SHORT")
        sell_btn.setStyleSheet(f"""
            QPushButton {{ background:{RED}; color:#fff; border:none;
                border-radius:4px; padding:7px 4px; font-weight:bold; font-size:11px; }}
            QPushButton:hover {{ background:#ff7070; }}
        """)
        sell_btn.clicked.connect(lambda: self._place_order("SELL"))

        bs_row.addWidget(buy_btn, 1); bs_row.addWidget(sell_btn, 1)
        vl.addLayout(bs_row)

        # Open / Close price labels
        oc_row = QHBoxLayout(); oc_row.setSpacing(4)
        self._open_lbl  = QLabel("Open: —")
        self._open_lbl.setStyleSheet("color:#445;font-size:9px;")
        self._close_lbl = QLabel("Close: —")
        self._close_lbl.setStyleSheet("color:#445;font-size:9px;")
        oc_row.addWidget(self._open_lbl); oc_row.addWidget(self._close_lbl)
        vl.addLayout(oc_row)

        # Auto-fill entry price from chart
        self._autofill_timer = QTimer()
        self._autofill_timer.timeout.connect(self._autofill_price)
        self._autofill_timer.start(1000)

        return w

    def _autofill_price(self):
        if hasattr(self.chart_view, "candles") and self.chart_view.candles:
            c = self.chart_view.candles[-1]
            self._entry_price.setValue(float(c["close"]))
            self._open_lbl.setText(f"O: {float(c['open']):,.2f}")
            self._close_lbl.setText(f"C: {float(c['close']):,.2f}")

    def _place_order(self, side: str):
        entry = self._entry_price.value()
        sl    = self._sl.value()
        tp    = self._tp.value()
        lev   = self._lev.currentText()
        sym   = getattr(self.chart_view, "current_symbol", "—").upper()
        import time as _time
        trade = {
            "time":  _time.strftime("%H:%M"),
            "side":  side,
            "sym":   sym,
            "entry": entry,
            "sl":    sl,
            "tp":    tp,
            "lev":   lev,
            "pnl":   None,
        }
        self._trade_history.insert(0, trade)
        self._refresh_history()

    # ── History ───────────────────────────────────────────────────────────────
    def _build_history_section(self) -> QWidget:
        self._hist_body = QWidget()
        self._hist_body.setStyleSheet(f"background:{BG2};border:1px solid {BORDER};"
                                      f"border-top:none;border-bottom-left-radius:4px;"
                                      f"border-bottom-right-radius:4px;")
        self._hist_vl = QVBoxLayout(self._hist_body)
        self._hist_vl.setContentsMargins(4,4,4,4); self._hist_vl.setSpacing(2)
        self._hist_body.setVisible(False)

        wrapper = QWidget(); wrapper.setStyleSheet("background:transparent;")
        wl = QVBoxLayout(wrapper); wl.setContentsMargins(0,0,0,0); wl.setSpacing(0)

        self._hist_btn = QPushButton("▸  HISTORY")
        self._hist_btn.setCheckable(True)
        self._hist_btn.setStyleSheet(f"""
            QPushButton {{
                background:#101418; color:#9a9ab0;
                border:1px solid {BORDER}; border-radius:5px;
                padding:7px 10px; font-size:11px; font-weight:bold;
                text-align:left; letter-spacing:1px;
            }}
            QPushButton:checked {{
                background:{BG2}; color:{AMBER};
                border:1px solid {AMBER}; border-bottom-left-radius:0;
                border-bottom-right-radius:0;
            }}
            QPushButton:hover:!checked {{ color:#ccc; }}
        """)
        self._hist_btn.toggled.connect(lambda c: (
            self._hist_body.setVisible(c),
            self._hist_btn.setText(f"{'▾' if c else '▸'}  HISTORY")
        ))
        wl.addWidget(self._hist_btn)
        wl.addWidget(self._hist_body)
        self._refresh_history()
        return wrapper

    def _refresh_history(self):
        while self._hist_vl.count():
            item = self._hist_vl.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        if not self._trade_history:
            lbl = QLabel("No trades yet"); lbl.setStyleSheet("color:#334;font-size:10px;")
            self._hist_vl.addWidget(lbl); return

        for t in self._trade_history[:8]:
            row = QWidget(); row.setStyleSheet("background:transparent;")
            hl  = QHBoxLayout(row); hl.setContentsMargins(0,1,0,1); hl.setSpacing(4)

            side_col = GREEN if t["side"] == "BUY" else RED
            sl = QLabel(t["side"][:1])
            sl.setStyleSheet(f"color:{side_col};font-size:10px;font-weight:bold;"
                             f"background:transparent;border:none;")
            sl.setFixedWidth(10); hl.addWidget(sl)

            sym_l = QLabel(f"{t['sym']} {t['lev']}")
            sym_l.setStyleSheet("color:#9a9ab0;font-size:9px;background:transparent;border:none;")
            hl.addWidget(sym_l, 1)

            ep_l = QLabel(f"@{t['entry']:,.0f}")
            ep_l.setStyleSheet("color:#668;font-size:9px;font-family:Consolas;"
                               "background:transparent;border:none;")
            hl.addWidget(ep_l)

            pnl = t.get("pnl")
            if pnl is not None:
                pc = GREEN if pnl >= 0 else RED
                pl = QLabel(f"{'+' if pnl>=0 else ''}{pnl:.1f}%")
                pl.setStyleSheet(f"color:{pc};font-size:9px;font-family:Consolas;"
                                 f"background:transparent;border:none;")
                hl.addWidget(pl)

            self._hist_vl.addWidget(row)

    # ── Signal handlers ───────────────────────────────────────────────────────
    def _on_ind_toggle(self, key, checked):
        if checked: self._active_indicators.add(key)
        else:       self._active_indicators.discard(key)
        self.indicator_toggled.emit(key, checked)
        if hasattr(self.chart_view, "set_active_indicators"):
            self.chart_view.set_active_indicators(self._active_indicators)
        self._refresh_scores()

    def _on_smc_toggle(self, key, checked):
        if checked: self._active_smc.add(key)
        else:       self._active_smc.discard(key)
        self.smc_toggled.emit(key, checked)
        if hasattr(self.chart_view, "set_active_smc"):
            self.chart_view.set_active_smc(self._active_smc)
        self._refresh_scores()

    def _open_params(self, key, label):
        from gui.indicator_settings import IndicatorSettingsDialog
        from auth.user_manager import current_user
        user    = current_user() or {}
        user_id = user.get("id", 1)
        symbol  = getattr(self.chart_view, "current_symbol", "btcusdt")
        dlg = IndicatorSettingsDialog(key, user_id=user_id, symbol=symbol, parent=self)
        dlg.settings_applied.connect(self._on_settings_applied)
        dlg.exec()

    def _on_settings_applied(self, key, style):
        self.params_changed.emit(key, style.get("params", {}))
        if hasattr(self.chart_view, "apply_indicator_style"):
            self.chart_view.apply_indicator_style(key, style)

    def _refresh_scores(self):
        if hasattr(self.chart_view, "get_confluence_scores"):
            s = self.chart_view.get_confluence_scores()
            self.bull_score_lbl.setText(str(s.get("bullish", "--")))
            self.bear_score_lbl.setText(str(s.get("bearish", "--")))

    def update_scores(self, bull, bear):
        self.bull_score_lbl.setText(str(bull))
        self.bear_score_lbl.setText(str(bear))

    # ── Hover tooltips ────────────────────────────────────────────────────────
    def _on_ind_hover(self, key, event):
        import numpy as np
        cursor_pos = QCursor.pos()
        current_value = extra_values = signal = None
        if hasattr(self.chart_view, "_indicator_results"):
            r = self.chart_view._indicator_results
            if key in r and len(r[key]) > 0:
                v = r[key][-1]
                try:
                    current_value = float(v) if not np.isnan(float(v)) else None
                except Exception: pass
            if key == "STOCHRSI":
                k_v = float(r.get("STOCHRSI_K",[0])[-1])
                d_v = float(r.get("STOCHRSI_D",[0])[-1])
                extra_values = {"K": k_v, "D": d_v}; current_value = k_v
            elif key == "MACD":
                extra_values = {
                    "MACD":   float(r.get("MACD",       [0])[-1]),
                    "signal": float(r.get("MACD_SIGNAL",[0])[-1]),
                    "hist":   float(r.get("MACD_HIST",  [0])[-1]),
                }; current_value = extra_values["MACD"]
        if hasattr(self.chart_view, "_indicator_engine"):
            sigs = self.chart_view._indicator_engine.get_signals()
            signal = sigs.get(key, sigs.get("EMA_TREND" if "EMA" in key else key))
        self._summary.show_indicator(key, cursor_pos, current_value, signal, extra_values)

    def _on_smc_hover(self, key, event):
        cursor_pos = QCursor.pos()
        nearest_zones = {}; current_price = None
        if (hasattr(self.chart_view, "_smc_detector") and
                hasattr(self.chart_view, "_smc_results") and
                self.chart_view._smc_results and self.chart_view.candles):
            current_price = self.chart_view.candles[-1]["close"]
            det = self.chart_view._smc_detector
            res = self.chart_view._smc_results
            ob = det.get_nearest_ob(current_price)
            if ob: nearest_zones["ob"] = ob
            fvg = det.get_nearest_fvg(current_price)
            if fvg: nearest_zones["fvg"] = fvg
            liq = [l for l in res.get("liquidity",[]) if "price" in l]
            if liq:
                nearest_zones["liq"] = min(liq, key=lambda l: abs(current_price - l["price"]))
            struct = res.get("structure", [])
            if struct: nearest_zones["structure"] = struct[-1]
        self._summary.show_smc(key, cursor_pos, nearest_zones, current_price)

    def _on_leave(self):
        self._summary.dismiss(); self._tooltip.dismiss()

    # Legacy
    def set_overlay(self, name): pass
