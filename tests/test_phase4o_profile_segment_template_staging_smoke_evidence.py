from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools/check_phase4o_profile_segment_template_staging_smoke_evidence.py"
RUNNER = ROOT / "tools/run_phase4o_profile_segment_template_staging_smoke_evidence.py"
PLAN_YAML = ROOT / "docs/development/phase_4o_profile_segment_template_staging_smoke_evidence.yaml"
PLAN_MD = ROOT / "docs/development/phase_4o_profile_segment_template_staging_smoke_evidence.md"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_yaml() -> dict:
    return _load_module(CHECKER, "phase4o_checker").load_yaml(PLAN_YAML)


def _run_runner(tmp_path: Path, env: dict[str, str], *extra_args: str) -> dict:
    output = tmp_path / "phase4o.json"
    proc = subprocess.run(
        ["python3", str(RUNNER.relative_to(ROOT)), *extra_args, "--output-json", str(output)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    data = json.loads(output.read_text(encoding="utf-8"))
    data["_returncode"] = proc.returncode
    data["_stdout"] = proc.stdout
    return data


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


def test_evidence_tool_refuses_missing_staging_db(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.pop("AICRM_PROFILE_SEGMENT_TEMPLATE_STAGING_DATABASE_URL", None)
    env.pop("DATABASE_URL", None)
    data = _run_runner(tmp_path, env)
    assert data["_returncode"] == 1
    assert data["execution"]["result_status"] == "not_executed_missing_staging_db"
    assert data["db_url_safety"]["checked"] is True
    assert data["db_url_safety"]["secret_redacted"] is True
    assert data["production_data_used"] is False


def test_evidence_tool_refuses_production_looking_url(tmp_path: Path) -> None:
    env = {
        **os.environ,
        "AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND": "sqlalchemy",
        "AICRM_PROFILE_SEGMENT_TEMPLATE_STAGING_DATABASE_URL": "postgresql://user:topsecret@db/aicrm_production",
    }
    data = _run_runner(tmp_path, env)
    assert data["_returncode"] == 1
    assert data["execution"]["result_status"] == "not_executed_db_url_safety_failed"
    assert data["db_url_safety"]["forbidden_marker_present"] is True
    assert "topsecret" not in json.dumps(data["db_url_safety"])
    assert data["db_url_safety"]["redacted_url"] == "postgresql://<redacted>@db/aicrm_production"


def test_evidence_tool_refuses_write_smoke_without_approval(tmp_path: Path) -> None:
    env = {
        **os.environ,
        "AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND": "sqlalchemy",
        "AICRM_PROFILE_SEGMENT_TEMPLATE_STAGING_DATABASE_URL": "postgresql://user:topsecret@db/staging_ai_crm",
    }
    env.pop("AICRM_PHASE4O_STAGING_WRITE_APPROVED", None)
    data = _run_runner(tmp_path, env, "--execute-writes")
    assert data["_returncode"] == 1
    assert data["execution"]["result_status"] == "not_executed_missing_approval"
    assert data["execution"]["write_smoke_attempted"] is False
    assert data["execution"]["write_smoke_owner_approved"] is False
    assert data["db_url_safety"]["safe"] is True
    assert "topsecret" not in json.dumps(data["db_url_safety"])


def test_yaml_flags_false_and_side_effect_safety_false() -> None:
    data = _load_yaml()
    for field in (
        "production_data_used",
        "production_repository_enablement_authorized",
        "production_route_ownership_switch_authorized",
        "fallback_removal_authorized",
        "production_compat_change_authorized",
        "production_dry_run_authorized",
        "production_write_canary_authorized",
        "real_external_call_authorized",
        "delete_ready",
    ):
        assert data[field] is False
    assert all(value is False for value in data["side_effect_safety"].values())


def test_phase4p_recommendation_blocks_unsafe_next_steps() -> None:
    rec = _load_yaml()["phase_4p_recommendation"]
    assert rec["recommended_next_step"]
    assert rec["production_dry_run_allowed"] is False
    assert rec["production_route_switch_allowed"] is False
    assert rec["production_write_canary_allowed"] is False


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
        "production dry-run authorized",
        "production repository enabled",
        "route switch authorized",
        "fallback removal authorized",
        "production approved",
        "canary approved",
        "delete_ready true",
    ):
        assert forbidden not in text
