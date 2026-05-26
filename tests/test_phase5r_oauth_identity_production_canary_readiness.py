from __future__ import annotations

import argparse
import json
from pathlib import Path

import tools.check_phase5r_oauth_identity_production_canary_readiness as checker
import tools.run_phase5r_oauth_identity_production_canary_readiness as runner


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_5r_oauth_identity_production_canary_readiness.md"


def _args(**overrides):
    values = {
        "staging_evidence_json": None,
        "confirm_no_production_live_oauth_call": False,
        "confirm_no_production_callback_cutover": False,
        "confirm_no_production_session_write": False,
        "confirm_no_production_identity_write": False,
        "confirm_no_token_persistence": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _acceptable_evidence(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "result_status": "staging_live_oauth_canary_evidence_completed",
                "redacted_state": "sta***123",
                "redacted_code": "cod***456",
                "token_redacted": True,
                "production_live_oauth_call_executed": False,
                "production_callback_cutover_executed": False,
                "production_session_write_executed": False,
                "production_identity_write_executed": False,
                "side_effect_safety": {},
            }
        ),
        encoding="utf-8",
    )
    return path


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report["blockers"]


def test_readiness_runner_default_blocked() -> None:
    report = runner.build_report(_args())
    assert report["result_status"] == "not_executed_missing_staging_evidence"
    assert report["production_live_oauth_call_executed"] is False


def test_missing_staging_evidence_returns_blocked() -> None:
    report = runner.build_report(_args(staging_evidence_json="/tmp/does-not-exist-phase5r.json"))
    assert report["result_status"] == "not_executed_missing_staging_evidence"


def test_invalid_staging_evidence_returns_blocked(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"result_status": "not_executed_missing_live_adapter_enabled"}), encoding="utf-8")
    report = runner.build_report(_args(staging_evidence_json=str(bad)))
    assert report["result_status"] == "not_executed_invalid_staging_evidence"


def test_missing_approvals_returns_blocked(tmp_path: Path, monkeypatch) -> None:
    evidence = _acceptable_evidence(tmp_path / "staging.json")
    for env in runner.REQUIRED_ENV:
        monkeypatch.delenv(env, raising=False)
    report = runner.build_report(_args(staging_evidence_json=str(evidence)))
    assert report["result_status"] == "not_executed_missing_production_canary_planning_approval"


def test_missing_no_production_confirm_flags_returns_blocked(tmp_path: Path, monkeypatch) -> None:
    evidence = _acceptable_evidence(tmp_path / "staging.json")
    for env in runner.REQUIRED_ENV:
        monkeypatch.setenv(env, "1")
    report = runner.build_report(_args(staging_evidence_json=str(evidence)))
    assert report["result_status"] == "not_executed_missing_confirm_no_production_live_oauth_call"
    report = runner.build_report(_args(staging_evidence_json=str(evidence), confirm_no_production_live_oauth_call=True))
    assert report["result_status"] == "not_executed_missing_confirm_no_production_callback_cutover"


def test_runner_never_imports_or_calls_live_oauth_gateway() -> None:
    text = Path(runner.__file__).read_text(encoding="utf-8")
    assert "oauth_identity_live_gateway" not in text
    assert "oauth_identity_live_adapter" not in text
    assert "exchange_code_live(" not in text
    assert "build_live_oauth_identity_adapter" not in text


def test_production_side_effects_false() -> None:
    report = runner.build_report(_args())
    assert report["production_live_oauth_call_executed"] is False
    assert report["production_callback_cutover_executed"] is False
    assert report["production_session_write_executed"] is False
    assert report["production_identity_write_executed"] is False
    assert report["token_persisted"] is False


def test_target_and_rollback_policy_are_guarded() -> None:
    data = checker.load_yaml(checker.PLAN_YAML)
    assert data["production_callback_target_policy"]["production_callback_url_cutover_allowed"] is False
    assert data["rollback_policy"]["cleanup_requires_explicit_approval"] is True


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden = [
        "production canary executed",
        "production callback cutover enabled",
        "production session write enabled",
        "production identity write enabled",
        "token persistence enabled",
        "production owner switched",
        "fallback removed",
        "production_compat changed",
        "delete_ready true",
        "delete_ready: true",
    ]
    assert not any(claim in text for claim in forbidden)
