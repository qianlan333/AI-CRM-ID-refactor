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


def _ensure_sqlite_questionnaire_external_push_tables(db) -> None:
    questionnaire_columns = _sqlite_table_columns(db, "questionnaires")
    if questionnaire_columns:
        if "external_push_enabled" not in questionnaire_columns:
            db.execute("ALTER TABLE questionnaires ADD COLUMN external_push_enabled INTEGER NOT NULL DEFAULT 0")
        if "external_push_url" not in questionnaire_columns:
            db.execute("ALTER TABLE questionnaires ADD COLUMN external_push_url TEXT NOT NULL DEFAULT ''")
        db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_questionnaires_external_push_enabled
            ON questionnaires (external_push_enabled)
            """
        )

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS questionnaire_external_push_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            questionnaire_id INTEGER NOT NULL REFERENCES questionnaires(id) ON DELETE CASCADE,
            questionnaire_title_snapshot TEXT NOT NULL DEFAULT '',
            submission_record_id INTEGER NOT NULL REFERENCES questionnaire_submissions(id) ON DELETE CASCADE,
            retry_from_log_id INTEGER REFERENCES questionnaire_external_push_logs(id) ON DELETE SET NULL,
            retry_attempt INTEGER NOT NULL DEFAULT 0,
            user_id TEXT NOT NULL DEFAULT '',
            target_url TEXT NOT NULL DEFAULT '',
            request_payload TEXT NOT NULL DEFAULT '{}',
            response_status_code INTEGER,
            response_body TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'failed',
            failure_reason TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_questionnaire_external_push_logs_questionnaire
        ON questionnaire_external_push_logs (questionnaire_id, created_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_questionnaire_external_push_logs_status
        ON questionnaire_external_push_logs (status, created_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_questionnaire_external_push_logs_submission
        ON questionnaire_external_push_logs (submission_record_id)
        """
    )
    push_log_columns = _sqlite_table_columns(db, "questionnaire_external_push_logs")
    if push_log_columns and "retry_from_log_id" not in push_log_columns:
        db.execute("ALTER TABLE questionnaire_external_push_logs ADD COLUMN retry_from_log_id INTEGER")
    if push_log_columns and "retry_attempt" not in push_log_columns:
        db.execute("ALTER TABLE questionnaire_external_push_logs ADD COLUMN retry_attempt INTEGER NOT NULL DEFAULT 0")
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_questionnaire_external_push_logs_retry_from
        ON questionnaire_external_push_logs (retry_from_log_id, created_at DESC, id DESC)
        """
    )


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
    if send_record_columns and "task_results_json" not in send_record_columns:
        db.execute("ALTER TABLE user_ops_send_records ADD COLUMN task_results_json TEXT NOT NULL DEFAULT '[]'")
    if send_record_columns and "last_status_sync_at" not in send_record_columns:
        db.execute("ALTER TABLE user_ops_send_records ADD COLUMN last_status_sync_at TEXT")


def _ensure_sqlite_customer_value_segment_tables(db) -> None:
    current_columns = _sqlite_table_columns(db, "customer_value_segment_current")
    if current_columns:
        if "submission_id" not in current_columns:
            db.execute("ALTER TABLE customer_value_segment_current ADD COLUMN submission_id INTEGER")
        if "matched_question_ids_json" not in current_columns:
            db.execute(
                "ALTER TABLE customer_value_segment_current ADD COLUMN matched_question_ids_json TEXT NOT NULL DEFAULT '[]'"
            )
        if "evaluated_at" not in current_columns:
            db.execute(
                "ALTER TABLE customer_value_segment_current ADD COLUMN evaluated_at TEXT NOT NULL DEFAULT ''"
            )

    history_columns = _sqlite_table_columns(db, "customer_value_segment_history")
    if history_columns:
        if "submission_id" not in history_columns:
            db.execute("ALTER TABLE customer_value_segment_history ADD COLUMN submission_id INTEGER")
        if "matched_question_ids_json" not in history_columns:
            db.execute(
                "ALTER TABLE customer_value_segment_history ADD COLUMN matched_question_ids_json TEXT NOT NULL DEFAULT '[]'"
            )
        if "evaluated_at" not in history_columns:
            db.execute(
                "ALTER TABLE customer_value_segment_history ADD COLUMN evaluated_at TEXT NOT NULL DEFAULT ''"
            )


def _rebuild_sqlite_customer_marketing_state_current_table(db) -> None:
    current_columns = _sqlite_table_columns(db, "customer_marketing_state_current")
    if not current_columns:
        return
    db.execute("DROP TABLE IF EXISTS customer_marketing_state_current__new")
    db.execute(
        """
        CREATE TABLE customer_marketing_state_current__new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id INTEGER REFERENCES people(id) ON DELETE SET NULL,
            external_userid TEXT NOT NULL DEFAULT '',
            automation_key TEXT NOT NULL DEFAULT 'signup_conversion_v1',
            main_stage TEXT NOT NULL DEFAULT 'pending',
            sub_stage TEXT NOT NULL DEFAULT '',
            activated INTEGER NOT NULL DEFAULT 0,
            converted INTEGER NOT NULL DEFAULT 0,
            eligible_for_conversion INTEGER NOT NULL DEFAULT 0,
            lifecycle_status TEXT NOT NULL DEFAULT 'idle',
            last_activation_at TEXT NOT NULL DEFAULT '',
            last_conversion_marked_at TEXT NOT NULL DEFAULT '',
            last_message_at TEXT NOT NULL DEFAULT '',
            last_batch_id INTEGER REFERENCES message_batches(id) ON DELETE SET NULL,
            last_batch_status TEXT NOT NULL DEFAULT '',
            last_batch_window_start TEXT NOT NULL DEFAULT '',
            last_batch_window_end TEXT NOT NULL DEFAULT '',
            last_trigger_message_at TEXT NOT NULL DEFAULT '',
            entered_at TEXT,
            exited_at TEXT,
            exit_reason TEXT NOT NULL DEFAULT '',
            state_payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        f"""
        INSERT INTO customer_marketing_state_current__new (
            id,
            person_id,
            external_userid,
            automation_key,
            main_stage,
            sub_stage,
            activated,
            converted,
            eligible_for_conversion,
            lifecycle_status,
            last_activation_at,
            last_conversion_marked_at,
            last_message_at,
            last_batch_id,
            last_batch_status,
            last_batch_window_start,
            last_batch_window_end,
            last_trigger_message_at,
            entered_at,
            exited_at,
            exit_reason,
            state_payload_json,
            created_at,
            updated_at
        )
        SELECT
            id,
            {"person_id" if "person_id" in current_columns else "NULL"} AS person_id,
            CASE
                WHEN substr(COALESCE(external_userid, ''), 1, 7) = 'person:' THEN ''
                ELSE COALESCE(external_userid, '')
            END AS external_userid,
            {"automation_key" if "automation_key" in current_columns else "'signup_conversion_v1'"} AS automation_key,
            {"main_stage" if "main_stage" in current_columns else "'pending'"} AS main_stage,
            {"sub_stage" if "sub_stage" in current_columns else "''"} AS sub_stage,
            {"activated" if "activated" in current_columns else "0"} AS activated,
            {"converted" if "converted" in current_columns else "0"} AS converted,
            {"eligible_for_conversion" if "eligible_for_conversion" in current_columns else "0"} AS eligible_for_conversion,
            {"lifecycle_status" if "lifecycle_status" in current_columns else "'idle'"} AS lifecycle_status,
            {"last_activation_at" if "last_activation_at" in current_columns else "''"} AS last_activation_at,
            {"last_conversion_marked_at" if "last_conversion_marked_at" in current_columns else "''"} AS last_conversion_marked_at,
            {"last_message_at" if "last_message_at" in current_columns else "''"} AS last_message_at,
            {"last_batch_id" if "last_batch_id" in current_columns else "NULL"} AS last_batch_id,
            {"last_batch_status" if "last_batch_status" in current_columns else "''"} AS last_batch_status,
            {"last_batch_window_start" if "last_batch_window_start" in current_columns else "''"} AS last_batch_window_start,
            {"last_batch_window_end" if "last_batch_window_end" in current_columns else "''"} AS last_batch_window_end,
            {"last_trigger_message_at" if "last_trigger_message_at" in current_columns else "''"} AS last_trigger_message_at,
            {"entered_at" if "entered_at" in current_columns else "NULL"} AS entered_at,
            {"exited_at" if "exited_at" in current_columns else "NULL"} AS exited_at,
            {"exit_reason" if "exit_reason" in current_columns else "''"} AS exit_reason,
            {"state_payload_json" if "state_payload_json" in current_columns else "'{}'"} AS state_payload_json,
            {"created_at" if "created_at" in current_columns else "CURRENT_TIMESTAMP"} AS created_at,
            {"updated_at" if "updated_at" in current_columns else "CURRENT_TIMESTAMP"} AS updated_at
        FROM customer_marketing_state_current
        """
    )
    db.execute(
        """
        DELETE FROM customer_marketing_state_current__new
        WHERE id IN (
            SELECT id
            FROM (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY person_id
                        ORDER BY updated_at DESC, id DESC
                    ) AS row_number
                FROM customer_marketing_state_current__new
                WHERE person_id IS NOT NULL
            ) AS ranked
            WHERE row_number > 1
        )
        """
    )
    db.execute("DROP TABLE customer_marketing_state_current")
    db.execute("ALTER TABLE customer_marketing_state_current__new RENAME TO customer_marketing_state_current")
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_customer_marketing_state_current_external_userid
        ON customer_marketing_state_current (external_userid)
        """
    )
    db.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_customer_marketing_state_current_person_id_non_null
        ON customer_marketing_state_current (person_id)
        WHERE person_id IS NOT NULL
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_customer_marketing_state_current_main_stage
        ON customer_marketing_state_current (main_stage)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_customer_marketing_state_current_sub_stage
        ON customer_marketing_state_current (sub_stage)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_customer_marketing_state_current_eligible_for_conversion
        ON customer_marketing_state_current (eligible_for_conversion)
        """
    )


