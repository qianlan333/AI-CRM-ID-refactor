from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import pytest

from tools import automation_readonly_gray_smoke as gray_smoke

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _args(
    *,
    old_base_url: str = "",
    next_testclient: bool = True,
    next_base_url: str = "",
    include_fake_writes: bool = False,
) -> Namespace:
    return Namespace(
        old_base_url=old_base_url,
        next_testclient=next_testclient,
        next_base_url=next_base_url,
        include_fake_writes=include_fake_writes,
        output_md="/tmp/unused.md",
        output_json="/tmp/unused.json",
    )


def _overview_payload() -> dict:
    return {
        "ok": True,
        "cards": [{"key": "total", "label": "总人数", "value": 1}],
        "total": 1,
        "filters": {},
        "generated_at": "fixture",
    }


def _pools_payload() -> dict:
    return {
        "ok": True,
        "pools": [
            {
                "pool_key": "new_user",
                "label": "新用户",
                "count": 1,
                "description": "masked",
                "active_action_count": 0,
                "allow_broadcast": False,
            }
        ],
        "total": 1,
        "generated_at": "fixture",
    }


def _members_payload(*, with_sample: bool = True) -> dict:
    items = []
    if with_sample:
        items.append(
            {
                "member_id": "member_masked_001",
                "person_id": "person_masked_001",
                "external_userid": "external_user_masked_001",
                "mobile": "mobile_masked_001",
                "customer_name": "customer_masked_001",
                "owner_userid": "owner_masked_001",
                "current_pool": "new_user",
                "current_pool_label": "新用户",
                "followup_type": "normal",
                "questionnaire_followup_type": "normal",
                "manual_followup_type": "",
                "trial_opened": False,
                "activated": False,
                "converted": False,
                "exited": False,
                "silent": False,
                "latest_event_at": "fixture",
                "next_action": {"type": "wait_trial_opened", "label": "等待体验打开"},
                "can_manual_override": True,
                "can_confirm_conversion": True,
                "can_enter_silent": True,
                "can_exit_marketing": True,
            }
        )
    return {"ok": True, "items": items, "total": len(items), "limit": 50, "offset": 0, "filters": {}}


def _member_detail_payload() -> dict:
    member = _members_payload()["items"][0]
    return {"ok": True, "member": member, "history": [], "customer_context": {}, "recent_timeline_events": [], "warnings": []}


def _execution_records_payload() -> dict:
    return {
        "ok": True,
        "items": [
            {
                "id": "exec_masked_001",
                "record_type": "workflow",
                "member_id": "member_masked_001",
                "trigger": "fixture",
                "status": "succeeded",
                "status_label": "已完成",
                "delivery_status": "not_sent",
                "payload_preview": {},
                "created_at": "fixture",
            }
        ],
        "total": 1,
        "limit": 50,
        "offset": 0,
    }


def _payload_for_path(path: str, *, with_sample: bool = True) -> dict | str:
    if path == "/admin/automation-conversion":
        return "<html>自动化转化 池子 成员</html>"
    if path == "/api/admin/automation-conversion/overview":
        return _overview_payload()
    if path == "/api/admin/automation-conversion/pools":
        return _pools_payload()
    if path == "/api/admin/automation-conversion/members":
        return _members_payload(with_sample=with_sample)
    if path.startswith("/api/admin/automation-conversion/members/"):
        return _member_detail_payload()
    if path == "/api/admin/automation-conversion/execution-records":
        return _execution_records_payload()
    raise AssertionError(f"unexpected path: {path}")


def test_default_smoke_endpoints_are_get_only() -> None:
    assert gray_smoke.READ_ENDPOINTS
    assert all(endpoint.method == "GET" for endpoint in gray_smoke.READ_ENDPOINTS)


def test_no_write_or_external_endpoint_is_present_by_default() -> None:
    paths = {endpoint.path_template for endpoint in gray_smoke.READ_ENDPOINTS}
    forbidden = [
        "override-followup-type",
        "confirm-conversion",
        "enter-silent",
        "exit-marketing",
        "push-openclaw-context",
        "activation-webhook",
    ]
    assert not any(fragment in path for fragment in forbidden for path in paths)
    assert not any(endpoint.method in {"POST", "PUT", "PATCH", "DELETE"} for endpoint in gray_smoke.READ_ENDPOINTS)


