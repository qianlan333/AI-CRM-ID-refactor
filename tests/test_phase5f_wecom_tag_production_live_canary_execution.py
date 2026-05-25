from __future__ import annotations

import json
import subprocess
from pathlib import Path

import tools.check_phase5f_wecom_tag_production_live_canary_execution as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_5f_wecom_tag_production_live_canary_execution.md"
CANARY_RUNNER = ROOT / "tools/run_phase5f_wecom_tag_production_live_canary_execution.py"
CLEANUP_RUNNER = ROOT / "tools/run_phase5f_wecom_tag_production_canary_cleanup.py"


def _clear_env(monkeypatch) -> None:
    for name in (
        "AICRM_WECOM_TAG_LIVE_ADAPTER_ENABLED",
        "AICRM_WECOM_TAG_LIVE_CALL_APPROVED",
        "AICRM_WECOM_TAG_CONFIG_REVIEWED",
        "AICRM_PHASE5F_WECOM_TAG_PRODUCTION_CANARY_APPROVED",
        "AICRM_PHASE5F_WECOM_TAG_PRODUCTION_TARGET_APPROVED",
        "AICRM_PHASE5F_WECOM_TAG_ROLLBACK_OWNER_APPROVED",
        "AICRM_PHASE5F_WECOM_TAG_CLEANUP_STRATEGY_APPROVED",
        "AICRM_PHASE5F_WECOM_TAG_PRODUCTION_CLEANUP_APPROVED",
        "AICRM_WECOM_TAG_CORP_ID",
        "AICRM_WECOM_TAG_AGENT_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)


def _set_canary_env(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_WECOM_TAG_LIVE_ADAPTER_ENABLED", "1")
    monkeypatch.setenv("AICRM_WECOM_TAG_LIVE_CALL_APPROVED", "1")
    monkeypatch.setenv("AICRM_WECOM_TAG_CONFIG_REVIEWED", "1")
    monkeypatch.setenv("AICRM_PHASE5F_WECOM_TAG_PRODUCTION_CANARY_APPROVED", "1")
    monkeypatch.setenv("AICRM_PHASE5F_WECOM_TAG_PRODUCTION_TARGET_APPROVED", "1")
    monkeypatch.setenv("AICRM_PHASE5F_WECOM_TAG_ROLLBACK_OWNER_APPROVED", "1")
    monkeypatch.setenv("AICRM_PHASE5F_WECOM_TAG_CLEANUP_STRATEGY_APPROVED", "1")
    monkeypatch.setenv("AICRM_WECOM_TAG_CORP_ID", "corp")
    monkeypatch.setenv("AICRM_WECOM_TAG_AGENT_SECRET", "secret")


def _phase5e_ready(path: Path) -> Path:
    data = {
        "ok": True,
        "mode": "production_canary_readiness",
        "result_status": "ready_for_phase5f_production_canary_execution",
        "ready_for_phase5f_production_canary_execution": True,
        "production_live_call_executed": False,
        "production_tag_write_executed": False,
        "staging_evidence_summary": {"external_userid_redacted": "exte...c123"},
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _staging_evidence(path: Path) -> Path:
    data = {
        "ok": True,
        "mode": "phase5d_staging_live_canary",
        "result_status": "staging_canary_live_evidence_completed",
        "external_userid_redacted": "exte...c123",
        "production_live_call_executed": False,
        "side_effect_safety": {"outbound_send_executed": False},
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _canary_evidence(path: Path, *, valid: bool = True) -> Path:
    data = {
        "ok": True,
        "mode": "production_live_canary_execution",
        "result_status": "production_live_canary_completed",
        "production_live_call_executed": True,
        "production_tag_write_executed": True,
        "external_userid_redacted": "exte...c123",
        "tag_id": "tag_contract_001",
        "idempotency_key": "phase5f-test",
    }
    if not valid:
        data.pop("tag_id")
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _run_canary(tmp_path: Path, args: list[str]) -> dict:
    output = tmp_path / "canary.json"
    proc = subprocess.run(
        ["python3", str(CANARY_RUNNER), *args, "--output-json", str(output)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(output.read_text(encoding="utf-8"))


def _run_cleanup(tmp_path: Path, args: list[str]) -> dict:
    output = tmp_path / "cleanup.json"
    proc = subprocess.run(
        ["python3", str(CLEANUP_RUNNER), *args, "--output-json", str(output)],
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


def test_canary_runner_default_blocked(tmp_path: Path, monkeypatch) -> None:
    _clear_env(monkeypatch)
    data = _run_canary(tmp_path, [])
    assert data["result_status"] == "not_executed_missing_phase5e_readiness"
    assert data["production_live_call_executed"] is False
    assert data["production_tag_write_executed"] is False


def test_missing_phase5e_readiness_returns_blocked(tmp_path: Path, monkeypatch) -> None:
    _clear_env(monkeypatch)
    data = _run_canary(tmp_path, ["--phase5e-readiness-json", str(tmp_path / "missing.json")])
    assert data["result_status"] == "not_executed_missing_phase5e_readiness"


def test_missing_staging_evidence_returns_blocked(tmp_path: Path, monkeypatch) -> None:
    _clear_env(monkeypatch)
    phase5e = _phase5e_ready(tmp_path / "phase5e.json")
    data = _run_canary(tmp_path, ["--phase5e-readiness-json", str(phase5e)])
    assert data["result_status"] == "not_executed_missing_staging_evidence"


def test_missing_approvals_return_blocked(tmp_path: Path, monkeypatch) -> None:
    _clear_env(monkeypatch)
    phase5e = _phase5e_ready(tmp_path / "phase5e.json")
    staging = _staging_evidence(tmp_path / "staging.json")
    data = _run_canary(tmp_path, ["--phase5e-readiness-json", str(phase5e), "--staging-evidence-json", str(staging)])
    assert data["result_status"] == "not_executed_missing_canary_approval"


def test_missing_target_idempotency_and_confirm_flags_return_blocked(tmp_path: Path, monkeypatch) -> None:
    _clear_env(monkeypatch)
    _set_canary_env(monkeypatch)
    phase5e = _phase5e_ready(tmp_path / "phase5e.json")
    staging = _staging_evidence(tmp_path / "staging.json")
    base = ["--phase5e-readiness-json", str(phase5e), "--staging-evidence-json", str(staging)]
    data = _run_canary(tmp_path, base)
    assert data["result_status"] == "not_executed_missing_external_userid"
    data = _run_canary(tmp_path, [*base, "--external-userid", "external_userid_abc123"])
    assert data["result_status"] == "not_executed_missing_tag_id"
    data = _run_canary(tmp_path, [*base, "--external-userid", "external_userid_abc123", "--tag-id", "tag_contract_001"])
    assert data["result_status"] == "not_executed_missing_idempotency_key"
    data = _run_canary(
        tmp_path,
        [*base, "--external-userid", "external_userid_abc123", "--tag-id", "tag_contract_001", "--idempotency-key", "key"],
    )
    assert data["result_status"] == "not_executed_missing_confirm_production_live_call"


def test_batch_targets_rejected(tmp_path: Path, monkeypatch) -> None:
    _clear_env(monkeypatch)
    _set_canary_env(monkeypatch)
    phase5e = _phase5e_ready(tmp_path / "phase5e.json")
    staging = _staging_evidence(tmp_path / "staging.json")
    data = _run_canary(
        tmp_path,
        [
            "--phase5e-readiness-json",
            str(phase5e),
            "--staging-evidence-json",
            str(staging),
            "--external-userid",
            "external_userid_abc123",
            "--tag-id",
            "tag_contract_001",
            "--tag-id",
            "tag_contract_002",
            "--idempotency-key",
            "key",
        ],
    )
    assert data["result_status"] == "not_executed_missing_confirm_no_batch"


def test_cleanup_runner_default_blocked(tmp_path: Path, monkeypatch) -> None:
    _clear_env(monkeypatch)
    data = _run_cleanup(tmp_path, [])
    assert data["result_status"] == "not_executed_missing_canary_evidence"
    assert data["cleanup_executed"] is False
    assert data["unmark_tag_executed"] is False
    assert data["batch_cleanup_executed"] is False


def test_cleanup_requires_same_target_tag_evidence(tmp_path: Path, monkeypatch) -> None:
    _clear_env(monkeypatch)
    evidence = _canary_evidence(tmp_path / "canary.json", valid=False)
    data = _run_cleanup(tmp_path, ["--canary-evidence-json", str(evidence)])
    assert data["result_status"] == "not_executed_invalid_canary_evidence"


def test_no_outbound_send_and_production_compat_unchanged_tokens_present() -> None:
    text = CANARY_RUNNER.read_text(encoding="utf-8") + CLEANUP_RUNNER.read_text(encoding="utf-8")
    assert "outbound_send_executed" in text
    assert "production_compat_changed" in text
    assert "route_owner_changed" in text
    assert "create_group_message_task" not in text


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    for phrase in checker.FORBIDDEN_DOC_CLAIMS:
        assert phrase not in text
