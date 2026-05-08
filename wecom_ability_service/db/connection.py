from __future__ import annotations

import sqlite3
from pathlib import Path

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


class PostgresCursor:
    """SQLite-cursor-shaped adapter so code written with ``cur = db.cursor()``
    + ``cur.execute(? params)`` + ``cur.fetchone() / fetchall() / lastrowid``
    works against psycopg without rewriting.

    - ``?`` → ``%s`` 自动翻译
    - ``lastrowid`` 通过 ``SELECT lastval()`` 兜底（INSERT 之后自增列）
    - ``rowcount`` 直接转发
    """

    def __init__(self, conn):
        self._conn = conn
        self._cursor = conn.cursor(row_factory=dict_row)
        self._last_was_insert = False
        self.lastrowid = None

    def execute(self, sql, params=None):
        sql_text = sql if isinstance(sql, str) else str(sql)
        translated = _translate_sql(sql_text)
        # ★ params 为空时**不要**传给 psycopg —— 否则它会做 placeholder
        # 解析，把 SQL 里的字面 %（如 LIKE '%abc%'）误认成 placeholder
        # 触发 "got '%3'" 之类错误。
        if params is None or (hasattr(params, "__len__") and len(params) == 0):
            self._cursor.execute(translated)
        elif isinstance(params, dict):
            self._cursor.execute(translated, params)
        else:
            self._cursor.execute(translated, tuple(params))
        upper_head = translated.lstrip().upper()[:6]
        self._last_was_insert = upper_head == "INSERT"
        self.lastrowid = None
        if self._last_was_insert:
            try:
                lv_cursor = self._conn.cursor()
                lv_cursor.execute("SELECT lastval()")
                row = lv_cursor.fetchone()
                lv_cursor.close()
                if row:
                    # row 是 tuple（plain cursor）
                    self.lastrowid = int(row[0])
            except Exception:
                self.lastrowid = None
        return self

    def executemany(self, sql, seq):
        translated = _translate_sql(sql if isinstance(sql, str) else str(sql))
        self._cursor.executemany(translated, list(seq))
        return self

    def executescript(self, script: str) -> None:
        statements = [s.strip() for s in script.split(";") if s.strip()]
        for s in statements:
            self._cursor.execute(s)

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchmany(self, n=None):
        if n is None:
            return self._cursor.fetchmany()
        return self._cursor.fetchmany(int(n))

    def fetchall(self):
        return self._cursor.fetchall()

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def description(self):
        return self._cursor.description

    def close(self):
        try:
            self._cursor.close()
        except Exception:
            pass


class PostgresConnection:
    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return PostgresCursor(self._conn)

    def execute(self, sql: str, params: tuple | list | None = None):
        cursor = self._conn.cursor(row_factory=dict_row)
        translated = _translate_sql(sql)
        # 同 PostgresCursor.execute — params 为空时不传，避免 LIKE '%X%' 中
        # 的字面 % 被 psycopg 当 placeholder 解析失败。
        if params is None or (hasattr(params, "__len__") and len(params) == 0):
            cursor.execute(translated)
        else:
            cursor.execute(translated, tuple(params))
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
