from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = ROOT / "tools/check_phase3d_recent_messages_readonly.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_phase3d_recent_messages_readonly",
        CHECKER_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _client_and_checker():
    pytest.importorskip("fastapi")
    checker = _load_checker()
    with checker.production_recent_messages_probe_env():
        return checker._make_client(), checker


def test_checker_current_repo_passes_when_fastapi_available():
    pytest.importorskip("fastapi")
    checker = _load_checker()
    report = checker.build_report()
    assert report["overall"] == "PASS", report


def test_endpoint_module_is_exact_next_readonly_owner():
    client, checker = _client_and_checker()
    assert (
        checker.first_matching_endpoint_module(
            client.app,
            method="GET",
            path="/api/messages/external-phase3d-probe/recent",
        )
        == "aicrm_next.customer_read_model.api"
    )


def test_production_probe_does_not_return_200_fake_success():
    client, checker = _client_and_checker()
    response = client.get("/api/messages/external-phase3d-probe/recent?limit=2")
    body = response.text
    assert not (response.status_code == 200 and checker._contains_fixture_marker(body))
    if response.status_code == 200:
        payload = response.json()
        assert payload.get("source_status") not in {"fixture", "local_contract", "demo"}


def test_target_handler_calls_application_query_only():
    checker = _load_checker()
    report = checker.check_static_boundaries()
    assert report["ok"], report
    api_source = (ROOT / "aicrm_next/customer_read_model/api.py").read_text(encoding="utf-8")
    source = checker._function_source(api_source, "get_recent_messages")
    assert "ListRecentMessagesQuery" in source
    assert "JSONResponse" in source
    for forbidden in checker.FORBIDDEN_HANDLER_CALLS:
        assert forbidden not in source


def test_api_does_not_directly_import_recent_messages_legacy_facade():
    source = (ROOT / "aicrm_next/customer_read_model/api.py").read_text(encoding="utf-8")
    assert "recent_messages_via_legacy" not in source
    assert "legacy_customer_read_facade" not in source


def test_phase3a_3b_3c_routes_still_resolve_to_next_exact_owners():
    client, checker = _client_and_checker()
    expected = {
        "/api/sidebar/contact-binding-status": "aicrm_next.identity_contact.api",
        "/api/sidebar/customer-context": "aicrm_next.customer_read_model.api",
        "/api/admin/customers/profile": "aicrm_next.customer_read_model.api",
        "/api/admin/customers/profile/tags": "aicrm_next.customer_read_model.api",
        "/api/customers": "aicrm_next.customer_read_model.api",
        "/api/customers/external-phase3d-probe": "aicrm_next.customer_read_model.api",
        "/api/customers/external-phase3d-probe/timeline": "aicrm_next.customer_read_model.api",
    }
    for path, endpoint_module in expected.items():
        assert checker.first_matching_endpoint_module(client.app, method="GET", path=path) == endpoint_module


def test_production_compat_runtime_behavior_is_preserved():
    source = (ROOT / "aicrm_next/production_compat/api.py").read_text(encoding="utf-8")
    assert '@wildcard_router.api_route("/api/messages/{path:path}", methods=_ALL_METHODS)' in source
    assert "async def legacy_production_compat_routes" in source
    assert "return await forward_to_legacy_flask(request)" in source


def test_phase3d_does_not_enable_real_external_calls():
    changed_sources = [
        ROOT / "aicrm_next/customer_read_model/api.py",
        ROOT / "aicrm_next/customer_read_model/application.py",
        CHECKER_PATH,
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in changed_sources)
    forbidden_markers = (
        "WECHAT_REAL_CALL",
        "WECOM_REAL_CALL",
        "PAYMENT_REAL_CALL",
        "OPENCLAW_REAL_CALL",
        "MCP_REAL_CALL",
        "real_allowed",
        "real_enabled",
    )
    assert not any(marker in combined for marker in forbidden_markers)


def test_not_found_still_returns_404(monkeypatch):
    pytest.importorskip("fastapi")
    checker = _load_checker()
    monkeypatch.setenv("AICRM_NEXT_ENV", "development")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    client = checker._make_client()
    response = client.get("/api/messages/external-phase3d-not-found/recent?limit=2")
    assert response.status_code == 404
