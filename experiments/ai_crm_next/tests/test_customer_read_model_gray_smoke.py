from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import pytest

from tools import customer_read_model_gray_smoke as gray_smoke
from tools.doc_paths import read_experiment_doc

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _args(*, old_base_url: str = "", next_testclient: bool = True, next_base_url: str = "") -> Namespace:
    return Namespace(
        old_base_url=old_base_url,
        next_testclient=next_testclient,
        next_base_url=next_base_url,
        output_md="/tmp/unused.md",
        output_json="/tmp/unused.json",
    )


def test_default_smoke_endpoints_are_get_only() -> None:
    assert gray_smoke.READ_ENDPOINTS
    assert all(endpoint.method == "GET" for endpoint in gray_smoke.READ_ENDPOINTS)


def test_no_write_endpoint_is_present() -> None:
    paths = {endpoint.path for endpoint in gray_smoke.READ_ENDPOINTS}
    forbidden_fragments = ["submit", "checkout", "notify", "activation-webhook", "batch-send", "do-not-disturb"]
    assert all(endpoint.method == "GET" for endpoint in gray_smoke.READ_ENDPOINTS)
    assert not any(fragment in path for fragment in forbidden_fragments for path in paths)


def test_default_smoke_covers_customer_list_and_admin_page() -> None:
    report = gray_smoke.run_smoke(_args())
    names = {item["name"] for item in report["route_results"]}
    assert "admin_customers_page" in names
    assert "customers.default" in names
    assert "customers.page" in names
    assert "customers.is_bound_true" in names
    assert "customers.keyword" in names


def test_sample_external_userid_is_selected_from_list_response() -> None:
    report = gray_smoke.run_smoke(_args())
    assert report["ok"] is True
    assert report["sample_external_userid"]
    detail_paths = [item["path"] for item in report["route_results"] if item["name"] == "customer_detail.sample"]
    assert detail_paths == [f"/api/customers/{report['sample_external_userid']}"]
    assert not report["sample_external_userid"].startswith("real_")


def test_detail_timeline_messages_skip_when_no_sample_exists(monkeypatch) -> None:
    empty_list = {
        "ok": True,
        "customers": [],
        "items": [],
        "count": 0,
        "total": 0,
        "limit": 50,
        "offset": 0,
        "filters": {},
    }

    def fake_request(_client, method: str, path: str):
        if path == "/admin/customers":
            return 200, "<html>客户中心</html>"
        if path.startswith("/api/customers"):
            return 200, empty_list
        raise AssertionError(f"sample endpoint should have been skipped: {method} {path}")

    monkeypatch.setattr(gray_smoke, "_request_testclient", fake_request)
    report = gray_smoke.run_smoke(_args())
    skipped = {item["name"]: item["reason"] for item in report["skipped"]}
    assert skipped["customers.keyword"] == "missing_keyword_sample"
    assert skipped["customer_detail.sample"] == "no_customer_sample"
    assert skipped["customer_timeline.sample"] == "no_customer_sample"
    assert skipped["recent_messages.sample"] == "no_customer_sample"


def test_side_effect_safety_present_and_all_false() -> None:
    report = gray_smoke.run_smoke(_args())
    safety = report["side_effect_safety"]
    assert safety["old_write_endpoints_executed"] is False
    assert safety["external_wecom_call_executed"] is False
    assert safety["archive_sync_executed"] is False
    assert safety["tag_refresh_executed"] is False
    assert safety["openclaw_webhook_executed"] is False


def test_old_base_url_mode_refuses_non_get_endpoint() -> None:
    with pytest.raises(ValueError, match="not readonly"):
        gray_smoke.ensure_readonly("POST", "/api/customers", target="old")


