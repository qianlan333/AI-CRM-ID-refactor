from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _route_methods() -> dict[str, set[str]]:
    pytest.importorskip("flask")
    from wecom_ability_service import create_app

    app = create_app({"TESTING": True})
    routes: dict[str, set[str]] = {}
    for rule in app.url_map.iter_rules():
        routes.setdefault(rule.rule, set()).update(set(rule.methods) - {"HEAD", "OPTIONS"})
    return routes


def test_legacy_flask_no_longer_registers_automation_core_readonly_routes() -> None:
    routes = _route_methods()
    for route in [
        "/admin/automation-conversion",
        "/api/admin/automation-conversion/overview",
        "/api/admin/automation-conversion/pools",
        "/api/admin/automation-conversion/members",
        "/api/admin/automation-conversion/members/<member_id>",
        "/api/admin/automation-conversion/execution-records",
    ]:
        assert "GET" not in routes.get(route, set()), route


def test_legacy_flask_no_longer_registers_known_automation_readonly_aliases() -> None:
    routes = _route_methods()
    for route in [
        "/admin/automation-conversion/programs/<int:program_id>/overview",
        "/admin/automation-conversion/programs/<int:program_id>/executions",
        "/admin/automation-conversion/programs/<int:program_id>/member-ops",
        "/api/admin/automation-conversion/dashboard",
        "/api/admin/automation-conversion/programs/<int:program_id>/members/segment-search",
        "/api/admin/automation-conversion/member",
        "/api/admin/automation-conversion/executions",
        "/api/admin/automation-conversion/executions/<int:execution_id>",
        "/api/admin/automation-conversion/executions/<int:execution_id>/items",
        "/api/admin/automation-conversion/execution-items/<int:execution_item_id>",
    ]:
        assert "GET" not in routes.get(route, set()), route
    assert "POST" in routes["/api/admin/automation-conversion/programs/<int:program_id>/members/segment-search"]


def test_legacy_flask_preserves_automation_write_external_and_runtime_fallbacks() -> None:
    routes = _route_methods()
    for route in [
        "/api/admin/automation-conversion/member/push-openclaw",
        "/api/admin/automation-conversion/stage/<stage_key>/manual-send/preview",
        "/api/admin/automation-conversion/stage/<stage_key>/manual-send",
        "/api/admin/automation-conversion/member/put-in-pool",
        "/api/admin/automation-conversion/member/mark-won",
        "/api/admin/automation-conversion/focus-send-batches/run-due",
        "/api/admin/automation-conversion/sop/run-due",
        "/api/admin/automation-conversion/tasks/run-due",
        "/api/admin/automation-conversion/jobs/run-due",
        "/api/admin/automation-conversion/message-activity-sync/run",
        "/api/admin/automation-conversion/reply-monitor/run-due",
        "/api/admin/automation-conversion/router-pending-callback-check",
        "/api/internal/automation-conversion/lobster-results",
        "/api/internal/automation-conversion/laohuang-chat-results",
        "/api/internal/automation-conversion/router-test-dispatch",
        "/api/customers/automation/activation-webhook",
        "/api/admin/automation-conversion/review-outputs/<output_id>/send-via-webhook",
        "/api/admin/automation-conversion/review-outputs/<output_id>/send-via-wecom",
    ]:
        assert "POST" in routes[route], route


def test_automation_mixed_modules_keep_expected_fallback_route_registrations() -> None:
    source = _read("wecom_ability_service/http/automation_conversion.py")
    for stopped in [
        'bp.route("/admin/automation-conversion", methods=["GET"])',
        'bp.route("/api/admin/automation-conversion/dashboard", methods=["GET"])',
        'bp.route("/api/admin/automation-conversion/member", methods=["GET"])',
        'bp.route("/api/admin/automation-conversion/executions", methods=["GET"])',
    ]:
        assert stopped not in source
    for retained in [
        'bp.route("/api/admin/automation-conversion/member/push-openclaw", methods=["POST"])',
        'bp.route("/api/admin/automation-conversion/stage/<stage_key>/manual-send/preview", methods=["POST"])',
        'bp.route("/api/admin/automation-conversion/jobs/run-due", methods=["POST"])',
    ]:
        assert retained in source
    assert 'methods=["GET", "POST"])(api_admin_automation_program_member_segment_search)' not in source
    assert 'methods=["POST"],\n    )(api_admin_automation_program_member_segment_search)' in source


