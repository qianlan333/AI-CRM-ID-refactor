from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from flask import current_app, g

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - sqlite mode does not require psycopg locally
    psycopg = None
    dict_row = None


def dict_factory(cursor: sqlite3.Cursor, row: tuple) -> dict:
    return {column[0]: row[idx] for idx, column in enumerate(cursor.description)}


def get_db_backend() -> str:
    database_url = str(current_app.config.get("DATABASE_URL", "") or "").strip()
    return "postgres" if database_url else "sqlite"


def _translate_sql(sql: str) -> str:
    return sql.replace("?", "%s")


class PostgresConnection:
    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql: str, params: tuple | list | None = None):
        cursor = self._conn.cursor(row_factory=dict_row)
        cursor.execute(_translate_sql(sql), tuple(params or ()))
        return cursor

    def executemany(self, sql: str, seq_of_params: list[tuple] | list[list]):
        cursor = self._conn.cursor(row_factory=dict_row)
        cursor.executemany(_translate_sql(sql), seq_of_params)
        return cursor

    def executescript(self, script: str) -> None:
        cursor = self._conn.cursor()
        statements = [statement.strip() for statement in script.split(";") if statement.strip()]
        for statement in statements:
            cursor.execute(statement)
        cursor.close()

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


def _connect_postgres():
    if psycopg is None:
        raise RuntimeError("psycopg is required for PostgreSQL mode. Install requirements first.")
    conn = psycopg.connect(current_app.config["DATABASE_URL"], autocommit=False)
    return PostgresConnection(conn)


def _connect_sqlite():
    db_path = Path(current_app.config["DATABASE_PATH"])
    db_path.parent.mkdir(parents=True, exist_ok=True)
    busy_timeout_ms = int(current_app.config.get("SQLITE_BUSY_TIMEOUT_MS", 5000))
    conn = sqlite3.connect(db_path, timeout=max(busy_timeout_ms / 1000, 1))
    conn.row_factory = dict_factory
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute(f"PRAGMA busy_timeout = {busy_timeout_ms}")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    if "db" not in g:
        if get_db_backend() == "postgres":
            g.db = _connect_postgres()
        else:
            g.db = _connect_sqlite()
    return g.db


def close_db(_: object | None = None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _sqlite_table_columns(db, table_name: str) -> set[str]:
    return {row["name"] for row in db.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _init_sqlite(db) -> None:
    schema_path = Path(current_app.root_path) / "schema.sql"
    db.executescript(schema_path.read_text(encoding="utf-8"))
    columns = _sqlite_table_columns(db, "archived_messages")
    if "chat_type" not in columns:
        db.execute("ALTER TABLE archived_messages ADD COLUMN chat_type TEXT NOT NULL DEFAULT 'private'")
    contact_columns = _sqlite_table_columns(db, "contacts")
    if contact_columns:
        if "description" not in contact_columns:
            db.execute("ALTER TABLE contacts ADD COLUMN description TEXT")
        if "remark" not in contact_columns:
            db.execute("ALTER TABLE contacts ADD COLUMN remark TEXT")
    batch_columns = _sqlite_table_columns(db, "message_batches")
    if batch_columns and "acked_by" not in batch_columns:
        db.execute("ALTER TABLE message_batches ADD COLUMN acked_by TEXT")
    db.commit()


def _init_postgres(db) -> None:
    schema_path = Path(current_app.root_path) / "schema_postgres.sql"
    db.executescript(schema_path.read_text(encoding="utf-8"))
    db.commit()


def init_db() -> None:
    db = get_db()
    if get_db_backend() == "postgres":
        _init_postgres(db)
    else:
        _init_sqlite(db)


def init_app(app) -> None:
    @app.cli.command("init-db")
    def init_db_command() -> None:
        init_db()
        print("Initialized the database.")