def _ensure_sqlite_customer_marketing_state_tables(db) -> None:
    current_columns = _sqlite_table_columns(db, "customer_marketing_state_current")
    if current_columns:
        create_sql = _sqlite_table_sql(db, "customer_marketing_state_current").upper()
        if "EXTERNAL_USERID TEXT NOT NULL UNIQUE" in create_sql:
            _rebuild_sqlite_customer_marketing_state_current_table(db)
            current_columns = _sqlite_table_columns(db, "customer_marketing_state_current")
        if "person_id" not in current_columns:
            db.execute(
                "ALTER TABLE customer_marketing_state_current ADD COLUMN person_id INTEGER REFERENCES people(id) ON DELETE SET NULL"
            )
        if "activated" not in current_columns:
            db.execute(
                "ALTER TABLE customer_marketing_state_current ADD COLUMN activated INTEGER NOT NULL DEFAULT 0"
            )
        if "converted" not in current_columns:
            db.execute(
                "ALTER TABLE customer_marketing_state_current ADD COLUMN converted INTEGER NOT NULL DEFAULT 0"
            )
        if "last_activation_at" not in current_columns:
            db.execute(
                "ALTER TABLE customer_marketing_state_current ADD COLUMN last_activation_at TEXT NOT NULL DEFAULT ''"
            )
        if "last_conversion_marked_at" not in current_columns:
            db.execute(
                "ALTER TABLE customer_marketing_state_current ADD COLUMN last_conversion_marked_at TEXT NOT NULL DEFAULT ''"
            )
        if "last_message_at" not in current_columns:
            db.execute(
                "ALTER TABLE customer_marketing_state_current ADD COLUMN last_message_at TEXT NOT NULL DEFAULT ''"
            )
        db.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_customer_marketing_state_current_person_id_non_null
            ON customer_marketing_state_current (person_id)
            WHERE person_id IS NOT NULL
            """
        )
        db.execute(
            """
            UPDATE customer_marketing_state_current
            SET external_userid = ''
            WHERE substr(COALESCE(external_userid, ''), 1, 7) = 'person:'
            """
        )

    history_columns = _sqlite_table_columns(db, "customer_marketing_state_history")
    if history_columns:
        if "person_id" not in history_columns:
            db.execute(
                "ALTER TABLE customer_marketing_state_history ADD COLUMN person_id INTEGER REFERENCES people(id) ON DELETE SET NULL"
            )
        if "activated" not in history_columns:
            db.execute(
                "ALTER TABLE customer_marketing_state_history ADD COLUMN activated INTEGER NOT NULL DEFAULT 0"
            )
        if "converted" not in history_columns:
            db.execute(
                "ALTER TABLE customer_marketing_state_history ADD COLUMN converted INTEGER NOT NULL DEFAULT 0"
            )
        if "exit_reason" not in history_columns:
            db.execute(
                "ALTER TABLE customer_marketing_state_history ADD COLUMN exit_reason TEXT NOT NULL DEFAULT ''"
            )
        if "last_activation_at" not in history_columns:
            db.execute(
                "ALTER TABLE customer_marketing_state_history ADD COLUMN last_activation_at TEXT NOT NULL DEFAULT ''"
            )
        if "last_conversion_marked_at" not in history_columns:
            db.execute(
                "ALTER TABLE customer_marketing_state_history ADD COLUMN last_conversion_marked_at TEXT NOT NULL DEFAULT ''"
            )
        if "last_message_at" not in history_columns:
            db.execute(
                "ALTER TABLE customer_marketing_state_history ADD COLUMN last_message_at TEXT NOT NULL DEFAULT ''"
            )
        db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_customer_marketing_state_history_person_id
            ON customer_marketing_state_history (person_id, recorded_at DESC)
            """
        )
        db.execute(
            """
            UPDATE customer_marketing_state_history
            SET external_userid = ''
            WHERE substr(COALESCE(external_userid, ''), 1, 7) = 'person:'
            """
        )


