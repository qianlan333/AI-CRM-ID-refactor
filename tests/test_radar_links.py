from __future__ import annotations

import base64
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from aicrm_next.main import create_app
from aicrm_next.radar_links.repo import build_radar_links_repository


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    monkeypatch.setenv("SECRET_KEY", "radar-links-test-secret")
    monkeypatch.setenv("AICRM_NEXT_WECHAT_OAUTH_MODE", "fake")
    return TestClient(create_app(), raise_server_exceptions=False)


def _create_link(client: TestClient, **overrides):
    payload = {
        "title": "直播报名页",
        "original_url": "https://example.com/landing",
        "enabled": True,
        "auth_required": False,
        "source_channel": "wechat_group",
        "campaign_id": "campaign_001",
        "staff_id": "staff_001",
    }
    payload.update(overrides)
    response = client.post("/api/admin/radar-links", json=payload)
    assert response.status_code == 200, response.text
    return response.json()["radar_link"]


def _state_from_oauth_start_location(location: str) -> str:
    parsed = urlparse(location)
    values = parse_qs(parsed.query)
    return values["state"][0]


def _decode_state_payload(state: str) -> dict:
    body = state.split(".", 1)[0]
    padding = "=" * (-len(body) % 4)
    return json.loads(base64.urlsafe_b64decode((body + padding).encode("ascii")).decode("utf-8"))


def test_create_radar_link_returns_wrapper_url(client):
    link = _create_link(client)

    assert link["id"] >= 1
    assert link["code"]
    assert link["wrapper_url"].endswith(f"/r/{link['code']}")
    assert link["original_url"] == "https://example.com/landing"


def test_admin_radar_links_page_is_in_operations_nav(client):
    response = client.get("/admin/radar-links")

    assert response.status_code == 200
    assert "雷达外链" in response.text
    assert "/api/admin/radar-links" in response.text


@pytest.mark.parametrize("original_url", ["javascript:alert(1)", "data:text/plain,hello", "file:///tmp/a", "ftp://example.com/a"])
def test_rejects_illegal_url_scheme(client, original_url):
    response = client.post(
        "/api/admin/radar-links",
        json={"title": "bad", "original_url": original_url},
    )

    assert response.status_code == 400
    assert "http or https" in response.text


@pytest.mark.parametrize("original_url", ["http://localhost/a", "http://127.0.0.1/a", "http://10.0.0.1/a", "http://172.16.1.2/a", "http://192.168.1.3/a", "http://[::1]/a"])
def test_rejects_localhost_and_private_ip_targets(client, original_url):
    response = client.post(
        "/api/admin/radar-links",
        json={"title": "bad", "original_url": original_url},
    )

    assert response.status_code == 400
    assert "host is not allowed" in response.text


def test_disabled_link_access_returns_404(client):
    link = _create_link(client)
    disable_response = client.post(f"/api/admin/radar-links/{link['id']}/disable")
    assert disable_response.status_code == 200

    response = client.get(f"/r/{link['code']}", follow_redirects=False)

    assert response.status_code == 404


def test_public_radar_redirect_records_landing(client):
    link = _create_link(client)

    response = client.get(f"/r/{link['code']}", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "https://example.com/landing"
    events = client.get(f"/api/admin/radar-links/{link['id']}/events").json()["events"]
    assert [event["stage"] for event in events] == ["landing"]


def test_fake_oauth_callback_with_unionid_records_authorized_click_and_redirects(client):
    link = _create_link(client, auth_required=True)
    landing_response = client.get(f"/r/{link['code']}", follow_redirects=False)
    assert landing_response.status_code == 302
    state = _state_from_oauth_start_location(landing_response.headers["location"])
    state_payload = _decode_state_payload(state)
    assert set(state_payload) == {"code", "nonce", "exp"}
    assert state_payload["code"] == link["code"]

    callback_response = client.get(
        "/api/h5/radar/oauth/callback",
        params={"state": state, "unionid": "unionid_from_fake_callback"},
        follow_redirects=False,
    )

    assert callback_response.status_code == 302
    assert callback_response.headers["location"] == "https://example.com/landing"
    events = client.get(f"/api/admin/radar-links/{link['id']}/events").json()["events"]
    stages = [event["stage"] for event in events]
    assert stages == ["authorized_click", "oauth_callback", "landing"]
    assert events[0]["unionid"] == "unionid_from_fake_callback"


def test_stats_returns_required_click_fields(client):
    link = _create_link(client, auth_required=True)
    landing_response = client.get(f"/r/{link['code']}", follow_redirects=False)
    state = _state_from_oauth_start_location(landing_response.headers["location"])
    client.get("/api/h5/radar/oauth/callback", params={"state": state, "unionid": "unionid_stats"}, follow_redirects=False)

    response = client.get(f"/api/admin/radar-links/{link['id']}/stats")

    assert response.status_code == 200
    stats = response.json()["stats"]
    assert set(stats) == {"total_clicks", "authorized_clicks", "unique_users", "today_clicks", "last_clicked_at"}
    assert stats["total_clicks"] == 1
    assert stats["authorized_clicks"] == 1
    assert stats["unique_users"] == 1
    assert stats["today_clicks"] == 1
    assert stats["last_clicked_at"]


def test_public_redirect_query_cannot_override_original_url(client):
    link = _create_link(client, original_url="https://example.com/fixed")

    response = client.get(f"/r/{link['code']}?redirect=https://evil.example/phish", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "https://example.com/fixed"


def test_radar_links_uses_postgres_repo_when_production_data_ready(monkeypatch):
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("DATABASE_URL", "postgresql://probe:probe@127.0.0.1:1/aicrm_probe")
    monkeypatch.delenv("AICRM_NEXT_ALLOW_FIXTURE_REPO_IN_PROD", raising=False)

    repo = build_radar_links_repository()

    assert repo.__class__.__name__ == "PostgresRadarLinksRepository"


def test_radar_links_api_does_not_return_fixture_success_when_production_data_ready(monkeypatch):
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("DATABASE_URL", "postgresql://probe:probe@127.0.0.1:1/aicrm_probe")
    monkeypatch.delenv("AICRM_NEXT_ALLOW_FIXTURE_REPO_IN_PROD", raising=False)

    response = TestClient(create_app(), raise_server_exceptions=False).get("/api/admin/radar-links")

    assert response.status_code == 503
    assert "production_unavailable" in response.text
    assert "fixture_repository_blocked_in_production" not in response.text


def test_postgres_schema_includes_radar_tables():
    schema = (ROOT / "wecom_ability_service" / "schema_postgres.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS radar_links" in schema
    assert "CREATE TABLE IF NOT EXISTS radar_click_events" in schema
    assert "idx_radar_click_events_link_created" in schema
