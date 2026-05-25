from __future__ import annotations

import json
import subprocess
from pathlib import Path

import tools.check_phase5e_wecom_tag_production_canary_readiness as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_5e_wecom_tag_production_canary_readiness.md"
PLAN_YAML = ROOT / "docs/development/phase_5e_wecom_tag_production_canary_readiness.yaml"
RUNNER = ROOT / "tools/run_phase5e_wecom_tag_production_canary_readiness.py"


def _clear_env(monkeypatch) -> None:
    for name in (
        "AICRM_PHASE5E_WECOM_TAG_PRODUCTION_CANARY_PLANNING_APPROVED",
        "AICRM_PHASE5E_WECOM_TAG_PRODUCTION_CONFIG_REVIEWED",
        "AICRM_PHASE5E_WECOM_TAG_ROLLBACK_OWNER_APPROVED",
        "AICRM_PHASE5E_WECOM_TAG_TARGET_POLICY_REVIEWED",
    ):
        monkeypatch.delenv(name, raising=False)


def _set_all_env(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_PHASE5E_WECOM_TAG_PRODUCTION_CANARY_PLANNING_APPROVED", "1")
    monkeypatch.setenv("AICRM_PHASE5E_WECOM_TAG_PRODUCTION_CONFIG_REVIEWED", "1")
    monkeypatch.setenv("AICRM_PHASE5E_WECOM_TAG_ROLLBACK_OWNER_APPROVED", "1")
    monkeypatch.setenv("AICRM_PHASE5E_WECOM_TAG_TARGET_POLICY_REVIEWED", "1")


def _valid_staging_evidence(path: Path) -> Path:
    data = {
        "ok": True,
        "mode": "phase5d_staging_live_canary",
        "result_status": "staging_canary_live_evidence_completed",
        "live_call_executed": True,
        "production_live_call_executed": False,
        "production_tag_write_executed": False,
        "external_userid_redacted": "exte***c123",
        "side_effect_safety": {
            "production_live_call_executed": False,
            "production_tag_write_executed": False,
            "outbound_send_executed": False,
        },
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _run(tmp_path: Path, args: list[str]) -> dict:
    output = tmp_path / "phase5e.json"
    proc = subprocess.run(
        ["python3", str(RUNNER), *args, "--output-json", str(output)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(output.read_text(encoding="utf-8"))


def test_checker_current_repo_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)
    assert report["autopilot_deliverable"] is True


def test_readiness_runner_default_blocked(tmp_path: Path, monkeypatch) -> None:
    _clear_env(monkeypatch)
    data = _run(tmp_path, [])
    assert data["result_status"] == "not_executed_missing_staging_evidence"
    assert data["ready_for_phase5f_production_canary_execution"] is False
    assert data["production_live_call_executed"] is False
    assert data["production_tag_write_executed"] is False


def test_missing_staging_evidence_returns_blocked(tmp_path: Path, monkeypatch) -> None:
    _clear_env(monkeypatch)
    data = _run(
        tmp_path,
        [
            "--staging-evidence-json",
            str(tmp_path / "missing.json"),
            "--confirm-no-production-live-call",
            "--confirm-no-production-tag-write",
        ],
    )
    assert data["result_status"] == "not_executed_missing_staging_evidence"


def test_invalid_staging_evidence_returns_blocked(tmp_path: Path, monkeypatch) -> None:
    _clear_env(monkeypatch)
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{not json", encoding="utf-8")
    data = _run(
        tmp_path,
        [
            "--staging-evidence-json",
            str(invalid),
            "--confirm-no-production-live-call",
            "--confirm-no-production-tag-write",
        ],
    )
    assert data["result_status"] == "not_executed_invalid_staging_evidence"


def test_missing_approvals_return_blocked(tmp_path: Path, monkeypatch) -> None:
    _clear_env(monkeypatch)
    evidence = _valid_staging_evidence(tmp_path / "staging.json")
    data = _run(
        tmp_path,
        [
            "--staging-evidence-json",
            str(evidence),
            "--confirm-no-production-live-call",
            "--confirm-no-production-tag-write",
        ],
    )
    assert data["result_status"] == "not_executed_missing_production_canary_planning_approval"


def test_missing_no_production_confirm_flags_return_blocked(tmp_path: Path, monkeypatch) -> None:
    _clear_env(monkeypatch)
    _set_all_env(monkeypatch)
    evidence = _valid_staging_evidence(tmp_path / "staging.json")
    data = _run(tmp_path, ["--staging-evidence-json", str(evidence)])
    assert data["result_status"] == "not_executed_missing_confirm_no_production_live_call"
    data = _run(tmp_path, ["--staging-evidence-json", str(evidence), "--confirm-no-production-live-call"])
    assert data["result_status"] == "not_executed_missing_confirm_no_production_tag_write"


def test_runner_never_imports_or_calls_live_wecom_gateway() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    for forbidden in (
        "wecom_tag_live_gateway",
        "wecom_tag_live_adapter",
        "build_live_wecom_tag_adapter",
        "mark_tags_live",
        "unmark_tags_live",
        "urlopen",
        "externalcontact/mark_tag",
    ):
        assert forbidden not in text


def test_ready_case_still_never_executes_production_live_call(tmp_path: Path, monkeypatch) -> None:
    _clear_env(monkeypatch)
    _set_all_env(monkeypatch)
    evidence = _valid_staging_evidence(tmp_path / "staging.json")
    data = _run(
        tmp_path,
        [
            "--staging-evidence-json",
            str(evidence),
            "--confirm-no-production-live-call",
            "--confirm-no-production-tag-write",
        ],
    )
    assert data["ready_for_phase5f_production_canary_execution"] is True
    assert data["production_live_call_executed"] is False
    assert data["production_tag_write_executed"] is False
    assert data["route_owner_changed"] is False


def test_target_policy_forbids_batch_target() -> None:
    data = checker.load_yaml(PLAN_YAML)
    policy = data["production_target_policy"]
    assert policy["single_target_only"] is True
    assert policy["single_tag_only"] is True
    assert policy["batch_targets_allowed"] is False
    assert policy["customer_pool_target_allowed"] is False
    assert policy["automatic_segment_target_allowed"] is False


def test_rollback_policy_requires_explicit_approval() -> None:
    data = checker.load_yaml(PLAN_YAML)
    policy = data["rollback_policy"]
    assert policy["rollback_owner_required"] is True
    assert policy["cleanup_requires_explicit_approval"] is True
    assert policy["cleanup_limited_to_same_target_and_same_tag"] is True
    assert policy["automatic_cleanup_allowed"] is False
    assert policy["batch_cleanup_allowed"] is False


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    for phrase in checker.FORBIDDEN_DOC_CLAIMS:
        assert phrase not in text