def test_default_smoke_covers_automation_readonly_routes() -> None:
    paths = {endpoint.path_template for endpoint in gray_smoke.READ_ENDPOINTS}
    assert "/admin/automation-conversion" in paths
    assert "/api/admin/automation-conversion/overview" in paths
    assert "/api/admin/automation-conversion/pools" in paths
    assert "/api/admin/automation-conversion/members" in paths
    assert "/api/admin/automation-conversion/members/{member_id}" in paths
    assert "/api/admin/automation-conversion/execution-records" in paths


def test_default_smoke_selects_member_id_from_members_list() -> None:
    report = gray_smoke.run_smoke(_args())
    assert report["ok"] is True
    assert report["sample_member_id"]
    detail = next(item for item in report["route_results"] if item["name"] == "member_detail.sample")
    assert detail["next_path"] == f"/api/admin/automation-conversion/members/{report['sample_member_id']}"


def test_old_route_aliases_are_defined_for_legacy_flask_mapping() -> None:
    aliases = {endpoint.name: endpoint.old_path_template for endpoint in gray_smoke.READ_ENDPOINTS}
    assert aliases["overview.default"] == "/api/admin/automation-conversion/dashboard"
    assert aliases["pools.default"] == "/api/admin/automation-conversion/dashboard"
    assert aliases["members.default"] == "/api/admin/automation-conversion/programs/1/members/segment-search?page=1&page_size=50"
    assert aliases["member_detail.sample"] == "/api/admin/automation-conversion/member?external_contact_id={external_userid}"
    assert aliases["execution_records.default"] == "/api/admin/automation-conversion/executions"


def test_no_member_sample_skips_detail(monkeypatch) -> None:
    def fake_request(_client, method: str, path: str, payload=None):
        if path == "/api/admin/automation-conversion/members":
            return 200, _members_payload(with_sample=False)
        return 200, _payload_for_path(path)

    monkeypatch.setattr(gray_smoke, "_request_testclient", fake_request)
    report = gray_smoke.run_smoke(_args())
    skipped = {item["name"]: item["reason"] for item in report["skipped"] if "name" in item}
    assert skipped["member_detail.sample"] == "missing_member_id"


def test_old_member_sample_selected_from_legacy_segment_search_payload() -> None:
    context = gray_smoke._sample_context_from_old_members(
        {
            "ok": True,
            "items": [
                {
                    "id": 123,
                    "external_contact_id": "external_user_masked_automation_001",
                    "phone": "mobile_masked_automation_001",
                }
            ],
        }
    )
    assert context["external_userid"] == "external_user_masked_automation_001"
    assert context["member_id"] == "123"


def test_fake_writes_require_explicit_include_fake_writes() -> None:
    default_report = gray_smoke.run_smoke(_args())
    assert not any(item["method"] == "POST" for item in default_report["route_results"])
    assert any(item.get("reason") == "fake_writes_not_requested" for item in default_report["skipped"])

    fake_report = gray_smoke.run_smoke(_args(include_fake_writes=True))
    assert fake_report["ok"] is True
    assert any(item["method"] == "POST" for item in fake_report["route_results"])
    assert not any("push-openclaw-context" in item["path"] for item in fake_report["route_results"])
    assert not any("activation-webhook" in item["path"] for item in fake_report["route_results"])
    assert fake_report["side_effect_safety"]["openclaw_push_executed"] is False
    assert fake_report["side_effect_safety"]["activation_webhook_executed"] is False


def test_fake_writes_only_target_next_testclient() -> None:
    report = gray_smoke.run_smoke(
        _args(include_fake_writes=True, next_testclient=False, next_base_url="http://127.0.0.1:8000")
    )
    assert report["ok"] is False
    assert any(item["reason"] == "fake_writes_require_next_testclient" for item in report["blockers"])


def test_old_base_url_mode_refuses_non_get_and_external_paths() -> None:
    with pytest.raises(ValueError, match="not readonly"):
        gray_smoke.ensure_readonly("POST", "/api/admin/automation-conversion/members/member_001/confirm-conversion", target="old")
    with pytest.raises(ValueError, match="forbidden"):
        gray_smoke.ensure_readonly("GET", "/api/admin/automation-conversion/members/member_001/push-openclaw-context", target="old")
    with pytest.raises(ValueError, match="forbidden"):
        gray_smoke.ensure_readonly("GET", "/api/customer-automation/activation-webhook", target="old")


