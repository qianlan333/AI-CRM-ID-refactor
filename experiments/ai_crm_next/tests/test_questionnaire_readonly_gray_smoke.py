from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import pytest

from tools import questionnaire_readonly_gray_smoke as gray_smoke

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _args(
    *,
    old_base_url: str = "",
    next_testclient: bool = True,
    next_base_url: str = "",
    include_fake_submit: bool = False,
) -> Namespace:
    return Namespace(
        old_base_url=old_base_url,
        next_testclient=next_testclient,
        next_base_url=next_base_url,
        include_fake_submit=include_fake_submit,
        output_md="/tmp/unused.md",
        output_json="/tmp/unused.json",
    )


def test_default_smoke_endpoints_are_get_only() -> None:
    assert gray_smoke.READ_ENDPOINTS
    assert all(endpoint.method == "GET" for endpoint in gray_smoke.READ_ENDPOINTS)


def test_no_admin_write_or_submit_endpoint_is_present_by_default() -> None:
    paths = {endpoint.path_template for endpoint in gray_smoke.READ_ENDPOINTS}
    assert "/api/admin/questionnaires" in paths
    assert "/api/h5/questionnaires/{slug}/submit" not in paths
    assert "/api/h5/wechat/oauth/callback" not in paths
    assert not any(fragment in path for fragment in ["external-push", "retry", "webhook"] for path in paths)
    assert not any(endpoint.method in {"POST", "PUT", "PATCH", "DELETE"} for endpoint in gray_smoke.READ_ENDPOINTS)


def test_admin_and_public_questionnaire_routes_are_covered() -> None:
    paths = {endpoint.path_template for endpoint in gray_smoke.READ_ENDPOINTS}
    assert "/admin/questionnaires" in paths
    assert "/admin/questionnaires/ui" in paths
    assert "/api/admin/questionnaires" in paths
    assert "/api/admin/questionnaires/{questionnaire_id}" in paths
    assert "/api/admin/questionnaires/preflight" in paths
    assert "/api/admin/questionnaires/{questionnaire_id}/latest-submit-debug" in paths
    assert "/api/admin/questionnaires/{questionnaire_id}/export" in paths
    assert "/s/{slug}" in paths
    assert "/api/h5/questionnaires/{slug}" in paths
    assert "/api/h5/questionnaires/{slug}/result/{submission_id}" in paths


def test_default_smoke_selects_sample_from_next_list_response() -> None:
    report = gray_smoke.run_smoke(_args())
    assert report["ok"] is True
    assert report["sample_questionnaire_id"]
    assert report["sample_slug"]
    assert not report["sample_slug"].startswith("real_")
    detail = next(item for item in report["route_results"] if item["name"] == "admin_detail.sample")
    assert detail["next_path"] == f"/api/admin/questionnaires/{report['sample_questionnaire_id']}"


def test_no_sample_skips_sample_dependent_routes(monkeypatch) -> None:
    def fake_request(_client, method: str, path: str, payload=None):
        if path in {"/admin/questionnaires", "/admin/questionnaires/ui"}:
            return 200, "<html>问卷管理</html>"
        if path == "/api/admin/questionnaires":
            return 200, {"ok": True, "items": [], "questionnaires": [], "total": 0, "limit": 50, "offset": 0}
        if path == "/api/admin/questionnaires/preflight":
            return 200, {"ok": True, "checks": {"wechat_oauth_configured": False, "wecom_contact_configured": False, "debug_session_api_enabled": True, "questionnaire_admin_ui_enabled": True, "wecom_tags_api_available": False, "identity_map_available": True}}
        raise AssertionError(f"sample endpoint should have been skipped: {method} {path}")

    monkeypatch.setattr(gray_smoke, "_request_testclient", fake_request)
    report = gray_smoke.run_smoke(_args())
    skipped = {item["name"]: item["reason"] for item in report["skipped"] if "name" in item}
    assert skipped["admin_detail.sample"] == "missing_questionnaire_id"
    assert skipped["admin_latest_submit_debug.sample"] == "missing_questionnaire_id"
    assert skipped["public_page.sample"] == "missing_slug"
    assert skipped["public_result.sample"] == "missing_slug_submission_id"


def test_latest_submit_debug_flat_submission_id_updates_sample_context() -> None:
    context = gray_smoke._add_submission_context({}, {"ok": True, "submission_id": 123})
    assert context["submission_id"] == "123"


def test_fake_submit_requires_explicit_include_fake_submit() -> None:
    default_report = gray_smoke.run_smoke(_args())
    assert not any(item["method"] == "POST" for item in default_report["route_results"])
    assert any(item.get("reason") == "fake_submit_not_requested" for item in default_report["skipped"])

    fake_submit_report = gray_smoke.run_smoke(_args(include_fake_submit=True))
    assert fake_submit_report["ok"] is True
    fake_submit = next(item for item in fake_submit_report["route_results"] if item["name"] == "submit.fake_next_only")
    assert fake_submit["method"] == "POST"
    assert fake_submit["old_status"] is None
    assert fake_submit_report["side_effect_safety"]["old_submit_executed"] is False


