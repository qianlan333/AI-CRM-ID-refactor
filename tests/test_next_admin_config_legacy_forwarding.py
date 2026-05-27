from __future__ import annotations

from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

from aicrm_next.main import create_app


def _client(monkeypatch) -> TestClient:
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SECRET_KEY", "admin-config-legacy-forwarding-test")
    return TestClient(create_app())


def test_admin_config_routes_forward_to_legacy_facade(monkeypatch):
    import aicrm_next.frontend_compat.legacy_routes as legacy_routes

    forwarded: list[tuple[str, str]] = []

    class ExplodingRuntimeConfigQuery:
        def __call__(self):
            raise AssertionError("/admin/config must not render real_data_page runtime config")

    async def fake_forward_to_legacy_flask(request):
        forwarded.append((request.method, request.url.path))
        return PlainTextResponse(f"legacy-config-center:{request.url.path}")

    monkeypatch.setattr(legacy_routes, "GetAdminConfigPageQuery", ExplodingRuntimeConfigQuery)
    monkeypatch.setattr(legacy_routes, "forward_to_legacy_flask", fake_forward_to_legacy_flask)

    client = _client(monkeypatch)

    expectations = [
        ("get", "/admin/config"),
        ("get", "/admin/config/app-settings"),
        ("get", "/admin/config/login-access"),
        ("get", "/admin/config/checklist"),
        ("post", "/admin/config/app-settings/save"),
        ("post", "/admin/config/login-access/save"),
        ("get", "/setup/wizard"),
        ("post", "/setup/wizard/save"),
        ("get", "/api/admin/config/app-settings"),
        ("put", "/api/admin/config/app-settings"),
    ]
    for method, path in expectations:
        request = getattr(client, method)
        response = request(path, json={"confirm": True}) if method == "put" else request(path)
        assert response.status_code == 200, path
        assert response.text == f"legacy-config-center:{path}"
        assert "production_data_ready" not in response.text
        assert "callback_fallback" not in response.text
        assert "release_sha" not in response.text

    assert forwarded == [(method.upper(), path) for method, path in expectations]


def test_admin_config_manifest_lists_legacy_config_center_routes(monkeypatch):
    routes = _client(monkeypatch).get("/api/frontend-compat/legacy-routes").json()["routes"]

    for route in [
        "/admin/config",
        "/admin/config/app-settings",
        "/admin/config/login-access",
        "/admin/config/checklist",
        "/setup/wizard",
    ]:
        assert route in routes
