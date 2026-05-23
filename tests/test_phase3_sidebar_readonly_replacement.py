from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = ROOT / "tools/check_phase3_sidebar_readonly_replacement.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_phase3_sidebar_readonly_replacement",
        CHECKER_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _client_and_checker():
    pytest.importorskip("fastapi")
    checker = _load_checker()
    with checker.production_sidebar_probe_env():
        return checker._make_client(), checker


def test_checker_current_repo_passes_when_fastapi_available():
    pytest.importorskip("fastapi")
    checker = _load_checker()
    report = checker.build_report()
    assert report["overall"] == "PASS", report


def test_endpoint_modules_are_exact_next_readonly_owners():
    client, checker = _client_and_checker()
    assert (
        checker.first_matching_endpoint_module(
            client.app,
            method="GET",
            path="/api/sidebar/contact-binding-status",
        )
        == "aicrm_next.identity_contact.api"
    )
    assert (
        checker.first_matching_endpoint_module(
            client.app,
            method="GET",
            path="/api/sidebar/customer-context",
        )
        == "aicrm_next.customer_read_model.api"
    )


def test_missing_external_userid_returns_400_without_fixture_marker():
    client, checker = _client_and_checker()
    for path in ("/api/sidebar/contact-binding-status", "/api/sidebar/customer-context"):
        response = client.get(path)
        assert response.status_code == 400
        assert not checker._contains_fixture_marker(response.text)


def test_production_probe_does_not_return_200_fake_success():
    client, checker = _client_and_checker()
    for path in ("/api/sidebar/contact-binding-status", "/api/sidebar/customer-context"):
        response = client.get(path, params={"external_userid": "wm_phase3_probe"})
        body = response.text
        assert not (response.status_code == 200 and checker._contains_fixture_marker(body))
        if response.status_code == 200:
            payload = response.json()
            assert payload.get("source_status") not in {"fixture", "local_contract", "demo"}


def test_identity_contact_api_has_no_direct_legacy_customer_read_facade_import():
    api_source = (ROOT / "aicrm_next/identity_contact/api.py").read_text(encoding="utf-8")
    assert "legacy_customer_read_facade" not in api_source
    assert "get_customer_via_legacy" not in api_source


def test_bind_mobile_write_route_is_not_changed_to_unguarded_next_write():
    client, checker = _client_and_checker()
    endpoint_module = checker.first_matching_endpoint_module(
        client.app,
        method="POST",
        path="/api/sidebar/bind-mobile",
    )
    assert endpoint_module != "aicrm_next.identity_contact.api"


def test_production_compat_sidebar_wildcard_runtime_behavior_is_preserved():
    source = (ROOT / "aicrm_next/production_compat/api.py").read_text(encoding="utf-8")
    assert '@wildcard_router.api_route("/api/sidebar/{path:path}", methods=_ALL_METHODS)' in source
    assert "async def legacy_production_compat_routes" in source
    assert "return await forward_to_legacy_flask(request)" in source


def test_phase3_checker_does_not_enable_real_external_calls():
    changed_sources = [
        ROOT / "aicrm_next/identity_contact/api.py",
        ROOT / "aicrm_next/identity_contact/application.py",
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
