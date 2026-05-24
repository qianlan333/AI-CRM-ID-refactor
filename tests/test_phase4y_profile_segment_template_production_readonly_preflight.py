from __future__ import annotations

import json
import os
import subprocess
import sys
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools/check_phase4y_profile_segment_template_production_readonly_preflight.py"
TOOL = ROOT / "tools/run_phase4y_profile_segment_template_production_readonly_preflight.py"
DOC = ROOT / "docs/development/phase_4y_profile_segment_template_production_readonly_preflight.md"
YAML = ROOT / "docs/development/phase_4y_profile_segment_template_production_readonly_preflight.yaml"
FALSE_FLAGS = {
    "production_dry_run_execution_authorized",
    "production_data_connection_authorized",
    "production_write_authorized",
    "production_repository_route_enablement_authorized",
    "production_route_ownership_switch_authorized",
    "fallback_removal_authorized",
    "production_compat_change_authorized",
    "production_write_canary_authorized",
    "real_external_call_authorized",
    "delete_ready",
}
CLOSURE_ITEMS = {
    "automation_engine_owner_approval",
    "integration_gateway_owner_approval",
    "db_config_owner_approval",
    "business_owner_approval",
    "rollback_owner_assigned",
    "dry_run_operator_assigned",
    "release_config_reviewer_approval",
    "security_data_reviewer_approval",
    "production_config_review_completed",
    "production_db_env_confirmed",
    "read_only_flags_confirmed",
    "evidence_path_confirmed",
    "fallback_validation_plan_confirmed",
    "secret_redaction_confirmed",
    "pii_redaction_confirmed",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_4y_profile_segment_template_production_readonly_preflight.md",
    "docs/development/phase_4y_profile_segment_template_production_readonly_preflight.yaml",
    "tools/run_phase4y_profile_segment_template_production_readonly_preflight.py",
    "tools/check_phase4y_profile_segment_template_production_readonly_preflight.py",
    "tests/test_phase4y_profile_segment_template_production_readonly_preflight.py",
    "tools/check_phase4x_profile_segment_template_production_readonly_final_gate.py",
    "tools/check_phase4w_profile_segment_template_production_readonly_execution_ready_gate.py",
    "tools/check_phase4v_profile_segment_template_production_readonly_execution_blocker_and_readiness.py",
}
PROTECTED_PREFIXES = (
    "aicrm_next/",
    "wecom_ability_service/",
    "migrations/",
    "deploy/",
    "systemd/",
    "nginx/",
)
PROTECTED_EXACT = {"app.py", "legacy_flask_app.py"}


def _run(command: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        env=merged_env,
    )


def _load_yaml(path: Path) -> dict:
    spec = importlib.util.spec_from_file_location("phase4y_checker", CHECKER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.load_yaml(path)


def test_checker_current_repo_passes() -> None:
    proc = _run([sys.executable, str(CHECKER)])
    assert proc.returncode == 0, proc.stdout
    assert "overall: PASS" in proc.stdout


def test_yaml_top_level_flags_false() -> None:
    data = _load_yaml(YAML)
    for field in FALSE_FLAGS:
        assert data[field] is False


def test_closure_items_complete() -> None:
    data = _load_yaml(YAML)
    closure = data["closure_items"]
    assert set(closure) == CLOSURE_ITEMS
    assert set(closure.values()) == {"pending"}


def test_preflight_tool_does_not_connect_db_or_call_lower_runner() -> None:
    source = TOOL.read_text(encoding="utf-8")
    assert "create_engine" not in source
    assert "from sqlalchemy" not in source
    assert "import sqlalchemy" not in source
    assert "subprocess" not in source
    assert "run_phase4r" not in source
    assert "run_phase4u" not in source


def test_preflight_tool_supports_closure_status_file() -> None:
    source = TOOL.read_text(encoding="utf-8")
    assert "--closure-status-file" in source


def test_default_result_ready_false(tmp_path: Path) -> None:
    output = tmp_path / "default.json"
    proc = _run([sys.executable, str(TOOL), "--output-json", str(output)])
    assert proc.returncode == 0, proc.stdout
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["ready_for_phase_4z_readonly_dry_run_execution"] is False
    assert report["production_data_connected"] is False
    assert report["dry_run_executed"] is False
    assert report["writes_attempted"] is False
    assert report["db_url_secret_redacted"] is True


def test_synthetic_complete_status_can_report_ready_without_execution(tmp_path: Path) -> None:
    status_file = tmp_path / "closure.json"
    status_file.write_text(
        json.dumps({"closure_items": {field: "completed" for field in CLOSURE_ITEMS}}, sort_keys=True),
        encoding="utf-8",
    )
    output = tmp_path / "ready.json"
    env = {
        "AICRM_PHASE4R_PRODUCTION_READONLY_DRY_RUN_APPROVED": "1",
        "AICRM_PHASE4R_PRODUCTION_CONFIG_REVIEWED": "1",
        "AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND": "sqlalchemy",
        "AICRM_PROFILE_SEGMENT_TEMPLATE_PRODUCTION_DATABASE_URL": "postgresql://user:secret@example.internal/app",
    }
    proc = _run(
        [
            sys.executable,
            str(TOOL),
            "--closure-status-file",
            str(status_file),
            "--read-only",
            "--confirm-no-writes",
            "--output-json",
            str(output),
        ],
        env=env,
    )
    assert proc.returncode == 0, proc.stdout
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["ready_for_phase_4z_readonly_dry_run_execution"] is True
    assert report["production_data_connected"] is False
    assert report["dry_run_executed"] is False
    assert report["writes_attempted"] is False
    assert report["route_owner_changed"] is False
    assert report["production_compat_changed"] is False
    assert report["db_url_secret_redacted"] is True
    serialized = json.dumps(report)
    assert "user:secret" not in serialized
    assert "postgresql://user" not in serialized


def test_no_runtime_files_changed_if_git_diff_available() -> None:
    proc = _run(["git", "diff", "--name-only", "origin/main...HEAD"])
    if proc.returncode != 0:
        return
    changed = {line.strip() for line in proc.stdout.splitlines() if line.strip()}
    unexpected = changed - ALLOWED_CHANGED_FILES
    protected = {
        path
        for path in changed
        if path not in ALLOWED_CHANGED_FILES
        and (path in PROTECTED_EXACT or any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES))
    }
    assert unexpected == set()
    assert protected == set()


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden = [
        "production dry-run executed",
        "production data connected",
        "production write executed",
        "production repository enabled as route owner",
        "route switch authorized",
        "fallback removal authorized",
        "production approved",
        "canary approved",
        "delete_ready true",
    ]
    for phrase in forbidden:
        assert phrase not in text
