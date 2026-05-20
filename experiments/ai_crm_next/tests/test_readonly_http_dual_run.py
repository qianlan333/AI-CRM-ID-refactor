from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from conftest import make_client
from tools import readonly_http_dual_run as dual_run
from aicrm_next.ops_enrollment import parity_spec as user_ops_spec

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _args(tmp_path: Path, *, scope: str = "customer,user_ops") -> object:
    return type(
        "Args",
        (),
        {
            "old_base_url": "http://old.example.test",
            "next_base_url": "",
            "next_testclient": True,
            "scope": scope,
            "output_md": str(tmp_path / "dual.md"),
            "output_json": str(tmp_path / "dual.json"),
        },
    )()


def _next_payload(path: str) -> dict:
    response = make_client().get(path)
    return {"status_code": response.status_code, "payload": response.json()}


def _without_overview_card(payload: dict, label: str = "激活待录入") -> dict:
    copied = json.loads(json.dumps(payload, ensure_ascii=False))
    copied["cards"] = [card for card in copied.get("cards", []) if card.get("label") != label]
    return copied


def test_default_endpoints_are_get_only() -> None:
    plans = dual_run.default_endpoint_plans(["customer", "user_ops"])
    assert plans
    assert all(plan.method == "GET" for plan in plans)


def test_old_service_refuses_post_endpoints() -> None:
    with pytest.raises(ValueError, match="not readonly"):
        dual_run.ensure_old_endpoint_is_readonly("POST", "/api/admin/user-ops/batch-send/preview")


def test_customer_scope_includes_required_readonly_endpoints() -> None:
    paths = {plan.path for plan in dual_run.default_endpoint_plans(["customer"])}
    assert "/api/customers" in paths
    assert "/api/customers?limit=5&offset=0" in paths
    assert "/api/customers/{external_userid}" in paths
    assert "/api/customers/{external_userid}/timeline" in paths
    assert "/api/messages/{external_userid}/recent" in paths


def test_user_ops_scope_includes_required_readonly_endpoints() -> None:
    paths = {plan.path for plan in dual_run.default_endpoint_plans(["user_ops"])}
    assert "/api/admin/user-ops/overview" in paths
    assert "/api/admin/user-ops/list" in paths
    assert "/api/admin/user-ops/list?wecom_status=added" in paths
    assert "/api/admin/user-ops/list?wecom_status=not_added" in paths
    assert "/api/admin/user-ops/list?mobile_binding_status=bound" in paths
    assert "/api/admin/user-ops/list?activation_bucket=activated" in paths
    assert "/api/admin/user-ops/send-records" in paths
    assert not any("batch-send" in path for path in paths)
    assert not any("do-not-disturb" in path for path in paths)


def test_tool_runs_with_mock_old_and_next_testclient(monkeypatch, tmp_path: Path) -> None:
    old_calls: list[tuple[str, str]] = []

    def fake_old(base_url: str, method: str, path: str) -> dict:
        dual_run.ensure_old_endpoint_is_readonly(method, path)
        old_calls.append((method, path))
        return _next_payload(path)

    monkeypatch.setattr(dual_run, "_fetch_old_http", fake_old)
    report = dual_run.run_dual_run(_args(tmp_path))
    assert report["ok"] is True
    assert old_calls
    assert all(method == "GET" for method, _ in old_calls)
    assert report["side_effect_safety"]["old_service_write_endpoints_executed"] is False


def test_report_detects_next_missing_required_key(monkeypatch, tmp_path: Path) -> None:
    def fake_old(base_url: str, method: str, path: str) -> dict:
        return _next_payload(path)

    def fake_next(method: str, path: str) -> dict:
        if path == "/api/customers":
            return {"status_code": 200, "payload": {"ok": True, "customers": [], "count": 0, "total": 0, "limit": 50, "offset": 0, "filters": {}}}
        return _next_payload(path)

    monkeypatch.setattr(dual_run, "_fetch_old_http", fake_old)
    monkeypatch.setattr(dual_run, "_fetch_next_testclient", fake_next)
    report = dual_run.run_dual_run(_args(tmp_path, scope="customer"))
    assert report["ok"] is False
    assert any(
        issue.get("side") == "next" and issue.get("rule") == "required_key" and issue.get("key") == "items"
        for item in report["endpoint_results"]
        for issue in item.get("issues", [])
    )


def test_old_missing_required_card_is_legacy_drift_when_next_has_it(monkeypatch, tmp_path: Path) -> None:
    def fake_old(base_url: str, method: str, path: str) -> dict:
        result = _next_payload(path)
        if path == "/api/admin/user-ops/overview":
            result["payload"] = _without_overview_card(result["payload"])
        return result

    monkeypatch.setattr(dual_run, "_fetch_old_http", fake_old)
    report = dual_run.run_dual_run(_args(tmp_path, scope="user_ops"))
    assert report["ok"] is True
    assert not report["blockers"]
    assert report["warnings"]
    assert report["legacy_drift"]
    drift = report["legacy_drift"][0]
    assert drift["field"] == "激活待录入"
    assert drift["reason"] == "legacy_missing_required_card_label"
    assert drift["next_satisfies_contract"] is True


