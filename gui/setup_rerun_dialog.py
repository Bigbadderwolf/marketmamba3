# gui/setup_rerun_dialog.py
"""
Floating setup dialog — launched from topbar "⚙ Setup" button.
Shows a searchable list of ALL Binance pairs. User selects which
symbols to re-run data download + ML training for.
"""
import threading
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QScrollArea, QWidget, QCheckBox, QProgressBar,
    QFrame, QGridLayout,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont

from data.symbol_registry import ALL_SYMBOLS, SYMBOL_CATEGORIES, get_display_name

STYLE = """
QDialog {
    background:#080c14; color:#d1d4dc;
    font-family:'Segoe UI', sans-serif;
    border:1px solid #1a2a3a; border-radius:10px;
}
QLabel  { background:transparent; border:none; }
QLineEdit {
    background:#0f1e30; color:#d1d4dc;
    border:1px solid #1a2a3a; border-radius:4px;
    padding:6px 10px; font-size:12px;
}
QLineEdit:focus { border-color:#4a9eff; }
QCheckBox { color:#d1d4dc; spacing:6px; font-size:11px; }
QCheckBox::indicator {
    width:13px; height:13px;
    border:1px solid #2a3a4a; border-radius:3px; background:#0f1e30;
}
QCheckBox::indicator:checked { background:#4a9eff; border-color:#4a9eff; }
QScrollArea { border:none; background:transparent; }
QScrollBar:vertical {
    background:#080c14; width:6px; border-radius:3px;
}
QScrollBar::handle:vertical {
    background:#1a2a3a; border-radius:3px; min-height:20px;
}
QPushButton#primary {
    background:#4a9eff; color:#000; border:none;
    border-radius:5px; padding:9px 20px;
    font-size:13px; font-weight:bold;
}
QPushButton#primary:hover { background:#6ab4ff; }
QPushButton#secondary {
    background:#0f1e30; color:#9a9ab0;
    border:1px solid #1a2a3a; border-radius:5px;
    padding:9px 20px; font-size:13px;
}
QPushButton#secondary:hover { background:#162840; color:#fff; }
QProgressBar {
    background:#0f1e30; border:1px solid #1a2a3a;
    border-radius:3px; height:8px;
}
QProgressBar::chunk { background:#00c896; border-radius:3px; }
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


class SetupRerunDialog(QDialog):
    setup_requested = pyqtSignal(list)   # emits selected symbol list

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Market Mamba — Setup")
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(620, 580)
        self.setStyleSheet(STYLE)
        self._checks: dict[str, QCheckBox] = {}
        self._build_ui()
        self._populate_symbols(ALL_SYMBOLS)

    # ── Build UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        vl = QVBoxLayout(self)
        vl.setContentsMargins(24, 20, 24, 20); vl.setSpacing(14)

        # Title row
        tl = QHBoxLayout()
        title = QLabel("⚙  Setup — Select Pairs")
        title.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        title.setStyleSheet("color:#4a9eff;")
        tl.addWidget(title); tl.addStretch()
        sub = QLabel("Download historical data & train ML models\nfor the selected symbols.")
        sub.setStyleSheet("color:#668;font-size:11px;")
        sub.setAlignment(Qt.AlignmentFlag.AlignRight)
        tl.addWidget(sub)
        vl.addLayout(tl)

        # Search bar
        self._search = QLineEdit()
        self._search.setPlaceholderText("🔍  Search symbols  (e.g. BTC, ETH, SOL…)")
        self._search.textChanged.connect(self._on_search)
        vl.addWidget(self._search)

        # Quick-select buttons
        qs = QHBoxLayout(); qs.setSpacing(6)
        for label, action in [
            ("Select All",   self._select_all),
            ("Clear All",    self._clear_all),
            ("Top 10",       self._select_top10),
        ]:
            b = QPushButton(label)
            b.setStyleSheet("""
                QPushButton { background:#0f1e30; color:#9a9ab0;
                    border:1px solid #1a2a3a; border-radius:3px;
                    padding:4px 10px; font-size:10px; }
                QPushButton:hover { background:#162840; color:#fff; }
            """)
            b.clicked.connect(action); qs.addWidget(b)
        self._selected_lbl = QLabel("0 selected")
        self._selected_lbl.setStyleSheet("color:#4a9eff;font-size:10px;")
        qs.addStretch(); qs.addWidget(self._selected_lbl)
        vl.addLayout(qs)

        # Scrollable symbol grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._grid_w = QWidget()
        self._grid_w.setStyleSheet("background:transparent;")
        self._grid = QVBoxLayout(self._grid_w)
        self._grid.setContentsMargins(0,0,0,0); self._grid.setSpacing(10)
        scroll.setWidget(self._grid_w)
        vl.addWidget(scroll, 1)

        # Progress bar (hidden until running)
        self._progress = QProgressBar()
        self._progress.setRange(0, 100); self._progress.setValue(0)
        self._progress.hide()
        vl.addWidget(self._progress)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color:#668;font-size:10px;")
        self._status_lbl.hide()
        vl.addWidget(self._status_lbl)

        # Buttons
        bl = QHBoxLayout(); bl.setSpacing(10)
        self._run_btn = QPushButton("▶  Run Setup")
        self._run_btn.setObjectName("primary")
        self._run_btn.clicked.connect(self._on_run)
        close_btn = QPushButton("Cancel")
        close_btn.setObjectName("secondary")
        close_btn.clicked.connect(self.reject)
        bl.addStretch(); bl.addWidget(close_btn); bl.addWidget(self._run_btn)
        vl.addLayout(bl)

    # ── Symbol grid ───────────────────────────────────────────────────────────
    def _populate_symbols(self, symbols: list):
        """Rebuild grid from symbol list, grouped by category."""
        # Clear
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self._checks.clear()

        # Group symbols by category
        shown = set(symbols)
        grouped: dict[str, list] = {}
        already = set()
        for cat, syms in SYMBOL_CATEGORIES.items():
            cat_syms = [s for s in syms if s in shown]
            if cat_syms:
                grouped[cat] = cat_syms
                already.update(cat_syms)
        leftover = [s for s in symbols if s not in already]
        if leftover:
            grouped["Other"] = leftover

        for cat, syms in grouped.items():
            # Category header
            hdr = QLabel(cat)
            color = CAT_COLORS.get(cat, "#668")
            hdr.setStyleSheet(
                f"color:{color};font-size:10px;font-weight:bold;"
                f"letter-spacing:1.5px;padding:4px 0 2px 0;"
            )
            self._grid.addWidget(hdr)

            # Symbol checkboxes in a 4-column grid
            gw = QWidget(); gw.setStyleSheet("background:transparent;")
            g  = QGridLayout(gw); g.setSpacing(3); g.setContentsMargins(0,0,0,0)
            for i, sym in enumerate(syms):
                cb = QCheckBox(get_display_name(sym))
                cb.setToolTip(sym)
                cb.stateChanged.connect(self._on_check_changed)
                g.addWidget(cb, i // 4, i % 4)
                self._checks[sym] = cb
            self._grid.addWidget(gw)

            # Divider
            d = QFrame(); d.setFixedHeight(1)
            d.setStyleSheet("background:#1a2a3a;")
            self._grid.addWidget(d)

        self._grid.addStretch()
        self._update_count()

    def _on_search(self, text: str):
        q = text.strip().upper()
        if not q:
            self._populate_symbols(ALL_SYMBOLS)
        else:
            filtered = [s for s in ALL_SYMBOLS if q in s]
            self._populate_symbols(filtered)

    def _select_all(self):
        for cb in self._checks.values(): cb.setChecked(True)

    def _clear_all(self):
        for cb in self._checks.values(): cb.setChecked(False)

    def _select_top10(self):
        self._clear_all()
        TOP10 = ["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT",
                 "ADAUSDT","DOGEUSDT","AVAXUSDT","MATICUSDT","DOTUSDT"]
        for sym in TOP10:
            if sym in self._checks: self._checks[sym].setChecked(True)

    def _on_check_changed(self):
        self._update_count()

    def _update_count(self):
        n = sum(1 for cb in self._checks.values() if cb.isChecked())
        self._selected_lbl.setText(
            f"{n} selected" + (f"  ·  ~{n*2}–{n*5} min" if n else "")
        )

    # ── Run ───────────────────────────────────────────────────────────────────
    def _on_run(self):
        selected = [sym for sym, cb in self._checks.items() if cb.isChecked()]
        if not selected:
            self._status_lbl.setText("Please select at least one symbol.")
            self._status_lbl.setStyleSheet("color:#ff5252;font-size:10px;")
            self._status_lbl.show()
            return
        self._run_btn.setEnabled(False)
        self._run_btn.setText("Running…")
        self._progress.show(); self._progress.setValue(0)
        self._status_lbl.setText(f"Setting up {len(selected)} symbol(s)…")
        self._status_lbl.setStyleSheet("color:#668;font-size:10px;")
        self._status_lbl.show()
        self.setup_requested.emit(selected)

    def set_progress(self, pct: int, msg: str = ""):
        self._progress.setValue(pct)
        if msg: self._status_lbl.setText(msg)

    def set_done(self):
        self._progress.setValue(100)
        self._status_lbl.setText("✓ Setup complete!")
        self._status_lbl.setStyleSheet("color:#00c896;font-size:11px;font-weight:bold;")
        self._run_btn.setText("✓ Done"); self._run_btn.setEnabled(True)
        QTimer.singleShot(2000, self.accept)
