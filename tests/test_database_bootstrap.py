from __future__ import annotations

import os
import re
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
import yaml
from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy.exc import SQLAlchemyError

from scripts.ops.bootstrap_database import (
    BASELINE_PATH,
    DatabaseBootstrapRefused,
    _psycopg_url,
    _safe_target,
    install_or_upgrade_database,
    redact_sensitive_text,
)


ROOT = Path(__file__).resolve().parents[1]
CREATE_TABLE_PATTERN = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:public\.)?([a-zA-Z_][a-zA-Z0-9_]*)",
    re.IGNORECASE,
)


def test_test_suite_uses_the_versioned_database_baseline() -> None:
    conftest_source = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    baseline_source = BASELINE_PATH.read_text(encoding="utf-8")

    assert "install_or_upgrade_database(url)" in conftest_source
    assert "CREATE TABLE" not in conftest_source
    assert len(CREATE_TABLE_PATTERN.findall(baseline_source)) >= 35


def test_every_active_manifest_table_has_a_versioned_create_source() -> None:
    manifest = yaml.safe_load((ROOT / "docs" / "architecture" / "data_table_lifecycle_manifest.yml").read_text(encoding="utf-8"))["tables"]
    created_tables = set(CREATE_TABLE_PATTERN.findall(BASELINE_PATH.read_text(encoding="utf-8")))
    for migration in sorted((ROOT / "migrations" / "versions").glob("*.py")):
        created_tables.update(CREATE_TABLE_PATTERN.findall(migration.read_text(encoding="utf-8")))

    active_tables = {table for table, entry in manifest.items() if entry.get("lifecycle") not in {"retired", "legacy"}}
    assert active_tables - created_tables == {"alembic_version"}
    assert not [
        table
        for table, entry in manifest.items()
        if entry.get("lifecycle") not in {"retired", "legacy"} and str(entry.get("migration_source") or "").startswith("pre-Alembic baseline")
    ]


def test_database_url_helpers_are_postgres_only_and_redact_passwords() -> None:
    url = "postgresql+psycopg://alice:secret@db.internal:5433/aicrm"

    assert _psycopg_url(url) == "postgresql://alice:secret@db.internal:5433/aicrm"
    assert _safe_target(_psycopg_url(url)) == "postgresql://db.internal:5433/aicrm"
    assert "secret" not in redact_sensitive_text(f"failed for {url}: secret", url)
    with pytest.raises(ValueError, match="PostgreSQL"):
        _psycopg_url("sqlite:///tmp/aicrm.db")


