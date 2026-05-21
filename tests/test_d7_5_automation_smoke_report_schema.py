from __future__ import annotations

from argparse import Namespace

from tools import automation_readonly_gray_smoke as smoke


def _args() -> Namespace:
    return Namespace(
        old_base_url="",
        next_testclient=True,
        next_base_url="",
        include_fake_writes=False,
        output_md="/tmp/unused.md",
        output_json="/tmp/unused.json",
    )


def test_automation_smoke_report_has_top_level_schema() -> None:
    report = smoke.run_smoke(_args())
    assert {"ok", "overall", "summary", "route_results", "side_effect_safety", "blockers", "warnings", "skipped", "legacy_drift"} <= set(report)
    assert report["ok"] is True
    assert report["overall"] == "PASS"
    assert {"compared", "passed", "failed", "skipped", "warnings", "blockers", "legacy_drift"} <= set(report["summary"])
    assert report["summary"]["compared"] == len(report["route_results"])
    assert report["summary"]["failed"] == 0
    assert report["summary"]["blockers"] == 0


def test_every_route_result_has_schema_compatibility_fields() -> None:
    report = smoke.run_smoke(_args())
    assert report["route_results"]
    for item in report["route_results"]:
        assert {"name", "method", "path", "status", "result", "warnings", "blockers", "skip_reason", "issues"} <= set(item)
        assert isinstance(item["warnings"], list)
        assert isinstance(item["blockers"], list)
        assert item["skip_reason"] == ""


def test_missing_member_detail_skip_is_represented_per_route(monkeypatch) -> None:
    def fake_request(_client, _method: str, path: str, payload=None):
        if path == "/api/admin/automation-conversion/members":
            return 200, {"ok": True, "items": [], "total": 0, "limit": 50, "offset": 0, "filters": {}}
        return 200, {"ok": True, "items": [], "total": 0, "filters": {}, "cards": [], "pools": []}

    monkeypatch.setattr(smoke, "_request_testclient", fake_request)
    report = smoke.run_smoke(_args())
    skipped_detail = next(item for item in report["route_results"] if item["name"] == "member_detail.sample")
    assert skipped_detail["result"] == "skipped"
    assert skipped_detail["skip_reason"] == "missing_member_id"
    assert skipped_detail["warnings"] == []
    assert skipped_detail["blockers"] == []


def test_report_overall_fails_when_route_fails(monkeypatch) -> None:
    def fake_request(_client, _method: str, path: str, payload=None):
        if path == "/api/admin/automation-conversion/overview":
            return 500, {"ok": False}
        return 200, {"ok": True, "items": [], "total": 0, "filters": {}, "cards": [], "pools": []}

    monkeypatch.setattr(smoke, "_request_testclient", fake_request)
    report = smoke.run_smoke(_args())
    assert report["ok"] is False
    assert report["overall"] == "FAIL"
    assert report["summary"]["failed"] >= 1
    assert report["summary"]["blockers"] >= 1


def test_read_endpoints_exclude_write_external_runtime_paths() -> None:
    forbidden = (
        "override-followup-type",
        "confirm-conversion",
        "enter-silent",
        "exit-marketing",
        "activation-webhook",
        "push-openclaw-context",
        "workflow",
        "agent",
    )
    for endpoint in smoke.READ_ENDPOINTS:
        assert endpoint.method == "GET"
        lowered = endpoint.path_template.lower()
        assert not any(fragment in lowered for fragment in forbidden)


def test_side_effect_safety_schema_fields_are_false() -> None:
    report = smoke.run_smoke(_args())
    for field in [
        "old_write_endpoints_executed",
        "manual_override_executed",
        "confirm_conversion_executed",
        "activation_webhook_executed",
        "openclaw_push_executed",
        "workflow_runtime_executed",
        "agent_runtime_executed",
        "wecom_dispatch_executed",
        "external_webhook_executed",
        "real_traffic_cutover_executed",
        "production_config_modified",
    ]:
        assert report["side_effect_safety"][field] is False
