from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools/check_phase4am_action_templates_staging_wait_and_next_candidate.py"
DOC = ROOT / "docs/development/phase_4am_action_templates_staging_wait_and_next_candidate.md"
YAML = ROOT / "docs/development/phase_4am_action_templates_staging_wait_and_next_candidate.yaml"


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def _load_yaml(path: Path = YAML) -> dict:
    spec = importlib.util.spec_from_file_location("phase4am_checker", CHECKER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.load_yaml(path)


def _items(values: list) -> set[str]:
    result = set()
    for item in values:
        result.add(str(item.get("item") if isinstance(item, dict) else item))
    return result


def test_checker_current_repo_passes() -> None:
    proc = _run([sys.executable, str(CHECKER)])
    assert proc.returncode == 0, proc.stdout
    assert "overall: PASS" in proc.stdout


def test_action_templates_status_is_awaiting_staging_approval_config() -> None:
    action = _load_yaml()["action_templates"]
    assert action["status"] == "awaiting_staging_approval_config"


def test_authorizations_false() -> None:
    data = _load_yaml()
    action = data["action_templates"]
    assert action["staging_smoke_executed"] is False
    assert action["production_route_owner_switch_authorized"] is False
    assert action["fallback_removal_authorized"] is False
    assert action["production_write_authorized"] is False
    assert action["delete_ready"] is False
    for value in data["authorizations"].values():
        assert value is False


def test_completed_assets_include_required_assets() -> None:
    spec = importlib.util.spec_from_file_location("phase4am_checker", CHECKER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    action = _load_yaml()["action_templates"]
    assert module.COMPLETED_ASSETS <= set(action["completed_assets"])


def test_blockers_and_resume_conditions_complete() -> None:
    spec = importlib.util.spec_from_file_location("phase4am_checker", CHECKER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    action = _load_yaml()["action_templates"]
    assert module.BLOCKERS <= set(action["blockers"])
    assert module.RESUME_CONDITIONS <= set(action["resume_conditions"])


def test_next_candidate_selected_and_valid() -> None:
    candidate = _load_yaml()["next_candidate"]
    assert candidate["selected_route_family"] == "/api/admin/automation-conversion/task-groups*"
    assert candidate["capability_owner"] == "aicrm_next.automation_engine"
    assert candidate["replacement_phase"] == "phase_4_internal_write"
    assert candidate["replacement_category"] == "internal_write"
    assert candidate["rollback_requirement"]
    assert candidate["business_continuity_requirement"]


def test_next_candidate_excludes_high_risk_side_effects() -> None:
    candidate = _load_yaml()["next_candidate"]
    excluded = _items(candidate["excluded_side_effects"])
    required = {
        "payment",
        "oauth",
        "wecom external",
        "callback",
        "run-due",
        "timer",
        "execution",
        "send",
        "upload",
        "openclaw",
        "mcp",
        "public submit",
        "external push",
    }
    assert required <= excluded


def test_phase_4an_recommendation_forbids_high_risk_next_steps() -> None:
    rec = _load_yaml()["phase_4an_recommendation"]
    assert rec["recommended_next_step"]
    assert rec["production_write_allowed"] is False
    assert rec["production_route_switch_allowed"] is False
    assert rec["fallback_removal_allowed"] is False
    assert rec["production_write_canary_allowed"] is False


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
        if path not in {
            "docs/development/phase_4am_action_templates_staging_wait_and_next_candidate.md",
            "docs/development/phase_4am_action_templates_staging_wait_and_next_candidate.yaml",
            "tools/check_phase4am_action_templates_staging_wait_and_next_candidate.py",
            "tests/test_phase4am_action_templates_staging_wait_and_next_candidate.py",
            "tools/check_phase4al_action_templates_staging_execution_ready_gate.py",
            "tools/check_phase4ak_action_templates_staging_smoke_evidence.py",
        }
        and (
            path in {"app.py", "legacy_flask_app.py"}
            or any(path.startswith(prefix) for prefix in ("aicrm_next/", "wecom_ability_service/", "migrations/", "deploy/", "systemd/", "nginx/"))
        )
    }
    assert protected == set()


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden = [
        "action-templates staging smoke executed",
        "production dry-run executed",
        "production route switch authorized",
        "fallback removal authorized",
        "production approved",
        "canary approved",
        "delete_ready true",
    ]
    for phrase in forbidden:
        assert phrase not in text
