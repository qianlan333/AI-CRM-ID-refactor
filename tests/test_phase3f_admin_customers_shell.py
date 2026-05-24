from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = ROOT / "tools/check_phase3f_admin_customers_shell.py"
ACCEPTANCE_CHECKER_PATH = ROOT / "tools/check_phase3_readonly_acceptance.py"


def _load_checker(path: Path = CHECKER_PATH):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _client_and_checker():
    pytest.importorskip("fastapi")
    checker = _load_checker()
    with checker.production_admin_customers_probe_env():
        return checker._make_client(), checker


def test_checker_current_repo_passes_when_fastapi_available():
    pytest.importorskip("fastapi")
    checker = _load_checker()
    report = checker.build_report()
    assert report["overall"] == "PASS", report


def test_admin_customers_endpoint_module_is_exact_next_shell_owner():
    client, checker = _client_and_checker()
    assert (
        checker.first_matching_endpoint_module(client.app, method="GET", path="/admin/customers")
        == "aicrm_next.frontend_compat.legacy_routes"
    )


def test_production_probe_does_not_render_fixture_customer_success():
    client, checker = _client_and_checker()
    response = client.get("/admin/customers?keyword=phase3f")
    assert response.status_code < 500
    assert response.headers.get("X-AICRM-Compatibility-Facade", "") != "legacy_flask_facade"
    assert not (
        response.status_code == 200
        and checker._contains_fixture_marker(response.text)
    )


def test_admin_customers_handler_calls_application_query_boundary():
    checker = _load_checker()
    report = checker.check_static_boundaries()
    assert report["ok"], report
    source = (ROOT / "aicrm_next/frontend_compat/legacy_routes.py").read_text(encoding="utf-8")
    handler = checker._function_source(source, "admin_customers")
    assert "ListCustomersQuery" in handler
    assert "ListCustomersRequest" in handler
    for forbidden in checker.FORBIDDEN_HANDLER_CALLS:
        assert forbidden not in handler
    assert "list_customers_via_legacy" not in source


def test_admin_customers_still_renders_customer_list_page():
    pytest.importorskip("fastapi")
    checker = _load_checker()
    client = checker._make_client()
    response = client.get("/admin/customers")
    assert response.status_code == 200
    assert "客户查找" in response.text
    assert "客户列表" in response.text


def test_phase3_acceptance_routes_still_pass_when_fastapi_available():
    pytest.importorskip("fastapi")
    acceptance = _load_checker(ACCEPTANCE_CHECKER_PATH)
    report = acceptance.build_report()
    assert report["overall"] == "PASS", report


def test_production_compat_runtime_behavior_is_not_modified():
    result = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            "origin/main",
            "--",
            "aicrm_next/main.py",
            "aicrm_next/production_compat/api.py",
        ],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    assert result.stdout.strip() == ""


def test_phase3f_does_not_enable_real_external_calls():
    changed_sources = [
        ROOT / "aicrm_next/frontend_compat/legacy_routes.py",
        ROOT / "docs/development/phase_3f_admin_customers_shell_hardening.md",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in changed_sources)
    forbidden_markers = (
        "WECHAT_REAL_CALL",
        "WECOM_REAL_CALL",
        "PAYMENT_REAL_CALL",
        "OPENCLAW_REAL_CALL",
        "MCP_REAL_CALL",
        "AICRM_NEXT_ENABLE_REAL_ARCHIVE_SYNC=1",
        "real_allowed",
        "real_enabled",
    )
    assert not any(marker in combined for marker in forbidden_markers)
