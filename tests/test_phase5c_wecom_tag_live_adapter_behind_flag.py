from __future__ import annotations

import json
import subprocess
from pathlib import Path

import tools.check_phase5c_wecom_tag_live_adapter_behind_flag as checker
from aicrm_next.customer_tags.application import WeComTagApplicationService
from aicrm_next.customer_tags.wecom_tag_adapter import build_fake_stub_wecom_tag_adapter
from aicrm_next.customer_tags.wecom_tag_live_adapter import build_live_wecom_tag_adapter


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_5c_wecom_tag_live_adapter_behind_flag.md"
STAGING_RUNNER = ROOT / "tools/run_phase5c_wecom_tag_live_staging_evidence.py"
PROD_RUNNER = ROOT / "tools/run_phase5c_wecom_tag_live_production_dry_run_gate.py"


class FakeGateway:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def list_wecom_tags_live(self) -> dict:
        self.calls.append("list")
        return {"errcode": 0, "tag_group": []}

    def mark_tags_live(self, *, external_userid: str, tag_ids: list[str], operator: str) -> dict:
        self.calls.append("mark")
        return {"errcode": 0, "external_userid": external_userid, "tag_ids": tag_ids, "operator": operator}

    def unmark_tags_live(self, *, external_userid: str, tag_ids: list[str], operator: str) -> dict:
        self.calls.append("unmark")
        return {"errcode": 0, "external_userid": external_userid, "tag_ids": tag_ids, "operator": operator}


def _clear_live_env(monkeypatch) -> None:
    for name in (
        "AICRM_WECOM_TAG_LIVE_ADAPTER_ENABLED",
        "AICRM_WECOM_TAG_LIVE_CALL_APPROVED",
        "AICRM_WECOM_TAG_CONFIG_REVIEWED",
        "AICRM_WECOM_TAG_CORP_ID",
        "AICRM_WECOM_TAG_AGENT_SECRET",
        "AICRM_PHASE5C_WECOM_TAG_STAGING_LIVE_APPROVED",
        "AICRM_PHASE5C_WECOM_TAG_PRODUCTION_DRY_RUN_APPROVED",
    ):
        monkeypatch.delenv(name, raising=False)


def test_checker_current_repo_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)
    assert report["autopilot_deliverable"] is True


def test_live_adapter_default_blocked(monkeypatch) -> None:
    _clear_live_env(monkeypatch)
    gateway = FakeGateway()
    result = build_live_wecom_tag_adapter(gateway=gateway).list_wecom_tags_live()
    assert result["ok"] is False
    assert result["error_code"] == "live_adapter_not_enabled"
    assert result["live_call_executed"] is False
    assert gateway.calls == []


def test_missing_approval_returns_live_call_not_approved(monkeypatch) -> None:
    _clear_live_env(monkeypatch)
    monkeypatch.setenv("AICRM_WECOM_TAG_LIVE_ADAPTER_ENABLED", "1")
    monkeypatch.setenv("AICRM_WECOM_TAG_CONFIG_REVIEWED", "1")
    monkeypatch.setenv("AICRM_WECOM_TAG_CORP_ID", "corp")
    monkeypatch.setenv("AICRM_WECOM_TAG_AGENT_SECRET", "secret")
    result = build_live_wecom_tag_adapter(gateway=FakeGateway()).list_wecom_tags_live()
    assert result["error_code"] == "live_call_not_approved"
    assert result["live_call_executed"] is False


def test_missing_config_returns_wecom_config_missing(monkeypatch) -> None:
    _clear_live_env(monkeypatch)
    monkeypatch.setenv("AICRM_WECOM_TAG_LIVE_ADAPTER_ENABLED", "1")
    monkeypatch.setenv("AICRM_WECOM_TAG_LIVE_CALL_APPROVED", "1")
    result = build_live_wecom_tag_adapter(gateway=FakeGateway()).list_wecom_tags_live()
    assert result["error_code"] == "wecom_config_missing"
    assert result["live_call_executed"] is False


def test_missing_idempotency_returns_idempotency_key_required(monkeypatch) -> None:
    _clear_live_env(monkeypatch)
    result = build_live_wecom_tag_adapter(gateway=FakeGateway()).mark_tags_live(
        external_userid="external_userid_abc123",
        tag_ids=["tag_contract_001"],
        operator="operator",
        idempotency_key="",
    )
    assert result["error_code"] == "idempotency_key_required"
    assert result["live_call_executed"] is False


def test_fake_stub_behavior_from_phase5b_still_works() -> None:
    service = WeComTagApplicationService(build_fake_stub_wecom_tag_adapter())
    listed = service.list_wecom_tags()
    assert listed["ok"] is True
    assert [item["tag_id"] for item in listed["tags"]] == ["tag_contract_001", "tag_contract_002", "tag_contract_003"]
    dry_run = service.dry_run_mark_tags(
        external_userid="external_userid_abc123",
        tag_ids=["tag_contract_001"],
        operator="tester",
        idempotency_key="phase5c-keeps-phase5b",
    )
    assert dry_run["ok"] is True
    assert dry_run["live_call_executed"] is False


def test_staging_evidence_runner_default_blocked(tmp_path: Path, monkeypatch) -> None:
    _clear_live_env(monkeypatch)
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
    assert data["result_status"] == "blocked_not_executed"
    assert data["live_call_executed"] is False


def test_production_dry_run_gate_never_calls_live_wecom(tmp_path: Path, monkeypatch) -> None:
    _clear_live_env(monkeypatch)
    output = tmp_path / "prod.json"
    proc = subprocess.run(
        ["python3", str(PROD_RUNNER), "--dry-run", "--confirm-no-live-call", "--output-json", str(output)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert proc.returncode == 0
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["live_call_executed"] is False
    assert data["production_tag_write_executed"] is False
    assert "build_live_wecom_tag_adapter" not in PROD_RUNNER.read_text(encoding="utf-8")


def test_side_effect_safety_forbids_adjacent_surfaces(monkeypatch) -> None:
    _clear_live_env(monkeypatch)
    result = build_live_wecom_tag_adapter(gateway=FakeGateway()).list_wecom_tags_live()
    safety = result["side_effect_safety"]
    for field in (
        "outbound_send_executed",
        "oauth_callback_executed",
        "payment_executed",
        "media_upload_executed",
        "openclaw_mcp_executed",
    ):
        assert safety[field] is False


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    for phrase in checker.FORBIDDEN_DOC_CLAIMS:
        assert phrase not in text
