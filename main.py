# main.py
"""
Market Mamba v2.0 — Entry Point
Flow: init DB → splash → login → setup wizard (first run) → MainWindow
"""
import sys
import logging
import traceback

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("market_mamba")


def run():
    from PyQt6.QtWidgets import QApplication, QSplashScreen, QMessageBox
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtGui import QFont, QColor, QPainter, QPixmap

    app = QApplication(sys.argv)
    app.setApplicationName("Market Mamba")
    app.setApplicationVersion("2.0.0")
    app.setStyle("Fusion")

    # ── Global exception handler — never silently crash ───────────────────────
    def handle_exception(exc_type, exc_value, exc_tb):
        msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        log.error("Unhandled exception:\n%s", msg)
        try:
            QMessageBox.critical(
                None,
                "Market Mamba — Error",
                f"An unexpected error occurred:\n\n{exc_value}\n\n"
                f"Check terminal for full traceback."
            )
        except Exception:
            pass
        print("\n=== FULL TRACEBACK ===")
        traceback.print_exception(exc_type, exc_value, exc_tb)

    sys.excepthook = handle_exception

    # ── Init database ─────────────────────────────────────────────────────────
    try:
        from auth.db import init_db
        init_db()
        log.info("Database ready")
    except Exception as e:
        traceback.print_exc()
        QMessageBox.critical(None, "DB Error", f"Database failed to initialise:\n\n{e}")
        sys.exit(1)

    # ── Splash screen ─────────────────────────────────────────────────────────
    try:
        pix = QPixmap(480, 280)
        pix.fill(QColor("#0a0a0a"))
        p = QPainter(pix)
        p.setPen(QColor("#00c896"))
        p.setFont(QFont("Segoe UI", 32, QFont.Weight.Bold))
        p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "MARKET MAMBA")
        p.setPen(QColor("#444444"))
        p.setFont(QFont("Segoe UI", 12))
        p.drawText(
            pix.rect().adjusted(0, 60, 0, 0),
            Qt.AlignmentFlag.AlignCenter,
            "Professional Trading Platform v2.0"
        )
        p.end()
        splash = QSplashScreen(pix)
        splash.show()
        app.processEvents()
        log.info("Splash shown")
    except Exception as e:
        traceback.print_exc()
        log.warning("Splash failed (non-fatal): %s", e)
        splash = None

    # ── Login window ──────────────────────────────────────────────────────────
    try:
        from auth.login_window import LoginWindow
        login_win = LoginWindow()
    except Exception as e:
        traceback.print_exc()
        QMessageBox.critical(None, "Import Error", f"Failed to load login window:\n\n{e}")
        sys.exit(1)

    # Store references so Qt does not garbage collect windows
    app._login_win  = login_win
    app._main_win   = None
    app._wizard     = None

    def on_login(user: dict):
        log.info("Login success: %s (id=%s)", user.get("username"), user.get("id"))
        login_win.hide()
        _launch(user)

    login_win.login_successful.connect(on_login)

    def show_login():
        if splash:
            splash.finish(login_win)
        login_win.show()

    QTimer.singleShot(1400, show_login)

    # ── Post-login: setup wizard check ────────────────────────────────────────
    def _launch(user: dict):
        try:
            from gui.setup_wizard import SetupWizard
            if SetupWizard.needs_setup():
                log.info("First run — showing setup wizard")
                wiz = SetupWizard()
                app._wizard = wiz
                wiz.setup_complete.connect(lambda: _open(user))
                wiz.show()
            else:
                _open(user)
        except Exception as e:
            traceback.print_exc()
            log.warning("Setup wizard failed (%s) — opening main window directly", e)
            _open(user)

    # ── Open main trading window ───────────────────────────────────────────────
    def _open(user: dict):
        log.info("Opening MainWindow for user: %s", user.get("username"))
        try:
            from gui.window import MainWindow
            win = MainWindow(user=user)
            app._main_win = win   # keep reference — prevents garbage collection
            win.show()
            win.raise_()
            win.activateWindow()
            log.info("MainWindow opened successfully")
        except Exception as e:
            traceback.print_exc()
            QMessageBox.critical(
                None,
                "MainWindow Error",
                f"Failed to open trading interface:\n\n{str(e)}\n\n"
                f"Full error has been printed to terminal."
            )

    sys.exit(app.exec())



if __name__ == "__main__":
    run()
