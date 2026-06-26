"""src/api/db.py — SQLite connection helper for FastAPI."""
import sqlite3
from pathlib import Path
from typing import Generator

BASE_DIR = Path(__file__).resolve().parents[2]
DB_PATH  = BASE_DIR / "data" / "nifty100.db"


def get_conn() -> Generator[sqlite3.Connection, None, None]:
    """Yield a SQLite connection; close when done."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def query(conn: sqlite3.Connection, sql: str,
          params: tuple = ()) -> list[dict]:
    """Execute SQL and return list of dicts."""
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def query_one(conn: sqlite3.Connection, sql: str,
              params: tuple = ()) -> dict | None:
    """Execute SQL and return first row as dict or None."""
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None
