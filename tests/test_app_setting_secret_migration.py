from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from aicrm_next.shared.secret_store import FileSecretStore, SecretStoreError, is_secret_reference
from scripts.ops import migrate_app_setting_secrets as migration_script
from scripts.ops.check_secret_reference_cutover import reconcile_secret_reference_cutover
from scripts.ops.migrate_app_setting_secrets import (
    migrate_app_setting_secrets,
    rollback_secret_reference,
)


def _engine(tmp_path: Path) -> Engine:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'migration.sqlite3'}", future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE admin_operation_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    before_json TEXT NOT NULL DEFAULT '{}',
                    after_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
        )
    return engine


def _upsert(engine: Engine, key: str, value: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (:key, :value, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
                """
            ),
            {"key": key, "value": value},
        )


def _value(engine: Engine, key: str) -> str:
    with engine.connect() as conn:
        row = conn.execute(text("SELECT value FROM app_settings WHERE key = :key"), {"key": key}).first()
    return str((row or [""])[0] or "")


def test_secret_migration_dry_run_reports_metadata_only_and_writes_nothing(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    root = tmp_path / "secrets"
    raw_db = "dry-run-db-secret-sentinel"
    raw_env = "dry-run-env-secret-sentinel"
    _upsert(engine, "WECOM_SECRET", raw_db)

    report = migrate_app_setting_secrets(
        engine=engine,
        store=FileSecretStore(root),
        environment={"WECOM_CONTACT_SECRET": raw_env},
        dry_run=True,
    )

    rendered = json.dumps(report, ensure_ascii=False, sort_keys=True)
    assert raw_db not in rendered
    assert raw_env not in rendered
    assert _value(engine, "WECOM_SECRET") == raw_db
    assert _value(engine, "AICRM_SECRET_REFERENCE_CUTOVER") == ""
    assert not root.exists()
    assert report["dry_run"] is True
    assert report["plaintext_pending"] == 2
    assert {item["source"] for item in report["items"] if item["present"]} == {"app_settings", "environment"}
    assert all(set(item) == {"key", "source", "version", "present", "status"} for item in report["items"])


def test_filesystem_failure_happens_before_database_transaction(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    raw = "filesystem-failure-secret-sentinel"
    _upsert(engine, "WECOM_SECRET", raw)

    class FailingStore(FileSecretStore):
        def write(self, key: str, value: str, *, current_reference: str = "") -> str:
            raise SecretStoreError("injected filesystem failure")

    with pytest.raises(SecretStoreError, match="injected filesystem failure"):
        migrate_app_setting_secrets(
            engine=engine,
            store=FailingStore(tmp_path / "secrets"),
            environment={},
            dry_run=False,
        )

    assert _value(engine, "WECOM_SECRET") == raw
    assert _value(engine, "AICRM_SECRET_REFERENCE_CUTOVER") == ""


def test_database_failure_rolls_back_rows_after_immutable_file_write(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    root = tmp_path / "secrets"
    raw = "database-failure-secret-sentinel"
    _upsert(engine, "WECOM_SECRET", raw)

    def fail_before_commit(_connection) -> None:
        raise RuntimeError("injected database failure")

    with pytest.raises(RuntimeError, match="injected database failure"):
        migrate_app_setting_secrets(
            engine=engine,
            store=FileSecretStore(root),
            environment={},
            dry_run=False,
            transaction_hook=fail_before_commit,
        )

    assert _value(engine, "WECOM_SECRET") == raw
    assert _value(engine, "AICRM_SECRET_REFERENCE_CUTOVER") == ""
    assert len(list((root / "WECOM_SECRET").iterdir())) == 1


def test_mixed_raw_reference_and_environment_rows_migrate_idempotently(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    root = tmp_path / "secrets"
    store = FileSecretStore(root)
    existing_reference = store.write("WECOM_CONTACT_SECRET", "existing-reference-secret")
    _upsert(engine, "WECOM_SECRET", "raw-database-secret")
    _upsert(engine, "WECOM_CONTACT_SECRET", existing_reference)
    environment = {"SECRET_KEY": "environment-signing-secret"}

    first = migrate_app_setting_secrets(
        engine=engine,
        store=store,
        environment=environment,
        dry_run=False,
    )
    version_files_after_first = sorted(path.relative_to(root) for path in root.glob("*/*"))
    second = migrate_app_setting_secrets(
        engine=engine,
        store=store,
        environment=environment,
        dry_run=False,
    )

    assert first["migrated"] == 2
    assert first["plaintext_pending"] == 0
    assert second["migrated"] == 0
    assert second["already_referenced"] == 3
    assert sorted(path.relative_to(root) for path in root.glob("*/*")) == version_files_after_first
    for key in ("WECOM_SECRET", "WECOM_CONTACT_SECRET", "SECRET_KEY"):
        assert is_secret_reference(_value(engine, key))
    assert _value(engine, "AICRM_SECRET_REFERENCE_CUTOVER") == "true"
    rendered = json.dumps(first, ensure_ascii=False, sort_keys=True)
    assert "raw-database-secret" not in rendered
    assert "environment-signing-secret" not in rendered
    assert existing_reference not in rendered


def test_secret_reference_can_roll_back_to_an_existing_immutable_version(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    store = FileSecretStore(tmp_path / "secrets")
    previous = store.write("WECOM_SECRET", "previous-secret-version")
    current = store.write("WECOM_SECRET", "current-secret-version", current_reference=previous)
    _upsert(engine, "WECOM_SECRET", current)

    report = rollback_secret_reference(
        engine=engine,
        store=store,
        key="WECOM_SECRET",
        reference=previous,
    )

    assert _value(engine, "WECOM_SECRET") == previous
    assert store.read(_value(engine, "WECOM_SECRET")) == "previous-secret-version"
    assert report == {
        "key": "WECOM_SECRET",
        "present": True,
        "source": "app_settings",
        "status": "rolled_back",
        "version": previous.rsplit(":", 1)[-1],
    }
    assert previous not in json.dumps(report, sort_keys=True)


def test_reconciliation_counts_plaintext_unresolved_audit_and_permission_failures(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    root = tmp_path / "secrets"
    store = FileSecretStore(root)
    raw = "unsafe-audit-secret-sentinel"
    _upsert(engine, "WECOM_SECRET", raw)
    migrate_app_setting_secrets(engine=engine, store=store, environment={}, dry_run=False)
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO admin_operation_logs (before_json, after_json) VALUES (:before_json, '{}')"),
            {"before_json": json.dumps({"value": raw})},
        )

    unsafe = reconcile_secret_reference_cutover(engine=engine, store=store)
    assert unsafe["unsafe_audit_hits"] == 1
    assert unsafe["ok"] is False
    assert raw not in json.dumps(unsafe, ensure_ascii=False, sort_keys=True)

    with engine.begin() as conn:
        conn.execute(text("UPDATE admin_operation_logs SET before_json = '{\"value\": \"[redacted]\"}'"))
    safe = reconcile_secret_reference_cutover(engine=engine, store=store)
    assert safe["ok"] is True
    assert safe["plaintext_sensitive_rows"] == 0
    assert safe["unresolved_refs"] == 0
    assert safe["unsafe_audit_hits"] == 0
    assert safe["permission_errors"] == 0

    reference = _value(engine, "WECOM_SECRET")
    version = reference.rsplit(":", 1)[-1]
    os.chmod(root / "WECOM_SECRET" / version, 0o644)
    permissions = reconcile_secret_reference_cutover(engine=engine, store=store)
    assert permissions["permission_errors"] >= 1
    assert permissions["ok"] is False


def test_migration_persists_only_non_sensitive_runtime_environment_values(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    root = tmp_path / "secrets"
    env_file = tmp_path / "runtime.env"
    raw = "environment-file-secret-sentinel"
    env_file.write_text(f"WECOM_SECRET='{raw}'\nEXISTING_FLAG='keep-me'\n", encoding="utf-8")
    os.chmod(env_file, 0o600)

    report = migrate_app_setting_secrets(
        engine=engine,
        store=FileSecretStore(root),
        environment={"WECOM_SECRET": raw},
        dry_run=False,
        environment_file=env_file,
    )

    body = env_file.read_text(encoding="utf-8")
    assert f"AICRM_SECRET_STORE_DIR='{root}'" in body
    assert "AICRM_SECRET_REFERENCE_CUTOVER='true'" in body
    assert raw not in body
    assert "WECOM_SECRET='secretref:file:WECOM_SECRET:" in body
    assert "EXISTING_FLAG='keep-me'" in body
    assert report["environment_file_updated"] is True
    assert raw not in json.dumps(report, ensure_ascii=False, sort_keys=True)

    reconciled = reconcile_secret_reference_cutover(engine=engine, store=FileSecretStore(root), environment_file=env_file)
    assert reconciled["ok"] is True
    assert reconciled["plaintext_environment_entries"] == 0

    current_reference = _value(engine, "WECOM_SECRET")
    rotated_reference = FileSecretStore(root).write(
        "WECOM_SECRET",
        "rotated-environment-version",
        current_reference=current_reference,
    )
    env_file.write_text(f"WECOM_SECRET='{rotated_reference}'\n", encoding="utf-8")
    os.chmod(env_file, 0o600)
    mismatched = reconcile_secret_reference_cutover(engine=engine, store=FileSecretStore(root), environment_file=env_file)
    assert mismatched["environment_reference_mismatches"] == 1
    assert mismatched["ok"] is False

    env_file.write_text(f"WECOM_SECRET='{raw}'\n", encoding="utf-8")
    os.chmod(env_file, 0o600)
    unsafe = reconcile_secret_reference_cutover(engine=engine, store=FileSecretStore(root), environment_file=env_file)
    assert unsafe["plaintext_environment_entries"] == 1
    assert unsafe["ok"] is False

    os.chmod(env_file, 0o644)
    bad_permissions = reconcile_secret_reference_cutover(engine=engine, store=FileSecretStore(root), environment_file=env_file)
    assert bad_permissions["environment_permission_errors"] == 1
    assert bad_permissions["ok"] is False


def test_migration_cli_failure_never_prints_exception_text(monkeypatch, tmp_path: Path, capsys) -> None:
    raw = "cli-exception-secret-sentinel"

    def fail_migration(**_kwargs):
        raise RuntimeError(raw)

    monkeypatch.setattr(migration_script, "get_engine", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(migration_script, "migrate_app_setting_secrets", fail_migration)

    exit_code = migration_script.main(
        [
            "--execute",
            "--secret-store-dir",
            str(tmp_path / "secrets"),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 1
    assert raw not in output
    assert json.loads(output) == {"error": "RuntimeError", "ok": False}