def test_old_base_url_mode_uses_old_list_sample(monkeypatch) -> None:
    old_calls: list[tuple[str, str]] = []
    next_calls: list[tuple[str, str]] = []

    old_list = {
        "ok": True,
        "customers": [],
        "items": [
            {
                "external_userid": "external_user_masked_old_001",
                "customer_name": "masked old sample",
                "owner_userid": "owner_masked_001",
                "owner_display_name": "Owner Masked",
                "mobile": "mobile_masked_001",
                "is_bound": True,
                "binding_status": "bound",
                "tags": ["tag_masked_001"],
                "class_user_status": {"activation_bucket": "activated"},
                "last_message_at": "2026-05-20T00:00:00Z",
                "last_touch_at": "2026-05-20T00:00:00Z",
                "updated_at": "2026-05-20T00:00:00Z",
            }
        ],
        "count": 1,
        "total": 1,
        "limit": 50,
        "offset": 0,
        "filters": {},
    }

    def fake_old(args, method: str, path: str):
        gray_smoke.ensure_readonly(method, path, target="old")
        old_calls.append((method, path))
        if path == "/admin/customers":
            return 200, "<html>客户中心</html>"
        if path == "/api/customers":
            return 200, old_list
        return 200, _payload_for_path(path)

    def fake_next(args, client, method: str, path: str):
        gray_smoke.ensure_readonly(method, path, target="next")
        next_calls.append((method, path))
        if path == "/admin/customers":
            return 200, "<html>客户中心</html>"
        if path == "/api/customers":
            return 200, old_list
        return 200, _payload_for_path(path)

    monkeypatch.setattr(gray_smoke, "_fetch_old", fake_old)
    monkeypatch.setattr(gray_smoke, "_fetch_next", fake_next)
    report = gray_smoke.run_smoke(_args(old_base_url="http://old.example.test"))
    assert report["ok"] is True
    assert report["sample_external_userid"] == "external_user_masked_old_001"
    assert all(method == "GET" for method, _ in old_calls)
    assert any(path == "/api/customers/external_user_masked_old_001" for _, path in next_calls)


def test_old_admin_customers_auth_redirect_is_legacy_drift(monkeypatch) -> None:
    old_list = {
        "ok": True,
        "customers": [],
        "items": [
            {
                "external_userid": "external_user_masked_old_001",
                "customer_name": "masked old sample",
                "owner_userid": "owner_masked_001",
                "owner_display_name": "Owner Masked",
                "mobile": "mobile_masked_001",
                "is_bound": True,
                "binding_status": "bound",
                "tags": [],
                "class_user_status": {"activation_bucket": "activated"},
                "last_message_at": "2026-05-20T00:00:00Z",
                "last_touch_at": "2026-05-20T00:00:00Z",
                "updated_at": "2026-05-20T00:00:00Z",
            }
        ],
        "count": 1,
        "total": 1,
        "limit": 50,
        "offset": 0,
        "filters": {},
    }

    def fake_old(args, method: str, path: str):
        gray_smoke.ensure_readonly(method, path, target="old")
        if path == "/admin/customers":
            return 302, "<html>login</html>"
        if path == "/api/customers":
            return 200, old_list
        return 200, _payload_for_path(path)

    def fake_next(args, client, method: str, path: str):
        gray_smoke.ensure_readonly(method, path, target="next")
        if path == "/admin/customers":
            return 200, "<html>客户中心</html>"
        if path == "/api/customers":
            return 200, old_list
        return 200, _payload_for_path(path)

    monkeypatch.setattr(gray_smoke, "_fetch_old", fake_old)
    monkeypatch.setattr(gray_smoke, "_fetch_next", fake_next)
    report = gray_smoke.run_smoke(_args(old_base_url="http://old.example.test"))
    assert report["ok"] is True
    assert not report["blockers"]
    assert any(item["reason"] == "legacy_admin_auth_redirect" for item in report["legacy_drift"])


def test_report_contains_skipped_reason_for_no_sample(monkeypatch, tmp_path: Path) -> None:
    def fake_request(_client, method: str, path: str):
        if path == "/admin/customers":
            return 200, "<html>客户中心</html>"
        return 200, {"ok": True, "customers": [], "items": [], "count": 0, "total": 0, "limit": 50, "offset": 0, "filters": {}}

    monkeypatch.setattr(gray_smoke, "_request_testclient", fake_request)
    report = gray_smoke.run_smoke(_args())
    output_md = tmp_path / "customer_gray.md"
    output_json = tmp_path / "customer_gray.json"
    gray_smoke.write_markdown_report(report, output_md)
    gray_smoke.write_json_report(report, output_json)
    assert "no_customer_sample" in output_md.read_text(encoding="utf-8")
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert any(item["reason"] == "no_customer_sample" for item in payload["skipped"])


