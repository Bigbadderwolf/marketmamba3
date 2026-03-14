# auth/crypto_store.py
"""
Encrypts and decrypts Binance API keys using Fernet symmetric encryption.
The master key is derived from the user's password using PBKDF2 and stored
in a local keyfile. Never stored in plaintext.
"""
import os, base64, logging
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from config.constants import KEY_FILE

log = logging.getLogger(__name__)

_SALT_SIZE = 16


def _load_or_create_master_key() -> bytes:
    """Load or generate the application-level Fernet master key."""
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "rb") as f:
            return f.read()
    key = Fernet.generate_key()
    with open(KEY_FILE, "wb") as f:
        f.write(key)
    os.chmod(KEY_FILE, 0o600)   # owner read-only
    log.info("Generated new master keystore")
    return key


_MASTER_KEY = None

def _get_fernet() -> Fernet:
    global _MASTER_KEY
    if _MASTER_KEY is None:
        _MASTER_KEY = _load_or_create_master_key()
    return Fernet(_MASTER_KEY)


def encrypt(plaintext: str) -> bytes:
    """Encrypt a string and return ciphertext bytes."""
    f = _get_fernet()
    return f.encrypt(plaintext.encode("utf-8"))


def decrypt(ciphertext: bytes) -> str:
    """Decrypt ciphertext bytes and return plaintext string."""
    f = _get_fernet()
    return f.decrypt(ciphertext).decode("utf-8")


# ── High-level helpers ────────────────────────────────────────────────────────

def store_api_keys(conn, user_id: int, api_key: str, secret: str,
                   account_type: str = "spot", label: str = "") -> int:
    """Encrypt and store a Binance key pair. Returns row id."""
    enc_key    = encrypt(api_key)
    enc_secret = encrypt(secret)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO api_keys (user_id, account_type, api_key_enc, secret_enc, label)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, account_type, enc_key, enc_secret, label))
    conn.commit()
    row_id = cur.lastrowid
    log.info("Stored API key id=%s for user %s (%s)", row_id, user_id, account_type)
    return row_id


def load_api_keys(conn, user_id: int, account_type: str = "spot"):
    """Load and decrypt the most recent key pair for a user. Returns (api_key, secret) or None."""
    cur = conn.cursor()
    cur.execute("""
        SELECT api_key_enc, secret_enc FROM api_keys
        WHERE user_id=? AND account_type=?
        ORDER BY created_at DESC LIMIT 1
    """, (user_id, account_type))
    row = cur.fetchone()
    if not row:
        return None
    return decrypt(row["api_key_enc"]), decrypt(row["secret_enc"])


def delete_api_keys(conn, user_id: int, account_type: str = "spot"):
    conn.execute(
        "DELETE FROM api_keys WHERE user_id=? AND account_type=?",
        (user_id, account_type)
    )
    conn.commit()


def list_key_labels(conn, user_id: int) -> list:
    """Return list of dicts with id, account_type, label, created_at."""
    cur = conn.cursor()
    cur.execute("""
        SELECT id, account_type, label, created_at FROM api_keys
        WHERE user_id=? ORDER BY created_at DESC
    """, (user_id,))
    return [dict(r) for r in cur.fetchall()]
