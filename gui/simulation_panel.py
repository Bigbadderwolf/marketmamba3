# gui/simulation_panel.py  — Phase 5 redesign
"""
Bottom-right simulation dock.

Page 0: Landing  — "Champ, which sim do you want to run?"
                   [⏪ REPLAY]  [◈ MODELS]
Page 1: Replay   — date range, playback controls
Page 2: Models   — 6 model checkboxes + generate button

Sim candles draw directly on main chart via sim_overlay.draw_simulation().
"""
import time, threading
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QSlider, QDateEdit, QComboBox, QStackedWidget, QCheckBox,
    QSpinBox, QProgressBar, QSizePolicy, QGridLayout, QScrollArea,
)
from PyQt6.QtCore import Qt, QTimer, QDate, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QLinearGradient

from simulation.sim_manager import SimManager

# ── palette ──────────────────────────────────────────────────────────────────
BG     = "#08101e"
BG2    = "#060c18"
BORDER = "#1a2a3a"
ACCENT = "#4a9eff"
GREEN  = "#00c896"
AMBER  = "#ff9800"

BASE = f"""
QWidget  {{ background:{BG}; color:#d1d4dc; font-size:11px; }}
QLabel   {{ background:transparent; border:none; }}
QDateEdit, QComboBox, QSpinBox {{
    background:#0f1e30; color:#d1d4dc;
    border:1px solid {BORDER}; border-radius:3px; padding:3px 6px; }}
QComboBox QAbstractItemView {{ background:#0f1e30; color:#d1d4dc; }}
QSlider::groove:horizontal {{ height:3px; background:{BORDER}; border-radius:2px; }}
QSlider::handle:horizontal {{
    width:12px; height:12px; margin:-5px 0;
    background:{ACCENT}; border-radius:6px; }}
QSlider::sub-page:horizontal {{ background:{ACCENT}; border-radius:2px; }}
QProgressBar {{ background:#0f1e30; border:1px solid {BORDER};
                border-radius:2px; height:5px; text-align:center; }}
QProgressBar::chunk {{ background:{ACCENT}; border-radius:2px; }}
"""

def _btn(label, color=ACCENT, bg="#0a1628", bold=True, h=34):
    return f"""
    QPushButton {{
        background:{bg}; color:{color};
        border:1.5px solid {color}; border-radius:5px;
        padding:6px 10px; font-weight:{'bold' if bold else 'normal'};
        font-size:11px; min-height:{h}px;
    }}
    QPushButton:hover {{ background:{color}; color:#000; }}
    QPushButton:pressed {{ background:{color}; color:#000; opacity:.85; }}
    """

BTN_PLAY = f"""
QPushButton {{ background:{GREEN}; color:#000; border:none; border-radius:4px;
    padding:5px 14px; font-weight:bold; font-size:14px; min-height:30px; }}
QPushButton:hover {{ background:#00e5ad; }}"""

BTN_STOP = """QPushButton { background:#ff5252; color:#fff; border:none;
    border-radius:4px; padding:5px 8px; font-weight:bold; }"""

BTN_CTRL = f"""QPushButton {{ background:#0f1e30; color:#9a9ab0;
    border:1px solid {BORDER}; border-radius:3px;
    padding:4px 8px; font-size:12px; min-width:26px; }}
QPushButton:hover {{ background:#162840; color:#fff; }}"""

def _div():
    d = QFrame(); d.setFixedHeight(1)
    d.setStyleSheet(f"background:{BORDER}; border:none;")
    return d


