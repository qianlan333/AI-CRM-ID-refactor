from __future__ import annotations

import json
import os

from sqlalchemy import text

from aicrm_next.shared.db_session import get_session_factory
from scripts import ai_audience_apply_package_spec as spec_script
from tests.test_ai_audience_package_spec import VALID_SPEC


TOKEN = "external-spec-test-token"


def _headers(token: str = TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _ready_env(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_AI_AUDIENCE_SPEC_API_TOKEN", TOKEN)
    monkeypatch.setenv("AICRM_AI_AUDIENCE_SPEC_ALLOWED_PREFIXES", "prod_verify_")
    monkeypatch.setenv("AICRM_AI_AUDIENCE_SPEC_ALLOW_PUBLISH", "false")
    monkeypatch.setenv("AICRM_AI_AUDIENCE_SPEC_ALLOW_NON_VERIFY_PREFIX", "false")
    if os.getenv("DATABASE_URL"):
        monkeypatch.setenv("AICRM_AUDIENCE_READONLY_DATABASE_URL", os.environ["DATABASE_URL"])


def _spec(package_key: str = "spec_q101") -> str:
    return VALID_SPEC.replace("package_key: spec_q101", f"package_key: {package_key}")


def test_external_spec_auth_guards(next_client, monkeypatch) -> None:
    monkeypatch.delenv("AICRM_AI_AUDIENCE_SPEC_API_TOKEN", raising=False)
    missing_config = next_client.post("/api/external/ai-audience/spec/dry-run", json={"spec_markdown": _spec(), "package_key_prefix": "prod_verify_"})
    assert missing_config.status_code == 503
    assert missing_config.json()["error"] == "external_token_not_configured"

    monkeypatch.setenv("AICRM_AI_AUDIENCE_SPEC_API_TOKEN", TOKEN)
    no_auth = next_client.post("/api/external/ai-audience/spec/dry-run", json={"spec_markdown": _spec(), "package_key_prefix": "prod_verify_"})
    assert no_auth.status_code == 401
    assert no_auth.json()["error"] == "external_token_required"

    wrong = next_client.post("/api/external/ai-audience/spec/dry-run", headers=_headers("bad"), json={"spec_markdown": _spec(), "package_key_prefix": "prod_verify_"})
    assert wrong.status_code == 401
    assert wrong.json()["error"] == "external_token_invalid"
    assert TOKEN not in wrong.text


def test_external_spec_dry_run_validates_without_creating_package(next_client, next_pg_schema, monkeypatch) -> None:
    del next_pg_schema
    _ready_env(monkeypatch)

    response = next_client.post(
        "/api/external/ai-audience/spec/dry-run",
        headers=_headers(),
        json={"spec_markdown": _spec(), "package_key_prefix": "prod_verify_"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["mode"] == "dry_run"
    assert payload["package_key"] == "prod_verify_spec_q101"
    assert payload["validation_errors"] == []
    assert "audience_read.questionnaire_submissions_v1" in payload["dependencies"]
    with get_session_factory()() as session:
        count = session.execute(text("SELECT COUNT(*) FROM ai_audience_package WHERE package_key = 'prod_verify_spec_q101'")).scalar_one()
        audit_count = session.execute(text("SELECT COUNT(*) FROM admin_operation_logs WHERE target_type = 'ai_audience_external_spec'")).scalar_one()
    assert count == 0
    assert audit_count == 1


def test_external_spec_dry_run_blocks_invalid_sql_and_prefix(next_client, next_pg_schema, monkeypatch) -> None:
    del next_pg_schema
    _ready_env(monkeypatch)
    invalid_refresh = _spec().replace("refresh_mode: incremental_3m", "refresh_mode: incremental_5m")
    select_star = _spec().replace(
        "SELECT\n  'external_userid' AS identity_type,",
        "SELECT\n  *,\n  'external_userid' AS identity_type,",
    )
    public_schema = _spec().replace("FROM audience_read.questionnaire_submissions_v1 qs", "FROM public.users qs")

    cases = [
        (invalid_refresh, "invalid_refresh_mode"),
        (select_star, "incremental:select_star_forbidden"),
        (public_schema, "incremental:dependency_not_allowed:public.users"),
    ]
    for markdown, expected in cases:
        response = next_client.post(
            "/api/external/ai-audience/spec/dry-run",
            headers=_headers(),
            json={"spec_markdown": markdown, "package_key_prefix": "prod_verify_"},
        )
        assert response.status_code == 400
        assert expected in response.json()["validation_errors"]

    bad_prefix = next_client.post(
        "/api/external/ai-audience/spec/dry-run",
        headers=_headers(),
        json={"spec_markdown": _spec(), "package_key_prefix": "official_"},
    )
    assert bad_prefix.status_code == 400
    assert "package_key_prefix_not_allowed" in bad_prefix.json()["validation_errors"]


def test_external_spec_apply_creates_package_version_and_no_side_effects(next_client, next_pg_schema, monkeypatch) -> None:
    del next_pg_schema
    _ready_env(monkeypatch)

    response = next_client.post(
        "/api/external/ai-audience/spec/apply",
        headers=_headers(),
        json={"spec_markdown": _spec(), "package_key_prefix": "prod_verify_", "operator": "codex", "publish": False},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["package_key"] == "prod_verify_spec_q101"
    assert payload["created"] is True
    assert payload["updated"] is False
    assert payload["package_id"]
    assert payload["version_id"]
    assert payload["preview_ok"] is True
    assert payload["published"] is False
    assert "secret" not in json.dumps(payload, ensure_ascii=False).lower()
    with get_session_factory()() as session:
        package = session.execute(text("SELECT status, current_version_id FROM ai_audience_package WHERE id = :id"), {"id": payload["package_id"]}).mappings().one()
        version = session.execute(text("SELECT parameters_json FROM ai_audience_package_version WHERE id = :id"), {"id": payload["version_id"]}).mappings().one()
        effects = session.execute(text("SELECT COUNT(*) FROM external_effect_job")).scalar_one()
        sends = session.execute(text("SELECT COUNT(*) FROM user_ops_send_records")).scalar_one()
    assert package["status"] == "paused"
    assert package["current_version_id"] is None
    assert version["parameters_json"] == {"questionnaire_id": 101}
    assert effects == 0
    assert sends == 0


def test_external_spec_publish_gate_and_no_activate(next_client, next_pg_schema, monkeypatch) -> None:
    del next_pg_schema
    _ready_env(monkeypatch)
    applied = next_client.post(
        "/api/external/ai-audience/spec/apply",
        headers=_headers(),
        json={"spec_markdown": _spec("publish_spec"), "package_key_prefix": "prod_verify_", "operator": "codex", "publish": False},
    ).json()

    blocked = next_client.post(
        "/api/external/ai-audience/spec/publish",
        headers=_headers(),
        json={"package_key": "prod_verify_publish_spec", "version_id": applied["version_id"], "operator": "codex"},
    )
    assert blocked.status_code == 403
    assert blocked.json()["error"] == "publish_not_allowed"

    monkeypatch.setenv("AICRM_AI_AUDIENCE_SPEC_ALLOW_PUBLISH", "true")
    published = next_client.post(
        "/api/external/ai-audience/spec/publish",
        headers=_headers(),
        json={"package_key": "prod_verify_publish_spec", "version_id": applied["version_id"], "operator": "codex"},
    )
    assert published.status_code == 200
    assert published.json()["published"] is True
    with get_session_factory()() as session:
        package = session.execute(text("SELECT status, current_version_id FROM ai_audience_package WHERE id = :id"), {"id": applied["package_id"]}).mappings().one()
    assert package["status"] == "paused"
    assert package["current_version_id"] == applied["version_id"]


def test_external_spec_archive_allows_only_configured_prefix(next_client, next_pg_schema, monkeypatch) -> None:
    del next_pg_schema
    _ready_env(monkeypatch)
    applied = next_client.post(
        "/api/external/ai-audience/spec/apply",
        headers=_headers(),
        json={"spec_markdown": _spec("archive_spec"), "package_key_prefix": "prod_verify_", "operator": "codex"},
    ).json()

    denied = next_client.post(
        "/api/external/ai-audience/packages/official_archive_spec/archive",
        headers=_headers(),
        json={"operator": "codex"},
    )
    assert denied.status_code == 403
    assert denied.json()["error"] in {"package_key_prefix_not_allowed", "non_verify_prefix_not_allowed"}

    archived = next_client.post(
        "/api/external/ai-audience/packages/prod_verify_archive_spec/archive",
        headers=_headers(),
        json={"operator": "codex"},
    )
    assert archived.status_code == 200
    assert archived.json()["archived"] is True
    with get_session_factory()() as session:
        status = session.execute(text("SELECT status FROM ai_audience_package WHERE id = :id"), {"id": applied["package_id"]}).scalar_one()
    assert status == "archived"


def test_external_spec_script_mode_uses_bearer_token(monkeypatch, tmp_path) -> None:
    spec_path = tmp_path / "spec.md"
    spec_path.write_text(_spec(), encoding="utf-8")
    calls: list[dict] = []

    def fake_http_json(method, url, *, cookie="", bearer_token="", payload=None):
        calls.append({"method": method, "url": url, "cookie": cookie, "bearer_token": bearer_token, "payload": payload})
        return {
            "ok": True,
            "package_key": "prod_verify_spec_q101",
            "package_id": 1,
            "version_id": 2,
            "created": True,
            "updated": False,
            "preview_ok": True,
            "published": False,
            "validation_errors": [],
            "warnings": [],
        }

    monkeypatch.setattr(spec_script, "_http_json", fake_http_json)
    monkeypatch.setenv("AICRM_AI_AUDIENCE_SPEC_API_TOKEN", TOKEN)
    rc = spec_script.main(
        [
            str(spec_path),
            "--external-api-base",
            "https://example.test",
            "--external-token-from-env",
            "--apply",
            "--package-key-prefix",
            "prod_verify_",
        ]
    )

    assert rc == 0
    assert calls
    assert calls[0]["url"] == "https://example.test/api/external/ai-audience/spec/apply"
    assert calls[0]["bearer_token"] == TOKEN
    assert calls[0]["cookie"] == ""