def test_old_missing_new_read_route_is_legacy_drift_when_next_passes() -> None:
    plan = next(endpoint for endpoint in gray_smoke.READ_ENDPOINTS if endpoint.name == "overview.default")
    result, blockers, warnings, legacy_drift = gray_smoke._result_for_plan(
        plan,
        next_path="/api/admin/automation-conversion/overview",
        next_status=200,
        next_payload=_overview_payload(),
        old_path="/api/admin/automation-conversion/overview",
        old_status=404,
        old_payload={"detail": "not found"},
    )
    assert result["status"] == "WARN"
    assert blockers == []
    assert warnings[0]["reason"] == "legacy_missing_read_route"
    assert legacy_drift[0]["next_satisfies_contract"] is True


def test_next_missing_required_contract_is_blocker(monkeypatch) -> None:
    def fake_request(_client, method: str, path: str, payload=None):
        if path == "/api/admin/automation-conversion/overview":
            return 200, {"ok": True}
        return 200, _payload_for_path(path)

    monkeypatch.setattr(gray_smoke, "_request_testclient", fake_request)
    report = gray_smoke.run_smoke(_args())
    assert report["ok"] is False
    assert any(item["reason"] == "next_missing_required_contract" for item in report["blockers"])


def test_side_effect_safety_present_and_all_false_for_default() -> None:
    report = gray_smoke.run_smoke(_args())
    safety = report["side_effect_safety"]
    assert safety["old_write_endpoints_executed"] is False
    assert safety["openclaw_push_executed"] is False
    assert safety["wecom_dispatch_executed"] is False
    assert safety["external_webhook_executed"] is False
    assert safety["activation_webhook_executed"] is False
    assert safety["workflow_runtime_executed"] is False


def test_report_contains_json_fields(tmp_path: Path) -> None:
    report = gray_smoke.run_smoke(_args())
    output_md = tmp_path / "automation_gray.md"
    output_json = tmp_path / "automation_gray.json"
    gray_smoke.write_markdown_report(report, output_md)
    gray_smoke.write_json_report(report, output_json)
    text = output_md.read_text(encoding="utf-8")
    assert "## Blockers" in text
    assert "## Legacy Drift" in text
    assert "## Side Effect Safety" in text
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert "side_effect_safety" in payload
    assert "legacy_drift" in payload


def test_route_cutover_manifest_includes_readonly_and_write_external_routes() -> None:
    text = (PROJECT_ROOT / "docs" / "automation_readonly_route_cutover_manifest.md").read_text(encoding="utf-8")
    required_routes = [
        "/admin/automation-conversion",
        "/api/admin/automation-conversion/overview",
        "/api/admin/automation-conversion/pools",
        "/api/admin/automation-conversion/members/{member_id}",
        "/api/admin/automation-conversion/execution-records",
        "/api/admin/automation-conversion/members/{member_id}/override-followup-type",
        "/api/admin/automation-conversion/members/{member_id}/confirm-conversion",
        "/api/admin/automation-conversion/members/{member_id}/enter-silent",
        "/api/admin/automation-conversion/members/{member_id}/exit-marketing",
        "/api/admin/automation-conversion/members/{member_id}/push-openclaw-context",
        "/api/customer-automation/activation-webhook",
        "workflow / agent runtime write routes",
    ]
    for route in required_routes:
        assert route in text
    assert "| POST |" in text
    assert "no_production" in text


def test_gray_release_plan_does_not_mark_production_ready() -> None:
    text = (PROJECT_ROOT / "docs" / "automation_readonly_gray_release_plan.md").read_text(encoding="utf-8")
    assert "status: production_ready" not in text
    assert "production_ready |" not in text
    assert "not ready" in text
    assert "OpenClaw fake" in text


def test_automation_gray_smoke_tool_does_not_import_old_backend() -> None:
    assert Path(gray_smoke.__file__).resolve().relative_to(PROJECT_ROOT.parents[1]) == Path("tools/automation_readonly_gray_smoke.py")
    report = gray_smoke.run_smoke(_args())
    safety = report["side_effect_safety"]
    assert safety["activation_webhook_executed"] is False
    assert safety["openclaw_push_executed"] is False
    assert safety["workflow_runtime_executed"] is False
    assert safety["wecom_dispatch_executed"] is False
    assert safety["external_webhook_executed"] is False
