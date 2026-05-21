from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import pytest

from aicrm_next.ops_enrollment import parity_spec
from tools import user_ops_readonly_gray_smoke as gray_smoke

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _args(*, old_base_url: str = "", next_testclient: bool = True, next_base_url: str = "") -> Namespace:
    return Namespace(
        old_base_url=old_base_url,
        next_testclient=next_testclient,
        next_base_url=next_base_url,
        output_md="/tmp/unused.md",
        output_json="/tmp/unused.json",
    )


def _overview_payload(*, include_activation_pending: bool = True) -> dict:
    labels = list(parity_spec.OVERVIEW_CARD_LABELS)
    if not include_activation_pending:
        labels.remove("激活待录入")
    return {
        "ok": True,
        "cards": [{"label": label, "value": 1} for label in labels],
        "filters": {},
        "generated_at": "2026-05-20T00:00:00Z",
    }


def _list_payload() -> dict:
    item = {key: f"{key}_masked" for key in parity_spec.LIST_ITEM_REQUIRED_KEYS}
    item.update(
        {
            "id": 1,
            "is_added_wecom": True,
            "is_wecom_added": True,
            "is_mobile_bound": True,
            "do_not_disturb": False,
            "do_not_disturb_reasons": [],
            "can_open_customer_detail": True,
            "can_batch_send": True,
        }
    )
    return {"ok": True, "items": [item], "total": 1, "filters": {}, "filter_options": {}, "meta": {}}


def _send_records_payload() -> dict:
    item = {key: f"{key}_masked" for key in parity_spec.SEND_RECORD_ITEM_REQUIRED_KEYS}
    item.update(
        {
            "id": 1,
            "selected_count": 1,
            "eligible_count": 1,
            "sent_count": 0,
            "skipped_count": 0,
            "skipped_reasons": {},
            "include_do_not_disturb": False,
            "image_count": 0,
            "sender_userids": [],
            "filter_snapshot": {},
        }
    )
    return {"ok": True, "items": [item], "limit": 50, "offset": 0, "total": 1}


def _payload_for_path(path: str, *, include_activation_pending: bool = True) -> dict | str:
    if path == "/admin/user-ops/ui":
        return "<html>引流品总数 已加微 未加微 发送记录</html>"
    if path == "/api/admin/user-ops/overview":
        return _overview_payload(include_activation_pending=include_activation_pending)
    if path.startswith("/api/admin/user-ops/list"):
        return _list_payload()
    if path == "/api/admin/user-ops/send-records":
        return _send_records_payload()
    raise AssertionError(f"unexpected path: {path}")


def test_default_smoke_endpoints_are_get_only() -> None:
    assert gray_smoke.READ_ENDPOINTS
    assert all(endpoint.method == "GET" for endpoint in gray_smoke.READ_ENDPOINTS)


def test_no_write_endpoint_is_present() -> None:
    paths = {endpoint.path for endpoint in gray_smoke.READ_ENDPOINTS}
    forbidden = ["do-not-disturb", "batch-send", "execute", "run-deferred-jobs", "/api/internal/user-ops"]
    assert not any(fragment in path for fragment in forbidden for path in paths)


def test_dnd_batch_send_execute_not_in_default_smoke() -> None:
    combined = "\n".join(endpoint.path for endpoint in gray_smoke.READ_ENDPOINTS)
    assert "/api/admin/user-ops/do-not-disturb" not in combined
    assert "/api/admin/user-ops/batch-send/preview" not in combined
    assert "/api/admin/user-ops/batch-send/execute" not in combined


def test_default_smoke_covers_overview_list_filters_send_records() -> None:
    paths = {endpoint.path for endpoint in gray_smoke.READ_ENDPOINTS}
    assert "/admin/user-ops/ui" in paths
    assert "/api/admin/user-ops/overview" in paths
    assert "/api/admin/user-ops/list" in paths
    assert "/api/admin/user-ops/list?wecom_status=added" in paths
    assert "/api/admin/user-ops/list?wecom_status=not_added" in paths
    assert "/api/admin/user-ops/list?mobile_binding_status=bound" in paths
    assert "/api/admin/user-ops/list?activation_bucket=activated" in paths
    assert "/api/admin/user-ops/send-records" in paths


def test_user_ops_overview_legacy_drift_warning_when_old_missing_activation_card(monkeypatch) -> None:
    def fake_old(args, method: str, path: str):
        gray_smoke.ensure_readonly(method, path, target="old")
        return 200, _payload_for_path(path, include_activation_pending=False)

    def fake_next(args, client, method: str, path: str):
        gray_smoke.ensure_readonly(method, path, target="next")
        return 200, _payload_for_path(path, include_activation_pending=True)

    monkeypatch.setattr(gray_smoke, "_fetch_old", fake_old)
    monkeypatch.setattr(gray_smoke, "_fetch_next", fake_next)
    report = gray_smoke.run_smoke(_args(old_base_url="http://old.example.test"))
    assert report["ok"] is True
    assert not report["blockers"]
    assert any(item["reason"] == "legacy_missing_required_card_label" for item in report["legacy_drift"])
    assert any(item["field"] == "激活待录入" for item in report["legacy_drift"])


