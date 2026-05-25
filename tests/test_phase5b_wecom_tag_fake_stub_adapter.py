from __future__ import annotations

import json
import subprocess
from pathlib import Path

import tools.check_phase5b_wecom_tag_fake_stub_adapter as checker
from aicrm_next.customer_tags.application import WeComTagApplicationService
from aicrm_next.customer_tags.wecom_tag_adapter import build_fake_stub_wecom_tag_adapter


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_5b_wecom_tag_fake_stub_adapter.md"
STAGING_RUNNER = ROOT / "tools/run_phase5b_wecom_tag_fake_stub_staging_smoke.py"
PROD_RUNNER = ROOT / "tools/run_phase5b_wecom_tag_fake_stub_production_dry_run.py"


def _service() -> WeComTagApplicationService:
    return WeComTagApplicationService(build_fake_stub_wecom_tag_adapter())


def test_checker_current_repo_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)
    assert report["autopilot_deliverable"] is True


def test_list_wecom_tags_returns_deterministic_tags() -> None:
    result = _service().list_wecom_tags()
    assert result["ok"] is True
    assert [item["tag_id"] for item in result["tags"]] == ["tag_contract_001", "tag_contract_002", "tag_contract_003"]
    assert result["live_call_executed"] is False
    assert result["network_call_executed"] is False


def test_validate_tag_ids_accepts_known_tags() -> None:
    result = _service().validate_tag_ids([" tag_contract_001 ", "tag_contract_001", "tag_contract_002"])
    assert result["ok"] is True
    assert result["normalized_tag_ids"] == ["tag_contract_001", "tag_contract_002"]
    assert result["invalid_tag_ids"] == []


def test_validate_tag_ids_rejects_unknown_tags() -> None:
    result = _service().validate_tag_ids(["tag_contract_001", "unknown"])
    assert result["ok"] is False
    assert result["error_code"] == "invalid_tag_id"
    assert result["invalid_tag_ids"] == ["unknown"]


def test_dry_run_mark_tags_requires_idempotency_key() -> None:
    result = _service().dry_run_mark_tags(
        external_userid="external_userid_abc123",
        tag_ids=["tag_contract_001"],
        operator="tester",
        idempotency_key="",
    )
    assert result["ok"] is False
    assert result["error_code"] == "idempotency_key_required"


def test_dry_run_mark_tags_replay_and_conflict() -> None:
    service = _service()
    first = service.dry_run_mark_tags(
        external_userid="external_userid_abc123",
        tag_ids=["tag_contract_001"],
        operator="tester",
        idempotency_key="same-key",
    )
    replay = service.dry_run_mark_tags(
        external_userid="external_userid_abc123",
        tag_ids=["tag_contract_001"],
        operator="tester",
        idempotency_key="same-key",
    )
    conflict = service.dry_run_mark_tags(
        external_userid="external_userid_abc123",
        tag_ids=["tag_contract_002"],
        operator="tester",
        idempotency_key="same-key",
    )
    assert first["ok"] is True
    assert replay["idempotency_replay"] is True
    assert replay["result_status"] == "replay"
    assert conflict["ok"] is False
    assert conflict["error_code"] == "duplicate_idempotency_key"


def test_dry_run_unmark_tags_replay_and_conflict() -> None:
    service = _service()
    first = service.dry_run_unmark_tags(
        external_userid="external_userid_abc123",
        tag_ids=["tag_contract_001"],
        operator="tester",
        idempotency_key="unmark-key",
    )
    replay = service.dry_run_unmark_tags(
        external_userid="external_userid_abc123",
        tag_ids=["tag_contract_001"],
        operator="tester",
        idempotency_key="unmark-key",
    )
    conflict = service.dry_run_unmark_tags(
        external_userid="external_userid_abc123",
        tag_ids=["tag_contract_003"],
        operator="tester",
        idempotency_key="unmark-key",
    )
    assert first["ok"] is True
    assert replay["idempotency_replay"] is True
    assert conflict["ok"] is False
    assert conflict["error_code"] == "duplicate_idempotency_key"


def test_side_effect_safety_all_false() -> None:
    result = _service().dry_run_mark_tags(
        external_userid="external_userid_abc123",
        tag_ids=["tag_contract_001"],
        operator="tester",
        idempotency_key="safety-key",
    )
    for field in (
        "live_call_executed",
        "mark_tag_executed",
        "unmark_tag_executed",
        "outbound_send_executed",
        "token_used",
        "network_call_executed",
        "production_behavior_changed",
    ):
        assert result[field] is False
    assert all(value is False for value in result["side_effect_safety"].values())


def test_staging_runner_default_blocked_unless_approved(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("AICRM_PHASE5B_WECOM_TAG_STAGING_SMOKE_APPROVED", raising=False)
    output = tmp_path / "staging.json"
    proc = subprocess.run(
        ["python3", str(STAGING_RUNNER), "--output-json", str(output)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert proc.returncode == 0
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["status"] == "blocked_not_executed"
    assert data["live_call_executed"] is False


def test_production_dry_run_runner_requires_approval_config_and_args(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("AICRM_PHASE5B_WECOM_TAG_PRODUCTION_DRY_RUN_APPROVED", raising=False)
    monkeypatch.delenv("AICRM_PHASE5B_WECOM_TAG_PRODUCTION_CONFIG_REVIEWED", raising=False)
    output = tmp_path / "prod.json"
    proc = subprocess.run(
        ["python3", str(PROD_RUNNER), "--output-json", str(output)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert proc.returncode == 0
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["status"] == "blocked_not_executed"
    assert data["live_call_executed"] is False
    assert data["production_tag_write_executed"] is False


def test_no_live_wecom_call_imported_or_executed() -> None:
    blockers: list[str] = []
    for source in checker.ADAPTER_SOURCES:
        blockers.extend(checker._source_static_blockers(source))
    blockers.extend(checker._runner_blockers(STAGING_RUNNER))
    blockers.extend(checker._runner_blockers(PROD_RUNNER))
    assert blockers == []
    live_attempt = _service().live_call_attempt()
    assert live_attempt["ok"] is False
    assert live_attempt["error_code"] == "live_call_not_enabled"
    assert live_attempt["live_call_executed"] is False


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    for phrase in checker.FORBIDDEN_DOC_CLAIMS:
        assert phrase not in text
