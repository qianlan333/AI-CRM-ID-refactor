from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


def make_client(monkeypatch) -> TestClient:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SECRET_KEY", "next-admin-mcp-console-test")
    return TestClient(create_app(), follow_redirects=False)


def test_admin_mcp_console_paths_redirect_to_next_api_docs(monkeypatch) -> None:
    client = make_client(monkeypatch)

    for method, path in [
        ("GET", "/admin/mcp"),
        ("POST", "/admin/mcp/preflight"),
        ("POST", "/admin/mcp/sample-call"),
    ]:
        response = client.request(method, path, data={"tool_name": "resolve_customer"})
        assert response.status_code in {302, 307}
        assert response.headers["location"].endswith("/admin/api-docs")


def test_admin_api_docs_renders_current_mcp_section(monkeypatch) -> None:
    client = TestClient(create_app())

    response = client.get("/admin/api-docs")
    html = response.text

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert "MCP" in html or "/mcp" in html