def test_empty_postgres_database_installs_and_reuses_alembic_head() -> None:
    with _isolated_database("install") as database_url:
        first = install_or_upgrade_database(database_url)
        second = install_or_upgrade_database(database_url)

        assert first.baseline_applied is True
        assert first.revision_before is None
        assert first.revision_after == "0125_execution_runtime_correctness"
        assert second.baseline_applied is False
        assert second.revision_before == first.revision_after
        assert second.revision_after == first.revision_after
        with psycopg.connect(database_url) as connection:
            rows = connection.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                """
            ).fetchall()
        table_names = {str(row[0]) for row in rows}
        assert {
            "alembic_version",
            "auth_api_clients",
            "automation_channel_qrcode_asset",
            "automation_channel_scene_alias",
            "service_period_huangyoucan_usage_snapshot",
            "service_period_huangyoucan_usage_sync_runs",
            "sync_runs",
            "wecom_external_contact_event_logs",
            "wecom_media_leases",
        } <= table_names
        with psycopg.connect(database_url) as connection:
            manifest_columns = connection.execute(
                """
                SELECT column_name, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'internal_event'
                  AND column_name IN (
                      'fanout_manifest_version', 'fanout_manifest_hash',
                      'fanout_manifest_json', 'expected_consumer_count'
                  )
                """
            ).fetchall()
        assert {row[0] for row in manifest_columns} == {
            "fanout_manifest_version",
            "fanout_manifest_hash",
            "fanout_manifest_json",
            "expected_consumer_count",
        }
        assert all(row[1] == "NO" for row in manifest_columns)


def test_production_shape_alembic_database_upgrades_without_reapplying_baseline() -> None:
    with _isolated_database("production_shape") as database_url:
        with psycopg.connect(database_url, autocommit=True) as connection:
            connection.execute(BASELINE_PATH.read_text(encoding="utf-8"))
        _upgrade_database_to(database_url, "0098_admin_session_revocation")
        with psycopg.connect(database_url) as connection:
            admin_user_id = int(
                connection.execute(
                    """
                    INSERT INTO admin_users (
                        wecom_userid, wecom_corpid, display_name, is_active,
                        login_enabled, admin_level, session_version
                    ) VALUES (
                        'production-shape-upgrade', 'corp-production-shape',
                        'Production shape upgrade', TRUE, TRUE, 'super_admin', 7
                    )
                    RETURNING id
                    """
                ).fetchone()[0]
            )
            connection.commit()

        result = install_or_upgrade_database(database_url)

        assert result.baseline_applied is False
        assert result.revision_before == "0098_admin_session_revocation"
        assert result.revision_after == "0125_execution_runtime_correctness"
        with psycopg.connect(database_url) as connection:
            preserved = connection.execute(
                "SELECT wecom_userid, session_version FROM admin_users WHERE id = %s",
                (admin_user_id,),
            ).fetchone()
            auth_table = connection.execute("SELECT to_regclass('public.auth_sessions')").fetchone()
        assert preserved == ("production-shape-upgrade", 7)
        assert auth_table == ("auth_sessions",)


def test_upgrade_repairs_missing_or_partial_automation_agent_audit_tables_without_data_loss() -> None:
    with _isolated_database("automation_agent_audit_repair") as database_url:
        with psycopg.connect(database_url, autocommit=True) as connection:
            connection.execute(BASELINE_PATH.read_text(encoding="utf-8"))
        _upgrade_database_to(database_url, "0123_required_physical_schema_repair")

        with psycopg.connect(database_url) as connection:
            connection.execute("DROP TABLE automation_agent_llm_call_log")
            connection.execute("DROP TABLE automation_agent_output")
            connection.execute("CREATE TABLE automation_agent_output (id BIGSERIAL PRIMARY KEY)")
            preserved_id = int(
                connection.execute("INSERT INTO automation_agent_output DEFAULT VALUES RETURNING id").fetchone()[0]
            )
            connection.commit()

        result = install_or_upgrade_database(database_url)

        assert result.baseline_applied is False
        assert result.revision_before == "0123_required_physical_schema_repair"
        assert result.revision_after == "0125_execution_runtime_correctness"

        expected_columns = {
            "automation_agent_output": {
                "id",
                "output_id",
                "run_id",
                "request_id",
                "userid",
                "unionid",
                "agent_code",
                "output_type",
                "raw_output_text",
                "normalized_output_json",
                "rendered_output_text",
                "target_agent_code",
                "target_pool",
                "confidence",
                "reason",
                "need_human_review",
                "applied_status",
                "adopted_by",
                "adopted_action",
                "outcome_status",
                "outcome_value",
                "revision_of_output_id",
                "error_code",
                "error_message",
                "created_at",
                "updated_at",
            },
            "automation_agent_llm_call_log": {
                "id",
                "run_id",
                "agent_code",
                "provider",
                "model",
                "model_name",
                "request_id",
                "prompt_hash",
                "request_summary",
                "response_summary",
                "status",
                "latency_ms",
                "error_code",
                "error_message",
                "created_at",
                "updated_at",
            },
        }
        with psycopg.connect(database_url) as connection:
            columns = connection.execute(
                """
                SELECT table_name, column_name, is_nullable, udt_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name IN (
                      'automation_agent_output',
                      'automation_agent_llm_call_log'
                  )
                ORDER BY table_name, ordinal_position
                """
            ).fetchall()
            indexes = connection.execute(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename IN (
                      'automation_agent_output',
                      'automation_agent_llm_call_log'
                  )
                """
            ).fetchall()
            foreign_keys = connection.execute(
                """
                SELECT constraint_name
                FROM information_schema.table_constraints
                WHERE table_schema = 'public'
                  AND table_name IN (
                      'automation_agent_output',
                      'automation_agent_llm_call_log'
                  )
                  AND constraint_type = 'FOREIGN KEY'
                """
            ).fetchall()
            preserved = connection.execute(
                """
                SELECT id, output_id, normalized_output_json
                FROM automation_agent_output
                WHERE id = %s
                """,
                (preserved_id,),
            ).fetchone()

        actual_columns = {
            table_name: {column_name for row_table, column_name, _, _ in columns if row_table == table_name}
            for table_name in expected_columns
        }
        assert actual_columns == expected_columns
        assert all(is_nullable == "NO" for _, _, is_nullable, _ in columns)
        assert {
            (table_name, column_name, udt_name)
            for table_name, column_name, _, udt_name in columns
            if column_name in {"normalized_output_json", "request_summary", "response_summary"}
        } == {
            ("automation_agent_output", "normalized_output_json", "jsonb"),
            ("automation_agent_llm_call_log", "request_summary", "jsonb"),
            ("automation_agent_llm_call_log", "response_summary", "jsonb"),
        }
        assert {row[0] for row in indexes} == {
            "automation_agent_output_pkey",
            "idx_automation_agent_output_run_created",
            "ix_automation_agent_output_unionid",
            "automation_agent_llm_call_log_pkey",
            "idx_automation_agent_llm_call_log_agent_created",
        }
        assert foreign_keys == []
        assert preserved == (preserved_id, "", {})

        _downgrade_database_to(database_url, "0123_required_physical_schema_repair")
        _upgrade_database_to(database_url, "head")
        with psycopg.connect(database_url) as connection:
            preserved_after_reapply = connection.execute(
                "SELECT COUNT(*) FROM automation_agent_output WHERE id = %s",
                (preserved_id,),
            ).fetchone()
        assert preserved_after_reapply == (1,)


