from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_old_customer_http_route_files_are_absent() -> None:
    for path in [
        "wecom_ability_service/http/customer_center.py",
        "wecom_ability_service/http/customer_timeline.py",
    ]:
        assert not (REPO_ROOT / path).exists(), path


def test_customer_dependency_directories_are_preserved_as_legacy_fallback_only() -> None:
    for directory in [
        REPO_ROOT / "wecom_ability_service" / "customer_center",
        REPO_ROOT / "wecom_ability_service" / "customer_timeline",
    ]:
        assert directory.exists()
        marker = directory / "LEGACY_DEPENDENCY_FALLBACK.md"
        assert marker.exists()
        content = marker.read_text(encoding="utf-8")
        assert "no longer owns legacy Flask Customer Read Model" in content
        assert "Do not add new business features" in content


def test_old_http_registrar_has_no_customer_center_or_timeline_import_or_register_entry() -> None:
    content = _read("wecom_ability_service/http/__init__.py")
    forbidden_tokens = [
        "from .customer_center import",
        "from .customer_timeline import",
        "register_customer_center_routes",
        "register_customer_timeline_routes",
        '"customer_center": "wecom_ability_service.http.customer_center"',
        '"customer_timeline": "wecom_ability_service.http.customer_timeline"',
        '("customer_center", register_customer_center_routes)',
        '("customer_timeline", register_customer_timeline_routes)',
    ]
    assert [token for token in forbidden_tokens if token in content] == []


def test_archive_contacts_identity_fallback_files_still_exist() -> None:
    for path in [
        "wecom_ability_service/http/archive.py",
        "wecom_ability_service/http/contacts.py",
        "wecom_ability_service/http/identity.py",
    ]:
        assert (REPO_ROOT / path).exists(), path


def test_legacy_flask_no_longer_registers_customer_readonly_routes_but_keeps_recent_messages() -> None:
    pytest.importorskip("flask")
    from wecom_ability_service import create_app

    app = create_app({"TESTING": True})
    routes = {rule.rule for rule in app.url_map.iter_rules()}
    for route in [
        "/admin/customers",
        "/api/customers",
        "/api/customers/<external_userid>",
        "/api/customers/<external_userid>/timeline",
    ]:
        assert route not in routes
    assert "/api/messages/<external_userid>/recent" in routes


def test_aicrm_next_customer_read_model_package_exists() -> None:
    assert (REPO_ROOT / "aicrm_next" / "customer_read_model" / "api.py").exists()
    assert (REPO_ROOT / "aicrm_next" / "customer_read_model" / "repo.py").exists()


def test_next_customer_readonly_routes_are_served_by_ai_crm_next() -> None:
    testclient_module = pytest.importorskip("fastapi.testclient")
    TestClient = testclient_module.TestClient
    from aicrm_next.main import app

    client = TestClient(app)
    list_response = client.get("/api/customers?limit=5&offset=0")
    assert list_response.status_code == 200
    assert list_response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    items = list_response.json()["items"]
    assert items
    external_userid = items[0]["external_userid"]

    for path in [
        "/admin/customers",
        f"/api/customers/{external_userid}",
        f"/api/customers/{external_userid}/timeline?limit=5&offset=0",
        f"/api/messages/{external_userid}/recent?limit=5",
    ]:
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"


def test_app_py_default_is_still_next() -> None:
    content = _read("app.py")
    assert 'NEXT_APP_IMPORT = "aicrm_next.main:app"' in content
    assert "uvicorn.run(NEXT_APP_IMPORT" in content
    assert "command = args.command or \"run\"" in content


def test_legacy_fallback_still_exists_and_help_works() -> None:
    assert (REPO_ROOT / "legacy_flask_app.py").exists()
    help_result = subprocess.run(
        ["python3", "legacy_flask_app.py", "--help"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "legacy Flask fallback" in help_result.stdout or "legacy Flask fallback" in help_result.stderr


def test_deploy_and_production_config_not_modified_by_d3() -> None:
    result = subprocess.run(
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    changed = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    forbidden = [
        path
        for path in changed
        if path.startswith("deploy/")
        or path.startswith(".github/")
        or any(keyword in path.lower() for keyword in ["nginx", "systemd", "supervisor", "docker-compose", "production"])
        and not path.startswith(("docs/", "tests/", "tools/"))
    ]
    assert forbidden == []


def test_d4_to_d9_docs_are_not_marked_retired() -> None:
    content = _read("docs/legacy_delete_batches.md")
    for batch in ["D4", "D5", "D6", "D7", "D8", "D9"]:
        section = content.split(f"## {batch}:", 1)[1].split("## ", 1)[0]
        status_line = next((line.strip().lower() for line in section.splitlines() if line.strip().lower().startswith("status:")), "")
        assert not status_line.startswith("status: retired")
        assert not status_line.startswith("status: deleted")


def test_d3_retirement_checker_returns_ok(tmp_path: Path) -> None:
    output_md = tmp_path / "d3.md"
    output_json = tmp_path / "d3.json"
    subprocess.run(
        [
            "python3",
            "tools/check_legacy_d3_customer_retirement.py",
            "--output-md",
            str(output_md),
            "--output-json",
            str(output_json),
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["production_config_modified"] is False
    assert payload["archive_contacts_identity_preserved"]["wecom_ability_service/http/archive.py"] is True
