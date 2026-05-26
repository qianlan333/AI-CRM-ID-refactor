from __future__ import annotations

import argparse
import json
from pathlib import Path

import tools.check_phase5s_oauth_identity_production_live_canary_execution as checker
import tools.run_phase5s_oauth_identity_production_canary_cleanup as cleanup_runner
import tools.run_phase5s_oauth_identity_production_live_canary_execution as canary_runner


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_5s_oauth_identity_production_live_canary_execution.md"


def _canary_args(**overrides):
    values = {
        "phase5r_readiness_json": None,
        "staging_evidence_json": None,
        "state": None,
        "code": None,
        "safe_test_code": None,
        "idempotency_key": None,
        "confirm_production_live_oauth_call": False,
        "confirm_single_approved_callback": False,
        "confirm_no_production_callback_cutover": False,
        "confirm_no_production_session_write": False,
        "confirm_no_production_identity_write": False,
        "confirm_no_token_persistence": False,
        "confirm_rollback_owner_approved": False,
        "confirm_no_batch_replay": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _cleanup_args(**overrides):
    values = {
        "canary_evidence_json": None,
        "confirm_production_cleanup_reviewed": False,
        "confirm_no_production_session_delete": False,
        "confirm_no_production_identity_delete": False,
        "confirm_rollback_owner_approved": False,
        "confirm_no_batch_cleanup": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _phase5r_readiness(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "result_status": "ready_for_phase5s_production_canary_execution",
                "ready_for_phase5s_production_canary_execution": True,
                "production_live_oauth_call_executed": False,
                "production_callback_cutover_executed": False,
                "production_session_write_executed": False,
                "production_identity_write_executed": False,
                "token_persisted": False,
                "staging_evidence_summary": {
                    "redacted_code_present": True,
                    "redacted_state_present": True,
                    "token_redacted": True,
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _staging_evidence(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "result_status": "staging_live_oauth_canary_evidence_completed",
                "redacted_state": "sta***123",
                "redacted_code": "cod***456",
                "token_redacted": True,
                "production_callback_cutover_executed": False,
                "production_session_write_executed": False,
                "production_identity_write_executed": False,
                "side_effect_safety": {},
            }
        ),
        encoding="utf-8",
    )
    return path


def _canary_evidence(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "mode": "oauth_identity_production_live_canary_execution",
                "result_status": "blocked",
                "production_live_oauth_call_executed": False,
                "production_callback_cutover_executed": False,
                "production_session_write_executed": False,
                "production_identity_write_executed": False,
                "token_persisted": False,
                "state_redacted": "sta***123",
                "code_redacted": "cod***456",
            }
        ),
        encoding="utf-8",
    )
    return path


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report["blockers"]


def test_canary_runner_default_blocked() -> None:
    report = canary_runner.build_report(_canary_args())
    assert report["ok"] is False
    assert report["result_status"] == "not_executed_missing_phase5r_readiness"


def test_missing_phase5r_readiness_returns_blocked() -> None:
    report = canary_runner.build_report(_canary_args(phase5r_readiness_json="/tmp/missing-phase5r.json"))
    assert report["result_status"] == "not_executed_missing_phase5r_readiness"


def test_missing_staging_evidence_returns_blocked(tmp_path: Path) -> None:
    readiness = _phase5r_readiness(tmp_path / "phase5r.json")
    report = canary_runner.build_report(_canary_args(phase5r_readiness_json=str(readiness)))
    assert report["result_status"] == "not_executed_missing_staging_evidence"


def test_missing_approvals_returns_blocked(tmp_path: Path, monkeypatch) -> None:
    readiness = _phase5r_readiness(tmp_path / "phase5r.json")
    staging = _staging_evidence(tmp_path / "staging.json")
    for env in canary_runner.FLAG_ENV:
        monkeypatch.delenv(env, raising=False)
    report = canary_runner.build_report(_canary_args(phase5r_readiness_json=str(readiness), staging_evidence_json=str(staging)))
    assert report["result_status"] == "not_executed_missing_canary_approval"


def test_missing_state_code_idempotency_and_confirm_flags_return_blocked(tmp_path: Path, monkeypatch) -> None:
    readiness = _phase5r_readiness(tmp_path / "phase5r.json")
    staging = _staging_evidence(tmp_path / "staging.json")
    for env in set(canary_runner.FLAG_ENV) | set(canary_runner.CONFIG_ENV):
        monkeypatch.setenv(env, "1")
    base = {"phase5r_readiness_json": str(readiness), "staging_evidence_json": str(staging)}
    assert canary_runner.build_report(_canary_args(**base))["result_status"] == "not_executed_missing_state"
    assert canary_runner.build_report(_canary_args(**base, state="state-1"))["result_status"] == "not_executed_missing_code"
    assert canary_runner.build_report(_canary_args(**base, state="state-1", code="code-1"))["result_status"] == "not_executed_missing_idempotency_key"
    assert canary_runner.build_report(_canary_args(**base, state="state-1", code="code-1", idempotency_key="idem-1"))["result_status"] == "not_executed_missing_confirm_production_live_oauth_call"


def test_batch_replay_rejected(tmp_path: Path, monkeypatch) -> None:
    readiness = _phase5r_readiness(tmp_path / "phase5r.json")
    staging = _staging_evidence(tmp_path / "staging.json")
    for env in set(canary_runner.FLAG_ENV) | set(canary_runner.CONFIG_ENV):
        monkeypatch.setenv(env, "1")
    report = canary_runner.build_report(
        _canary_args(
            phase5r_readiness_json=str(readiness),
            staging_evidence_json=str(staging),
            state="state-1,state-2",
            code="code-1",
            idempotency_key="idem-1",
        )
    )
    assert report["result_status"] == "not_executed_missing_confirm_no_batch_replay"


def test_cleanup_runner_default_blocked() -> None:
    report = cleanup_runner.build_report(_cleanup_args())
    assert report["ok"] is False
    assert report["result_status"] == "not_executed_missing_canary_evidence"


def test_cleanup_refuses_production_session_and_identity_delete(tmp_path: Path, monkeypatch) -> None:
    evidence = _canary_evidence(tmp_path / "canary.json")
    for env in cleanup_runner.REQUIRED_ENV:
        monkeypatch.setenv(env, "1")
    report = cleanup_runner.build_report(_cleanup_args(canary_evidence_json=str(evidence), confirm_production_cleanup_reviewed=True))
    assert report["result_status"] == "not_executed_missing_confirm_no_production_session_delete"
    report = cleanup_runner.build_report(
        _cleanup_args(
            canary_evidence_json=str(evidence),
            confirm_production_cleanup_reviewed=True,
            confirm_no_production_session_delete=True,
        )
    )
    assert report["result_status"] == "not_executed_missing_confirm_no_production_identity_delete"


def test_token_persistence_false_and_no_outbound_send() -> None:
    report = canary_runner.build_report(_canary_args())
    assert report["token_persisted"] is False
    assert report["outbound_send_executed"] is False
    assert report["production_compat_changed"] is False


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden = [
        "route owner switched",
        "fallback removed",
        "production session write enabled",
        "production identity write enabled",
        "token persistence enabled",
        "delete_ready true",
        "delete_ready: true",
    ]
    assert not any(claim in text for claim in forbidden)