def test_execution_runtime_correctness_freezes_and_classifies_pre_cutover_queue_history() -> None:
    with _isolated_database("queue_history_freeze") as database_url:
        with psycopg.connect(database_url, autocommit=True) as connection:
            connection.execute(BASELINE_PATH.read_text(encoding="utf-8"))
        _upgrade_database_to(database_url, "0123_required_physical_schema_repair")

        with psycopg.connect(database_url) as connection:
            connection.execute(
                """
                INSERT INTO external_effect_job (
                    effect_type, adapter_name, operation, target_type, target_id,
                    idempotency_key, status, scheduled_at
                ) VALUES
                    ('wecom.media.upload', 'wecom', 'upload', 'media', 'legacy-media',
                     'history-freeze-media', 'queued', CURRENT_TIMESTAMP - INTERVAL '1 hour'),
                    ('webhook.test', 'http', 'post', 'loopback', 'terminal',
                     'history-freeze-terminal', 'succeeded', CURRENT_TIMESTAMP - INTERVAL '1 hour')
                    """
                )
            connection.execute(
                """
                INSERT INTO external_effect_job (
                    effect_type, adapter_name, operation, target_type, target_id,
                    idempotency_key, status, scheduled_at, attempt_count, max_attempts,
                    side_effect_executed, provider_result_received, reconciliation_required
                ) VALUES
                    ('webhook.test', 'http', 'post', 'loopback', 'ambiguous',
                     'history-freeze-ambiguous', 'dispatching', CURRENT_TIMESTAMP, 1, 5,
                     TRUE, FALSE, TRUE),
                    ('webhook.test', 'http', 'post', 'loopback', 'retryable',
                     'history-freeze-retryable', 'failed_retryable', CURRENT_TIMESTAMP, 1, 5,
                     FALSE, FALSE, FALSE),
                    ('webhook.test', 'http', 'post', 'loopback', 'exhausted',
                     'history-freeze-exhausted', 'queued', CURRENT_TIMESTAMP, 5, 5,
                     FALSE, FALSE, FALSE)
                """
            )
            connection.execute(
                """
                INSERT INTO internal_event (
                    event_id, event_type, aggregate_type, aggregate_id, idempotency_key
                ) VALUES ('evt-history-freeze', 'payment.succeeded', 'order', 'history-freeze', 'evt-history-freeze')
                """
            )
            connection.execute(
                """
                INSERT INTO internal_event_consumer_run (event_id, consumer_name, status)
                VALUES ('evt-history-freeze', 'payment_projection_consumer', 'pending')
                """
            )
            connection.execute(
                """
                INSERT INTO internal_event_outbox (
                    outbox_id, event_type, aggregate_type, aggregate_id, idempotency_key
                ) VALUES ('ieo-history-freeze', 'payment.succeeded', 'order', 'history-freeze', 'ieo-history-freeze')
                """
            )
            connection.execute(
                """
                INSERT INTO webhook_inbox (provider, event_family, route, idempotency_key)
                VALUES ('wecom', 'contact_change', '/callback', 'webhook-history-freeze')
                """
            )
            connection.execute(
                """
                INSERT INTO broadcast_jobs (
                    source_type, source_id, source_table, scheduled_for, status,
                    idempotency_key, target_unionids_json, content_payload
                ) VALUES (
                    'manual', 'history-freeze', 'manual', CURRENT_TIMESTAMP - INTERVAL '1 hour', 'queued',
                    'broadcast-history-freeze', '[]'::jsonb, '{}'::jsonb
                )
                """
            )
            connection.commit()

        _upgrade_database_to(database_url, "head")

        with psycopg.connect(database_url) as connection:
            classifications = dict(
                connection.execute(
                    """
                    SELECT classification, COUNT(*)
                    FROM queue_history_classification
                    GROUP BY classification
                    """
                ).fetchall()
            )
            hold_counts = {
                table: int(connection.execute(f"SELECT COUNT(*) FROM {table} WHERE hold_reason <> ''").fetchone()[0])
                for table in (
                    "external_effect_job",
                    "internal_event_consumer_run",
                    "internal_event_outbox",
                    "webhook_inbox",
                    "broadcast_jobs",
                )
            }
            external_candidates = int(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM external_effect_job
                    WHERE status IN ('queued', 'failed_retryable')
                      AND hold_reason = ''
                      AND scheduled_at <= CURRENT_TIMESTAMP
                    """
                ).fetchone()[0]
            )
            connection.execute(
                """
                INSERT INTO external_effect_job (
                    effect_type, adapter_name, operation, target_type, target_id,
                    idempotency_key, status, scheduled_at
                ) VALUES (
                    'webhook.test', 'http', 'post', 'loopback', 'new-row',
                    'history-freeze-new-row', 'queued', CURRENT_TIMESTAMP
                )
                """
            )
            new_hold = connection.execute(
                "SELECT hold_reason, hold_at FROM external_effect_job WHERE idempotency_key = 'history-freeze-new-row'"
            ).fetchone()
            connection.commit()

        assert classifications == {
            "ambiguous_hold": 1,
            "inconsistent_quarantine": 1,
            "safe_pre_provider": 5,
            "safe_retryable": 1,
            "terminal_readonly": 1,
        }
        assert hold_counts == {
            "external_effect_job": 4,
            "internal_event_consumer_run": 1,
            "internal_event_outbox": 1,
            "webhook_inbox": 1,
            "broadcast_jobs": 1,
        }
        assert external_candidates == 0
        assert new_hold == ("", None)

        from aicrm_next.platform_foundation.repository import RuntimeReadinessRepository

        with RuntimeReadinessRepository(database_url) as readiness_repo:
            queue_metrics = readiness_repo.queue_metrics(
                allowed_pairs=(("payment.succeeded", "payment_projection_consumer"),)
            )
        assert queue_metrics["queue_policy_version"] == 1
        assert queue_metrics["queue_raw_open_count"] == 9
        assert queue_metrics["queue_held_count"] == 8
        assert queue_metrics["queue_eligible_count"] == 1
        assert queue_metrics["internal_event_pending_count"] == 1
        assert queue_metrics["internal_event_actionable_pending_count"] == 0
        assert queue_metrics["internal_event_outbox_raw_open_count"] == 1
        assert queue_metrics["internal_event_outbox_held_count"] == 1
        assert queue_metrics["internal_event_outbox_eligible_count"] == 0
        assert queue_metrics["webhook_raw_open_count"] == 1
        assert queue_metrics["webhook_held_count"] == 1
        assert queue_metrics["webhook_eligible_count"] == 0
        assert queue_metrics["external_effect_pending_count"] == 5
        assert queue_metrics["external_effect_held_count"] == 4
        assert queue_metrics["external_effect_eligible_count"] == 1
        assert queue_metrics["broadcast_raw_open_count"] == 1
        assert queue_metrics["broadcast_held_count"] == 1
        assert queue_metrics["broadcast_eligible_count"] == 0

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from aicrm_next.background_jobs.broadcast_queue_worker import PostgresBroadcastQueueRepository
        from aicrm_next.platform_foundation.external_effects.repo import SQLAlchemyExternalEffectRepository
        from aicrm_next.platform_foundation.internal_events.repository import SQLAlchemyInternalEventRepository
        from aicrm_next.platform_foundation.webhook_inbox.repository import PostgresWebhookInboxRepository

        sqlalchemy_url = (
            "postgresql+psycopg://" + database_url[len("postgresql://") :]
            if database_url.startswith("postgresql://")
            else database_url
        )
        engine = create_engine(sqlalchemy_url)
        session_factory = sessionmaker(bind=engine, expire_on_commit=False)
        external_repo = SQLAlchemyExternalEffectRepository(session_factory)
        internal_repo = SQLAlchemyInternalEventRepository(session_factory)
        assert external_repo.list_due_jobs(effect_types=["wecom.media.upload"]) == []
        assert internal_repo.list_due_runs() == []
        assert internal_repo.acquire_due_runs(locked_by="history-freeze-test") == []
        assert internal_repo.list_due_outbox() == []
        assert internal_repo.acquire_due_outbox(locked_by="history-freeze-test") == []
        webhook_repo = PostgresWebhookInboxRepository(database_url)
        assert webhook_repo.preview_due(provider="wecom") == []
        assert webhook_repo.claim_due(provider="wecom", locked_by="history-freeze-test") == []
        previous_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = database_url
        try:
            assert PostgresBroadcastQueueRepository().claim_due_jobs(
                limit=10,
                now=datetime.now(timezone.utc),
                claim_token="history-freeze-test",
                lease_seconds=30,
            ) == []
        finally:
            if previous_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = previous_url
            engine.dispose()

        with psycopg.connect(database_url) as connection:
            with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
                connection.execute("UPDATE queue_history_classification SET source_status = 'tampered'")
            connection.rollback()

        config = Config(str(ROOT / "alembic.ini"))
        config.set_main_option("sqlalchemy.url", database_url)
        previous_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = database_url
        try:
            command.downgrade(config, "0123_required_physical_schema_repair")
        finally:
            if previous_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = previous_url
        with psycopg.connect(database_url) as connection:
            assert connection.execute("SELECT to_regclass('public.queue_history_classification')").fetchone() == (None,)
            downgraded_statuses = dict(
                connection.execute(
                    """
                    SELECT idempotency_key, status
                    FROM external_effect_job
                    WHERE idempotency_key IN ('history-freeze-media', 'history-freeze-ambiguous')
                    """
                ).fetchall()
            )
            assert downgraded_statuses == {
                "history-freeze-ambiguous": "unknown_after_dispatch",
                "history-freeze-media": "blocked",
            }
            assert connection.execute(
                """
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_schema = 'public' AND column_name IN ('hold_reason', 'hold_at')
                  AND table_name IN (
                    'external_effect_job', 'internal_event_consumer_run', 'internal_event_outbox',
                    'webhook_inbox', 'broadcast_jobs'
                  )
                """
            ).fetchone() == (0,)


def test_questionnaire_auto_execute_upgrade_skips_only_pre_cutover_runs() -> None:
    with _isolated_database("questionnaire_auto_execute") as database_url:
        with psycopg.connect(database_url, autocommit=True) as connection:
            connection.execute(BASELINE_PATH.read_text(encoding="utf-8"))
        _upgrade_database_to(database_url, "0108_customer_read_model_refresh")

        with psycopg.connect(database_url) as connection:
            connection.execute(
                """
                INSERT INTO internal_event (
                    event_id, event_type, aggregate_type, aggregate_id,
                    idempotency_key, occurred_at, created_at
                ) VALUES
                    (
                        'evt-questionnaire-pre-cutover', 'questionnaire.submitted',
                        'questionnaire_submission', 'pre-cutover', 'questionnaire-pre-cutover',
                        '2026-07-13 16:19:59+00', '2026-07-13 16:19:59+00'
                    ),
                    (
                        'evt-questionnaire-post-cutover', 'questionnaire.submitted',
                        'questionnaire_submission', 'post-cutover', 'questionnaire-post-cutover',
                        '2026-07-13 16:20:01+00', '2026-07-13 16:20:01+00'
                    )
                """
            )
            connection.execute(
                """
                INSERT INTO internal_event_consumer_run (
                    event_id, consumer_name, consumer_type, status
                )
                SELECT event_id, consumer_name, 'projection', 'pending'
                FROM (
                    VALUES
                        ('evt-questionnaire-pre-cutover'),
                        ('evt-questionnaire-post-cutover')
                ) AS event(event_id)
                CROSS JOIN (
                    VALUES
                        ('questionnaire_projection_consumer'),
                        ('questionnaire_webhook_consumer'),
                        ('questionnaire_tag_consumer'),
                        ('automation_questionnaire_consumer'),
                        ('customer_summary_consumer')
                ) AS consumer(consumer_name)
                """
            )
            connection.commit()

        _upgrade_database_to(database_url, "head")

        with psycopg.connect(database_url) as connection:
            statuses = connection.execute(
                """
                SELECT event_id, status, COUNT(*)
                FROM internal_event_consumer_run
                GROUP BY event_id, status
                ORDER BY event_id, status
                """
            ).fetchall()
            attempts = connection.execute(
                """
                SELECT status, error_code, COUNT(*)
                FROM internal_event_consumer_attempt
                GROUP BY status, error_code
                """
            ).fetchall()

        assert statuses == [
            ("evt-questionnaire-post-cutover", "pending", 5),
            ("evt-questionnaire-pre-cutover", "skipped", 5),
        ]
        assert attempts == [
            (
                "skipped",
                "questionnaire_shadow_before_auto_execute_cutover",
                5,
            )
        ]


def test_retired_workspace_drop_fails_closed_when_any_table_contains_data() -> None:
    with _isolated_database("retired_workspace_nonempty") as database_url:
        with psycopg.connect(database_url, autocommit=True) as connection:
            connection.execute(BASELINE_PATH.read_text(encoding="utf-8"))
        _upgrade_database_to(database_url, "0107_hyc_usage_snapshot")
        with psycopg.connect(database_url) as connection:
            connection.execute(
                """
                INSERT INTO group_ops_workspace_drafts (draft_id, idempotency_key)
                VALUES ('preserve_nonempty_draft', 'preserve_nonempty_draft')
                """
            )
            connection.commit()

        with pytest.raises(SQLAlchemyError, match="retired workspace table group_ops_workspace_drafts is not empty"):
            _upgrade_database_to(database_url, "head")

        with psycopg.connect(database_url) as connection:
            revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
            preserved = connection.execute("SELECT COUNT(*) FROM group_ops_workspace_drafts").fetchone()
            refresh_state = connection.execute("SELECT to_regclass('public.customer_read_model_refresh_state')").fetchone()
        assert revision == ("0107_hyc_usage_snapshot",)
        assert preserved == (1,)
        assert refresh_state == (None,)


def test_nonempty_database_without_alembic_state_is_rejected() -> None:
    with _isolated_database("ambiguous") as database_url:
        with psycopg.connect(database_url, autocommit=True) as connection:
            connection.execute("CREATE TABLE unmanaged_table (id BIGINT PRIMARY KEY)")

        with pytest.raises(DatabaseBootstrapRefused, match="user relations"):
            install_or_upgrade_database(database_url)

        with psycopg.connect(database_url) as connection:
            row = connection.execute("SELECT to_regclass('public.alembic_version')").fetchone()
        assert row == (None,)


def test_sequence_only_database_without_alembic_state_is_rejected() -> None:
    with _isolated_database("sequence_only") as database_url:
        with psycopg.connect(database_url, autocommit=True) as connection:
            connection.execute("CREATE SEQUENCE unmanaged_sequence")

        with pytest.raises(DatabaseBootstrapRefused, match="public.unmanaged_sequence"):
            install_or_upgrade_database(database_url)

        with psycopg.connect(database_url) as connection:
            row = connection.execute("SELECT to_regclass('public.alembic_version')").fetchone()
        assert row == (None,)


def test_failed_baseline_is_atomic_and_does_not_fake_alembic_head(tmp_path: Path) -> None:
    bad_baseline = tmp_path / "bad-baseline.sql"
    bad_baseline.write_text(
        "CREATE TABLE should_roll_back (id BIGINT PRIMARY KEY);\nTHIS IS INVALID SQL;\n",
        encoding="utf-8",
    )
    with _isolated_database("rollback") as database_url:
        with pytest.raises(psycopg.Error):
            install_or_upgrade_database(database_url, baseline_path=bad_baseline)

        with psycopg.connect(database_url) as connection:
            row = connection.execute(
                """
                SELECT to_regclass('public.should_roll_back'),
                       to_regclass('public.alembic_version')
                """
            ).fetchone()
        assert row == (None, None)


def _upgrade_database_to(database_url: str, revision: str) -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    previous_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    try:
        command.upgrade(config, revision)
    finally:
        if previous_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_url


def _downgrade_database_to(database_url: str, revision: str) -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    previous_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    try:
        command.downgrade(config, revision)
    finally:
        if previous_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_url


@contextmanager
def _isolated_database(label: str):
    source_url = os.getenv("AICRM_TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not source_url:
        pytest.skip("PostgreSQL integration URL is unavailable")
    source_url = _psycopg_url(source_url)
    parsed = urlsplit(source_url)
    maintenance_url = urlunsplit(parsed._replace(path="/postgres"))
    database_name = f"aicrm_bootstrap_test_{label}_{uuid.uuid4().hex[:8]}"
    database_url = urlunsplit(parsed._replace(path=f"/{database_name}"))

    with psycopg.connect(maintenance_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    try:
        yield database_url
    finally:
        with psycopg.connect(maintenance_url, autocommit=True) as connection:
            connection.execute(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = %s AND pid <> pg_backend_pid()
                """,
                (database_name,),
            )
            connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name)))
