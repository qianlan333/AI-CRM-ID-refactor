from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools/check_phase4am_action_templates_staging_approval_config_closure.py"
DOC = ROOT / "docs/development/phase_4am_action_templates_staging_approval_config_closure.md"
YAML = ROOT / "docs/development/phase_4am_action_templates_staging_approval_config_closure.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def _load_checker():
    spec = importlib.util.spec_from_file_location("phase4am_closure_checker", CHECKER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_yaml(path: Path = YAML) -> dict:
    return _load_checker().load_yaml(path)


def test_checker_current_repo_passes() -> None:
    proc = _run([sys.executable, str(CHECKER)])
    assert proc.returncode == 0, proc.stdout
    assert "overall: PASS" in proc.stdout


def test_authorizations_all_false() -> None:
    data = _load_yaml()
    for value in data["authorizations"].values():
        assert value is False


def test_blocked_evidence_folded_into_closure_package() -> None:
    checker = _load_checker()
    summary = _load_yaml()["blocked_evidence_summary"]
    assert summary["standalone_blocked_evidence_review_repeated"] is False
    assert summary["folded_into_closure_package"] is True
    assert checker.REQUIRED_BLOCKERS <= set(summary["blockers"])


def test_owner_and_config_closure_forms_default_pending() -> None:
    checker = _load_checker()
    data = _load_yaml()
    for field in checker.OWNER_CLOSURE_FIELDS:
        assert data["owner_closure_form"][field] == "pending"
    for field in checker.CONFIG_CLOSURE_FIELDS:
        assert data["config_closure_form"][field] == "pending"


def test_db_url_safety_rules_complete() -> None:
    checker = _load_checker()
    safety = _load_yaml()["db_url_safety"]
    assert safety["required_env"] == "AICRM_ACTION_TEMPLATES_STAGING_DATABASE_URL"
    assert safety["repo_backend_required_value"] == "sqlalchemy"
    assert checker.ALLOWED_MARKERS <= set(safety["allowed_markers"])
    assert checker.FORBIDDEN_MARKERS <= set(safety["forbidden_markers"])
    assert checker.FORBIDDEN_FALLBACK_ENV <= set(safety["forbidden_fallback_env"])


def test_evidence_requirements_do_not_claim_production_readiness() -> None:
    evidence = _load_yaml()["evidence_requirements"]
    assert evidence["raw_secret_export_allowed"] is False
    assert evidence["raw_pii_export_allowed"] is False
    assert evidence["staging_evidence_is_production_approval"] is False
    assert evidence["staging_evidence_is_route_switch_readiness"] is False
    assert evidence["staging_evidence_is_canary_approval"] is False


def test_resume_gate_blocks_production_and_staging_execution_by_default() -> None:
    gate = _load_yaml()["phase_4am_resume_gate"]
    assert gate["ready_for_staging_smoke_execution"] is False
    assert gate["production_dry_run_allowed"] is False
    assert gate["production_route_switch_allowed"] is False
    assert gate["fallback_removal_allowed"] is False
    assert gate["production_write_allowed"] is False


def test_phase_execution_state_matches_closure_package() -> None:
    data = _load_yaml()
    state = _load_yaml(STATE)
    state_update = data["phase_execution_state_update"]
    assert state["last_attempted_action"] == state_update["last_attempted_action"]
    assert state["last_created_pr"] == state_update["last_created_pr"]
    assert state["recommended_next_pr"] == state_update["recommended_next_pr"]
    assert state["owner_approval_required"] is True


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden = [
        "staging smoke executed",
        "production dry-run executed",
        "production approved",
        "canary approved",
        "delete_ready true",
        "delete_ready: true",
        "route_switch_ready=true",
    ]
    for phrase in forbidden:
        assert phrase not in text


def test_no_runtime_files_changed_if_git_diff_available() -> None:
    changed = set()
    for command in (
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        ["git", "diff", "--name-only", "--cached"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ):
        proc = _run(command)
        if proc.returncode != 0:
            continue
        changed.update(line.strip() for line in proc.stdout.splitlines() if line.strip())
    protected = {
        path
        for path in changed
        if path in {"app.py", "legacy_flask_app.py"}
        or any(path.startswith(prefix) for prefix in ("aicrm_next/", "wecom_ability_service/", "migrations/", "deploy/", "systemd/", "nginx/"))
    }
    assert protected == set()