# ── Accuracy row ──────────────────────────────────────────────────────────────
class _AccRow(QWidget):
    def __init__(self, row):
        super().__init__(); self.setFixedHeight(21)
        hl = QHBoxLayout(self); hl.setContentsMargins(4,0,4,0); hl.setSpacing(5)
        dot = QLabel("●")
        dot.setStyleSheet(f"color:{row['color']};font-size:9px;background:transparent;border:none;")
        dot.setFixedWidth(12); hl.addWidget(dot)
        nm = QLabel(("★ " if row.get("best") else "") + row["model_name"])
        nm.setStyleSheet(
            f"color:{'#00c896' if row.get('best') else '#9a9ab0'};"
            f"font-size:9px;background:transparent;border:none;"
            f"font-weight:{'bold' if row.get('best') else 'normal'};")
        nm.setFixedWidth(105); hl.addWidget(nm)
        wr  = row["win_rate"]; wrc = "#00c896" if wr >= .5 else "#ff5252"
        wl  = QLabel(f"{wr*100:.0f}%")
        wl.setStyleSheet(f"color:{wrc};font-size:9px;font-family:Consolas;background:transparent;border:none;")
        wl.setFixedWidth(28); hl.addWidget(wl)
        bar = QProgressBar(); bar.setRange(0,100); bar.setValue(int(wr*100))
        bar.setFixedWidth(44); bar.setFixedHeight(4); bar.setTextVisible(False)
        bar.setStyleSheet(f"QProgressBar{{background:#0f1e30;border:1px solid #1a2a3a;border-radius:2px;}}"
                          f"QProgressBar::chunk{{background:{wrc};border-radius:2px;}}")
        hl.addWidget(bar)
        sl = QLabel(f"{row['sessions']}s")
        sl.setStyleSheet("color:#445;font-size:9px;background:transparent;border:none;")
        sl.setFixedWidth(22); hl.addWidget(sl)
        st = QLabel("✓" if row["fitted"] else "…")
        st.setStyleSheet(f"color:{'#00c896' if row['fitted'] else AMBER};font-size:9px;"
                         f"background:transparent;border:none;"); hl.addWidget(st)
        hl.addStretch()


