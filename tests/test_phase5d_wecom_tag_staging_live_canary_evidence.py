from __future__ import annotations

import json
import subprocess
from pathlib import Path

import tools.check_phase5d_wecom_tag_staging_live_canary_evidence as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_5d_wecom_tag_staging_live_canary_evidence.md"
STAGING_RUNNER = ROOT / "tools/run_phase5d_wecom_tag_staging_live_canary_evidence.py"
PRODUCTION_REVIEW_RUNNER = ROOT / "tools/run_phase5d_wecom_tag_production_live_readiness_review.py"


def _clear_env(monkeypatch) -> None:
    for name in (
        "AICRM_WECOM_TAG_LIVE_ADAPTER_ENABLED",
        "AICRM_WECOM_TAG_LIVE_CALL_APPROVED",
        "AICRM_WECOM_TAG_CONFIG_REVIEWED",
        "AICRM_PHASE5D_WECOM_TAG_STAGING_CANARY_APPROVED",
        "AICRM_PHASE5D_WECOM_TAG_STAGING_CANARY_TARGET_APPROVED",
        "AICRM_WECOM_TAG_CORP_ID",
        "AICRM_WECOM_TAG_AGENT_SECRET",
        "AICRM_PHASE5C_WECOM_TAG_STAGING_LIVE_APPROVED",
    ):
        monkeypatch.delenv(name, raising=False)


def _set_all_phase5d_env(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_WECOM_TAG_LIVE_ADAPTER_ENABLED", "1")
    monkeypatch.setenv("AICRM_WECOM_TAG_LIVE_CALL_APPROVED", "1")
    monkeypatch.setenv("AICRM_WECOM_TAG_CONFIG_REVIEWED", "1")
    monkeypatch.setenv("AICRM_PHASE5D_WECOM_TAG_STAGING_CANARY_APPROVED", "1")
    monkeypatch.setenv("AICRM_PHASE5D_WECOM_TAG_STAGING_CANARY_TARGET_APPROVED", "1")
    monkeypatch.setenv("AICRM_WECOM_TAG_CORP_ID", "corp")
    monkeypatch.setenv("AICRM_WECOM_TAG_AGENT_SECRET", "secret")


def _run_staging(tmp_path: Path, args: list[str], monkeypatch) -> dict:
    output = tmp_path / "phase5d_staging.json"
    proc = subprocess.run(
        ["python3", str(STAGING_RUNNER), *args, "--output-json", str(output)],
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


def test_staging_runner_default_blocked(tmp_path: Path, monkeypatch) -> None:
    _clear_env(monkeypatch)
    data = _run_staging(tmp_path, [], monkeypatch)
    assert data["result_status"] == "not_executed_missing_live_adapter_enabled"
    assert data["live_call_executed"] is False
    assert data["mark_tag_executed"] is False
    assert data["unmark_tag_executed"] is False
    assert data["outbound_send_executed"] is False


def test_missing_approvals_return_blocked_statuses(tmp_path: Path, monkeypatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("AICRM_WECOM_TAG_LIVE_ADAPTER_ENABLED", "1")
    data = _run_staging(tmp_path, [], monkeypatch)
    assert data["result_status"] == "not_executed_missing_live_call_approval"
    monkeypatch.setenv("AICRM_WECOM_TAG_LIVE_CALL_APPROVED", "1")
    data = _run_staging(tmp_path, [], monkeypatch)
    assert data["result_status"] == "not_executed_missing_config_review"


def test_missing_target_returns_blocked(tmp_path: Path, monkeypatch) -> None:
    _clear_env(monkeypatch)
    _set_all_phase5d_env(monkeypatch)
    data = _run_staging(tmp_path, ["--execute-staging-canary"], monkeypatch)
    assert data["result_status"] == "not_executed_missing_external_userid"
    data = _run_staging(tmp_path, ["--execute-staging-canary", "--external-userid", "external_userid_abc123"], monkeypatch)
    assert data["result_status"] == "not_executed_missing_tag_id"


def test_missing_idempotency_key_returns_blocked(tmp_path: Path, monkeypatch) -> None:
    _clear_env(monkeypatch)
    _set_all_phase5d_env(monkeypatch)
    data = _run_staging(
        tmp_path,
        ["--execute-staging-canary", "--external-userid", "external_userid_abc123", "--tag-id", "tag_contract_001"],
        monkeypatch,
    )
    assert data["result_status"] == "not_executed_missing_idempotency_key"


def test_missing_confirm_flags_return_blocked(tmp_path: Path, monkeypatch) -> None:
    _clear_env(monkeypatch)
    _set_all_phase5d_env(monkeypatch)
    base = [
        "--execute-staging-canary",
        "--external-userid",
        "external_userid_abc123",
        "--tag-id",
        "tag_contract_001",
        "--idempotency-key",
        "phase5d-test",
    ]
    data = _run_staging(tmp_path, base, monkeypatch)
    assert data["result_status"] == "not_executed_missing_confirm_live_call"
    data = _run_staging(tmp_path, [*base, "--confirm-live-wecom-call"], monkeypatch)
    assert data["result_status"] == "not_executed_missing_confirm_staging_only"
    data = _run_staging(tmp_path, [*base, "--confirm-live-wecom-call", "--confirm-staging-only"], monkeypatch)
    assert data["result_status"] == "not_executed_missing_confirm_approved_target"


def test_batch_targets_rejected_by_default(tmp_path: Path, monkeypatch) -> None:
    _clear_env(monkeypatch)
    _set_all_phase5d_env(monkeypatch)
    data = _run_staging(
        tmp_path,
        [
            "--execute-staging-canary",
            "--external-userid",
            "external_userid_abc123",
            "--tag-id",
            "tag_contract_001",
            "--tag-id",
            "tag_contract_002",
            "--idempotency-key",
            "phase5d-test",
        ],
        monkeypatch,
    )
    assert data["result_status"] == "not_executed_batch_target_rejected"


def test_evidence_redacts_external_userid(tmp_path: Path, monkeypatch) -> None:
    _clear_env(monkeypatch)
    _set_all_phase5d_env(monkeypatch)
    data = _run_staging(
        tmp_path,
        [
            "--execute-staging-canary",
            "--external-userid",
            "external_userid_abc123",
            "--tag-id",
            "tag_contract_001",
            "--idempotency-key",
            "phase5d-test",
        ],
        monkeypatch,
    )
    assert data["external_userid_redacted"] != "external_userid_abc123"
    assert "abc123" not in json.dumps(data, ensure_ascii=False)
    assert data["requested_tag_ids"] == ["tag_contract_001"]


def test_production_readiness_review_never_calls_wecom(tmp_path: Path, monkeypatch) -> None:
    _clear_env(monkeypatch)
    output = tmp_path / "prod_review.json"
    proc = subprocess.run(
        [
            "python3",
            str(PRODUCTION_REVIEW_RUNNER),
            "--confirm-no-production-live-call",
            "--output-json",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert proc.returncode == 0
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["ready_for_phase5e_production_canary_planning"] is False
    assert data["production_live_call_executed"] is False
    assert data["production_tag_write_executed"] is False
    assert data["route_owner_changed"] is False
    assert "wecom_tag_live_adapter" not in PRODUCTION_REVIEW_RUNNER.read_text(encoding="utf-8")


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    for phrase in checker.FORBIDDEN_DOC_CLAIMS:
        assert phrase not in text
