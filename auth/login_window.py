# auth/login_window.py
"""
Login / Register window shown before the main trading interface.
Dark professional theme matching the rest of Market Mamba.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QStackedWidget, QFrame, QMessageBox, QSpacerItem,
    QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPalette
from auth.user_manager import login, register, AuthError


STYLE = """
QWidget {
    background-color: #0a0a0a;
    color: #d1d4dc;
    font-family: 'Segoe UI', sans-serif;
}
QLabel#title {
    font-size: 28px;
    font-weight: bold;
    color: #00c896;
    letter-spacing: 2px;
}
QLabel#subtitle {
    font-size: 12px;
    color: #666;
    margin-bottom: 20px;
}
QLabel#fieldlabel {
    font-size: 12px;
    color: #888;
    margin-bottom: 2px;
}
QLineEdit {
    background-color: #141414;
    border: 1px solid #2a2a2a;
    border-radius: 6px;
    padding: 10px 14px;
    font-size: 14px;
    color: #d1d4dc;
    min-height: 20px;
}
QLineEdit:focus {
    border: 1px solid #00c896;
}
QPushButton#primary {
    background-color: #00c896;
    color: #000;
    border: none;
    border-radius: 6px;
    padding: 12px;
    font-size: 14px;
    font-weight: bold;
    min-height: 24px;
}
QPushButton#primary:hover {
    background-color: #00e5ad;
}
QPushButton#secondary {
    background-color: transparent;
    color: #00c896;
    border: 1px solid #00c896;
    border-radius: 6px;
    padding: 10px;
    font-size: 13px;
}
QPushButton#secondary:hover {
    background-color: #0d2a22;
}
QPushButton#link {
    background: transparent;
    color: #00c896;
    border: none;
    font-size: 12px;
    text-decoration: underline;
}
QLabel#error {
    color: #ff5252;
    font-size: 12px;
}
QLabel#success {
    color: #00c896;
    font-size: 12px;
}
QFrame#card {
    background-color: #111111;
    border: 1px solid #1e1e1e;
    border-radius: 12px;
}
"""


class LoginWindow(QWidget):
    login_successful = pyqtSignal(dict)   # emits user dict on success

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Market Mamba — Login")
        self.setFixedSize(420, 580)
        self.setStyleSheet(STYLE)
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # Stack: 0=login, 1=register
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_login_page())
        self.stack.addWidget(self._build_register_page())

        outer.addWidget(self.stack)

    # ── Login page ──────────────────────────────────────────────────────────

    def _build_login_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(50, 50, 50, 50)
        layout.setSpacing(10)

        # Logo / title
        title = QLabel("MARKET MAMBA")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        sub = QLabel("Professional Trading Platform")
        sub.setObjectName("subtitle")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(title)
        layout.addWidget(sub)
        layout.addSpacing(20)

        # Card
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(12)

        # Username
        lbl_u = QLabel("Username")
        lbl_u.setObjectName("fieldlabel")
        self.login_username = QLineEdit()
        self.login_username.setPlaceholderText("Enter username")

        # Password
        lbl_p = QLabel("Password")
        lbl_p.setObjectName("fieldlabel")
        self.login_password = QLineEdit()
        self.login_password.setPlaceholderText("Enter password")
        self.login_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.login_password.returnPressed.connect(self._do_login)

        # Error label
        self.login_error = QLabel("")
        self.login_error.setObjectName("error")
        self.login_error.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.login_error.hide()

        # Login button
        btn_login = QPushButton("LOGIN")
        btn_login.setObjectName("primary")
        btn_login.clicked.connect(self._do_login)

        card_layout.addWidget(lbl_u)
        card_layout.addWidget(self.login_username)
        card_layout.addSpacing(4)
        card_layout.addWidget(lbl_p)
        card_layout.addWidget(self.login_password)
        card_layout.addSpacing(4)
        card_layout.addWidget(self.login_error)
        card_layout.addSpacing(8)
        card_layout.addWidget(btn_login)

        layout.addWidget(card)
        layout.addSpacing(16)

        # Switch to register
        switch_row = QHBoxLayout()
        lbl_no = QLabel("Don't have an account?")
        lbl_no.setObjectName("fieldlabel")
        btn_switch = QPushButton("Create Account")
        btn_switch.setObjectName("link")
        btn_switch.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        switch_row.addStretch()
        switch_row.addWidget(lbl_no)
        switch_row.addWidget(btn_switch)
        switch_row.addStretch()
        layout.addLayout(switch_row)
        layout.addStretch()

        return page

    # ── Register page ────────────────────────────────────────────────────────

    def _build_register_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(50, 40, 50, 40)
        layout.setSpacing(10)

        title = QLabel("CREATE ACCOUNT")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        sub = QLabel("Join Market Mamba")
        sub.setObjectName("subtitle")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(title)
        layout.addWidget(sub)
        layout.addSpacing(10)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(10)

        # Fields
        lbl_u = QLabel("Username")
        lbl_u.setObjectName("fieldlabel")
        self.reg_username = QLineEdit()
        self.reg_username.setPlaceholderText("Choose a username")

        lbl_e = QLabel("Email")
        lbl_e.setObjectName("fieldlabel")
        self.reg_email = QLineEdit()
        self.reg_email.setPlaceholderText("your@email.com")

        lbl_p = QLabel("Password")
        lbl_p.setObjectName("fieldlabel")
        self.reg_password = QLineEdit()
        self.reg_password.setPlaceholderText("Min 8 characters")
        self.reg_password.setEchoMode(QLineEdit.EchoMode.Password)

        lbl_p2 = QLabel("Confirm Password")
        lbl_p2.setObjectName("fieldlabel")
        self.reg_password2 = QLineEdit()
        self.reg_password2.setPlaceholderText("Repeat password")
        self.reg_password2.setEchoMode(QLineEdit.EchoMode.Password)
        self.reg_password2.returnPressed.connect(self._do_register)

        self.reg_error = QLabel("")
        self.reg_error.setObjectName("error")
        self.reg_error.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.reg_error.hide()

        self.reg_success = QLabel("")
        self.reg_success.setObjectName("success")
        self.reg_success.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.reg_success.hide()

        btn_reg = QPushButton("CREATE ACCOUNT")
        btn_reg.setObjectName("primary")
        btn_reg.clicked.connect(self._do_register)

        for w in [lbl_u, self.reg_username, lbl_e, self.reg_email,
                  lbl_p, self.reg_password, lbl_p2, self.reg_password2,
                  self.reg_error, self.reg_success, btn_reg]:
            card_layout.addWidget(w)

        layout.addWidget(card)
        layout.addSpacing(12)

        switch_row = QHBoxLayout()
        lbl_have = QLabel("Already have an account?")
        lbl_have.setObjectName("fieldlabel")
        btn_back = QPushButton("Sign In")
        btn_back.setObjectName("link")
        btn_back.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        switch_row.addStretch()
        switch_row.addWidget(lbl_have)
        switch_row.addWidget(btn_back)
        switch_row.addStretch()
        layout.addLayout(switch_row)
        layout.addStretch()

        return page

    # ── Actions ──────────────────────────────────────────────────────────────

    def _do_login(self):
        self.login_error.hide()
        username = self.login_username.text().strip()
        password = self.login_password.text().strip()

        if not username or not password:
            self._show_login_error("Please enter username and password.")
            return
        try:
            user = login(username, password)
            self.login_successful.emit(user)
        except AuthError as e:
            self._show_login_error(str(e))

    def _do_register(self):
        self.reg_error.hide()
        self.reg_success.hide()

        username  = self.reg_username.text().strip()
        email     = self.reg_email.text().strip()
        password  = self.reg_password.text().strip()
        password2 = self.reg_password2.text().strip()

        if password != password2:
            self._show_reg_error("Passwords do not match.")
            return
        try:
            user = register(username, email, password)
            self.reg_success.setText("Account created! Signing you in...")
            self.reg_success.show()
            self.login_successful.emit(user)
        except AuthError as e:
            self._show_reg_error(str(e))

    def _show_login_error(self, msg: str):
        self.login_error.setText(msg)
        self.login_error.show()

    def _show_reg_error(self, msg: str):
        self.reg_error.setText(msg)
        self.reg_error.show()