# ── Main panel ────────────────────────────────────────────────────────────────
class SimulationPanel(QWidget):
    replay_candle_ready = pyqtSignal(dict, int, int)
    paths_ready         = pyqtSignal(list)
    clear_requested     = pyqtSignal()

    def __init__(self, sim_manager: SimManager):
        super().__init__()
        self._mgr   = sim_manager
        self._paths = []
        self.setStyleSheet(BASE)
        self.setMinimumWidth(270); self.setMaximumWidth(360)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._build_ui()
        self._acc_timer = QTimer()
        self._acc_timer.timeout.connect(self._refresh_acc)
        self._acc_timer.start(5000)

    # ── Root layout ───────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0,0,0,0); root.setSpacing(0)
        root.addWidget(self._build_header())
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_landing())    # 0
        self._stack.addWidget(self._build_replay())     # 1
        self._stack.addWidget(self._build_models())     # 2
        root.addWidget(self._stack, 1)
        root.addWidget(self._build_acc_section())

    # ── Header ────────────────────────────────────────────────────────────────
    def _build_header(self):
        w = QWidget(); w.setFixedHeight(30)
        w.setStyleSheet(f"background:{BG2};border-bottom:1px solid {BORDER};")
        hl = QHBoxLayout(w); hl.setContentsMargins(10,0,10,0)
        lbl = QLabel("⚡  SIMULATION ENGINE")
        lbl.setStyleSheet(f"color:{ACCENT};font-size:10px;font-weight:bold;letter-spacing:2px;")
        hl.addWidget(lbl); hl.addStretch()
        self._best_lbl = QLabel("—")
        self._best_lbl.setStyleSheet(f"color:{GREEN};font-size:9px;")
        hl.addWidget(self._best_lbl)
        clr = QPushButton("✕ clear")
        clr.setFixedHeight(20)
        clr.setStyleSheet(f"QPushButton{{background:transparent;color:#445;"
                          f"border:none;font-size:9px;}}"
                          f"QPushButton:hover{{color:#ff5252;}}")
        clr.clicked.connect(self.clear_requested)
        hl.addWidget(clr)
        return w

    # ── Page 0: Landing ───────────────────────────────────────────────────────
    def _build_landing(self):
        w = QWidget()
        vl = QVBoxLayout(w); vl.setContentsMargins(16,20,16,20); vl.setSpacing(16)

        title = QLabel("Champ, which sim\ndo you want to run?")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"color:{ACCENT};font-size:15px;font-weight:bold;"
            f"line-height:1.5;background:transparent;"
        )
        vl.addWidget(title)
        vl.addWidget(_div())

        # Replay button — big card style
        btn_rep = QPushButton()
        btn_rep.setMinimumHeight(72)
        btn_rep.setStyleSheet(f"""
            QPushButton {{
                background:#060f1e; color:#d1d4dc;
                border:1.5px solid {ACCENT}; border-radius:8px;
                text-align:left; padding:12px 14px;
                font-size:12px;
            }}
            QPushButton:hover {{
                background:#0d1e38; border-color:#6ab4ff; color:#fff;
            }}
        """)
        rep_inner = QVBoxLayout(btn_rep)
        rep_inner.setContentsMargins(0,0,0,0); rep_inner.setSpacing(2)
        r1 = QLabel("⏪  HISTORICAL REPLAY")
        r1.setStyleSheet(f"color:{ACCENT};font-weight:bold;font-size:12px;"
                         f"background:transparent;border:none;")
        r2 = QLabel("Replay past candles. Sim predicts\nwhat happens next from any point.")
        r2.setStyleSheet("color:#668;font-size:9px;background:transparent;border:none;")
        r2.setWordWrap(True)
        rep_inner.addWidget(r1); rep_inner.addWidget(r2)
        btn_rep.clicked.connect(lambda: self._stack.setCurrentIndex(1))
        vl.addWidget(btn_rep)

        # Models button — card style
        btn_mod = QPushButton()
        btn_mod.setMinimumHeight(72)
        btn_mod.setStyleSheet(f"""
            QPushButton {{
                background:#0f0c02; color:#d1d4dc;
                border:1.5px solid {AMBER}; border-radius:8px;
                text-align:left; padding:12px 14px;
                font-size:12px;
            }}
            QPushButton:hover {{
                background:#201800; border-color:#ffcc44; color:#fff;
            }}
        """)
        mod_inner = QVBoxLayout(btn_mod)
        mod_inner.setContentsMargins(0,0,0,0); mod_inner.setSpacing(2)
        m1 = QLabel("◈  SYNTHETIC MODELS")
        m1.setStyleSheet(f"color:{AMBER};font-weight:bold;font-size:12px;"
                         f"background:transparent;border:none;")
        m2 = QLabel("Generate future candles using\n6 ML & statistical models.")
        m2.setStyleSheet("color:#668;font-size:9px;background:transparent;border:none;")
        m2.setWordWrap(True)
        mod_inner.addWidget(m1); mod_inner.addWidget(m2)
        btn_mod.clicked.connect(lambda: self._stack.setCurrentIndex(2))
        vl.addWidget(btn_mod)

        vl.addStretch()
        return w

    # ── Page 1: Replay ────────────────────────────────────────────────────────
    def _build_replay(self):
        w = QWidget()
        vl = QVBoxLayout(w); vl.setContentsMargins(10,8,10,6); vl.setSpacing(7)

        # Back + title row
        hl_top = QHBoxLayout(); hl_top.setSpacing(6)
        back = QPushButton("← Back")
        back.setStyleSheet(f"QPushButton{{background:transparent;color:{ACCENT};"
                           f"border:none;font-size:10px;padding:2px 4px;}}"
                           f"QPushButton:hover{{color:#fff;}}")
        back.clicked.connect(lambda: self._stack.setCurrentIndex(0))
        hl_top.addWidget(back)
        sec = QLabel("HISTORICAL REPLAY")
        sec.setStyleSheet(f"color:{ACCENT};font-size:9px;font-weight:bold;letter-spacing:2px;")
        hl_top.addWidget(sec); hl_top.addStretch()
        vl.addLayout(hl_top)

        # Date range
        dr = QHBoxLayout(); dr.setSpacing(4)
        dr.addWidget(QLabel("From"))
        self._date_from = QDateEdit(); self._date_from.setCalendarPopup(True)
        self._date_from.setDate(QDate.currentDate().addDays(-60))
        self._date_from.setDisplayFormat("yyyy-MM-dd")
        dr.addWidget(self._date_from, 1)
        dr.addWidget(QLabel("To"))
        self._date_to = QDateEdit(); self._date_to.setCalendarPopup(True)
        self._date_to.setDate(QDate.currentDate().addDays(-1))
        self._date_to.setDisplayFormat("yyyy-MM-dd")
        dr.addWidget(self._date_to, 1)
        vl.addLayout(dr)

        tf_r = QHBoxLayout(); tf_r.addWidget(QLabel("Timeframe"))
        self._replay_tf = QComboBox()
        for tf in ["1m","5m","15m","1h","4h","1d"]: self._replay_tf.addItem(tf)
        self._replay_tf.setCurrentText("1h")
        tf_r.addWidget(self._replay_tf); tf_r.addStretch()
        vl.addLayout(tf_r)

        lb = QPushButton("LOAD WINDOW")
        lb.setStyleSheet(_btn(label="LOAD WINDOW", color=ACCENT))
        lb.clicked.connect(self._load_replay)
        vl.addWidget(lb)

        self._rep_status = QLabel("No data loaded")
        self._rep_status.setStyleSheet("color:#445;font-size:10px;")
        self._rep_status.setWordWrap(True)
        vl.addWidget(self._rep_status)

        vl.addWidget(_div())

        # Scrub bar
        sr = QHBoxLayout(); sr.addWidget(QLabel("Pos"))
        self._scrub = QSlider(Qt.Orientation.Horizontal)
        self._scrub.setRange(0, 1000); self._scrub.setValue(0)
        self._scrub.sliderMoved.connect(self._on_scrub)
        sr.addWidget(self._scrub, 1)
        self._scrub_lbl = QLabel("0/0")
        self._scrub_lbl.setStyleSheet("font-size:9px;font-family:Consolas;")
        self._scrub_lbl.setFixedWidth(52); sr.addWidget(self._scrub_lbl)
        vl.addLayout(sr)

        # Speed
        sp_r = QHBoxLayout(); sp_r.addWidget(QLabel("Speed"))
        self._spd = QSlider(Qt.Orientation.Horizontal)
        self._spd.setRange(1, 100); self._spd.setValue(10)
        self._spd.valueChanged.connect(self._on_speed)
        sp_r.addWidget(self._spd, 1)
        self._spd_lbl = QLabel("1.0×")
        self._spd_lbl.setStyleSheet("font-size:9px;font-family:Consolas;")
        self._spd_lbl.setFixedWidth(30); sp_r.addWidget(self._spd_lbl)
        vl.addLayout(sp_r)

        # Playback controls
        cr = QHBoxLayout(); cr.setSpacing(4)
        for sym, tip, cb in [("⏮","Start",self._j_start),("◀","Back",self._step_back)]:
            b = QPushButton(sym); b.setFixedWidth(28); b.setStyleSheet(BTN_CTRL)
            b.setToolTip(tip); b.clicked.connect(cb); cr.addWidget(b)
        self._play_btn = QPushButton("▶")
        self._play_btn.setStyleSheet(BTN_PLAY)
        self._play_btn.setFixedWidth(44)
        self._play_btn.clicked.connect(self._play_pause)
        cr.addWidget(self._play_btn)
        for sym, tip, cb in [("▶|","Fwd",self._step_fwd),("⏭","End",self._j_end)]:
            b = QPushButton(sym); b.setFixedWidth(28); b.setStyleSheet(BTN_CTRL)
            b.setToolTip(tip); b.clicked.connect(cb); cr.addWidget(b)
        sb = QPushButton("■"); sb.setFixedWidth(26)
        sb.setStyleSheet(BTN_STOP); sb.clicked.connect(self._stop)
        cr.addWidget(sb); cr.addStretch()
        vl.addLayout(cr)

        vl.addStretch()
        return w

    # ── Page 2: Models ────────────────────────────────────────────────────────
    def _build_models(self):
        w = QWidget()
        vl = QVBoxLayout(w); vl.setContentsMargins(10,8,10,6); vl.setSpacing(7)

        hl_top = QHBoxLayout(); hl_top.setSpacing(6)
        back = QPushButton("← Back")
        back.setStyleSheet(f"QPushButton{{background:transparent;color:{AMBER};"
                           f"border:none;font-size:10px;padding:2px 4px;}}"
                           f"QPushButton:hover{{color:#fff;}}")
        back.clicked.connect(lambda: self._stack.setCurrentIndex(0))
        hl_top.addWidget(back)
        sec = QLabel("SYNTHETIC MODELS")
        sec.setStyleSheet(f"color:{AMBER};font-size:9px;font-weight:bold;letter-spacing:2px;")
        hl_top.addWidget(sec); hl_top.addStretch()
        vl.addLayout(hl_top)

        self._model_checks = {}
        MODELS = [
            ("monte_carlo",      "Monte Carlo",   "#4a9eff"),
            ("regime_switching", "Regime-Switch", "#ffb74d"),
            ("agent_based",      "Agent-Based",   "#e040fb"),
            ("gan",              "GAN",           "#ff9800"),
            ("fractal",          "Fractal",       "#00e5ff"),
            ("order_flow",       "Order Flow",    "#69f0ae"),
        ]
        gw = QWidget(); g = QGridLayout(gw)
        g.setSpacing(3); g.setContentsMargins(0,0,0,0)
        for i, (mid, mn, mc) in enumerate(MODELS):
            cb = QCheckBox(mn)
            cb.setStyleSheet(
                f"QCheckBox{{color:{mc};background:transparent;}}"
                f"QCheckBox::indicator{{width:11px;height:11px;"
                f"border:1px solid #2a3a4a;border-radius:2px;background:#0f1e30;}}"
                f"QCheckBox::indicator:checked{{background:{mc};}}"
            )
            cb.setChecked(True)
            cb.stateChanged.connect(self._model_toggle)
            self._model_checks[mid] = cb
            g.addWidget(cb, i // 2, i % 2)
        vl.addWidget(gw)

        note = QLabel("Ghosted candles drawn on right half of chart")
        note.setStyleSheet("color:#445;font-size:9px;"); note.setWordWrap(True)
        vl.addWidget(note)
        vl.addWidget(_div())

        fc = QHBoxLayout(); fc.addWidget(QLabel("Forward candles"))
        self._gen_n = QSpinBox(); self._gen_n.setRange(10, 500)
        self._gen_n.setValue(100); self._gen_n.setFixedWidth(65)
        fc.addWidget(self._gen_n); fc.addStretch()
        vl.addLayout(fc)

        gb = QPushButton("▶  GENERATE — DRAW ON CHART")
        gb.setStyleSheet(_btn("", AMBER, "#0f0c02"))
        gb.clicked.connect(self._generate)
        vl.addWidget(gb)

        self._gen_status = QLabel("")
        self._gen_status.setStyleSheet("color:#445;font-size:9px;")
        self._gen_status.setWordWrap(True)
        vl.addWidget(self._gen_status)

        vl.addStretch()
        return w

    # ── Accuracy section ──────────────────────────────────────────────────────
    def _build_acc_section(self):
        f = QFrame()
        f.setStyleSheet(f"QFrame{{background:{BG2};border-top:1px solid {BORDER};}}")
        vl = QVBoxLayout(f); vl.setContentsMargins(8,5,8,5); vl.setSpacing(2)
        hdr = QLabel("ACCURACY")
        hdr.setStyleSheet(f"color:{ACCENT};font-size:9px;font-weight:bold;letter-spacing:2px;")
        vl.addWidget(hdr)
        self._acc_vl = QVBoxLayout(); self._acc_vl.setSpacing(1)
        vl.addLayout(self._acc_vl)
        return f

    # ── Replay logic ──────────────────────────────────────────────────────────
    def _load_replay(self):
        from PyQt6.QtWidgets import QApplication
        symbol = "btcusdt"
        try:
            win = self.window()
            if hasattr(win, "chart_view"): symbol = win.chart_view.current_symbol
        except Exception: pass
        tf   = self._replay_tf.currentText()
        df   = self._date_from.date(); dt = self._date_to.date()
        import datetime
        ts0  = int(datetime.datetime(df.year(),df.month(),df.day()).timestamp()*1000)
        ts1  = int(datetime.datetime(dt.year(),dt.month(),dt.day(),23,59).timestamp()*1000)
        self._rep_status.setText("Loading…"); QApplication.processEvents()
        n = self._mgr.load_replay(symbol, tf, ts0, ts1)
        if n == 0:
            self._rep_status.setText("No candles found. Run setup first."); return
        self._rep_status.setText(f"{n:,} candles · {symbol.upper()} {tf}")
        self._scrub.setRange(0, max(1, n-1)); self._scrub.setValue(0)
        self._scrub_lbl.setText(f"0/{n}")
        self._mgr.set_replay_callback(self._replay_cb)
        if self._mgr._replay.candles: self._mgr.fit_all(self._mgr._replay.candles)

    def _play_pause(self):
        if self._mgr.replay_get_state().total == 0: return
        self._mgr.replay_play_pause()
        self._play_btn.setText("⏸" if self._mgr.replay_get_state().playing else "▶")

    def _stop(self):   self._mgr.stop_replay(); self._play_btn.setText("▶")
    def _step_fwd(self): self._mgr.replay_step()
    def _step_back(self):
        s = self._mgr.replay_get_state()
        self._mgr.replay_jump(max(0, s.current_idx - 1)); self._sync_scrub()
    def _j_start(self): self._mgr.replay_jump_start(); self._sync_scrub()
    def _j_end(self):   self._mgr.replay_jump_end();   self._sync_scrub()

    def _on_scrub(self, val):
        s = self._mgr.replay_get_state()
        if s.total == 0: return
        self._mgr.replay_scrub(val / max(self._scrub.maximum(), 1))
        idx = self._mgr.replay_get_state().current_idx
        vis = self._mgr.replay_get_visible()
        self._scrub_lbl.setText(f"{idx}/{s.total}")
        if vis: self.replay_candle_ready.emit(vis[-1], idx, s.total)

    def _on_speed(self, val):
        spd = val / 10.0
        self._mgr.replay_set_speed(spd); self._spd_lbl.setText(f"{spd:.1f}×")

    def _replay_cb(self, candle, idx, total):
        self._sync_scrub(); self.replay_candle_ready.emit(candle, idx, total)

    def _sync_scrub(self):
        try:
            s = self._mgr.replay_get_state()
            if s.total > 0:
                self._scrub.blockSignals(True)
                self._scrub.setValue(int(s.current_idx / s.total * self._scrub.maximum()))
                self._scrub.blockSignals(False)
            self._scrub_lbl.setText(f"{s.current_idx}/{s.total}")
        except Exception: pass

    # ── Model generation ──────────────────────────────────────────────────────
    def _model_toggle(self):
        self._mgr.set_active_models(
            [m for m, cb in self._model_checks.items() if cb.isChecked()])

    def _generate(self):
        self._gen_status.setText("Generating…")
        def _run():
            try:
                sp = 0.0; lt = int(time.time()); tfs = 3600
                try:
                    win = self.window()
                    if hasattr(win, "chart_view") and win.chart_view.candles:
                        c   = win.chart_view.candles
                        sp  = float(c[-1]["close"]); lt = int(c[-1]["time"])
                        if len(c) >= 2:
                            tfs = max(60, int(c[-1]["time"]) - int(c[-2]["time"]))
                        if not self._mgr.is_fitted():
                            self._mgr.fit_all(c, async_fit=False)
                except Exception: pass
                if sp <= 0:
                    self._gen_status.setText("No live price — connect chart first"); return
                n     = self._gen_n.value()
                paths = self._mgr.generate_all(n, sp, lt, tfs)
                self._paths = paths; self.paths_ready.emit(paths)
                self._gen_status.setText(f"✓ {len(paths)} model(s) × {n} candles")
                self._refresh_acc()
            except Exception as e:
                self._gen_status.setText(f"Error: {e}")
        threading.Thread(target=_run, daemon=True).start()

    # ── Accuracy ──────────────────────────────────────────────────────────────
    def _refresh_acc(self):
        rows = self._mgr.accuracy_table(); best = self._mgr.get_best_model()
        for r in rows: r["best"] = (r["model_id"] == best)
        while self._acc_vl.count():
            item = self._acc_vl.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        for r in rows: self._acc_vl.addWidget(_AccRow(r))
        self._best_lbl.setText(f"★ {self._mgr.get_model_name(best)}" if best else "—")

    def fit_on_candles(self, candles):
        if candles and len(candles) >= 50: self._mgr.fit_all(candles)
