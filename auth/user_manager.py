# auth/user_manager.py
"""
Handles user registration, login, session management.
Passwords are hashed with bcrypt — never stored in plaintext.
"""
import bcrypt, logging
from datetime import datetime
from auth.db import get_conn

log = logging.getLogger(__name__)


class AuthError(Exception):
    pass


# ── Current session ──────────────────────────────────────────────────────────
_current_user: dict | None = None


def current_user() -> dict | None:
    return _current_user


def is_logged_in() -> bool:
    return _current_user is not None


# ── Registration ─────────────────────────────────────────────────────────────

def register(username: str, email: str, password: str) -> dict:
    """
    Create a new user account.
    Returns user dict on success, raises AuthError on failure.
    """
    username = username.strip()
    email    = email.strip().lower()
    password = password.strip()

    if len(username) < 3:
        raise AuthError("Username must be at least 3 characters.")
    if len(password) < 8:
        raise AuthError("Password must be at least 8 characters.")
    if "@" not in email:
        raise AuthError("Invalid email address.")

    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
            (username, email, pw_hash)
        )
        conn.commit()
        log.info("Registered new user: %s", username)
    except Exception as e:
        if "UNIQUE" in str(e):
            raise AuthError("Username or email already exists.")
        raise AuthError(f"Registration failed: {e}")
    finally:
        conn.close()

    return login(username, password)


# ── Login ─────────────────────────────────────────────────────────────────────

def login(username: str, password: str) -> dict:
    """
    Authenticate a user. Returns user dict, raises AuthError on failure.
    Sets the global session on success.
    """
    global _current_user
    username = username.strip()
    password = password.strip()

    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM users WHERE username=? AND is_active=1",
            (username,)
        )
        row = cur.fetchone()

        if not row:
            raise AuthError("Invalid username or password.")

        if not bcrypt.checkpw(password.encode(), row["password_hash"].encode()):
            raise AuthError("Invalid username or password.")

        # Update last login
        conn.execute(
            "UPDATE users SET last_login=? WHERE id=?",
            (datetime.utcnow().isoformat(), row["id"])
        )
        conn.commit()

        user = {
            "id":         row["id"],
            "username":   row["username"],
            "email":      row["email"],
            "created_at": row["created_at"],
            "last_login": datetime.utcnow().isoformat(),
        }
        _current_user = user
        log.info("User logged in: %s (id=%s)", username, row["id"])
        return user

    finally:
        conn.close()


# ── Logout ────────────────────────────────────────────────────────────────────

def logout():
    global _current_user
    if _current_user:
        log.info("User logged out: %s", _current_user["username"])
    _current_user = None


# ── Password change ───────────────────────────────────────────────────────────

def change_password(user_id: int, old_password: str, new_password: str):
    if len(new_password) < 8:
        raise AuthError("New password must be at least 8 characters.")

    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT password_hash FROM users WHERE id=?", (user_id,))
        row = cur.fetchone()
        if not row:
            raise AuthError("User not found.")
        if not bcrypt.checkpw(old_password.encode(), row["password_hash"].encode()):
            raise AuthError("Current password is incorrect.")

        new_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
        conn.execute("UPDATE users SET password_hash=? WHERE id=?", (new_hash, user_id))
        conn.commit()
        log.info("Password changed for user id=%s", user_id)
    finally:
        conn.close()


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_user_by_id(user_id: int) -> dict | None:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, username, email, created_at FROM users WHERE id=?", (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
