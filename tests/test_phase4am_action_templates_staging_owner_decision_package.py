from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools/check_phase4am_action_templates_staging_owner_decision_package.py"
DOC = ROOT / "docs/development/phase_4am_action_templates_staging_owner_decision_package.md"
YAML = ROOT / "docs/development/phase_4am_action_templates_staging_owner_decision_package.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)


def _load_checker():
    spec = importlib.util.spec_from_file_location("phase4am_owner_decision_checker", CHECKER)
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


def test_owner_decision_package_is_manual_only() -> None:
    data = _load_yaml()
    package = data["package"]
    assert package["type"] == "owner_decision"
    assert package["auto_merge_allowed"] is False
    assert package["autopilot_safe_label_allowed"] is False
    assert {"owner-decision-required", "automerge-blocked"} <= set(package["required_labels"])


def test_missing_owner_decisions_and_config_complete() -> None:
    checker = _load_checker()
    data = _load_yaml()
    assert checker.MISSING_OWNER_DECISIONS <= set(data["missing_owner_decisions"])
    assert checker.MISSING_CONFIG <= set(data["missing_config"])


def test_safe_next_options_complete() -> None:
    checker = _load_checker()
    assert checker.SAFE_OPTIONS <= set(_load_yaml()["safe_next_options"])


def test_authorizations_all_false() -> None:
    data = _load_yaml()
    for value in data["authorizations"].values():
        assert value is False


def test_phase_execution_state_marks_owner_decision_required() -> None:
    data = _load_yaml()
    state = _load_yaml(STATE)
    state_update = data["phase_execution_state_update"]
    assert state["last_attempted_action"] == state_update["last_attempted_action"]
    assert state["last_created_pr"] == state_update["last_created_pr"]
    assert state["recommended_next_pr"] == state_update["recommended_next_pr"]
    assert state["owner_approval_required"] is True
    assert state["action_templates_readiness"]["owner_decision_required"] is True


def test_next_action_forbids_automerge_and_production_steps() -> None:
    next_action = _load_yaml()["next_action"]
    assert next_action["user_must_choose_next_safe_path"] is True
    assert next_action["production_dry_run_allowed"] is False
    assert next_action["production_route_switch_allowed"] is False
    assert next_action["fallback_removal_allowed"] is False
    assert next_action["auto_merge_allowed"] is False


def test_docs_do_not_claim_forbidden_states_or_autopilot_safe() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden = [
        "staging smoke executed",
        "production dry-run executed",
        "production approved",
        "canary approved",
        "delete_ready true",
        "delete_ready: true",
        "route_switch_ready=true",
        "autopilot-safe",
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