def test_route_cutover_manifest_includes_all_customer_routes() -> None:
    text = (PROJECT_ROOT / "docs" / "customer_read_model_route_cutover_manifest.md").read_text(encoding="utf-8")
    required_routes = [
        "/admin/customers",
        "/api/customers",
        "/api/customers?limit=5&offset=0",
        "/api/customers?owner_userid={owner_userid}",
        "/api/customers?is_bound=true",
        "/api/customers?keyword={keyword}",
        "/api/customers/{external_userid}",
        "/api/customers/{external_userid}/timeline",
        "/api/customers/{external_userid}/timeline?limit=5&offset=0",
        "/api/messages/{external_userid}/recent",
        "/api/messages/{external_userid}/recent?limit=5",
    ]
    for route in required_routes:
        assert route in text
    assert "pending_sample_data" in text
    assert "production_ready" not in text


def test_gray_release_plan_does_not_mark_production_ready() -> None:
    text = read_experiment_doc("customer_read_model_gray_release_plan.md")
    assert "production_ready |" not in text
    assert "status: production_ready" not in text
    assert "readonly gray release preparation only" in text
    assert "Real WeCom contact sync" in text


def test_customer_gray_smoke_tool_does_not_import_old_backend() -> None:
    assert Path(gray_smoke.__file__).resolve().relative_to(PROJECT_ROOT.parents[1]) == Path("tools/customer_read_model_gray_smoke.py")
    report = gray_smoke.run_smoke(_args())
    safety = report["side_effect_safety"]
    assert safety["old_write_endpoints_executed"] is False
    assert safety["external_wecom_call_executed"] is False
    assert safety["archive_sync_executed"] is False
    assert safety["tag_refresh_executed"] is False
    assert safety["openclaw_webhook_executed"] is False


def _payload_for_path(path: str) -> dict:
    external_userid = "external_user_masked_old_001"
    if "/timeline" in path:
        return {
            "ok": True,
            "timeline": {
                "external_userid": external_userid,
                "items": [
                    {
                        "event_id": "timeline_event_masked_001",
                        "event_type": "note",
                        "event_time": "2026-05-20T00:00:00Z",
                        "title": "masked event",
                        "summary": "masked summary",
                        "source_table": "fixture",
                        "source_id": "timeline_event_masked_001",
                        "metadata": {},
                    }
                ],
                "count": 1,
                "limit": 50,
                "offset": 0,
                "filters": {},
                "total": 1,
            },
        }
    if "/recent" in path:
        return {
            "ok": True,
            "messages": [
                {
                    "msgid": "msg_masked_001",
                    "msgtype": "text",
                    "content": "masked message",
                    "send_time": "2026-05-20T00:00:00Z",
                    "external_userid": external_userid,
                }
            ],
        }
    if path.startswith("/api/customers/"):
        return {
            "ok": True,
            "customer": {
                "external_userid": external_userid,
                "customer_name": "masked customer",
                "owner_userid": "owner_masked_001",
                "owner_display_name": "Owner Masked",
                "remark": "",
                "description": "",
                "mobile": "mobile_masked_001",
                "is_bound": True,
                "binding_status": "bound",
                "follow_user_userids": ["owner_masked_001"],
                "tags": ["tag_masked_001"],
                "class_user_status": {},
                "last_message_at": "2026-05-20T00:00:00Z",
                "last_touch_at": "2026-05-20T00:00:00Z",
                "updated_at": "2026-05-20T00:00:00Z",
                "binding": {},
                "identity": {},
                "follow_users": [],
                "marketing_summary": {},
                "marketing_profile": {},
                "contact": {},
                "sidebar_context": {},
            },
        }
    return {
        "ok": True,
        "customers": [],
        "items": [],
        "count": 0,
        "total": 0,
        "limit": 50,
        "offset": 0,
        "filters": {},
    }
