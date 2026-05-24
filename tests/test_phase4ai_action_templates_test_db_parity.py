from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

import tools.check_phase4ai_action_templates_test_db_parity as checker
import tools.run_phase4ai_action_templates_test_db_parity as harness


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tools/run_phase4ai_action_templates_test_db_parity.py"
DOC = ROOT / "docs/development/phase_4ai_action_templates_test_db_parity.md"
YAML = ROOT / "docs/development/phase_4ai_action_templates_test_db_parity.yaml"


def _create_sqlite_test_db(path: Path) -> str:
    url = f"sqlite+pysqlite:///{path}"
    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE automation_operation_templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    template_code TEXT NOT NULL UNIQUE,
                    template_name TEXT NOT NULL DEFAULT '',
                    template_source TEXT NOT NULL DEFAULT 'crm_local',
                    category TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',
                    default_config_json TEXT NOT NULL DEFAULT '{}',
                    ui_schema_json TEXT NOT NULL DEFAULT '{}',
                    workflow_blueprint_json TEXT NOT NULL DEFAULT '{}',
                    node_blueprints_json TEXT NOT NULL DEFAULT '[]',
                    created_by TEXT NOT NULL DEFAULT '',
                    updated_by TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    archived_at TEXT
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE automation_operation_template_idempotency (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    route_family TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    response_snapshot TEXT NOT NULL DEFAULT '{}',
                    resource_type TEXT NOT NULL DEFAULT 'action_template',
                    resource_id INTEGER NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(route_family, operation, operator, idempotency_key)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE automation_operation_template_audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    route_family TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    resource_type TEXT NOT NULL DEFAULT 'action_template',
                    resource_id INTEGER NULL,
                    before_snapshot TEXT NOT NULL DEFAULT '{}',
                    after_snapshot TEXT NOT NULL DEFAULT '{}',
                    request_payload TEXT NOT NULL DEFAULT '{}',
                    validation_result TEXT NOT NULL DEFAULT '{}',
                    rollback_payload TEXT NOT NULL DEFAULT '{}',
                    side_effect_safety TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
    return url


def test_checker_current_repo_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report.get("blockers", []), ensure_ascii=False, indent=2)


def test_harness_tool_exists_and_supports_outputs() -> None:
    text_body = HARNESS.read_text(encoding="utf-8")
    assert "--output-json" in text_body
    assert "--output-md" in text_body


def test_default_no_env_run_returns_not_executed_missing_test_db(monkeypatch) -> None:
    monkeypatch.delenv("AICRM_ACTION_TEMPLATES_TEST_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://prod.example/master")
    monkeypatch.setenv("AICRM_ACTION_TEMPLATES_DATABASE_URL", "postgresql://prod.example/master")

    report = harness.run_harness()

    assert report["ok"] is True
    assert report["result_status"] == "not_executed_missing_test_db"
    assert report["adapter_smoke_executed"] is False
    assert report["production_data_used"] is False