def test_next_missing_activation_card_is_blocker(monkeypatch) -> None:
    def fake_next(args, client, method: str, path: str):
        gray_smoke.ensure_readonly(method, path, target="next")
        return 200, _payload_for_path(path, include_activation_pending=False)

    monkeypatch.setattr(gray_smoke, "_fetch_next", fake_next)
    report = gray_smoke.run_smoke(_args())
    assert report["ok"] is False
    assert any(item["reason"] == "next_missing_required_contract" and item.get("label") == "激活待录入" for item in report["blockers"])


def test_both_missing_activation_card_is_blocker(monkeypatch) -> None:
    def fake_old(args, method: str, path: str):
        gray_smoke.ensure_readonly(method, path, target="old")
        return 200, _payload_for_path(path, include_activation_pending=False)

    def fake_next(args, client, method: str, path: str):
        gray_smoke.ensure_readonly(method, path, target="next")
        return 200, _payload_for_path(path, include_activation_pending=False)

    monkeypatch.setattr(gray_smoke, "_fetch_old", fake_old)
    monkeypatch.setattr(gray_smoke, "_fetch_next", fake_next)
    report = gray_smoke.run_smoke(_args(old_base_url="http://old.example.test"))
    assert report["ok"] is False
    assert any(item["reason"] == "both_missing_required_contract" for item in report["blockers"])


def test_side_effect_safety_present_and_all_false() -> None:
    report = gray_smoke.run_smoke(_args())
    safety = report["side_effect_safety"]
    assert safety["old_write_endpoints_executed"] is False
    assert safety["wecom_dispatch_executed"] is False
    assert safety["media_upload_executed"] is False
    assert safety["deferred_jobs_executed"] is False


def test_old_base_url_mode_refuses_non_get_endpoint() -> None:
    with pytest.raises(ValueError, match="not readonly"):
        gray_smoke.ensure_readonly("POST", "/api/admin/user-ops/list", target="old")
    with pytest.raises(ValueError, match="forbidden"):
        gray_smoke.ensure_readonly("GET", "/api/internal/user-ops/something", target="old")


def test_report_contains_legacy_drift_section_and_json_field(monkeypatch, tmp_path: Path) -> None:
    def fake_old(args, method: str, path: str):
        return 200, _payload_for_path(path, include_activation_pending=False)

    def fake_next(args, client, method: str, path: str):
        return 200, _payload_for_path(path, include_activation_pending=True)

    monkeypatch.setattr(gray_smoke, "_fetch_old", fake_old)
    monkeypatch.setattr(gray_smoke, "_fetch_next", fake_next)
    report = gray_smoke.run_smoke(_args(old_base_url="http://old.example.test"))
    output_md = tmp_path / "user_ops_gray.md"
    output_json = tmp_path / "user_ops_gray.json"
    gray_smoke.write_markdown_report(report, output_md)
    gray_smoke.write_json_report(report, output_json)
    assert "## Legacy Drift" in output_md.read_text(encoding="utf-8")
    assert "激活待录入" in output_md.read_text(encoding="utf-8")
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert "legacy_drift" in payload


def test_route_cutover_manifest_includes_readonly_and_write_routes() -> None:
    text = (PROJECT_ROOT / "docs" / "user_ops_readonly_route_cutover_manifest.md").read_text(encoding="utf-8")
    required_routes = [
        "/admin/user-ops/ui",
        "/api/admin/user-ops/overview",
        "/api/admin/user-ops/list?wecom_status=added",
        "/api/admin/user-ops/list?activation_bucket=activated",
        "/api/admin/user-ops/history",
        "/api/admin/user-ops/send-records/{record_id}",
        "/api/admin/user-ops/do-not-disturb",
        "/api/admin/user-ops/batch-send/preview",
        "/api/admin/user-ops/batch-send/execute",
        "/api/admin/user-ops/run-deferred-jobs",
        "/api/internal/user-ops/*",
    ]
    for route in required_routes:
        assert route in text
    assert "| POST |" in text
    assert "no_production" in text


def test_gray_release_plan_does_not_mark_production_ready() -> None:
    text = (PROJECT_ROOT / "docs" / "user_ops_readonly_gray_release_plan.md").read_text(encoding="utf-8")
    assert "status: production_ready" not in text
    assert "production_ready |" not in text
    assert "not ready" in text
    assert "激活待录入" in text


def test_activation_pending_remains_required_in_parity_spec() -> None:
    assert "激活待录入" in parity_spec.OVERVIEW_CARD_LABELS


def test_user_ops_gray_smoke_tool_does_not_import_old_backend() -> None:
    assert Path(gray_smoke.__file__).resolve().relative_to(PROJECT_ROOT.parents[1]) == Path("tools/user_ops_readonly_gray_smoke.py")
    report = gray_smoke.run_smoke(_args())
    safety = report["side_effect_safety"]
    assert safety["old_write_endpoints_executed"] is False
    assert safety["wecom_dispatch_executed"] is False
    assert safety["media_upload_executed"] is False
    assert safety["deferred_jobs_executed"] is False
