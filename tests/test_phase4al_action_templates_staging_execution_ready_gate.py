from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import tools.check_phase4al_action_templates_staging_execution_ready_gate as checker
import tools.run_phase4al_action_templates_staging_execution_preflight as preflight


ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = ROOT / "tools/run_phase4al_action_templates_staging_execution_preflight.py"
DOC = ROOT / "docs/development/phase_4al_action_templates_staging_execution_ready_gate.md"
YAML = ROOT / "docs/development/phase_4al_action_templates_staging_execution_ready_gate.yaml"


def test_checker_current_repo_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report.get("blockers", []), ensure_ascii=False, indent=2)


def test_preflight_tool_exists_and_supports_outputs() -> None:
    text_body = PREFLIGHT.read_text(encoding="utf-8")
    assert "--output-json" in text_body
    assert "--output-md" in text_body
    assert "--closure-status-file" in text_body
    assert "--read-only" in text_body


def test_default_no_closure_or_env_returns_ready_false(monkeypatch) -> None:
    monkeypatch.delenv("AICRM_ACTION_TEMPLATES_STAGING_DATABASE_URL", raising=False)
    monkeypatch.delenv("AICRM_ACTION_TEMPLATES_REPO_BACKEND", raising=False)
    monkeypatch.delenv("AICRM_PHASE4AK_STAGING_SMOKE_APPROVED", raising=False)

    report = preflight.run_preflight()

    assert report["ok"] is True
    assert report["ready_for_phase_4am_staging_execution"] is False
    assert report["production_data_connected"] is False
    assert report["staging_smoke_executed"] is False
    assert report["lower_runner_called"] is False
    assert report["missing_items"]


def test_closure_form_complete_and_pending() -> None:
    data = checker.load_yaml(YAML)
    assert set(data["closure_form"]) == checker.CLOSURE_FIELDS
    assert all(value == "pending" for value in data["closure_form"].values())


def test_complete_closure_and_safe_env_can_return_ready_true(monkeypatch, tmp_path: Path) -> None:
    status_file = tmp_path / "closure.json"
    status_file.write_text(
        json.dumps({"closure_form": {field: "complete" for field in preflight.REQUIRED_CLOSURE_ITEMS}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("AICRM_ACTION_TEMPLATES_STAGING_DATABASE_URL", "postgresql://db.example/staging_action_templates")
    monkeypatch.setenv("AICRM_ACTION_TEMPLATES_REPO_BACKEND", "sqlalchemy")
    monkeypatch.setenv("AICRM_PHASE4AK_STAGING_SMOKE_APPROVED", "1")

    report = preflight.run_preflight(
        closure_status_file=str(status_file),
        read_only=True,
        confirm_no_production=True,
        confirm_no_external_calls=True,
    )

    assert report["ready_for_phase_4am_staging_execution"] is True
    assert report["production_data_connected"] is False
    assert report["staging_smoke_executed"] is False
    assert report["writes_attempted"] is False
    assert report["lower_runner_called"] is False
    assert report["route_owner_changed"] is False
    assert report["production_compat_changed"] is False


def test_preflight_tool_does_not_connect_db() -> None:
    text_body = PREFLIGHT.read_text(encoding="utf-8")
    for forbidden in ("create_engine", "psycopg", "connect("):
        assert forbidden not in text_body


def test_preflight_tool_does_not_call_phase4aj_or_phase4ak_runner() -> None:
    text_body = PREFLIGHT.read_text(encoding="utf-8")
    assert "run_phase4aj_action_templates_staging_smoke" not in text_body
    assert "run_phase4ak_action_templates_staging_smoke_evidence" not in text_body


def test_phase_4am_constraints_forbid_risky_scope() -> None:
    data = checker.load_yaml(YAML)
    assert all(data["phase_4am_constraints"][field] is True for field in checker.PHASE_4AM_CONSTRAINTS)


def test_docs_do_not_claim_forbidden_states() -> None:
    text_body = DOC.read_text(encoding="utf-8").lower()
    forbidden_patterns = [
        r"staging smoke executed",
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
        assert not re.search(pattern, text_body), pattern


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