def test_harness_refuses_production_looking_url(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_ACTION_TEMPLATES_TEST_DATABASE_URL", "postgresql://db.example/prod")

    report = harness.run_harness()

    assert report["ok"] is False
    assert report["result_status"] == "blocked_unsafe_test_db_url"
    assert report["adapter_smoke_executed"] is False
    assert "prod" in report["db_url_safety"]["forbidden_hits"]


def test_harness_refuses_url_with_allowed_and_forbidden_marker(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_ACTION_TEMPLATES_TEST_DATABASE_URL", "postgresql://db.example/local_prod")

    report = harness.run_harness()

    assert report["ok"] is False
    assert report["result_status"] == "blocked_unsafe_test_db_url"
    assert report["db_url_safety"]["allowed_hits"]
    assert report["db_url_safety"]["forbidden_hits"]


def test_harness_never_falls_back_to_database_url(monkeypatch) -> None:
    monkeypatch.delenv("AICRM_ACTION_TEMPLATES_TEST_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///tmp/local_test_should_not_be_used.db")

    report = harness.run_harness()

    assert report["result_status"] == "not_executed_missing_test_db"
    text_body = HARNESS.read_text(encoding="utf-8")
    assert 'os.getenv("DATABASE_URL"' not in text_body
    assert 'os.environ.get("DATABASE_URL"' not in text_body


def test_harness_never_uses_action_templates_database_url_as_test_db(monkeypatch) -> None:
    monkeypatch.delenv("AICRM_ACTION_TEMPLATES_TEST_DATABASE_URL", raising=False)
    monkeypatch.setenv("AICRM_ACTION_TEMPLATES_DATABASE_URL", "sqlite+pysqlite:///tmp/local_test_should_not_be_used.db")

    report = harness.run_harness()

    assert report["result_status"] == "not_executed_missing_test_db"
    assert "AICRM_ACTION_TEMPLATES_DATABASE_URL" not in HARNESS.read_text(encoding="utf-8")


def test_safe_local_sqlite_test_db_runs_adapter_smoke(monkeypatch, tmp_path: Path) -> None:
    db_url = _create_sqlite_test_db(tmp_path / "phase4ai_local_test.db")
    monkeypatch.setenv("AICRM_ACTION_TEMPLATES_TEST_DATABASE_URL", db_url)

    report = harness.run_harness()

    assert report["ok"] is True
    assert report["result_status"] == "passed"
    assert report["adapter_smoke_executed"] is True
    assert report["production_data_used"] is False
    assert report["route_switch_ready"] is False
    assert {item["name"] for item in report["details"] if item["status"] == "passed"} >= {
        "main_table_available",
        "idempotency_table_available",
        "audit_table_available",
        "create_with_idempotency",
        "idempotency_replay",
        "idempotency_conflict",
        "audit_event_emitted",
        "rollback_payload_present",
        "side_effect_safety_false",
    }


def test_harness_matrix_complete() -> None:
    data = checker.load_yaml(YAML)
    assert checker.REQUIRED_SCHEMA_MATRIX <= set(data["harness_matrix"]["schema"])
    assert checker.REQUIRED_READ_MATRIX <= set(data["harness_matrix"]["read"])
    assert checker.REQUIRED_CREATE_MATRIX <= set(data["harness_matrix"]["create"])


def test_excluded_routes_remain_excluded() -> None:
    data = checker.load_yaml(YAML)
    assert all(data["excluded"][field] is True for field in checker.REQUIRED_EXCLUDED_TRUE)
    text_body = HARNESS.read_text(encoding="utf-8")
    for forbidden in ("action-templates/generate", "action-templates/from-workflow", ".delete(", ".put("):
        assert forbidden not in text_body


def test_side_effect_safety_false(monkeypatch, tmp_path: Path) -> None:
    db_url = _create_sqlite_test_db(tmp_path / "phase4ai_safety_local_test.db")
    monkeypatch.setenv("AICRM_ACTION_TEMPLATES_TEST_DATABASE_URL", db_url)

    report = harness.run_harness()

    assert report["side_effect_safety"]
    assert all(value is False for value in report["side_effect_safety"].values())


def test_no_runtime_files_changed_if_git_diff_available() -> None:
    proc = subprocess.run(
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        return
    changed = {line.strip() for line in proc.stdout.splitlines() if line.strip()}
    assert "aicrm_next/main.py" not in changed
    assert "aicrm_next/production_compat/api.py" not in changed
    assert not any(path.startswith("wecom_ability_service/") for path in changed)
    assert not any(path.startswith("migrations/") for path in changed)


def test_docs_do_not_claim_forbidden_states() -> None:
    text_body = DOC.read_text(encoding="utf-8").lower()
    forbidden_patterns = [
        r"production parity",
        r"production repository enabled as route owner",
        r"production write authorized",
        r"route switch authorized",
        r"fallback removal authorized",
        r"production approved",
        r"canary approved",
        r"delete_ready\s+true",
    ]

    for pattern in forbidden_patterns:
        assert re.search(pattern, text_body) is None, pattern