def test_automation_fallback_files_still_exist() -> None:
    for path in [
        "wecom_ability_service/http/automation_conversion.py",
        "wecom_ability_service/http/customer_automation.py",
        "wecom_ability_service/http/automation_conversion_member_api.py",
        "wecom_ability_service/http/automation_conversion_delivery.py",
        "wecom_ability_service/http/automation_conversion_runtime_api.py",
        "wecom_ability_service/http/automation_conversion_router_callback_api.py",
        "wecom_ability_service/http/automation_conversion_agent_api.py",
        "wecom_ability_service/http/automation_conversion_operation_tasks.py",
        "wecom_ability_service/http/automation_conversion_workflows.py",
        "wecom_ability_service/http/automation_conversion_review.py",
        "wecom_ability_service/domains/automation_conversion/service.py",
    ]:
        assert (REPO_ROOT / path).exists(), path


def test_aicrm_next_automation_readonly_routes_are_served_by_ai_crm_next() -> None:
    testclient_module = pytest.importorskip("fastapi.testclient")
    TestClient = testclient_module.TestClient
    from aicrm_next.automation_engine.repo import reset_automation_fixture_state
    from aicrm_next.main import create_app

    reset_automation_fixture_state()
    client = TestClient(create_app())
    member_response = client.get("/api/admin/automation-conversion/members")
    assert member_response.status_code == 200
    assert member_response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    member_id = member_response.json()["items"][0]["member_id"]

    for path in [
        "/admin/automation-conversion",
        "/api/admin/automation-conversion/overview",
        "/api/admin/automation-conversion/pools",
        "/api/admin/automation-conversion/members",
        f"/api/admin/automation-conversion/members/{member_id}",
        "/api/admin/automation-conversion/execution-records",
    ]:
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"


def test_automation_readonly_smoke_declares_writes_external_and_runtime_not_executed() -> None:
    source = _read("experiments/ai_crm_next/tools/automation_readonly_gray_smoke.py")
    for token in [
        '"activation_webhook_executed": False',
        '"openclaw_push_executed": False',
        '"workflow_runtime_executed": False',
        '"wecom_dispatch_executed": False',
        '"external_webhook_executed": False',
    ]:
        assert token in source
    assert "fake_writes_not_requested" in source


def test_app_py_default_is_still_next_and_legacy_fallback_exists() -> None:
    content = _read("app.py")
    assert 'NEXT_APP_IMPORT = "aicrm_next.main:app"' in content
    assert "uvicorn.run(NEXT_APP_IMPORT" in content
    assert (REPO_ROOT / "legacy_flask_app.py").exists()


def test_deploy_and_production_config_not_modified_by_d6() -> None:
    result = subprocess.run(
        ["git", "diff", "--name-only", "origin/codex/legacy-d5-questionnaire-retirement...HEAD"],
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
        or (
            any(keyword in path.lower() for keyword in ["nginx", "systemd", "supervisor", "docker-compose", "production"])
            and not path.startswith(("docs/", "tests/", "tools/"))
        )
    ]
    assert forbidden == []


def test_d7_to_d9_docs_are_not_marked_retired() -> None:
    content = _read("docs/legacy_delete_batches.md")
    for batch in ["D7", "D8", "D9"]:
        section = content.split(f"## {batch}:", 1)[1].split("## ", 1)[0]
        status_line = next((line.strip().lower() for line in section.splitlines() if line.strip().lower().startswith("status:")), "")
        assert not status_line.startswith("status: retired")
        assert not status_line.startswith("status: deleted")


def test_d6_retirement_checker_returns_ok(tmp_path: Path) -> None:
    output_md = tmp_path / "d6.md"
    output_json = tmp_path / "d6.json"
    subprocess.run(
        [
            "python3",
            "tools/check_legacy_d6_automation_retirement.py",
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
    assert payload["stale_readonly_routes"] == []
    assert payload["production_config_modified"] is False
