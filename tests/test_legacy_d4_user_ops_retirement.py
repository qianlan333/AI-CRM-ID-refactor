from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_old_user_ops_readonly_route_owner_is_absent_or_tombstoned() -> None:
    for path in [
        "wecom_ability_service/http/admin_user_ops.py",
        "wecom_ability_service/http/admin_user_ops_delivery.py",
    ]:
        file_path = REPO_ROOT / path
        if not file_path.exists():
            continue
        content = file_path.read_text(encoding="utf-8").lower()
        assert "tombstone" in content
        assert "def register_routes" not in content


def test_old_http_registrar_has_no_user_ops_admin_import_or_register_entry() -> None:
    content = _read("wecom_ability_service/http/__init__.py")
    forbidden_tokens = [
        "from .admin_user_ops import",
        "from .admin_user_ops_delivery import",
        "register_admin_user_ops_routes",
        "register_admin_user_ops_delivery_routes",
        '"admin_user_ops": "wecom_ability_service.http.admin_user_ops"',
        '"admin_user_ops_delivery": "wecom_ability_service.http.admin_user_ops_delivery"',
        '("admin_user_ops", register_admin_user_ops_routes)',
        '("admin_user_ops_delivery", register_admin_user_ops_delivery_routes)',
    ]
    assert [token for token in forbidden_tokens if token in content] == []


def test_user_ops_write_and_external_fallback_dependencies_are_preserved() -> None:
    for path in [
        "wecom_ability_service/domains/user_ops/page_service.py",
        "wecom_ability_service/domains/user_ops/service.py",
        "wecom_ability_service/domains/user_ops/user_ops_deferred_job_service.py",
        "wecom_ability_service/domains/user_ops/hxc_send_config_service.py",
        "wecom_ability_service/http/admin_jobs.py",
        "wecom_ability_service/http/tasks.py",
    ]:
        assert (REPO_ROOT / path).exists(), path


def test_legacy_flask_no_longer_registers_user_ops_admin_routes_but_keeps_job_and_task_fallbacks() -> None:
    pytest.importorskip("flask")
    from wecom_ability_service import create_app

    app = create_app({"TESTING": True})
    routes = {rule.rule for rule in app.url_map.iter_rules()}
    for route in [
        "/admin/user-ops/ui",
        "/api/admin/user-ops/overview",
        "/api/admin/user-ops/list",
        "/api/admin/user-ops/send-records",
        "/api/admin/user-ops/do-not-disturb",
        "/api/admin/user-ops/batch-send/preview",
        "/api/admin/user-ops/batch-send/execute",
        "/api/admin/user-ops/run-deferred-jobs",
        "/api/internal/user-ops/lead-pool/backfill-owner-class-terms",
    ]:
        assert route not in routes

    assert "/api/admin/jobs/deferred-jobs/run" in routes
    for route in [
        "/api/tasks/private-message",
        "/api/tasks/moment",
        "/api/tasks/group-message",
    ]:
        assert route in routes


def test_retired_user_ops_api_prefix_is_blocked_before_route_dispatch() -> None:
    pytest.importorskip("flask")
    from wecom_ability_service import create_app

    client = create_app({"TESTING": True}).test_client()
    response = client.get("/api/admin/user-ops/overview")
    assert response.status_code == 410
    assert response.get_json()["message"] == "user-ops admin page APIs have been retired"


def test_aicrm_next_ops_enrollment_package_exists() -> None:
    assert (REPO_ROOT / "aicrm_next" / "ops_enrollment" / "api.py").exists()
    assert (REPO_ROOT / "aicrm_next" / "ops_enrollment" / "repo.py").exists()


def test_next_user_ops_readonly_routes_are_served_by_ai_crm_next() -> None:
    testclient_module = pytest.importorskip("fastapi.testclient")
    TestClient = testclient_module.TestClient
    from aicrm_next.main import app

    client = TestClient(app)
    overview_response = client.get("/api/admin/user-ops/overview")
    assert overview_response.status_code == 200
    assert overview_response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    cards = overview_response.json()["cards"]
    assert any(card.get("label") == "激活待录入" for card in cards)

    list_response = client.get("/api/admin/user-ops/list?wecom_status=added")
    assert list_response.status_code == 200
    assert list_response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"

    for path in [
        "/admin/user-ops/ui",
        "/api/admin/user-ops/list?mobile_binding_status=bound",
        "/api/admin/user-ops/list?activation_bucket=activated",
        "/api/admin/user-ops/send-records",
    ]:
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"


def test_user_ops_readonly_smoke_declares_write_external_paths_not_executed() -> None:
    from tools import user_ops_readonly_gray_smoke as gray_smoke

    args = gray_smoke.build_parser().parse_args(["--next-testclient", "--output-md", "/tmp/user_ops.md", "--output-json", "/tmp/user_ops.json"])
    report = gray_smoke.run_smoke(args)
    safety = report["side_effect_safety"]
    assert safety["old_write_endpoints_executed"] is False
    assert safety["wecom_dispatch_executed"] is False
    assert safety["media_upload_executed"] is False
    assert safety["deferred_jobs_executed"] is False
    for method, excluded in [
        ("POST", "/do-not-disturb"),
        ("POST", "/batch-send/preview"),
        ("POST", "/batch-send/execute"),
        ("POST", "/run-deferred-jobs"),
        ("GET", "/api/internal/user-ops"),
    ]:
        with pytest.raises(ValueError):
            gray_smoke.ensure_readonly(method, excluded, target="old")
    for excluded in [
        "/do-not-disturb",
        "/batch-send/preview",
        "/batch-send/execute",
        "/run-deferred-jobs",
        "/api/internal/user-ops",
    ]:
        assert excluded in gray_smoke.FORBIDDEN_OLD_PATH_FRAGMENTS


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


def test_deploy_and_production_config_not_modified_by_d4() -> None:
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
        or (path.startswith(".github/") and path != ".github/workflows/ci.yml")
        or any(keyword in path.lower() for keyword in ["nginx", "systemd", "supervisor", "docker-compose", "production"])
        and not path.startswith(("docs/", "tests/", "tools/"))
    ]
    assert forbidden == []


def test_d7_to_d9_docs_are_not_marked_retired_or_deleted() -> None:
    content = _read("docs/legacy_delete_batches.md")
    for batch in ["D7", "D8", "D9"]:
        section = content.split(f"## {batch}:", 1)[1].split("## ", 1)[0]
        status_line = next((line.strip().lower() for line in section.splitlines() if line.strip().lower().startswith("status:")), "")
        assert not status_line.startswith("status: retired")
        assert not status_line.startswith("status: deleted")


def test_d4_retirement_checker_returns_ok(tmp_path: Path) -> None:
    output_md = tmp_path / "d4.md"
    output_json = tmp_path / "d4.json"
    subprocess.run(
        [
            sys.executable,
            "tools/check_legacy_d4_user_ops_retirement.py",
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
    assert payload["write_fallbacks_preserved"]["wecom_ability_service/domains/user_ops/page_service.py"] is True
