"""SQLite access. One connection per request; foreign keys on. Requires SQLite 3.38+ (JSON functions built in)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from flask import current_app, g

SCHEMA = Path(__file__).parent / "schema" / "redgrid_schema.sql"
MIN_SQLITE = (3, 38, 0)


def check_sqlite_version() -> None:
    if sqlite3.sqlite_version_info < MIN_SQLITE:
        raise RuntimeError(f"SQLite {'.'.join(map(str, MIN_SQLITE))}+ is required, found {sqlite3.sqlite_version}")


def connect(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(path, detect_types=0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exc=None) -> None:
    con = g.pop("db", None)
    if con is not None:
        con.close()


def init_db(path: str) -> None:
    """Create the schema and seed data (drops an existing database file)."""
    check_sqlite_version()
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        p.unlink()
    con = connect(path)
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    con.commit()
    con.close()