def _ensure_sqlite_automation_conversion_tables(db) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_channel (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_code TEXT NOT NULL UNIQUE,
            channel_name TEXT NOT NULL DEFAULT '',
            qr_url TEXT NOT NULL DEFAULT '',
            qr_ticket TEXT NOT NULL DEFAULT '',
            scene_value TEXT NOT NULL DEFAULT '',
            welcome_message TEXT NOT NULL DEFAULT '',
            auto_accept_friend INTEGER NOT NULL DEFAULT 0,
            owner_staff_id TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'inactive',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    channel_columns = _sqlite_table_columns(db, "automation_channel")
    if "welcome_message" not in channel_columns:
        db.execute("ALTER TABLE automation_channel ADD COLUMN welcome_message TEXT NOT NULL DEFAULT ''")
    if "auto_accept_friend" not in channel_columns:
        db.execute("ALTER TABLE automation_channel ADD COLUMN auto_accept_friend INTEGER NOT NULL DEFAULT 0")
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_member (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            external_contact_id TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL DEFAULT '',
            master_customer_id INTEGER REFERENCES people(id) ON DELETE SET NULL,
            owner_staff_id TEXT NOT NULL DEFAULT '',
            in_pool INTEGER NOT NULL DEFAULT 0,
            current_pool TEXT NOT NULL DEFAULT 'removed',
            follow_type TEXT NOT NULL DEFAULT '',
            activation_status TEXT NOT NULL DEFAULT 'unknown',
            questionnaire_status TEXT NOT NULL DEFAULT 'pending',
            questionnaire_result TEXT NOT NULL DEFAULT 'unknown',
            decision_source TEXT NOT NULL DEFAULT 'system',
            source_type TEXT NOT NULL DEFAULT 'system',
            source_channel_id INTEGER REFERENCES automation_channel(id) ON DELETE SET NULL,
            last_active_pool TEXT NOT NULL DEFAULT '',
            joined_at TEXT NOT NULL DEFAULT '',
            last_ai_push_at TEXT NOT NULL DEFAULT '',
            ai_cooldown_until TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_event (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL REFERENCES automation_member(id) ON DELETE CASCADE,
            action TEXT NOT NULL DEFAULT '',
            operator_type TEXT NOT NULL DEFAULT 'system',
            operator_id TEXT NOT NULL DEFAULT '',
            before_snapshot TEXT NOT NULL DEFAULT '{}',
            after_snapshot TEXT NOT NULL DEFAULT '{}',
            remark TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_ai_push_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL REFERENCES automation_member(id) ON DELETE CASCADE,
            scene TEXT NOT NULL DEFAULT 'sidebar_script',
            request_payload TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'accepted',
            request_id TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            pushed_at TEXT NOT NULL DEFAULT '',
            cooldown_until TEXT NOT NULL DEFAULT ''
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_message_activity_sync_run (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trigger_source TEXT NOT NULL DEFAULT 'manual',
            operator_type TEXT NOT NULL DEFAULT 'system',
            operator_id TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'success',
            candidate_count INTEGER NOT NULL DEFAULT 0,
            matched_count INTEGER NOT NULL DEFAULT 0,
            updated_count INTEGER NOT NULL DEFAULT 0,
            skipped_ambiguous_count INTEGER NOT NULL DEFAULT 0,
            skipped_unmatched_count INTEGER NOT NULL DEFAULT 0,
            skipped_missing_phone_count INTEGER NOT NULL DEFAULT 0,
            focus_count INTEGER NOT NULL DEFAULT 0,
            normal_count INTEGER NOT NULL DEFAULT 0,
            error_message TEXT NOT NULL DEFAULT '',
            summary_json TEXT NOT NULL DEFAULT '{}',
            started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_message_activity_sync_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL REFERENCES automation_message_activity_sync_run(id) ON DELETE CASCADE,
            member_id INTEGER REFERENCES automation_member(id) ON DELETE CASCADE,
            external_contact_id TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL DEFAULT '',
            phone_prefix3 TEXT NOT NULL DEFAULT '',
            phone_last4 TEXT NOT NULL DEFAULT '',
            phone_match_key TEXT NOT NULL DEFAULT '',
            message_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'updated',
            detail TEXT NOT NULL DEFAULT '',
            before_snapshot TEXT NOT NULL DEFAULT '{}',
            after_snapshot TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_focus_send_batch (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stage_key TEXT NOT NULL DEFAULT '',
            pool_key TEXT NOT NULL DEFAULT '',
            operator_type TEXT NOT NULL DEFAULT 'user',
            operator_id TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            total_count INTEGER NOT NULL DEFAULT 0,
            sent_count INTEGER NOT NULL DEFAULT 0,
            failed_count INTEGER NOT NULL DEFAULT 0,
            skipped_count INTEGER NOT NULL DEFAULT 0,
            cancelled_count INTEGER NOT NULL DEFAULT 0,
            next_run_at TEXT NOT NULL DEFAULT '',
            last_run_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TEXT NOT NULL DEFAULT ''
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_focus_send_batch_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER NOT NULL REFERENCES automation_focus_send_batch(id) ON DELETE CASCADE,
            member_id INTEGER REFERENCES automation_member(id) ON DELETE SET NULL,
            external_contact_id TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL DEFAULT '',
            position_index INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending',
            detail TEXT NOT NULL DEFAULT '',
            result_payload TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            started_at TEXT NOT NULL DEFAULT '',
            finished_at TEXT NOT NULL DEFAULT ''
        )
        """
    )
    db.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_member_external_non_empty
        ON automation_member (external_contact_id)
        WHERE external_contact_id <> ''
        """
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_automation_member_phone ON automation_member (phone)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_automation_member_pool ON automation_member (current_pool, in_pool)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_automation_member_owner ON automation_member (owner_staff_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_automation_member_channel ON automation_member (source_channel_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_automation_event_member_created ON automation_event (member_id, created_at DESC, id DESC)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_automation_event_action_created ON automation_event (action, created_at DESC, id DESC)")
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_ai_push_log_member_pushed ON automation_ai_push_log (member_id, pushed_at DESC, id DESC)"
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_automation_ai_push_log_status ON automation_ai_push_log (status, pushed_at DESC, id DESC)")
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_message_activity_sync_run_finished ON automation_message_activity_sync_run (finished_at DESC, id DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_message_activity_sync_run_status ON automation_message_activity_sync_run (status, finished_at DESC, id DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_message_activity_sync_item_run ON automation_message_activity_sync_item (run_id, id ASC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_message_activity_sync_item_status ON automation_message_activity_sync_item (status, created_at DESC, id DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_message_activity_sync_item_last4 ON automation_message_activity_sync_item (phone_last4, created_at DESC, id DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_message_activity_sync_item_match_key ON automation_message_activity_sync_item (phone_match_key, created_at DESC, id DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_focus_send_batch_stage_status ON automation_focus_send_batch (stage_key, status, id DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_focus_send_batch_due ON automation_focus_send_batch (status, next_run_at, id ASC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_focus_send_batch_item_batch_position ON automation_focus_send_batch_item (batch_id, position_index ASC, id ASC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_focus_send_batch_item_status ON automation_focus_send_batch_item (status, updated_at DESC, id DESC)"
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_automation_channel_status ON automation_channel (status, updated_at DESC, id DESC)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_automation_channel_scene ON automation_channel (scene_value)")


def _init_sqlite(db) -> None:
    schema_path = Path(current_app.root_path) / "schema.sql"
    db.executescript(schema_path.read_text(encoding="utf-8"))
    _ensure_sqlite_questionnaire_mobile_type(db)
    _ensure_sqlite_questionnaire_external_push_tables(db)
    _ensure_sqlite_user_ops_page_tables(db)
    _ensure_sqlite_customer_value_segment_tables(db)
    _ensure_sqlite_customer_marketing_state_tables(db)
    _ensure_sqlite_automation_conversion_tables(db)
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
    message_activity_sync_item_columns = _sqlite_table_columns(db, "automation_message_activity_sync_item")
    if message_activity_sync_item_columns:
        if "phone_prefix3" not in message_activity_sync_item_columns:
            db.execute("ALTER TABLE automation_message_activity_sync_item ADD COLUMN phone_prefix3 TEXT NOT NULL DEFAULT ''")
        if "phone_match_key" not in message_activity_sync_item_columns:
            db.execute("ALTER TABLE automation_message_activity_sync_item ADD COLUMN phone_match_key TEXT NOT NULL DEFAULT ''")
        db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_automation_message_activity_sync_item_match_key
            ON automation_message_activity_sync_item (phone_match_key, created_at DESC, id DESC)
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
        ALTER TABLE IF EXISTS automation_message_activity_sync_item
        ADD COLUMN IF NOT EXISTS phone_prefix3 TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_message_activity_sync_item
        ADD COLUMN IF NOT EXISTS phone_match_key TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_message_activity_sync_item_match_key
        ON automation_message_activity_sync_item (phone_match_key, created_at DESC, id DESC)
        """
    )


def _ensure_postgres_questionnaire_external_push_tables(db) -> None:
    db.execute(
        """
        ALTER TABLE IF EXISTS questionnaires
        ADD COLUMN IF NOT EXISTS external_push_enabled BOOLEAN NOT NULL DEFAULT FALSE
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS questionnaires
        ADD COLUMN IF NOT EXISTS external_push_url TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_questionnaires_external_push_enabled
        ON questionnaires (external_push_enabled)
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS questionnaire_external_push_logs (
            id BIGSERIAL PRIMARY KEY,
            questionnaire_id BIGINT NOT NULL REFERENCES questionnaires(id) ON DELETE CASCADE,
            questionnaire_title_snapshot TEXT NOT NULL DEFAULT '',
            submission_record_id BIGINT NOT NULL REFERENCES questionnaire_submissions(id) ON DELETE CASCADE,
            retry_from_log_id BIGINT REFERENCES questionnaire_external_push_logs(id) ON DELETE SET NULL,
            retry_attempt INTEGER NOT NULL DEFAULT 0,
            user_id TEXT NOT NULL DEFAULT '',
            target_url TEXT NOT NULL DEFAULT '',
            request_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            response_status_code INTEGER,
            response_body TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'failed',
            failure_reason TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_questionnaire_external_push_logs_questionnaire
        ON questionnaire_external_push_logs (questionnaire_id, created_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_questionnaire_external_push_logs_status
        ON questionnaire_external_push_logs (status, created_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_questionnaire_external_push_logs_submission
        ON questionnaire_external_push_logs (submission_record_id)
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS questionnaire_external_push_logs
        ADD COLUMN IF NOT EXISTS retry_from_log_id BIGINT REFERENCES questionnaire_external_push_logs(id) ON DELETE SET NULL
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS questionnaire_external_push_logs
        ADD COLUMN IF NOT EXISTS retry_attempt INTEGER NOT NULL DEFAULT 0
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_questionnaire_external_push_logs_retry_from
        ON questionnaire_external_push_logs (retry_from_log_id, created_at DESC, id DESC)
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS user_ops_send_records
        ADD COLUMN IF NOT EXISTS task_results_json JSONB NOT NULL DEFAULT '[]'::jsonb
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS user_ops_send_records
        ADD COLUMN IF NOT EXISTS last_status_sync_at TIMESTAMPTZ
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


def _ensure_postgres_customer_value_segment_tables(db) -> None:
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_value_segment_current
        ADD COLUMN IF NOT EXISTS submission_id BIGINT REFERENCES questionnaire_submissions(id) ON DELETE SET NULL
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_value_segment_current
        ADD COLUMN IF NOT EXISTS matched_question_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_value_segment_current
        ADD COLUMN IF NOT EXISTS evaluated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_value_segment_history
        ADD COLUMN IF NOT EXISTS submission_id BIGINT REFERENCES questionnaire_submissions(id) ON DELETE SET NULL
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_value_segment_history
        ADD COLUMN IF NOT EXISTS matched_question_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_value_segment_history
        ADD COLUMN IF NOT EXISTS evaluated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        """
    )


def _ensure_postgres_customer_marketing_state_tables(db) -> None:
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_marketing_state_current
        ALTER COLUMN external_userid SET DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_marketing_state_history
        ALTER COLUMN external_userid SET DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_marketing_state_current
        DROP CONSTRAINT IF EXISTS customer_marketing_state_current_external_userid_key
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_marketing_state_current
        ADD COLUMN IF NOT EXISTS person_id BIGINT REFERENCES people(id) ON DELETE SET NULL
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_marketing_state_current
        ADD COLUMN IF NOT EXISTS activated BOOLEAN NOT NULL DEFAULT FALSE
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_marketing_state_current
        ADD COLUMN IF NOT EXISTS converted BOOLEAN NOT NULL DEFAULT FALSE
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_marketing_state_current
        ADD COLUMN IF NOT EXISTS last_activation_at TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_marketing_state_current
        ADD COLUMN IF NOT EXISTS last_conversion_marked_at TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_marketing_state_current
        ADD COLUMN IF NOT EXISTS last_message_at TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_customer_marketing_state_current_person_id_non_null
        ON customer_marketing_state_current (person_id)
        WHERE person_id IS NOT NULL
        """
    )
    db.execute(
        """
        UPDATE customer_marketing_state_current
        SET external_userid = ''
        WHERE substr(COALESCE(external_userid, ''), 1, 7) = 'person:'
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_marketing_state_history
        ADD COLUMN IF NOT EXISTS person_id BIGINT REFERENCES people(id) ON DELETE SET NULL
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_marketing_state_history
        ADD COLUMN IF NOT EXISTS activated BOOLEAN NOT NULL DEFAULT FALSE
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_marketing_state_history
        ADD COLUMN IF NOT EXISTS converted BOOLEAN NOT NULL DEFAULT FALSE
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_marketing_state_history
        ADD COLUMN IF NOT EXISTS exit_reason TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_marketing_state_history
        ADD COLUMN IF NOT EXISTS last_activation_at TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_marketing_state_history
        ADD COLUMN IF NOT EXISTS last_conversion_marked_at TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_marketing_state_history
        ADD COLUMN IF NOT EXISTS last_message_at TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_customer_marketing_state_history_person_id
        ON customer_marketing_state_history (person_id, recorded_at DESC)
        """
    )
    db.execute(
        """
        UPDATE customer_marketing_state_history
        SET external_userid = ''
        WHERE substr(COALESCE(external_userid, ''), 1, 7) = 'person:'
        """
    )


def _init_postgres(db) -> None:
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_channel
        ADD COLUMN IF NOT EXISTS welcome_message TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_channel
        ADD COLUMN IF NOT EXISTS auto_accept_friend BOOLEAN NOT NULL DEFAULT FALSE
        """
    )
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
    _ensure_postgres_questionnaire_external_push_tables(db)
    _ensure_postgres_user_ops_page_tables(db)
    _ensure_postgres_customer_value_segment_tables(db)
    _ensure_postgres_customer_marketing_state_tables(db)
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
