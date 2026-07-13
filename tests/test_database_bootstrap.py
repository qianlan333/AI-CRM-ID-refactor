from __future__ import annotations

import os
import re
import uuid
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
import yaml
from alembic import command
from alembic.config import Config
from psycopg import sql

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
    manifest = yaml.safe_load(
        (ROOT / "docs" / "architecture" / "data_table_lifecycle_manifest.yml").read_text(
            encoding="utf-8"
        )
    )["tables"]
    created_tables = set(CREATE_TABLE_PATTERN.findall(BASELINE_PATH.read_text(encoding="utf-8")))
    for migration in sorted((ROOT / "migrations" / "versions").glob("*.py")):
        created_tables.update(CREATE_TABLE_PATTERN.findall(migration.read_text(encoding="utf-8")))

    active_tables = {
        table for table, entry in manifest.items() if entry.get("lifecycle") != "retired"
    }
    assert active_tables - created_tables == {"alembic_version"}
    assert not [
        table
        for table, entry in manifest.items()
        if entry.get("lifecycle") != "retired"
        and str(entry.get("migration_source") or "").startswith("pre-Alembic baseline")
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
        assert first.revision_after == "0106_critical_read_path_indexes"
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
            "sync_runs",
            "wecom_external_contact_event_logs",
        } <= table_names


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
        assert result.revision_after == "0106_critical_read_path_indexes"
        with psycopg.connect(database_url) as connection:
            preserved = connection.execute(
                "SELECT wecom_userid, session_version FROM admin_users WHERE id = %s",
                (admin_user_id,),
            ).fetchone()
            auth_table = connection.execute(
                "SELECT to_regclass('public.auth_sessions')"
            ).fetchone()
        assert preserved == ("production-shape-upgrade", 7)
        assert auth_table == ("auth_sessions",)


def test_nonempty_database_without_alembic_state_is_rejected() -> None:
    with _isolated_database("ambiguous") as database_url:
        with psycopg.connect(database_url, autocommit=True) as connection:
            connection.execute("CREATE TABLE unmanaged_table (id BIGINT PRIMARY KEY)")

        with pytest.raises(DatabaseBootstrapRefused, match="user relations"):
            install_or_upgrade_database(database_url)

        with psycopg.connect(database_url) as connection:
            row = connection.execute(
                "SELECT to_regclass('public.alembic_version')"
            ).fetchone()
        assert row == (None,)


def test_sequence_only_database_without_alembic_state_is_rejected() -> None:
    with _isolated_database("sequence_only") as database_url:
        with psycopg.connect(database_url, autocommit=True) as connection:
            connection.execute("CREATE SEQUENCE unmanaged_sequence")

        with pytest.raises(DatabaseBootstrapRefused, match="public.unmanaged_sequence"):
            install_or_upgrade_database(database_url)

        with psycopg.connect(database_url) as connection:
            row = connection.execute(
                "SELECT to_regclass('public.alembic_version')"
            ).fetchone()
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
