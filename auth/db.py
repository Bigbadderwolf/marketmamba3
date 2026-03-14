# auth/db.py
"""
Central SQLite database manager.
All tables for the entire application live here.
"""
import sqlite3, os, logging
from config.constants import DB_PATH

log = logging.getLogger(__name__)


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create all tables on first run."""
    conn = get_conn()
    c = conn.cursor()

    # ── Users ─────────────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT UNIQUE NOT NULL,
            email         TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login    TIMESTAMP,
            is_active     INTEGER DEFAULT 1
        )
    """)

    # ── API Keys (encrypted) ──────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            exchange      TEXT NOT NULL DEFAULT 'binance',
            account_type  TEXT NOT NULL DEFAULT 'spot',
            api_key_enc   BLOB NOT NULL,
            secret_enc    BLOB NOT NULL,
            label         TEXT,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Trade Journal ─────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            symbol          TEXT NOT NULL,
            side            TEXT NOT NULL,
            order_type      TEXT NOT NULL,
            account_type    TEXT NOT NULL DEFAULT 'spot',
            entry_price     REAL NOT NULL,
            exit_price      REAL,
            quantity        REAL NOT NULL,
            leverage        INTEGER DEFAULT 1,
            stop_loss       REAL,
            take_profit     REAL,
            pnl             REAL,
            pnl_pct         REAL,
            rr_ratio        REAL,
            status          TEXT DEFAULT 'open',
            is_simulation   INTEGER DEFAULT 0,
            sim_model       TEXT,
            smc_trigger     TEXT,
            indicator_state TEXT,
            binance_order_id TEXT,
            opened_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            closed_at       TIMESTAMP,
            notes           TEXT
        )
    """)

    # ── Simulation Results ────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS simulation_results (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            symbol          TEXT NOT NULL,
            timeframe       TEXT NOT NULL,
            sim_model       TEXT NOT NULL,
            accuracy_pct    REAL,
            predicted_dir   TEXT,
            actual_dir      TEXT,
            entry_price     REAL,
            optimal_entry   REAL,
            smc_setup       TEXT,
            ran_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Model Accuracy Tracker ────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS model_accuracy (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol      TEXT NOT NULL,
            timeframe   TEXT NOT NULL,
            model_name  TEXT NOT NULL,
            total_runs  INTEGER DEFAULT 0,
            correct     INTEGER DEFAULT 0,
            accuracy    REAL DEFAULT 0.0,
            updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, timeframe, model_name)
        )
    """)

    # ── ML Model Metadata ────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS ml_models (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol      TEXT NOT NULL UNIQUE,
            trained_at  TIMESTAMP,
            updated_at  TIMESTAMP,
            accuracy    REAL,
            n_samples   INTEGER,
            is_ready    INTEGER DEFAULT 0
        )
    """)

    # ── Candle Cache Index ────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS candle_cache (
            symbol      TEXT NOT NULL,
            timeframe   TEXT NOT NULL,
            open_time   INTEGER NOT NULL,
            open        REAL, high REAL, low REAL, close REAL, volume REAL,
            PRIMARY KEY (symbol, timeframe, open_time)
        )
    """)

    conn.commit()
    conn.close()
    log.info("Database initialised: %s", DB_PATH)
