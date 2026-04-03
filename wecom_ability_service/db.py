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


def _sqlite_table_sql(db, table_name: str) -> str:
    row = db.execute(
        """
        SELECT sql
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return str((row or {}).get("sql") or "")


def _ensure_sqlite_questionnaire_mobile_type(db) -> None:
    create_sql = _sqlite_table_sql(db, "questionnaire_questions").lower()
    if not create_sql or "'mobile'" in create_sql:
        return
    db.execute("PRAGMA foreign_keys = OFF")
    db.execute(
        """
        CREATE TABLE questionnaire_questions__new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            questionnaire_id INTEGER NOT NULL REFERENCES questionnaires(id) ON DELETE CASCADE,
            type TEXT NOT NULL CHECK (type IN ('single_choice', 'multi_choice', 'textarea', 'mobile')),
            title TEXT NOT NULL,
            required INTEGER NOT NULL DEFAULT 0,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        INSERT INTO questionnaire_questions__new (
            id, questionnaire_id, type, title, required, sort_order, created_at, updated_at
        )
        SELECT id, questionnaire_id, type, title, required, sort_order, created_at, updated_at
        FROM questionnaire_questions
        """
    )
    db.execute("DROP TABLE questionnaire_questions")
    db.execute("ALTER TABLE questionnaire_questions__new RENAME TO questionnaire_questions")
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_questionnaire_questions_questionnaire
        ON questionnaire_questions (questionnaire_id, sort_order, id)
        """
    )
    db.execute("PRAGMA foreign_keys = ON")


def _ensure_sqlite_user_ops_page_tables(db) -> None:
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_user_ops_send_records_created
        ON user_ops_send_records (created_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_user_ops_do_not_disturb_external_active
        ON user_ops_do_not_disturb (external_userid, is_active, updated_at DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_user_ops_do_not_disturb_mobile_active
        ON user_ops_do_not_disturb (mobile, is_active, updated_at DESC)
        """
    )
    send_record_columns = _sqlite_table_columns(db, "user_ops_send_records")
    if send_record_columns and "image_count" not in send_record_columns:
        db.execute("ALTER TABLE user_ops_send_records ADD COLUMN image_count INTEGER NOT NULL DEFAULT 0")


def _init_sqlite(db) -> None:
    schema_path = Path(current_app.root_path) / "schema.sql"
    db.executescript(schema_path.read_text(encoding="utf-8"))
    _ensure_sqlite_questionnaire_mobile_type(db)
    _ensure_sqlite_user_ops_page_tables(db)
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
    questionnaire_submission_columns = _sqlite_table_columns(db, "questionnaire_submissions")
    if questionnaire_submission_columns and "mobile_snapshot" not in questionnaire_submission_columns:
        db.execute("ALTER TABLE questionnaire_submissions ADD COLUMN mobile_snapshot TEXT NOT NULL DEFAULT ''")
    class_term_mapping_columns = _sqlite_table_columns(db, "class_term_tag_mapping")
    if class_term_mapping_columns:
        if "strategy_id" not in class_term_mapping_columns:
            db.execute("ALTER TABLE class_term_tag_mapping ADD COLUMN strategy_id TEXT NOT NULL DEFAULT ''")
        if "group_id" not in class_term_mapping_columns:
            db.execute("ALTER TABLE class_term_tag_mapping ADD COLUMN group_id TEXT NOT NULL DEFAULT ''")
        if "tag_id" not in class_term_mapping_columns:
            db.execute("ALTER TABLE class_term_tag_mapping ADD COLUMN tag_id TEXT NOT NULL DEFAULT ''")
        db.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_class_term_tag_mapping_tag_id_non_empty
            ON class_term_tag_mapping (tag_id)
            WHERE tag_id <> ''
            """
        )
    db.commit()


def _ensure_postgres_user_ops_page_tables(db) -> None:
    db.execute(
        """
        ALTER TABLE IF EXISTS user_ops_send_records
        ADD COLUMN IF NOT EXISTS image_count INTEGER NOT NULL DEFAULT 0
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_user_ops_send_records_created
        ON user_ops_send_records (created_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_user_ops_do_not_disturb_external_active
        ON user_ops_do_not_disturb (external_userid, is_active, updated_at DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_user_ops_do_not_disturb_mobile_active
        ON user_ops_do_not_disturb (mobile, is_active, updated_at DESC)
        """
    )


def _init_postgres(db) -> None:
    db.execute(
        """
        ALTER TABLE IF EXISTS class_term_tag_mapping
        ADD COLUMN IF NOT EXISTS strategy_id TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS class_term_tag_mapping
        ADD COLUMN IF NOT EXISTS group_id TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS class_term_tag_mapping
        ADD COLUMN IF NOT EXISTS tag_id TEXT NOT NULL DEFAULT ''
        """
    )
    schema_path = Path(current_app.root_path) / "schema_postgres.sql"
    db.executescript(schema_path.read_text(encoding="utf-8"))
    _ensure_postgres_user_ops_page_tables(db)
    db.execute("ALTER TABLE questionnaire_questions DROP CONSTRAINT IF EXISTS questionnaire_questions_type_check")
    db.execute(
        """
        ALTER TABLE questionnaire_questions
        ADD CONSTRAINT questionnaire_questions_type_check
        CHECK (type IN ('single_choice', 'multi_choice', 'textarea', 'mobile'))
        """
    )
    db.execute(
        """
        ALTER TABLE questionnaire_submissions
        ADD COLUMN IF NOT EXISTS mobile_snapshot TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE class_term_tag_mapping
        ADD COLUMN IF NOT EXISTS strategy_id TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE class_term_tag_mapping
        ADD COLUMN IF NOT EXISTS group_id TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE class_term_tag_mapping
        ADD COLUMN IF NOT EXISTS tag_id TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_class_term_tag_mapping_tag_id_non_empty
        ON class_term_tag_mapping (tag_id)
        WHERE tag_id <> ''
        """
    )
    db.commit()


def init_db() -> None:
    db = get_db()
    if get_db_backend() == "postgres":
        _init_postgres(db)
    else:
        _init_sqlite(db)


def migrate_db() -> None:
    init_db()


def init_app(app) -> None:
    @app.cli.command("init-db")
    def init_db_command() -> None:
        init_db()
        print("Initialized the database.")
