from __future__ import annotations

import json
import os
import subprocess
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools/check_phase4k_profile_segment_template_local_parity_harness.py"
HARNESS = ROOT / "tools/run_phase4k_profile_segment_template_local_parity.py"
PLAN_YAML = ROOT / "docs/development/phase_4k_profile_segment_template_local_parity_harness.yaml"
PLAN_MD = ROOT / "docs/development/phase_4k_profile_segment_template_local_parity_harness.md"


def _load_yaml() -> dict:
    spec = importlib.util.spec_from_file_location("phase4k_checker", CHECKER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.load_yaml(PLAN_YAML)


def test_checker_current_repo_passes() -> None:
    proc = subprocess.run(
        ["python3", str(CHECKER.relative_to(ROOT))],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout
    assert "overall: PASS" in proc.stdout


def test_yaml_flags_false_and_required_env() -> None:
    data = _load_yaml()
    for field in (
        "production_data_allowed",
        "production_repository_enablement_authorized",
        "production_route_ownership_switch_authorized",
        "fallback_removal_authorized",
        "production_compat_change_authorized",
        "real_external_call_authorized",
        "delete_ready",
    ):
        assert data[field] is False
    assert "AICRM_NEXT_TEST_DATABASE_URL" in data["required_env"]
    assert data["db_url_safety"]["require_test_local_tmp_dev_marker"] is True
    assert data["db_url_safety"]["forbidden_fallback_to_database_url"] is True


def test_harness_matrix_complete() -> None:
    data = _load_yaml()
    assert set(data["harness_matrix"]["read"]) >= {"catalog", "list", "options", "detail"}
    assert set(data["harness_matrix"]["write"]) >= {
        "create_idempotency_replay",
        "create_idempotency_conflict",
        "duplicate_template",
        "update_existing",
        "update_missing",
        "invalid_payload",
        "dangerous_field_rejection",
        "audit_log_shape",
        "rollback_payload_shape",
    }


def test_harness_refuses_unsafe_production_looking_url(tmp_path: Path) -> None:
    output = tmp_path / "unsafe.json"
    env = {
        **os.environ,
        "AICRM_NEXT_TEST_DATABASE_URL": "postgresql://user:pass@db.example.com/aicrm_prod",
    }
    proc = subprocess.run(
        ["python3", str(HARNESS.relative_to(ROOT)), "--output-json", str(output)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert proc.returncode == 1
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["ok"] is False
    assert data["db_url_safety"]["ok"] is False
    assert data["db_url_safety"]["connected"] is False
    assert data["production_data_used"] is False


def test_harness_does_not_fallback_to_database_url(tmp_path: Path) -> None:
    output = tmp_path / "missing.json"
    env = {**os.environ, "DATABASE_URL": "sqlite+pysqlite:////tmp/phase4k_local_fallback_test.db"}
    env.pop("AICRM_NEXT_TEST_DATABASE_URL", None)
    proc = subprocess.run(
        ["python3", str(HARNESS.relative_to(ROOT)), "--output-json", str(output)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert proc.returncode == 1
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["db_url_safety"]["reason"] == "AICRM_NEXT_TEST_DATABASE_URL is required"
    assert data["db_url_safety"]["connected"] is False


def test_no_runtime_files_changed_if_git_available() -> None:
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
    assert not any(path.startswith("aicrm_next/") for path in changed)
    assert not any(path.startswith("wecom_ability_service/") for path in changed)
    assert not any(path.startswith("migrations/") for path in changed)
    assert "app.py" not in changed
    assert "legacy_flask_app.py" not in changed


def test_docs_do_not_claim_forbidden_states() -> None:
    text = PLAN_MD.read_text(encoding="utf-8").lower()
    for forbidden in (
        "production data used",
        "production repository enabled",
        "route switch authorized",
        "fallback removal authorized",
        "smoke executed",
        "production approved",
        "canary approved",
        "delete_ready true",
    ):
        assert forbidden not in text
