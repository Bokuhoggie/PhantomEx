"""
SQLite persistence layer for PhantomEx.
Handles agents, portfolios, trades, and sessions.
"""

import sqlite3
import os
from contextlib import contextmanager

DB_PATH = os.environ.get("PHANTOMEX_DB", "data/phantomex.db")


def get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextmanager
def get_db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS agents (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                model       TEXT NOT NULL,
                mode        TEXT NOT NULL DEFAULT 'autonomous',
                allowance   REAL NOT NULL DEFAULT 10000.0,
                goal        TEXT NOT NULL DEFAULT '',
                created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                active      INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS portfolios (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id    TEXT NOT NULL REFERENCES agents(id),
                symbol      TEXT NOT NULL,
                quantity    REAL NOT NULL DEFAULT 0.0,
                avg_cost    REAL NOT NULL DEFAULT 0.0,
                updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(agent_id, symbol)
            );

            CREATE TABLE IF NOT EXISTS trades (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id    TEXT NOT NULL REFERENCES agents(id),
                symbol      TEXT NOT NULL,
                side        TEXT NOT NULL,
                quantity    REAL NOT NULL,
                price       REAL NOT NULL,
                total       REAL NOT NULL,
                reasoning   TEXT,
                mode        TEXT NOT NULL DEFAULT 'paper',
                timestamp   TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                mode        TEXT NOT NULL DEFAULT 'live',
                started_at  TEXT NOT NULL DEFAULT (datetime('now')),
                ended_at    TEXT,
                active      INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS price_snapshots (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol      TEXT NOT NULL,
                price       REAL NOT NULL,
                volume_24h  REAL,
                change_24h  REAL,
                timestamp   TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)
        # Migrations for existing databases
        conn.executescript("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_portfolios_agent_symbol
                ON portfolios(agent_id, symbol);
        """)
        # Add goal column to agents if it doesn't exist yet
        cols = [r[1] for r in conn.execute("PRAGMA table_info(agents)").fetchall()]
        if "goal" not in cols:
            conn.execute("ALTER TABLE agents ADD COLUMN goal TEXT NOT NULL DEFAULT ''")
        if "trade_interval" not in cols:
            conn.execute("ALTER TABLE agents ADD COLUMN trade_interval REAL NOT NULL DEFAULT 60.0")
    print("[db] Database initialized.")