def test_old_wechat_gate_is_legacy_drift_when_next_public_api_passes() -> None:
    plan = next(endpoint for endpoint in gray_smoke.READ_ENDPOINTS if endpoint.name == "public_get.sample")
    result, blockers, warnings, legacy_drift = gray_smoke._result_for_plan(
        plan,
        next_path="/api/h5/questionnaires/hxc-activation-v1",
        next_status=200,
        next_payload={
            "ok": True,
            "questionnaire": {"id": 1, "slug": "hxc-activation-v1", "title": "问卷", "questions": []},
        },
        old_path="/api/h5/questionnaires/hxc-activation-v1",
        old_status=403,
        old_payload={"ok": False, "error": "please_open_in_wechat"},
    )
    assert result["status"] == "WARN"
    assert blockers == []
    assert warnings[0]["reason"] == "legacy_wechat_browser_gate"
    assert legacy_drift[0]["next_satisfies_contract"] is True


def test_old_missing_result_api_is_legacy_drift_when_next_result_api_passes() -> None:
    plan = next(endpoint for endpoint in gray_smoke.READ_ENDPOINTS if endpoint.name == "public_result.sample")
    result, blockers, warnings, legacy_drift = gray_smoke._result_for_plan(
        plan,
        next_path="/api/h5/questionnaires/hxc-activation-v1/result/sub_001",
        next_status=200,
        next_payload={
            "ok": True,
            "result": {"submission_id": "sub_001", "questionnaire_id": "q_001", "slug": "hxc-activation-v1"},
            "result_message": "ok",
        },
        old_path="/api/h5/questionnaires/hxc-activation-v1/result/sub_001",
        old_status=404,
        old_payload="<html>not found</html>",
    )
    assert result["status"] == "WARN"
    assert blockers == []
    assert warnings[0]["reason"] == "legacy_missing_public_result_api"
    assert legacy_drift[0]["next_satisfies_contract"] is True


def test_fake_submit_only_targets_next_testclient() -> None:
    report = gray_smoke.run_smoke(_args(include_fake_submit=True, next_testclient=False, next_base_url="http://127.0.0.1:8000"))
    assert report["ok"] is False
    assert any(item["reason"] == "fake_submit_requires_next_testclient" for item in report["blockers"])


def test_old_base_url_mode_refuses_non_get_endpoint() -> None:
    with pytest.raises(ValueError, match="not readonly"):
        gray_smoke.ensure_readonly("POST", "/api/h5/questionnaires/hxc-activation-v1/submit", target="old")
    with pytest.raises(ValueError, match="forbidden"):
        gray_smoke.ensure_readonly("GET", "/api/h5/wechat/oauth/start", target="old")
    with pytest.raises(ValueError, match="forbidden"):
        gray_smoke.ensure_readonly("GET", "/api/h5/wechat/oauth/callback", target="old")


def test_side_effect_safety_present_and_all_false_for_default() -> None:
    report = gray_smoke.run_smoke(_args())
    safety = report["side_effect_safety"]
    assert safety["old_write_endpoints_executed"] is False
    assert safety["old_submit_executed"] is False
    assert safety["real_oauth_executed"] is False
    assert safety["wecom_tag_executed"] is False
    assert safety["external_webhook_executed"] is False


def test_report_contains_json_fields(tmp_path: Path) -> None:
    report = gray_smoke.run_smoke(_args())
    output_md = tmp_path / "questionnaire_gray.md"
    output_json = tmp_path / "questionnaire_gray.json"
    gray_smoke.write_markdown_report(report, output_md)
    gray_smoke.write_json_report(report, output_json)
    assert "## Blockers" in output_md.read_text(encoding="utf-8")
    assert "## Skipped" in output_md.read_text(encoding="utf-8")
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert "side_effect_safety" in payload
    assert "legacy_drift" in payload


def test_route_cutover_manifest_includes_readonly_and_write_external_routes() -> None:
    text = (PROJECT_ROOT / "docs" / "questionnaire_readonly_route_cutover_manifest.md").read_text(encoding="utf-8")
    required_routes = [
        "/admin/questionnaires",
        "/admin/questionnaires/ui",
        "/api/admin/questionnaires/{questionnaire_id}/latest-submit-debug",
        "/api/admin/questionnaires/{questionnaire_id}/export",
        "/api/h5/questionnaires/{slug}/result/{submission_id}",
        "/api/h5/questionnaires/{slug}/submit",
        "/api/h5/wechat/oauth/start",
        "/api/h5/wechat/oauth/callback",
        "external push retry routes",
    ]
    for route in required_routes:
        assert route in text
    assert "no_production" in text
    assert "fake_next_only" in text


def test_gray_release_plan_does_not_mark_production_ready() -> None:
    text = (PROJECT_ROOT / "docs" / "questionnaire_readonly_gray_release_plan.md").read_text(encoding="utf-8")
    assert "status: production_ready" not in text
    assert "production_ready |" not in text
    assert "not ready" in text
    assert "fake/stubbed" in text


def test_questionnaire_gray_smoke_tool_does_not_import_old_backend() -> None:
    text = (PROJECT_ROOT / "tools" / "questionnaire_readonly_gray_smoke.py").read_text(encoding="utf-8")
    assert "import wecom_ability_service" not in text
    assert "from wecom_ability_service" not in text
    assert "import openclaw_service" not in text
    assert "from openclaw_service" not in text