def test_next_missing_required_card_is_blocker(monkeypatch, tmp_path: Path) -> None:
    def fake_old(base_url: str, method: str, path: str) -> dict:
        return _next_payload(path)

    def fake_next(method: str, path: str) -> dict:
        result = _next_payload(path)
        if path == "/api/admin/user-ops/overview":
            result["payload"] = _without_overview_card(result["payload"])
        return result

    monkeypatch.setattr(dual_run, "_fetch_old_http", fake_old)
    monkeypatch.setattr(dual_run, "_fetch_next_testclient", fake_next)
    report = dual_run.run_dual_run(_args(tmp_path, scope="user_ops"))
    assert report["ok"] is False
    assert any(
        issue.get("side") == "next" and issue.get("reason") == "next_missing_required_card_label"
        for blocker in report["blockers"]
        for issue in blocker["issues"]
    )


def test_both_missing_required_card_is_blocker(monkeypatch, tmp_path: Path) -> None:
    def fake_missing_card(method: str, path: str) -> dict:
        result = _next_payload(path)
        if path == "/api/admin/user-ops/overview":
            result["payload"] = _without_overview_card(result["payload"])
        return result

    def fake_old(base_url: str, method: str, path: str) -> dict:
        return fake_missing_card(method, path)

    monkeypatch.setattr(dual_run, "_fetch_old_http", fake_old)
    monkeypatch.setattr(dual_run, "_fetch_next_testclient", fake_missing_card)
    report = dual_run.run_dual_run(_args(tmp_path, scope="user_ops"))
    assert report["ok"] is False
    assert not report["legacy_drift"]
    assert any(
        issue.get("reason") == "both_missing_required_card_label"
        for blocker in report["blockers"]
        for issue in blocker["issues"]
    )


def test_report_detects_old_unreachable(monkeypatch, tmp_path: Path) -> None:
    def fake_old(base_url: str, method: str, path: str) -> dict:
        raise httpx.ConnectError("old service unavailable")

    monkeypatch.setattr(dual_run, "_fetch_old_http", fake_old)
    report = dual_run.run_dual_run(_args(tmp_path, scope="user_ops"))
    assert report["ok"] is False
    assert report["blockers"]
    assert all(item["issues"][0]["rule"] == "old_unreachable" for item in report["blockers"])


def test_report_skips_detail_when_no_customer_sample(monkeypatch, tmp_path: Path) -> None:
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

    def fake_old(base_url: str, method: str, path: str) -> dict:
        if path.startswith("/api/customers"):
            return {"status_code": 200, "payload": empty_list}
        raise AssertionError(f"detail endpoint should have been skipped: {path}")

    monkeypatch.setattr(dual_run, "_fetch_old_http", fake_old)
    report = dual_run.run_dual_run(_args(tmp_path, scope="customer"))
    skipped = {item["endpoint"]: item for item in report["skipped"]}
    assert skipped["customer_detail.sample"]["reason"] == "no_customer_sample"
    assert skipped["customer_timeline.sample"]["reason"] == "no_customer_sample"
    assert skipped["recent_messages.sample"]["reason"] == "no_customer_sample"


def test_tool_writes_reports(monkeypatch, tmp_path: Path) -> None:
    def fake_old(base_url: str, method: str, path: str) -> dict:
        return _next_payload(path)

    monkeypatch.setattr(dual_run, "_fetch_old_http", fake_old)
    args = _args(tmp_path, scope="user_ops")
    report = dual_run.run_dual_run(args)
    dual_run.write_markdown_report(report, Path(args.output_md))
    dual_run.write_json_report(report, Path(args.output_json))
    assert "Readonly HTTP Dual-Run Report" in Path(args.output_md).read_text(encoding="utf-8")
    assert "## Warnings" in Path(args.output_md).read_text(encoding="utf-8")
    assert "## Legacy Drift" in Path(args.output_md).read_text(encoding="utf-8")
    assert json.loads(Path(args.output_json).read_text(encoding="utf-8"))["ok"] is True
    assert "legacy_drift" in json.loads(Path(args.output_json).read_text(encoding="utf-8"))


def test_activation_pending_card_remains_required_in_user_ops_spec() -> None:
    assert "激活待录入" in user_ops_spec.OVERVIEW_CARD_LABELS


def test_tool_does_not_import_old_backends() -> None:
    text = (PROJECT_ROOT / "tools" / "readonly_http_dual_run.py").read_text(encoding="utf-8")
    assert "import wecom_ability_service" not in text
    assert "from wecom_ability_service" not in text
    assert "import openclaw_service" not in text
    assert "from openclaw_service" not in text
